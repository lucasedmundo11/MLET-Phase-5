"""Pipeline de treinamento com MLflow tracking padronizado.

A função ``train_and_log`` é reproduzida **verbatim** da seção *MLflow Tracking
Padronizado* (Etapa 1) do guia oficial do Datathon — Fase 05.

A função ``register_model_to_registry`` aplica em cima o **schema obrigatório
de tags do GAP 05** (página 6) e registra o modelo no **MLflow Model Registry**,
satisfazendo o Nível 2 de maturidade em Model Management.

A função ``main`` orquestra: carrega dados → treina LogReg + MLP →
``train_and_log`` (verbatim) → ``register_model_to_registry`` (governança).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path

import mlflow
import pandas as pd
import yaml
from mlflow.tracking import MlflowClient
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from src.models.baseline import (
    FEATURE_COLUMNS,
    LogisticRegressionBaseline,
    MLPClassifierTorch,
)

logger = logging.getLogger(__name__)

PROCESSED_PATH = Path("data/processed/prices_features.parquet")
CONFIG_PATH = Path("configs/model_config.yaml")
DVC_LOCK_PATH = Path("dvc.lock")
METRICS_DIR = Path("metrics")
MODELS_DIR = Path("models")
MODEL_VERSION_SEMVER = "0.1.0"


def train_and_log(
    df: pd.DataFrame,
    target_col: str,
    model_name: str,
    model_class,
    model_params: dict,
    test_size: float = 0.2,
    random_state: int = 42,
) -> str:
    """Treina modelo, loga tudo no MLflow, retorna run_id.

    Args:
        df: DataFrame com features e target.
        target_col: Nome da coluna target.
        model_name: Nome para registro no MLflow.
        model_class: Classe do modelo (ex: RandomForestClassifier).
        model_params: Hiperparâmetros do modelo.
        test_size: Proporção de teste.
        random_state: Semente para reprodutibilidade.

    Returns:
        run_id do experimento MLflow.
    """
    X = df.drop(columns=[target_col])
    y = df[target_col]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    with mlflow.start_run(run_name=model_name) as run:
        # Log de parâmetros
        mlflow.log_params(model_params)
        mlflow.log_param("test_size", test_size)
        mlflow.log_param("random_state", random_state)
        mlflow.log_param("n_features", X_train.shape[1])
        mlflow.log_param("n_samples_train", X_train.shape[0])

        # Tags padronizadas (obrigatório)
        mlflow.set_tag("model_type", "classification")
        mlflow.set_tag("framework", model_class.__module__.split(".")[0])
        mlflow.set_tag("owner", "grupo-XX")
        mlflow.set_tag("phase", "datathon-fase05")

        # Treino
        model = model_class(**model_params)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        # Métricas padronizadas
        metrics = {
            "auc": roc_auc_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),
            "recall": recall_score(y_test, y_pred, zero_division=0),
            "f1": f1_score(y_test, y_pred, zero_division=0),
        }
        mlflow.log_metrics(metrics)

        # Log do modelo
        mlflow.sklearn.log_model(model, "model")

        logger.info(
            "Modelo %s treinado: AUC=%.4f, F1=%.4f",
            model_name,
            metrics["auc"],
            metrics["f1"],
        )
        return run.info.run_id


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------- Governança Nível 2 (GAP 05) ------------------------------------ #


def _git_sha() -> str:
    """SHA curto do commit atual; ``unknown`` fora de um checkout git."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _training_data_version() -> str:
    """Versão dos dados de treino: hash DVC se disponível, fallback SHA256 do parquet."""
    if DVC_LOCK_PATH.exists():
        try:
            lock = yaml.safe_load(DVC_LOCK_PATH.read_text(encoding="utf-8")) or {}
            outs = lock.get("stages", {}).get("prepare", {}).get("outs", [])
            for o in outs:
                if "prices_features" in o.get("path", ""):
                    md5 = o.get("md5") or o.get("hash")
                    if md5:
                        return f"dvc:{md5[:12]}"
        except Exception:  # noqa: BLE001
            pass
    if PROCESSED_PATH.exists():
        h = hashlib.sha256(PROCESSED_PATH.read_bytes()).hexdigest()
        return f"sha256:{h[:12]}"
    return "unknown"


def register_model_to_registry(
    run_id: str,
    model_name: str,
    risk_level: str = "medium",
    fairness_checked: bool = False,
) -> str:
    """Aplica o schema completo do GAP 05 e registra o modelo no MLflow Registry.

    Schema mínimo obrigatório (replicado do guia, p. 6)::

        required_tags = {
            "model_name": str,
            "model_version": str,
            "model_type": str,
            "training_data_version": str,
            "metrics": dict,
            "owner": str,
            "risk_level": str,
            "fairness_checked": bool,
            "git_sha": str,
        }

    Args:
        run_id: Run MLflow já criado por ``train_and_log``.
        model_name: Nome para registro no Model Registry.
        risk_level: Classificação de risco (low / medium / high / critical).
        fairness_checked: Indica se a auditoria de fairness foi realizada
            (ver ``docs/EXPLAINABILITY_FAIRNESS.md``).

    Returns:
        Versão do modelo registrada no Model Registry.
    """
    client = MlflowClient()
    run = client.get_run(run_id)
    metrics = {k: float(v) for k, v in run.data.metrics.items()}

    governance_tags = {
        "model_name": model_name,
        "model_version": MODEL_VERSION_SEMVER,
        "training_data_version": _training_data_version(),
        "metrics_json": json.dumps(metrics, ensure_ascii=False),
        "risk_level": risk_level,
        "fairness_checked": str(fairness_checked).lower(),
        "git_sha": _git_sha(),
    }
    for k, v in governance_tags.items():
        client.set_tag(run_id, k, v)

    model_uri = f"runs:/{run_id}/model"
    mv = mlflow.register_model(model_uri=model_uri, name=model_name)
    logger.info(
        "Modelo registrado no Registry: %s versão %s (run %s)",
        model_name,
        mv.version,
        run_id[:8],
    )
    return mv.version


def _load_dataset() -> pd.DataFrame:
    if not PROCESSED_PATH.exists():
        raise FileNotFoundError(
            f"Dataset processado não encontrado em {PROCESSED_PATH}. "
            "Rode `python -m src.features.feature_engineering` (ou `dvc repro prepare`)."
        )
    df = pd.read_parquet(PROCESSED_PATH)
    cols = list(FEATURE_COLUMNS) + ["target"]
    return df[cols].dropna().reset_index(drop=True)


def main() -> None:
    """Pipeline DVC: carrega features → treina LogReg + MLP → loga MLflow."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    config = _load_config()
    training_cfg = config.get("training", {})
    mlflow_cfg = config.get("mlflow", {})
    logreg_cfg = config.get("model", {}).get("hyperparameters", {})
    mlp_cfg = config.get("mlp", {})

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI") or mlflow_cfg.get(
        "tracking_uri", "file:./mlruns"
    )
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(mlflow_cfg.get("experiment_name", "mlet-phase5"))

    df = _load_dataset()
    logger.info("Dataset carregado: %d linhas, %d colunas", *df.shape)

    runs: dict[str, str] = {}

    runs["logreg"] = train_and_log(
        df=df,
        target_col="target",
        model_name="baseline_logreg",
        model_class=LogisticRegressionBaseline,
        model_params=logreg_cfg or {"C": 1.0, "max_iter": 1000, "solver": "lbfgs"},
        test_size=training_cfg.get("test_size", 0.2),
        random_state=training_cfg.get("random_state", 42),
    )

    runs["mlp"] = train_and_log(
        df=df,
        target_col="target",
        model_name="baseline_mlp_torch",
        model_class=MLPClassifierTorch,
        model_params=mlp_cfg
        or {"hidden_dim": 128, "dropout": 0.3, "learning_rate": 1e-3, "epochs": 50},
        test_size=training_cfg.get("test_size", 0.2),
        random_state=training_cfg.get("random_state", 42),
    )

    # Governança Nível 2 — GAP 05 + Model Registry
    versions: dict[str, str] = {}
    for name, run_id in runs.items():
        try:
            versions[name] = register_model_to_registry(
                run_id=run_id,
                model_name=f"baseline_{name}",
                risk_level=training_cfg.get("risk_level", "medium"),
                fairness_checked=bool(training_cfg.get("fairness_checked", False)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Registry indisponível para %s: %s", name, exc)
            versions[name] = "unregistered"

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"runs": runs, "registry_versions": versions}
    with open(METRICS_DIR / "baseline_runs.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Runs registrados: %s", payload)


if __name__ == "__main__":
    main()
