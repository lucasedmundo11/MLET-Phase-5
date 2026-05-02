"""Retraining champion-challenger — fechamento do GAP 07 do guia.

Pipeline:

1. **Recarrega features** do parquet versionado (DVC) — ver
   ``src/features/feature_engineering.py``.
2. **Treina o challenger** reusando ``train_and_log`` (verbatim do guia,
   Etapa 1) e o registra no Model Registry com governança GAP 05.
3. **Compara com o champion** atualmente em ``Production`` no Model Registry.
4. **Promove o challenger para Staging** se ``Δauc ≥ 0.005`` (limiar exato
   recomendado pelo guia, p. 8).
5. **Não promove a Production** — mantém *human-in-the-loop*: a transição
   ``Staging → Production`` é manual via MLflow UI.

Uso:
    python -m scripts.run_retraining
    python -m scripts.run_retraining --model-name baseline_logreg --threshold 0.005
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from src.models.baseline import LogisticRegressionBaseline, MLPClassifierTorch
from src.models.train import (
    _load_config,
    _load_dataset,
    register_model_to_registry,
    train_and_log,
)

logger = logging.getLogger(__name__)

REPORT_DIR = Path("metrics")
DEFAULT_THRESHOLD = 0.005  # GAP 07 (p. 8) — promover só se Δauc ≥ 0.5%
DEFAULT_MODEL_NAME = "baseline_logreg"


def _get_champion(client: MlflowClient, model_name: str) -> dict | None:
    """Devolve metadados do champion atual em ``Production`` ou ``None``."""
    try:
        versions = client.get_latest_versions(model_name, stages=["Production"])
    except MlflowException as exc:
        logger.warning("Modelo %s ainda não tem registro: %s", model_name, exc)
        return None
    if not versions:
        return None
    champ = versions[0]
    run = client.get_run(champ.run_id)
    return {
        "version": champ.version,
        "run_id": champ.run_id,
        "metrics": {k: float(v) for k, v in run.data.metrics.items()},
    }


def _transition_to_staging(client: MlflowClient, model_name: str, version: str) -> None:
    client.transition_model_version_stage(
        name=model_name,
        version=version,
        stage="Staging",
        archive_existing_versions=False,
    )
    logger.info("Challenger %s v%s movido para Staging.", model_name, version)


def _decide(
    challenger_auc: float,
    champion: dict | None,
    threshold: float,
) -> tuple[str, float | None]:
    """Aplica a regra de promoção do GAP 07. Retorna (decision, delta_auc)."""
    if champion is None:
        return "FIRST_CHALLENGER_TO_STAGING", None
    delta = challenger_auc - float(champion["metrics"].get("auc", 0.0))
    if delta >= threshold:
        return "PROMOTE_TO_STAGING", delta
    return "REJECT", delta


def main() -> int:
    parser = argparse.ArgumentParser(description="Champion-challenger retraining (GAP 07).")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--reason",
        default=os.environ.get("RETRAINING_REASON", "scheduled"),
        help="Motivo do retraining (audit trail): scheduled / manual / drift_critical.",
    )
    parser.add_argument(
        "--challenger-class",
        choices=["logreg", "mlp"],
        default="logreg",
        help="Família do challenger.",
    )
    args = parser.parse_args()

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
    mlflow.set_experiment(mlflow_cfg.get("experiment_name", "mlet-phase5-baseline"))

    df = _load_dataset()
    logger.info("Dataset carregado: %d linhas, %d colunas", *df.shape)

    if args.challenger_class == "mlp":
        model_class = MLPClassifierTorch
        model_params = mlp_cfg or {
            "hidden_dim": 128,
            "dropout": 0.3,
            "learning_rate": 1e-3,
            "epochs": 50,
        }
    else:
        model_class = LogisticRegressionBaseline
        model_params = logreg_cfg or {"C": 1.0, "max_iter": 1000, "solver": "lbfgs"}

    # Treina challenger (reusa o train_and_log verbatim da Etapa 1).
    challenger_run_id = train_and_log(
        df=df,
        target_col="target",
        model_name=f"{args.model_name}_challenger",
        model_class=model_class,
        model_params=model_params,
        test_size=training_cfg.get("test_size", 0.2),
        random_state=training_cfg.get("random_state", 42),
    )

    # Registra com governança GAP 05.
    challenger_version = register_model_to_registry(
        run_id=challenger_run_id,
        model_name=args.model_name,
        risk_level=training_cfg.get("risk_level", "medium"),
        fairness_checked=False,  # automatizado: humano valida no gate Staging→Prod
    )

    client = MlflowClient()
    challenger_metrics = {
        k: float(v) for k, v in client.get_run(challenger_run_id).data.metrics.items()
    }
    challenger_auc = float(challenger_metrics.get("auc", 0.0))

    champion = _get_champion(client, args.model_name)
    decision, delta_auc = _decide(challenger_auc, champion, args.threshold)

    if decision in ("PROMOTE_TO_STAGING", "FIRST_CHALLENGER_TO_STAGING"):
        try:
            _transition_to_staging(client, args.model_name, challenger_version)
        except MlflowException as exc:
            logger.error("Falha ao mover para Staging: %s", exc)
            decision = f"{decision}_FAILED"

    report = {
        "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trigger": args.reason,
        "model_name": args.model_name,
        "champion": champion,
        "challenger": {
            "run_id": challenger_run_id,
            "version": challenger_version,
            "metrics": challenger_metrics,
        },
        "delta_auc": delta_auc,
        "promotion_threshold": args.threshold,
        "decision": decision,
        "human_action_required": (
            "REVIEW: abrir MLflow Registry → Staging e transicionar para "
            "'Production' após validação manual (fairness, drift, regressão "
            "em métricas de negócio)."
            if decision.startswith(("PROMOTE", "FIRST"))
            else "NONE: challenger não atingiu Δauc ≥ 0.005; champion mantido."
        ),
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = REPORT_DIR / f"retraining_{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Decisão: %s (Δauc=%s) — relatório em %s", decision, delta_auc, out_path)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
