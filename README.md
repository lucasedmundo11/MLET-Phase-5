# MLET-Phase-5 — Datathon (LLMs e Agentes)

Repositório do Datathon — Fase 5. O entregável final é um agente conversacional
sobre o universo PETR4, VALE3, ITUB4, BBDC4, WEGE3 (B3). Esta release cobre a
**Etapa 1 — Dados + Baseline**.

## Etapa 1 — entregáveis

- ✅ EDA documentada com insights relevantes — [notebooks/01_eda.ipynb](notebooks/01_eda.ipynb).
- ✅ Baseline treinado (LogReg + MLP PyTorch) e métricas reportadas no MLflow — [src/models/train.py](src/models/train.py).
- ✅ Pipeline versionado com DVC e Docker — [dvc.yaml](dvc.yaml) + [Dockerfile](Dockerfile) + [docker-compose.yml](docker-compose.yml).
- ✅ Métricas de negócio mapeadas para métricas técnicas — [docs/BUSINESS_METRICS.md](docs/BUSINESS_METRICS.md).
- ✅ `pyproject.toml` com todas as dependências da fase — [pyproject.toml](pyproject.toml).

## Pré-requisitos

Python 3.11+, [uv](https://github.com/astral-sh/uv), Docker.

## Setup local

```bash
# 1. Clone
git clone <repo-url> && cd MLET-Phase-5

# 2. Virtualenv + dependências
uv venv .venv
.venv\Scripts\activate                # Windows PowerShell
uv pip install -e ".[dev]"

# 3. Variáveis de ambiente
copy .env.example .env

# 4. Hooks de qualidade
pre-commit install
```

## Reprodução do pipeline da Etapa 1

### Opção A — via Makefile (host)

```bash
make data        # baixa yfinance + calcula features → data/processed/*.parquet
make train       # treina LogReg + MLP, loga em MLflow → metrics/baseline_runs.json
make test        # pytest com cov ≥ 60%
```

### Opção B — via DVC

```bash
dvc repro        # executa stages prepare → train respeitando deps/outs
```

### Opção C — via Docker (totalmente reprodutível)

```bash
make docker-up   # sobe MLflow + container trainer
# o container trainer executa: feature_engineering -> train
# acompanhe os runs em http://localhost:5000
```

| Serviço | URL                     |
|---------|-------------------------|
| MLflow  | <http://localhost:5000> |

## Estrutura — Etapa 1

```
src/
├── features/
│   └── feature_engineering.py   # yfinance + RSI/MACD/BB + fundamentos
└── models/
    ├── baseline.py              # LogReg + MLP PyTorch (mesma API sklearn)
    └── train.py                 # MLflow tracking padronizado (replicado do guia)
tests/
├── conftest.py                  # OHLCV sintético
├── test_features.py             # schema contracts (pandera)
└── test_models.py               # determinismo + binariedade
configs/
└── model_config.yaml            # tickers, hiperparâmetros, MLflow
notebooks/
└── 01_eda.ipynb                 # EDA + insights
docs/
└── BUSINESS_METRICS.md          # métricas de negócio × técnicas
dvc.yaml                          # stages: prepare → train
Dockerfile                        # container reprodutível da Etapa 1
docker-compose.yml                # MLflow + trainer
```

## Métricas e tags padronizadas (MLflow)

Conforme o guia do Datathon (Nível 2 de maturidade em *Experiment Management*),
cada run loga obrigatoriamente:

- **Métricas:** `auc`, `precision`, `recall`, `f1`.
- **Parâmetros:** hiperparâmetros do modelo + `test_size`, `random_state`,
  `n_features`, `n_samples_train`.
- **Tags:** `model_type`, `framework`, `owner`, `phase`.
- **Artefatos:** modelo serializado (`mlflow.sklearn.log_model`).

O detalhamento de como cada métrica técnica conecta com as perguntas de
negócio do agente está em [docs/BUSINESS_METRICS.md](docs/BUSINESS_METRICS.md).
