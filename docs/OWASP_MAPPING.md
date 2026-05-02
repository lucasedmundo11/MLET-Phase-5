# OWASP LLM Top 10 — Mapeamento de Ameaças

> Etapa 4 — Datathon Fase 5. Critério de aceite: **≥ 5 ameaças mapeadas e
> mitigadas**. Este mapeamento usa a versão **OWASP Top 10 for LLM Applications
> (2025)** — referência citada no guia oficial (página 17, snippet de
> `src/security/guardrails.py`).

| # | Ameaça (OWASP LLM 2025) | Mapeada para | Status |
|---|--------------------------|--------------|--------|
| 1 | LLM01 — Prompt Injection | InputGuardrail + isolation | ✅ Mitigado |
| 2 | LLM02 — Sensitive Information Disclosure | OutputGuardrail (Presidio) | ✅ Mitigado |
| 3 | LLM05 — Improper Output Handling | Pydantic schemas + sanitização | ✅ Mitigado |
| 4 | LLM06 — Excessive Agency | Tools read-only + max_iterations | ✅ Mitigado |
| 5 | LLM07 — System Prompt Leakage | Prompt isolation + fallback regex | ⚠️ Risco residual baixo |
| 6 | LLM09 — Misinformation | Tools determinísticas + RAGAS faithfulness | ✅ Mitigado |
| 7 | LLM10 — Unbounded Consumption | max_tokens + max_iterations + healthcheck | ✅ Mitigado |

---

## LLM01 — Prompt Injection

**Vetor.** Usuário insere texto que sobrescreve as instruções do system prompt
("Ignore all previous instructions...", role overrides, chat-template tags
como `<|im_start|>`, `[INST]`).

**Impacto no agente financeiro.** Atacante poderia fazer o agente recomendar
ações fora do universo monitorado, divulgar o prompt do sistema ou pular
verificações de risco antes de responder sobre carteiras.

**Mitigação implementada.**

- [src/security/guardrails.py::InputGuardrail](../src/security/guardrails.py)
  bloqueia 6 famílias de padrões via regex (replicado verbatim do guia).
- O agente ReAct usa um system prompt isolado em
  [src/agent/react_agent.py::REACT_PROMPT](../src/agent/react_agent.py),
  sem concatenar diretamente o input do usuário.
- Cobertura por testes: `tests/test_guardrails.py::TestInputGuardrail::test_rt01_*`.

## LLM02 — Sensitive Information Disclosure

**Vetor.** O LLM ecoar PII contida no contexto (queries do usuário, RAG, logs)
ou inferir dados sensíveis a partir de fragmentos.

**Impacto no agente financeiro.** Vazamento de CPF/email/telefone de um cliente
que envie algo como "Meu CPF é X, qual ação devo comprar?" — risco direto à
LGPD (Art. 46).

**Mitigação implementada.**

- [src/security/guardrails.py::OutputGuardrail](../src/security/guardrails.py)
  usa Presidio para anonimizar `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`,
  `BR_CPF` antes de devolver a resposta.
- [src/security/pii_detection.py](../src/security/pii_detection.py) adiciona
  fallback regex para CPF e CNPJ.
- O endpoint `/agent/chat` retorna `guardrail_action="sanitized"` quando
  removeu algo, permitindo telemetria via Prometheus.

## LLM05 — Improper Output Handling

**Vetor.** Saídas do LLM consumidas downstream sem validação podem causar
XSS, SQL injection ou code injection.

**Impacto no agente financeiro.** Resposta do agente exibida em UI web ou
copiada para planilha sem sanitização.

**Mitigação implementada.**

- Pydantic `ChatResponse` em [src/serving/app.py](../src/serving/app.py)
  garante tipo `str` válido com tamanho controlado.
- Tools devolvem strings já formatadas em
  [src/agent/tools.py](../src/agent/tools.py) (sem repassar JSON arbitrário).
- API expõe apenas `application/json`; nenhum endpoint serve HTML do LLM
  diretamente.

## LLM06 — Excessive Agency

**Vetor.** Agente com permissões além do necessário (executar trades, escrever
em filesystem, chamar serviços externos arbitrários).

**Impacto no agente financeiro.** Agente colocando ordens reais a partir de
um pedido como "compre PETR4 agora".

**Mitigação implementada.**

- **Todas as 5 tools são read-only** (consultam parquet local + retriever
  FAISS). Nenhuma escreve em banco, broker ou filesystem.
- `AgentExecutor(max_iterations=10)` em
  [src/agent/react_agent.py:80-86](../src/agent/react_agent.py#L80-L86) limita
  loops infinitos.
- O `search_reports` (RAG) só lê do índice local; sem acesso a HTTP.
- Documentado no Model/System Card que **o agente não executa transações**.

## LLM07 — System Prompt Leakage

**Vetor.** Atacante força o agente a revelar literalmente o system prompt /
ferramentas disponíveis / templates internos.

**Impacto no agente financeiro.** Conhecimento da estrutura interna facilita
ataques posteriores; expõe propriedade intelectual da equipe.

**Mitigação implementada.**

- Padrões de extração ("repeat your instructions", "what is your system
  prompt") cobertos pelo regex `forget\s+(everything|all|your\s+instructions)`
  + variantes adicionadas ao testar (`tests/test_guardrails.py::test_rt02_*`).
- **Risco residual:** parafrasagens criativas podem escapar do regex. Mitigação
  futura sugerida: adicionar verificação no `OutputGuardrail` que detecta o
  prefixo do `REACT_PROMPT` na resposta e a bloqueia.

## LLM09 — Misinformation

**Vetor.** LLM "alucina" números — ex.: inventa retorno de PETR4, cita um P/L
errado, fabrica trecho de relatório que não existe.

**Impacto no agente financeiro.** Investidor toma decisão baseada em dado
falso → dano financeiro real → risco reputacional e regulatório (CVM).

**Mitigação implementada.**

- **Toda métrica numérica vem de tool determinística** (yfinance via
  parquet local), não do LLM.
- RAG só devolve trechos textuais com referência ao arquivo fonte
  (`(petr.pdf #3) ...`), permitindo verificação manual.
- Avaliação contínua com **RAGAS faithfulness** + **LLM-as-judge correctness**
  (Etapa 3) — limiares em [configs/monitoring_config.yaml](../configs/monitoring_config.yaml).
- Model Card avisa explicitamente: "respostas devem ser revistas por humano
  antes de qualquer decisão financeira".

## LLM10 — Unbounded Consumption

**Vetor.** Atacante envia inputs longos / muitas requisições → custo de
inferência explode, serviço cai (DoS de LLM).

**Impacto no agente financeiro.** Custo operacional e indisponibilidade
durante o Demo Day ou em produção pós-Datathon.

**Mitigação implementada.**

- `InputGuardrail` rejeita qualquer input > 4096 chars
  ([src/security/guardrails.py:54-56](../src/security/guardrails.py#L54-L56)).
- `max_tokens ≤ 2048` no Pydantic schema de `/llm/complete`.
- `max_iterations=10` no agente ReAct evita loops Thought → Action infinitos.
- Healthcheck Docker (`HEALTHCHECK` em
  [src/serving/Dockerfile:18-19](../src/serving/Dockerfile#L18-L19)) detecta
  travamentos e força restart.
- Métrica `agent_question_failures_total{reason="..."}` permite alertar via
  Grafana quando crescer (ver dashboard provisionado).

---

## Revisão e ciclo

| Item | Frequência |
|------|------------|
| Revisão deste mapeamento | Trimestral ou após mudança arquitetural |
| Atualização de padrões `INJECTION_PATTERNS` | Mensal ou após incidente |
| Re-execução de `make red-team` | A cada PR que toca `src/security/` ou `src/agent/` |
| Re-execução de `make eval` (RAGAS + judge) | A cada release candidato |
