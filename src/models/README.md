# src/models/ — Modelos de Baseline + Pipeline MLflow

Pipeline de treinamento com rastreamento padronizado no MLflow e governança Nível 2 (GAP 05). Cobre a **Etapa 1** do Datathon.

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Modelos Implementados](#modelos-implementados)
3. [Pipeline de Treinamento](#pipeline-de-treinamento)
4. [MLflow — Rastreamento Padronizado](#mlflow--rastreamento-padronizado)
5. [Governança — GAP 05](#governança--gap-05)
6. [Champion-Challenger](#champion-challenger)
7. [Arquivos](#arquivos)
8. [Uso](#uso)

---

## Visão Geral

```
src/models/
├── __init__.py
├── baseline.py    # LogisticRegressionBaseline + MLPClassifierTorch
└── train.py       # train_and_log() + register_model_to_registry() + main()
```

---

## Modelos Implementados

### `LogisticRegressionBaseline`

Wrapper sobre `sklearn.linear_model.LogisticRegression` com API sklearn compatível.

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `C` | 1.0 | Regularização inversa |
| `max_iter` | 1000 | Iterações máximas do solver |
| `solver` | `lbfgs` | Algoritmo de otimização |

**Uso para explicabilidade:** coeficientes acessíveis via `model.coef_` para análise de importância de features.

### `MLPClassifierTorch`

Rede neural feedforward implementada em **PyTorch** com sklearn API (`fit/predict/predict_proba`).

```mermaid
graph LR
    IN[Input<br/>n_features] --> H1[Hidden Layer<br/>hidden_dim=128]
    H1 --> DO[Dropout<br/>p=0.3]
    DO --> H2[Hidden Layer<br/>hidden_dim // 2]
    H2 --> OUT[Output<br/>2 classes]

    style IN fill:#264653
    style OUT fill:#2a9d8f
```

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `hidden_dim` | 128 | Dimensão da camada oculta principal |
| `dropout` | 0.3 | Taxa de dropout para regularização |
| `learning_rate` | 1e-3 | Taxa de aprendizado Adam |
| `epochs` | 50 | Épocas de treinamento |

---

## Pipeline de Treinamento

```mermaid
flowchart TD
    START([python -m src.models.train]) --> CONF[Carrega configs/<br/>model_config.yaml]
    CONF --> MLFLOW[Configura MLflow URI<br/>e experiment name]
    MLFLOW --> DATA[Carrega<br/>data/processed/prices_features.parquet]
    DATA --> SPLIT[train_test_split<br/>stratify=y · test_size=0.2]

    SPLIT --> RUN1[train_and_log<br/>LogisticRegressionBaseline]
    SPLIT --> RUN2[train_and_log<br/>MLPClassifierTorch]

    RUN1 -->|run_id| REG1[register_model_to_registry<br/>baseline_logreg]
    RUN2 -->|run_id| REG2[register_model_to_registry<br/>baseline_mlp_torch]

    REG1 & REG2 --> SAVE[metrics/baseline_runs.json<br/>runs + registry_versions]
    SAVE --> END([Fim])

    style START fill:#2a9d8f,color:#fff
    style END fill:#2a9d8f,color:#fff
```

---

## MLflow — Rastreamento Padronizado

A função `train_and_log` replica **verbatim** o template da Etapa 1 do guia oficial.

```mermaid
sequenceDiagram
    participant TL as train_and_log
    participant ML as MLflow

    TL->>ML: mlflow.start_run(run_name=model_name)
    TL->>ML: log_params(model_params + test_size + random_state + n_features + n_samples_train)
    TL->>ML: set_tag("model_type", "classification")
    TL->>ML: set_tag("framework", module)
    TL->>ML: set_tag("owner", TEAM_OWNER)
    TL->>ML: set_tag("phase", "datathon-fase05")
    Note over TL: fit(X_train, y_train) → predict(X_test)
    TL->>ML: log_metrics({auc, precision, recall, f1})
    TL->>ML: sklearn.log_model(model, "model")
    ML-->>TL: run.info.run_id
```

**Métricas registradas:**

| Métrica | Função sklearn |
|---------|---------------|
| `auc` | `roc_auc_score` |
| `precision` | `precision_score(zero_division=0)` |
| `recall` | `recall_score(zero_division=0)` |
| `f1` | `f1_score(zero_division=0)` |

---

## Governança — GAP 05

A função `register_model_to_registry` aplica o **schema completo de 9 tags obrigatórias** do GAP 05 e registra o modelo no MLflow Model Registry.

```mermaid
flowchart LR
    RID[run_id] --> CLIENT[MlflowClient]
    CLIENT --> TAGS[Aplica 9 tags obrigatórias]

    TAGS --> T1["model_name: str"]
    TAGS --> T2["model_version: str (semver)"]
    TAGS --> T3["model_type: str"]
    TAGS --> T4["training_data_version: dvc:hash ou sha256:hash"]
    TAGS --> T5["metrics: JSON {auc, precision, recall, f1}"]
    TAGS --> T6["owner: str (TEAM_OWNER env)"]
    TAGS --> T7["risk_level: low|medium|high|critical"]
    TAGS --> T8["fairness_checked: bool"]
    TAGS --> T9["git_sha: str (git rev-parse --short HEAD)"]

    TAGS --> REG[mlflow.register_model<br/>Model Registry]
    REG --> VER[Versão registrada]
```

**Resolução da versão de dados (`training_data_version`):**

```mermaid
flowchart LR
    A{dvc.lock<br/>existe?} -->|Sim| B[Lê hash DVC do stage prepare]
    A -->|Não| C{prices_features<br/>.parquet existe?}
    B --> OK[dvc:abc123def456]
    C -->|Sim| D[SHA256 do parquet]
    C -->|Não| E[unknown]
    D --> OK2[sha256:abc123def456]
```

---

## Champion-Challenger

O processo de retraining usa a estratégia champion-challenger para decidir se um novo modelo deve ser promovido.

```mermaid
flowchart TD
    TRIGGER([Trigger: cron · drift · manual]) --> LOAD[Carrega champion<br/>do MLflow Registry]
    LOAD --> TRAIN[Treina challenger<br/>com dados novos]
    TRAIN --> COMP[Compara AUC<br/>em holdout set]

    COMP --> DELTA{Δ AUC ≥ 0.005?}
    DELTA -->|Sim| PROMOTE[Move challenger<br/>para Staging]
    DELTA -->|Não| REJECT[Rejeita challenger<br/>champion permanece]

    PROMOTE --> HUMAN[Human-in-the-loop<br/>Staging → Production<br/>via MLflow UI]

    style TRIGGER fill:#e9c46a
    style PROMOTE fill:#2a9d8f,color:#fff
    style REJECT fill:#e63946,color:#fff
    style HUMAN fill:#457b9d,color:#fff
```

> Implementado em `scripts/run_retraining.py` e orquestrado por `.github/workflows/retraining.yml`.

---

## Arquivos

### `baseline.py`

```python
FEATURE_COLUMNS: tuple[str, ...] = (
    "rsi_14", "macd", "macd_signal", "macd_diff",
    "bb_upper", "bb_lower", "bb_pct_b", "return_1d",
)

class LogisticRegressionBaseline:
    def fit(self, X: np.ndarray, y: np.ndarray) -> None: ...
    def predict(self, X: np.ndarray) -> np.ndarray: ...
    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...

class MLPClassifierTorch:
    def fit(self, X: np.ndarray, y: np.ndarray) -> None: ...
    def predict(self, X: np.ndarray) -> np.ndarray: ...
    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...
```

### `train.py`

```python
def train_and_log(
    df: pd.DataFrame,
    target_col: str,
    model_name: str,
    model_class,
    model_params: dict,
    test_size: float = 0.2,
    random_state: int = 42,
) -> str:  # retorna run_id

def register_model_to_registry(
    run_id: str,
    model_name: str,
    risk_level: str = "medium",
    fairness_checked: bool = False,
    owner: str | None = None,
) -> str:  # retorna versão registrada

def main() -> None:  # entrypoint DVC stage: train
```

---

## Uso

### Via DVC (recomendado)

```bash
dvc repro train
```

### Diretamente

```bash
python -m src.models.train
```

### Programático

```python
import mlflow
from src.models.baseline import LogisticRegressionBaseline
from src.models.train import train_and_log, register_model_to_registry

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("mlet-phase5")

run_id = train_and_log(
    df=df,
    target_col="target",
    model_name="meu_modelo",
    model_class=LogisticRegressionBaseline,
    model_params={"C": 0.5, "max_iter": 500},
)

version = register_model_to_registry(
    run_id=run_id,
    model_name="meu_modelo",
    risk_level="low",
    fairness_checked=True,
)
```

### Acessar Experimentos

```bash
mlflow ui --backend-store-uri mlruns/
# → http://localhost:5000
```
