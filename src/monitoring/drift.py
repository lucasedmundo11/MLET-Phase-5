"""Detecção de drift — Etapa 3 (Avaliação + Observabilidade).

Replica o snippet padronizado do guia (GAP 06) usando Evidently para gerar
um report de data drift e calcula o **PSI (Population Stability Index)**
por feature, conforme thresholds recomendados:

* PSI > 0.1 → *warning*
* PSI > 0.2 → *retrain trigger*

Saída persistida em ``data/processed/drift_reports/`` (HTML + JSON), o que
permite logar ``share_of_drifted_columns`` e ``psi`` no MLflow junto com as
métricas de modelo (recomendação do guia).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


REPORTS_DIR = Path("data/processed/drift_reports")
CONFIG_PATH = Path("configs/monitoring_config.yaml")
DEFAULT_PSI_WARNING = 0.10
DEFAULT_PSI_CRITICAL = 0.20


@dataclass
class DriftResult:
    share_of_drifted_columns: float
    drifted_features: list[str]
    psi_per_feature: dict[str, float]
    status: str  # "ok" | "warning" | "critical"
    report_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "share_of_drifted_columns": self.share_of_drifted_columns,
            "drifted_features": self.drifted_features,
            "psi_per_feature": self.psi_per_feature,
            "status": self.status,
            "report_path": self.report_path,
        }


def population_stability_index(
    reference: pd.Series,
    current: pd.Series,
    bins: int = 10,
    eps: float = 1e-6,
) -> float:
    """PSI = Σ (cur% - ref%) * ln(cur% / ref%) sobre bins discretizados.

    Para variáveis contínuas, usa quantis da série de referência como bordas.
    """
    ref = pd.to_numeric(reference, errors="coerce").dropna()
    cur = pd.to_numeric(current, errors="coerce").dropna()
    if len(ref) < bins or len(cur) < bins:
        return 0.0
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    ref_hist, _ = np.histogram(ref, bins=edges)
    cur_hist, _ = np.histogram(cur, bins=edges)
    ref_pct = ref_hist / max(ref_hist.sum(), 1) + eps
    cur_pct = cur_hist / max(cur_hist.sum(), 1) + eps
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def _load_thresholds() -> tuple[float, float]:
    if not CONFIG_PATH.exists():
        return DEFAULT_PSI_WARNING, DEFAULT_PSI_CRITICAL
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    alerts = cfg.get("alerts", {})
    return (
        float(alerts.get("psi_warning", DEFAULT_PSI_WARNING)),
        float(alerts.get("psi_critical", DEFAULT_PSI_CRITICAL)),
    )


def detect_drift(
    reference_data: pd.DataFrame,
    current_data: pd.DataFrame,
    save_html: bool = True,
    report_dir: Path = REPORTS_DIR,
) -> DriftResult:
    """Roda Evidently DataDriftPreset + PSI por feature numérica.

    Snippet original do guia (replicado):

        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset

        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=train_df, current_data=prod_df)
        drift_result = report.as_dict()
        drift_share = drift_result["metrics"][0]["result"]["share_of_drifted_columns"]
    """
    from evidently.metric_preset import DataDriftPreset
    from evidently.report import Report

    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference_data, current_data=current_data)
    drift_result = report.as_dict()
    drift_share = drift_result["metrics"][0]["result"]["share_of_drifted_columns"]

    drifted: list[str] = []
    drift_by_col = drift_result["metrics"][1].get("result", {}).get("drift_by_columns", {})
    for col, info in drift_by_col.items():
        if info.get("drift_detected"):
            drifted.append(col)

    psi: dict[str, float] = {}
    numeric_cols = reference_data.select_dtypes(include="number").columns.intersection(
        current_data.columns
    )
    for col in numeric_cols:
        psi[col] = round(population_stability_index(reference_data[col], current_data[col]), 4)

    warn, crit = _load_thresholds()
    max_psi = max(psi.values()) if psi else 0.0
    if max_psi >= crit:
        status = "critical"
    elif max_psi >= warn:
        status = "warning"
    else:
        status = "ok"

    report_path: str | None = None
    if save_html:
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
        html_path = report_dir / f"drift_{ts}.html"
        report.save_html(str(html_path))
        json_path = report_dir / f"drift_{ts}.json"
        json_path.write_text(json.dumps(drift_result, default=str, indent=2), encoding="utf-8")
        report_path = str(html_path)
        logger.info("Drift report salvo em %s", html_path)

    return DriftResult(
        share_of_drifted_columns=float(drift_share),
        drifted_features=drifted,
        psi_per_feature=psi,
        status=status,
        report_path=report_path,
    )
