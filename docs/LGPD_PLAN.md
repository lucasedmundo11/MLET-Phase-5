# Plano de Conformidade LGPD — Agente Financeiro Datathon Fase 5

> Etapa 4 — critério de aceite: **Plano LGPD aplicado ao caso real**.
> Referência: Lei nº 13.709/2018 (LGPD), citada na seção *Regulatórias* do
> guia oficial.

## 1. Escopo do tratamento

O sistema é um **agente conversacional financeiro** que responde sobre PETR4,
VALE3, ITUB4, BBDC4 e WEGE3 a partir de:

* Dados de **mercado público** (yfinance) — não são dados pessoais.
* **Relatórios PDF** indexados em FAISS — fontes públicas (relatórios anuais
  já divulgados ao mercado), também sem PII por design.
* **Queries do usuário** enviadas a `POST /agent/chat` — esta é a **única
  superfície** que pode receber dados pessoais (intencionalmente ou por
  acidente).

> Ponto-chave: a **LGPD aplica-se exclusivamente** ao tratamento das queries
> do usuário e às telemetrias geradas a partir delas.

## 2. Mapeamento de dados pessoais (Art. 5º, I)

| Categoria | Fonte | Onde aparece | Tratamento |
|-----------|-------|--------------|------------|
| Identificadores diretos (nome, CPF, email, telefone) | Query do usuário | Body de `POST /agent/chat`, logs estruturados, traces do agente | **Não persistido**; anonimizado pelo `OutputGuardrail` antes de retornar |
| Endereço IP | Cabeçalho HTTP | Logs do FastAPI / Prometheus | Reduzido para `/24` na agregação; não usado para identificação |
| Conteúdo livre da query | Body de `POST /agent/chat` | Logs INFO + métricas | Logado **apenas após** detecção de PII pelo `PIIDetector` (Art. 46) |

**Premissa:** o sistema **não solicita** PII em nenhum momento; quando aparece
é por iniciativa do usuário.

## 3. Bases legais (Art. 7º)

| Operação | Base legal | Justificativa |
|----------|------------|---------------|
| Receber e processar a query | Execução de **legítimo interesse** (Art. 7º, IX) | Atendimento ao usuário que enviou voluntariamente |
| Logar métricas anonimizadas no Prometheus | Legítimo interesse + Art. 12 (anonimização) | Necessário para observabilidade (Etapa 3) |
| Anonimização de PII | **Cumprimento de obrigação legal** (Art. 7º, II) | LGPD Art. 46 exige medidas técnicas |
| Persistir golden set / red team scenarios | **Dados sintéticos** — fora do escopo da LGPD | Nenhum dado real de pessoa identificada |

## 4. Princípios aplicados (Art. 6º)

| Princípio | Como aplicamos |
|-----------|----------------|
| Finalidade | Apenas responder perguntas sobre os 5 tickers da carteira-alvo |
| Adequação | Não é solicitada qualquer informação pessoal para responder |
| Necessidade (minimização) | PII enviada espontaneamente é descartada após sanitização |
| Livre acesso | Log de execução do agente é apresentado ao usuário (`intermediate_steps`) |
| Qualidade dos dados | Tools determinísticas (yfinance) garantem precisão |
| Transparência | [System Card](SYSTEM_CARD.md) + [Model Card](MODEL_CARD.md) públicos |
| Segurança | OWASP Top 10 LLM mitigado em [OWASP_MAPPING.md](OWASP_MAPPING.md) |
| Prevenção | `InputGuardrail` + `OutputGuardrail` + monitoramento contínuo |
| Não discriminação | [EXPLAINABILITY_FAIRNESS.md](EXPLAINABILITY_FAIRNESS.md) |
| Responsabilização | Logs imutáveis + System Card versionado em git |

## 5. Direitos do titular (Art. 18) — superfície atual

Como o sistema **não persiste** dados identificáveis, vários direitos
tornam-se trivialmente atendidos:

| Direito | Endpoint / processo |
|---------|---------------------|
| Confirmação da existência de tratamento | Resposta padrão: "este sistema não persiste dados pessoais identificáveis" |
| Acesso aos dados | Não aplicável — nada armazenado por usuário |
| Correção / atualização | Não aplicável |
| Anonimização / eliminação | Aplicada **automaticamente** no `OutputGuardrail` antes de devolver ou logar |
| Portabilidade | Não aplicável |
| Revogação do consentimento | Basta parar de chamar a API |
| Informação sobre uso compartilhado | Não há compartilhamento com terceiros (LLM é local quantizado) |

**Caso a equipe decida persistir histórico em produção pós-Datathon**,
implementar:

* Endpoint `DELETE /user/data` autenticado.
* `session_id` derivado de hash + sal, sem reverso para identidade.
* TTL automático de 90 dias para queries; 30 dias para PII flagged.

## 6. Medidas técnicas e administrativas (Art. 46)

| Categoria | Implementação |
|-----------|---------------|
| Anonimização | `OutputGuardrail` (Presidio) + fallback regex CPF/CNPJ em `PIIDetector` |
| Pseudonimização (futuro) | `session_id = sha256(client_ip + UA + sal_dia)` |
| Criptografia em trânsito | HTTPS/TLS via reverse-proxy (não incluso no MVP — recomendado) |
| Criptografia em repouso | Volumes Docker em disco cifrado (recomendado em produção) |
| Controle de acesso | API sem `auth` no MVP — adicionar API Key para uso externo |
| Logs sanitizados | `PIIDetector.contains_pii` aplicado antes de qualquer `logger.info` |
| Retenção mínima | Logs Prometheus com TTL de 15 dias |
| Auditoria | `guardrail_action` na resposta + métrica `agent_question_failures_total` |

## 7. DPIA (Relatório de Impacto — Art. 38)

**Necessidade:** O tratamento envolve dados pessoais (queries) com potencial
risco de vazamento de PII. Como mitigamos com anonimização automática **e
não persistimos** dados identificáveis, o **risco residual é baixo**.

| Vetor | Probabilidade | Impacto | Risco residual |
|-------|---------------|---------|----------------|
| Vazamento de CPF na resposta | Baixa (Presidio bloqueia) | Alto | **Baixo** |
| Vazamento via log INFO | Baixa (PIIDetector pré-log) | Médio | **Baixo** |
| Vazamento via Prometheus label | Muito baixa (sem PII em label) | Baixo | **Muito baixo** |
| Reidentificação por correlação | Muito baixa (sem persistência) | Médio | **Muito baixo** |

**Conclusão:** DPIA não é obrigatório nesta versão; recomenda-se elaborar um
**antes** de qualquer release que adicione persistência ou compartilhamento
com terceiros.

## 8. Encarregado (DPO)

| Item | Definição |
|------|-----------|
| DPO designado | A definir pelo grupo (Art. 41) |
| Canal de contato | `privacidade@<dominio-da-equipe>` |
| SLA de resposta | 15 dias corridos (mesmo prazo que o titular tem para os direitos do Art. 18) |

## 9. Plano de resposta a incidentes

1. **Detecção** — alerta automático em Grafana quando
   `agent_question_failures_total{reason="pii_leak"}` > 0 em janela de 5 min.
2. **Contenção** — desligar `/agent/chat` (kill-switch via `make docker-down`)
   ou retornar 503.
3. **Comunicação à ANPD** — em até 72 horas (Art. 48), via canal oficial.
4. **Comunicação ao titular** — quando aplicável (Art. 48 § 2º).
5. **Post-mortem** — registrado em [docs/](.) com lições aprendidas + PR de
   mitigação.

## 10. Cronograma de revisão

| Item | Frequência |
|------|------------|
| Revisão deste plano | Semestral ou após mudança no fluxo de dados |
| Re-execução `make red-team` | A cada PR em `src/security/` ou `src/agent/` |
| Verificação de cobertura PII | Mensal (script: `python -m scripts.run_red_team`) |
| Auditoria de logs | Trimestral por amostragem |
