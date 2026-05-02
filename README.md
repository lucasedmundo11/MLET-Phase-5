# MLET-Phase-5 — Datathon (LLMs e Agentes)

Repositório do Datathon — Fase 5. Entregável final: agente conversacional sobre
o universo PETR4, VALE3, ITUB4, BBDC4, WEGE3 (B3). Esta release cobre as
**Etapas 1, 2, 3 e 4** do guia oficial.

## Status do checklist

### Etapa 1 — Dados + Baseline
- ✅ EDA documentada — [notebooks/01_eda.ipynb](notebooks/01_eda.ipynb)
- ✅ Baseline (LogReg + MLP PyTorch) com MLflow — [src/models/train.py](src/models/train.py)
- ✅ Pipeline DVC + Docker — [dvc.yaml](dvc.yaml), [Dockerfile](Dockerfile)
- ✅ Métricas de negócio × técnicas — [docs/BUSINESS_METRICS.md](docs/BUSINESS_METRICS.md)
- ✅ `pyproject.toml` com todas as dependências — [pyproject.toml](pyproject.toml)

### Etapa 2 — LLM + Agente
- ✅ LLM servido via API com quantização (GGUF Q4_K_M / Q5_K_M via `llama-cpp-python`) — [src/serving/app.py](src/serving/app.py)
- ✅ Agente ReAct com 5 tools (≥ 3 exigidas) — [src/agent/react_agent.py](src/agent/react_agent.py), [src/agent/tools.py](src/agent/tools.py)
- ✅ RAG sobre PDFs (chunks → embeddings multilingues → FAISS) — [src/agent/rag_pipeline.py](src/agent/rag_pipeline.py)
- ✅ CI/CD GitHub Actions (lint + mypy + bandit + pytest + build) — [.github/workflows/ci.yml](.github/workflows/ci.yml)
- ✅ Benchmark com 3 configurações — [docs/BENCHMARK.md](docs/BENCHMARK.md)

### Etapa 3 — Avaliação + Observabilidade
- ✅ Golden set com 25 pares (≥ 20) — [data/golden_set/golden_set.json](data/golden_set/golden_set.json)
- ✅ RAGAS com as 4 métricas (replicado do guia) — [evaluation/ragas_eval.py](evaluation/ragas_eval.py)
- ✅ LLM-as-judge com 4 critérios (incl. negócio) — [evaluation/llm_judge.py](evaluation/llm_judge.py)
- ✅ Telemetria + dashboard end-to-end (Prometheus + Grafana provisionados) — [src/monitoring/metrics.py](src/monitoring/metrics.py), [configs/grafana/dashboards/agent_dashboard.json](configs/grafana/dashboards/agent_dashboard.json)
- ✅ Drift detection (Evidently + PSI) — [src/monitoring/drift.py](src/monitoring/drift.py), [docs/MONITORING.md](docs/MONITORING.md)

### Etapa 4 — Segurança + Governança
- ✅ OWASP LLM Top 10 (2025) com 7 ameaças mapeadas — [docs/OWASP_MAPPING.md](docs/OWASP_MAPPING.md)
- ✅ Guardrails de input + output funcionais (replicado do guia) — [src/security/guardrails.py](src/security/guardrails.py)
- ✅ 7 cenários adversariais documentados e automatizados — [docs/RED_TEAM_REPORT.md](docs/RED_TEAM_REPORT.md), [scripts/run_red_team.py](scripts/run_red_team.py)
- ✅ Plano LGPD aplicado ao caso real — [docs/LGPD_PLAN.md](docs/LGPD_PLAN.md)
- ✅ Explicabilidade (ReAct trace + LogReg coefs) e fairness (paridade por ticker) — [docs/EXPLAINABILITY_FAIRNESS.md](docs/EXPLAINABILITY_FAIRNESS.md)
- ✅ System Card + Model Card completos — [docs/SYSTEM_CARD.md](docs/SYSTEM_CARD.md), [docs/MODEL_CARD.md](docs/MODEL_CARD.md)

## Pré-requisitos

Python 3.11+, [uv](https://github.com/astral-sh/uv), Docker.

## Setup local

```bash
git clone <repo-url> && cd MLET-Phase-5
uv venv .venv
.venv\Scripts\activate                                # Windows PowerShell
uv pip install -e ".[dev,serve,eval,monitor,security]"  # Etapas 1+2+3+4
python -m spacy download pt_core_news_sm              # modelo PT do Presidio
copy .env.example .env
pre-commit install
```

## Reprodução — Etapa 1

```bash
make data        # baixa yfinance + features → data/processed/*.parquet
make train       # treina LogReg + MLP, loga em MLflow
make test        # pytest com cov ≥ 60%
```

Ou via DVC: `dvc repro`. Ou via Docker: `make docker-up` (sobe MLflow).

## Reprodução — Etapa 2

```bash
$env:LLM_MODEL_PATH = "C:\models\qwen2.5-3b-instruct-q4_k_m.gguf"
make rag-index    # opcional (PDFs em data/raw/reports/)
make serve        # FastAPI + LLM quantizado + agente
make benchmark    # roda config A do docs/BENCHMARK.md
```

## Reprodução — Etapa 3

```bash
# 1. Tudo no ar (API + MLflow + Prometheus + Grafana)
make docker-up
# → http://localhost:8000/docs    Swagger
# → http://localhost:8000/metrics Prometheus exposition
# → http://localhost:9090         Prometheus
# → http://localhost:3000         Grafana (admin/admin)
#                                 Dashboard "Datathon Fase 5 — Agente Financeiro"

# 2. Avaliação RAGAS + LLM-as-judge sobre o golden set
make eval         # → metrics/evaluation.json + gauges em /metrics

# 3. Drift detection
make drift        # → metrics/drift.json + report HTML em data/processed/drift_reports/
```

## Reprodução — Etapa 4

```bash
# 1. Subir o sistema completo (API + guardrails + observabilidade)
make docker-up

# 2. Rodar os 7 cenários adversariais contra a API
make red-team     # → metrics/red_team.json (sai 1 se algum cenário vazar)

# 3. Rodar testes de guardrails (offline; pula PII se Presidio/spaCy ausente)
pytest tests/test_guardrails.py -v
```

## Estrutura

```
src/
├── features/feature_engineering.py   # Etapa 1
├── models/{baseline,train}.py        # Etapa 1
├── agent/{tools,rag_pipeline,react_agent}.py  # Etapa 2
├── serving/{app,Dockerfile}          # Etapa 2 + /metrics (Etapa 3)
└── monitoring/{drift,metrics}.py     # Etapa 3
evaluation/
├── ragas_eval.py                     # Etapa 3 (replicado do guia)
├── llm_judge.py                      # Etapa 3
└── ab_test_prompts.py                # Etapa 3
data/
├── raw/{prices_raw.parquet,reports/} # Etapa 1+2
├── processed/{prices_features.parquet,fundamentals.parquet,rag_index/,drift_reports/}
└── golden_set/golden_set.json        # Etapa 3 (25 pares)
configs/
├── model_config.yaml                 # Etapa 1
├── llm_config.yaml                   # Etapa 2
├── monitoring_config.yaml            # Etapa 3
├── prometheus.yml                    # Etapa 3
└── grafana/                          # Etapa 3 (datasource + dashboard)
scripts/
├── build_rag_index.py                # Etapa 2
├── run_benchmark.py                  # Etapa 2
├── run_evaluation.py                 # Etapa 3
└── run_drift_check.py                # Etapa 3
tests/
├── conftest.py + test_features.py + test_models.py     # Etapa 1
├── test_agent.py + test_api.py                         # Etapa 2
└── test_evaluation.py + test_monitoring.py             # Etapa 3
docs/
├── BUSINESS_METRICS.md   BENCHMARK.md   MONITORING.md
.github/workflows/ci.yml              # lint → mypy → bandit → pytest → build
```

## Tools expostas pelo agente

| Tool                  | Pergunta-alvo                                   |
|-----------------------|-------------------------------------------------|
| `annual_returns`      | "Qual ação teve maior retorno em 2024?"          |
| `compare_fundamentals`| "Compare PETR4 e VALE3 pelo P/L."                |
| `portfolio_risk`      | "Gere um relatório de risco da carteira X."      |
| `technical_signal`    | "Qual o sinal técnico atual de PETR4?"           |
| `search_reports`      | RAG sobre PDFs (perguntas qualitativas)          |

## Onde os critérios de aceite são satisfeitos

| Critério (guia)                                | Arquivo                                      |
|------------------------------------------------|----------------------------------------------|
| LLM via API com quantização                    | `src/serving/app.py::get_llm` (GGUF Q4/Q5)   |
| Agente ReAct ≥ 3 tools                         | `src/agent/react_agent.py` + `tools.py` (5)  |
| RAG retornando contexto relevante              | `src/agent/rag_pipeline.py`                  |
| CI/CD funcional                                | `.github/workflows/ci.yml`                   |
| Benchmark ≥ 3 configurações                    | `docs/BENCHMARK.md` + `scripts/run_benchmark.py` |
| Golden set ≥ 20 pares                          | `data/golden_set/golden_set.json` (25)       |
| RAGAS — 4 métricas                              | `evaluation/ragas_eval.py`                   |
| LLM-as-judge ≥ 3 critérios (com negócio)        | `evaluation/llm_judge.py` (4 critérios)      |
| Telemetria + dashboard end-to-end              | `src/monitoring/metrics.py` + Grafana provisionado |
| Drift detection                                | `src/monitoring/drift.py` (Evidently + PSI)  |
