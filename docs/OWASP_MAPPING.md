# OWASP LLM Top 10 — Mapeamento de Ameaças

Baseado no OWASP Top 10 for LLM Applications (v1.1).

## LLM01 — Prompt Injection

**Descrição:** Inputs maliciosos manipulam o comportamento do LLM sobrescrevendo instruções do sistema.

**Controle implementado:** `InputGuardrail` em `src/security/guardrails.py` — regex patterns detectam e bloqueiam tentativas de injeção antes de atingir o agente.

## LLM02 — Insecure Output Handling

**Descrição:** Saídas do LLM usadas sem sanitização podem causar XSS, SSRF ou execução de código.

**Controle implementado:** `OutputGuardrail` sanitiza saídas antes de retorná-las ao cliente; API usa Pydantic para validação de schema.

## LLM06 — Sensitive Information Disclosure

**Descrição:** O modelo pode vazar PII ou dados confidenciais presentes no contexto de treino ou retrieval.

**Controle implementado:** Presidio (`src/security/pii_detection.py`) detecta e anonimiza PII em inputs e outputs. Logs não armazenam dados sensíveis.

## LLM08 — Excessive Agency

**Descrição:** Agente com permissões excessivas pode executar ações não intencionadas.

**Controle implementado:** Ferramenta `fetch_external_data` opera apenas em URLs explicitamente fornecidas pelo usuário. Sem acesso a filesystem, shell ou banco de dados.

## LLM09 — Overreliance

**Descrição:** Usuários confiam cegamente nas saídas do LLM sem verificação humana.

**Controle implementado:** Respostas incluem `flagged: bool` indicando conteúdo suspeito. LLM-as-judge em `evaluation/llm_judge.py` avalia qualidade antes de deploys.

---

*Revisão planejada: trimestral ou após mudanças arquiteturais significativas.*
