"""Modelos baseline da Etapa 1 — Scikit-Learn + MLP em PyTorch.

Conforme o guia do Datathon (Fase 05), a Etapa 1 entrega dois baselines:

* ``LogisticRegressionBaseline``: modelo linear simples, rápido e interpretável.
* ``MLPClassifierTorch``: MLP em PyTorch com a mesma API do scikit-learn,
  permitindo reaproveitar o pipeline de treino padronizado.

A interface ``fit`` / ``predict`` é mantida idêntica a ``sklearn`` para que o
``train_and_log`` (replicado da seção *MLflow Tracking Padronizado* do guia)
funcione sem alterações.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from torch import nn

logger = logging.getLogger(__name__)


FEATURE_COLUMNS: tuple[str, ...] = (
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_diff",
    "bb_pct_b",
    "log_return_1d",
    "log_return_5d",
    "log_return_21d",
    "volatility_21d",
)


class LogisticRegressionBaseline(LogisticRegression):
    """Wrapper enxuto de ``LogisticRegression`` para registro padronizado."""

    def __init__(
        self,
        C: float = 1.0,
        max_iter: int = 1000,
        solver: str = "lbfgs",
        random_state: int = 42,
    ) -> None:
        super().__init__(C=C, max_iter=max_iter, solver=solver, random_state=random_state)


class _MLPModule(nn.Module):
    def __init__(self, in_features: int, hidden_dim: int, dropout: float) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_features, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # noqa: D401
        return self.net(x)


class MLPClassifierTorch:
    """MLP binário em PyTorch com API ``fit``/``predict``/``predict_proba``."""

    def __init__(
        self,
        hidden_dim: int = 128,
        dropout: float = 0.3,
        learning_rate: float = 1e-3,
        epochs: int = 50,
        batch_size: int = 64,
        random_state: int = 42,
    ) -> None:
        self.hidden_dim = hidden_dim
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        self.random_state = random_state
        self._scaler = StandardScaler()
        self._model: _MLPModule | None = None
        self._device = torch.device("cpu")

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> "MLPClassifierTorch":
        torch.manual_seed(self.random_state)
        X_arr = self._scaler.fit_transform(np.asarray(X, dtype=np.float32))
        y_arr = np.asarray(y, dtype=np.float32).reshape(-1, 1)

        self._model = _MLPModule(X_arr.shape[1], self.hidden_dim, self.dropout).to(self._device)
        optimizer = torch.optim.Adam(self._model.parameters(), lr=self.learning_rate)
        loss_fn = nn.BCEWithLogitsLoss()

        X_t = torch.from_numpy(X_arr).to(self._device)
        y_t = torch.from_numpy(y_arr).to(self._device)
        n = X_t.shape[0]

        self._model.train()
        for epoch in range(self.epochs):
            perm = torch.randperm(n)
            epoch_loss = 0.0
            for start in range(0, n, self.batch_size):
                idx = perm[start : start + self.batch_size]
                optimizer.zero_grad()
                logits = self._model(X_t[idx])
                loss = loss_fn(logits, y_t[idx])
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item() * len(idx)
            if (epoch + 1) % 10 == 0:
                logger.info("Epoch %d/%d — loss=%.4f", epoch + 1, self.epochs, epoch_loss / n)
        return self

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Modelo MLP ainda não foi treinado.")
        self._model.eval()
        X_arr = self._scaler.transform(np.asarray(X, dtype=np.float32))
        with torch.no_grad():
            logits = self._model(torch.from_numpy(X_arr).to(self._device))
            proba = torch.sigmoid(logits).cpu().numpy().ravel()
        return np.column_stack([1 - proba, proba])

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
