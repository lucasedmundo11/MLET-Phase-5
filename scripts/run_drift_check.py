"""Roda detecção de drift comparando 'reference' (treino) vs. 'current'.

Por padrão usa as features do baseline em ``data/processed/prices_features.parquet``,
particionando por data: os últimos 30 dias formam o ``current`` e o restante a
``reference``. Empurra ``share_of_drifted_columns`` e ``psi_max`` para
Prometheus para alimentar o dashboard.

Uso:
    python -m scripts.run_drift_check
    python -m scripts.run_drift_check --window-days 60
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.models.baseline import FEATURE_COLUMNS

PROCESSED = Path("data/processed/prices_features.parquet")
METRICS_PATH = Path("metrics/drift.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROCESSED))
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--no-html", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    df = pd.read_parquet(args.input)
    df["date"] = pd.to_datetime(df["date"])
    cutoff = df["date"].max() - pd.Timedelta(days=args.window_days)
    reference = df.loc[df["date"] < cutoff, list(FEATURE_COLUMNS)].dropna()
    current = df.loc[df["date"] >= cutoff, list(FEATURE_COLUMNS)].dropna()

    if reference.empty or current.empty:
        raise SystemExit(
            f"Particionamento vazio: reference={len(reference)}, current={len(current)}."
        )

    from src.monitoring.drift import detect_drift

    result = detect_drift(reference, current, save_html=not args.no_html)
    logging.info("Drift status=%s share=%.3f psi_max=%.3f",
                 result.status, result.share_of_drifted_columns,
                 max(result.psi_per_feature.values()) if result.psi_per_feature else 0.0)

    try:
        from src.monitoring.metrics import drift_psi_max, drift_share_of_drifted_columns

        drift_share_of_drifted_columns.set(result.share_of_drifted_columns)
        if result.psi_per_feature:
            drift_psi_max.set(max(result.psi_per_feature.values()))
    except Exception:  # noqa: BLE001
        pass

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
