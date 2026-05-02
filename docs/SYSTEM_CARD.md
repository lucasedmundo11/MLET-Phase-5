# System Card — Agente Financeiro Datathon Fase 5

> Etapa 4 — critério de aceite: **System Card completo**. Cobre o sistema
> ponta-a-ponta (LLM quantizado + agente ReAct + RAG + tools + observabilidade
> + guardrails). Para o componente de ML específico (baseline de direção D+1),
> ver [MODEL_CARD.md](MODEL_CARD.md).

## 1. Visão geral

| Campo | Valor |
|-------|-------|
| Nome do sistema | Agente Financeiro PETR4/VALE3/ITUB4/BBDC4/WEGE3 |
| Versão | 0.4.0 (Etapa 4 — Datathon Fase 5) |
| Owner | `grupo-XX` |
| Componentes | LLM GGUF quantizado (Q4_K_M / Q5_K_M) + Agente ReAct (LangChain) + 5 tools + RAG (FAISS + sentence-transformers multilingue) + FastAPI + Prometheus + Grafana + Evidently |
| Repositório | Este projeto (commit `git_sha` versionado em CI) |
| Data desta versão | 2026-05-02 |

## 2. Capacidades

* **Q&A determinístico** sobre retornos anuais, fundamentos, risco de
  carteira e sinais técnicos dos 5 tickers.
* **RAG sobre relatórios PDF** depositados em `data/raw/reports/`.
* **Trace ReAct exposto** (`intermediate_steps` na resposta) — auditável.
* **Telemetria operacional** em Prometheus + dashboard Grafana provisionado.
* **Detecção de drift** com Evidently + PSI sobre features do baseline.
* **Guardrails** de input (regex anti-injection) e output (PII via Presidio).

## 3. Casos de uso pretendidos

| Persona | Pergunta típica | Tool acionada |
|---------|-----------------|---------------|
| Investidor pessoa física | "Qual ação teve maior retorno em 2024?" | `annual_returns` |
| Analista | "Compare PETR4 e VALE3 pelo P/L." | `compare_fundamentals` |
| Gestor de carteira | "Gere relatório de risco de PETR4+VALE3+WEGE3 com pesos iguais." | `portfolio_risk` |
| Trader técnico | "Qual o sinal técnico atual de PETR4?" | `technical_signal` |
| Estudante de finanças | "O que os relatórios da Vale dizem sobre minério de ferro?" | `search_reports` |

## 4. Casos de uso fora de escopo

* **Execução de ordens** (compra/venda real). Vetor LLM06 — bloqueado por
  design (todas as tools são read-only).
* **Tickers fora do universo monitorado** — sistema falha de forma explícita
  (RT07 do [Red Team Report](RED_TEAM_REPORT.md)), nunca extrapola.
* **Aconselhamento financeiro regulado.** O sistema **não substitui**
  consultor habilitado; é um assistente informativo.
* **Janela intradiária / HFT.** Apenas fechamento diário.
* **Decisões automatizadas que afetem direitos** (LGPD Art. 20). Toda decisão
  de compra/venda fica com o usuário humano.

## 5. Arquitetura (resumo)

```
[Cliente] → POST /agent/chat → InputGuardrail → AgentExecutor (ReAct, LangChain)
                                                  ↓
                              5 tools determinísticas + RAG (FAISS)
                                                  ↓
                                            LLM GGUF quantizado
                                                  ↓
                                            OutputGuardrail (Presidio)
                                                  ↓
                                            ChatResponse + métricas Prometheus
```

Detalhes em [README.md](../README.md) (seção *Estrutura*).

## 6. Avaliação contínua

* **RAGAS — 4 métricas** (faithfulness, answer_relevancy, context_precision,
  context_recall) — em [evaluation/ragas_eval.py](../evaluation/ragas_eval.py)
  (replicado verbatim do guia).
* **LLM-as-judge — 4 critérios** (correctness, faithfulness, actionability,
  risk_awareness — incluindo critérios de negócio) — em
  [evaluation/llm_judge.py](../evaluation/llm_judge.py).
* **Golden set:** 25 pares relevantes ao domínio em
  [data/golden_set/golden_set.json](../data/golden_set/golden_set.json).
* **Drift:** Evidently + PSI por feature em
  [src/monitoring/drift.py](../src/monitoring/drift.py).

Métricas exibidas em tempo real no dashboard Grafana
("Datathon Fase 5 — Agente Financeiro") — ver [MONITORING.md](MONITORING.md).

## 7. Avaliação de risco

| Risco | Probabilidade | Impacto | Mitigação | Documento |
|-------|---------------|---------|-----------|-----------|
| Prompt injection (LLM01) | Média | Alta | InputGuardrail (regex) | [OWASP_MAPPING.md](OWASP_MAPPING.md), [Red Team RT01](RED_TEAM_REPORT.md) |
| Vazamento de PII (LLM02) | Baixa | Alta | OutputGuardrail (Presidio) | [LGPD_PLAN.md](LGPD_PLAN.md), [Red Team RT04](RED_TEAM_REPORT.md) |
| System prompt leakage (LLM07) | Baixa | Média | Padrões regex + isolation | [Red Team RT02](RED_TEAM_REPORT.md) |
| Excessive agency (LLM06) | Muito baixa | Alta | Tools read-only por design | [Red Team RT06](RED_TEAM_REPORT.md) |
| Misinformation (LLM09) | Baixa | Alta | Tools determinísticas + RAGAS | [Red Team RT07](RED_TEAM_REPORT.md) |
| Indirect prompt injection (RAG) | Baixa | Média | Curadoria + tool isolation | [Red Team RT05](RED_TEAM_REPORT.md) — ⚠️ risco residual |
| Drift de mercado (regime) | Média | Média | Evidently + PSI + alerta | [MONITORING.md](MONITORING.md) |
| Overreliance (LLM09 lato) | Média | Alta | Disclaimer + RAGAS + judge | [MODEL_CARD.md](MODEL_CARD.md) §8 |

## 8. Observabilidade

* **Prometheus** (métricas operacionais) — `/metrics` exposto em
  [src/serving/app.py](../src/serving/app.py); definições em
  [src/monitoring/metrics.py](../src/monitoring/metrics.py).
* **Grafana** — dashboard provisionado em
  [configs/grafana/dashboards/agent_dashboard.json](../configs/grafana/dashboards/agent_dashboard.json).
* **Evidently** — relatórios HTML em `data/processed/drift_reports/`.

## 9. Conformidade & governança

| Categoria | Onde |
|-----------|------|
| LGPD (Lei 13.709/2018) | [LGPD_PLAN.md](LGPD_PLAN.md) |
| OWASP LLM Top 10 (2025) | [OWASP_MAPPING.md](OWASP_MAPPING.md) |
| Red Team (≥ 5 cenários) | [RED_TEAM_REPORT.md](RED_TEAM_REPORT.md) |
| Explicabilidade & Fairness | [EXPLAINABILITY_FAIRNESS.md](EXPLAINABILITY_FAIRNESS.md) |
| Métricas de negócio × técnicas | [BUSINESS_METRICS.md](BUSINESS_METRICS.md) |
| Benchmark de configurações | [BENCHMARK.md](BENCHMARK.md) |
| Monitoramento + drift | [MONITORING.md](MONITORING.md) |

## 10. Stakeholders

| Papel | Responsabilidade |
|-------|------------------|
| Equipe (`grupo-XX`) | Manutenção, retraining, atualização de docs |
| DPO designado | Resposta a titulares (Art. 18 LGPD) |
| Banca avaliadora | Auditoria no Demo Day |
| Empresa convidada | Validação de critérios de negócio |
| Usuário final | Consumo do agente; decisão final é humana |

## 11. Ciclo de vida

| Marco | Quando |
|-------|--------|
| Retraining do baseline | Trimestral ou quando `drift_psi_max ≥ 0,20` |
| Reavaliação RAGAS + judge | A cada release candidato |
| Re-execução red team | A cada PR em `src/security/` ou `src/agent/` |
| Revisão deste System Card | Semestral ou após mudança arquitetural significativa |
| Auditoria de logs | Trimestral por amostragem |

## 12. Disclaimer

> Este sistema é um **assistente informativo** para fins educacionais
> (Datathon MLET Fase 5). **Não constitui aconselhamento financeiro,
> recomendação de investimento ou oferta de valores mobiliários.** Decisões
> de compra/venda são responsabilidade exclusiva do usuário. Consulte um
> consultor de valores mobiliários credenciado pela CVM.
