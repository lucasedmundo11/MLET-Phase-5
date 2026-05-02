"""Testes dos baselines da Etapa 1 — determinismo e contrato de saída."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.models.baseline import (
    FEATURE_COLUMNS,
    LogisticRegressionBaseline,
    MLPClassifierTorch,
)


def _xy(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    X = features[list(FEATURE_COLUMNS)]
    y = features["target"]
    return X, y


def test_logreg_predicts_binary(sample_features: pd.DataFrame) -> None:
    X, y = _xy(sample_features)
    model = LogisticRegressionBaseline().fit(X, y)
    preds = model.predict(X)
    assert preds.shape == y.shape
    assert set(np.unique(preds)).issubset({0, 1})


def test_mlp_torch_predicts_binary(sample_features: pd.DataFrame) -> None:
    X, y = _xy(sample_features)
    model = MLPClassifierTorch(epochs=3, hidden_dim=16).fit(X, y)
    preds = model.predict(X)
    proba = model.predict_proba(X)
    assert preds.shape == y.shape
    assert proba.shape == (len(y), 2)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_mlp_torch_is_deterministic(sample_features: pd.DataFrame) -> None:
    """Mesmo random_state deve produzir as mesmas predições."""
    X, y = _xy(sample_features)
    a = MLPClassifierTorch(epochs=3, hidden_dim=16, random_state=7).fit(X, y).predict(X)
    b = MLPClassifierTorch(epochs=3, hidden_dim=16, random_state=7).fit(X, y).predict(X)
    np.testing.assert_array_equal(a, b)
