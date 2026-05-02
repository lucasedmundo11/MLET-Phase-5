"""Testes da Etapa 3 — drift (PSI) e métricas Prometheus."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_psi_zero_for_identical_distributions() -> None:
    from src.monitoring.drift import population_stability_index

    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(size=2000))
    assert population_stability_index(s, s.copy()) < 1e-3


def test_psi_grows_when_distribution_shifts() -> None:
    from src.monitoring.drift import population_stability_index

    rng = np.random.default_rng(0)
    ref = pd.Series(rng.normal(loc=0, scale=1, size=2000))
    cur = pd.Series(rng.normal(loc=2, scale=1, size=2000))  # shift forte
    psi = population_stability_index(ref, cur)
    assert psi > 0.2, f"PSI esperado > 0.2 para shift de 2σ; obtido {psi:.3f}"


def test_psi_returns_zero_for_too_few_samples() -> None:
    from src.monitoring.drift import population_stability_index

    s = pd.Series([1.0, 2.0, 3.0])
    assert population_stability_index(s, s) == 0.0


def test_metrics_render_returns_prometheus_payload() -> None:
    pytest.importorskip("prometheus_client")
    from src.monitoring.metrics import (
        agent_tool_calls_total,
        http_requests_total,
        render_metrics,
    )

    http_requests_total.labels(endpoint="/test", status="200").inc()
    agent_tool_calls_total.labels(tool="annual_returns").inc()
    payload, content_type = render_metrics()
    assert content_type.startswith("text/plain")
    body = payload.decode("utf-8")
    assert "agent_http_requests_total" in body
    assert "agent_tool_calls_total" in body


def test_drift_module_exposes_thresholds() -> None:
    from src.monitoring.drift import DEFAULT_PSI_CRITICAL, DEFAULT_PSI_WARNING

    assert DEFAULT_PSI_WARNING == 0.10
    assert DEFAULT_PSI_CRITICAL == 0.20
