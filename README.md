# MLET-Phase-5 — Datathon (LLMs e Agentes)

Repositório do Datathon — Fase 5. Entregável final: agente conversacional sobre
o universo PETR4, VALE3, ITUB4, BBDC4, WEGE3 (B3). Esta release cobre as
**Etapas 1 e 2** do guia oficial.

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

## Pré-requisitos

Python 3.11+, [uv](https://github.com/astral-sh/uv), Docker.

## Setup local

```bash
git clone <repo-url> && cd MLET-Phase-5
uv venv .venv
.venv\Scripts\activate                   # Windows PowerShell
uv pip install -e ".[dev,serve]"          # já inclui Etapas 1 e 2
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
# 1. Faça o download de um GGUF quantizado (ex. Qwen2.5-3B-Instruct-Q4_K_M)
#    e exporte o caminho:
$env:LLM_MODEL_PATH = "C:\models\qwen2.5-3b-instruct-q4_k_m.gguf"

# 2. (Opcional) Indexe relatórios PDF colocados em data/raw/reports/
make rag-index

# 3. Suba a API (FastAPI + LLM quantizado + agente)
make serve
# → http://localhost:8000/docs   (Swagger)

# 4. Pergunte algo ao agente
curl -X POST http://localhost:8000/agent/chat ^
     -H "Content-Type: application/json" ^
     -d "{\"question\": \"Qual ação teve maior retorno em 2024?\"}"

# 5. Rode o benchmark (≥ 3 configs)
make benchmark
```

## Estrutura

```
src/
├── features/feature_engineering.py   # Etapa 1: yfinance + RSI/MACD/BB
├── models/
│   ├── baseline.py                   # Etapa 1: LogReg + MLP PyTorch
│   └── train.py                      # Etapa 1: MLflow tracking padronizado
├── agent/
│   ├── tools.py                      # Etapa 2: 5 tools de domínio
│   ├── rag_pipeline.py               # Etapa 2: PDF → FAISS retriever
│   └── react_agent.py                # Etapa 2: ReAct (replicado do guia)
└── serving/
    ├── app.py                        # Etapa 2: FastAPI + LLM quantizado
    └── Dockerfile
tests/
├── conftest.py
├── test_features.py / test_models.py # Etapa 1
└── test_agent.py / test_api.py       # Etapa 2 (LLM mockado)
scripts/
├── build_rag_index.py
└── run_benchmark.py
docs/
├── BUSINESS_METRICS.md
└── BENCHMARK.md
configs/
├── model_config.yaml
└── llm_config.yaml
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
| RAG retornando contexto relevante              | `src/agent/rag_pipeline.py` (FAISS + MiniLM) |
| CI/CD funcional                                 | `.github/workflows/ci.yml`                   |
| Benchmark ≥ 3 configurações                    | `docs/BENCHMARK.md` + `scripts/run_benchmark.py` |
