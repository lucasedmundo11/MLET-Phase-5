"""Fixtures compartilhados para testes."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """OHLCV sintético cobrindo 2022-01 até início de 2024 (~800 dias) para 2 tickers.

    Janela longa o bastante para suportar:
      * warm-up de indicadores técnicos (MACD slow=26 + signal=9, retornos 21d);
      * cálculo de retornos anuais (precisa de >=2 anos para `pct_change`).

    Estrutura idêntica ao retorno de ``download_prices`` em
    ``src/features/feature_engineering.py``.
    """
    rng = np.random.default_rng(42)
    rows: list[dict] = []
    base_date = pd.Timestamp("2022-01-03")
    for ticker, start_price in [("TEST1.SA", 30.0), ("TEST2.SA", 75.0)]:
        price = start_price
        for i in range(800):
            ret = rng.normal(loc=0.0005, scale=0.015)
            price = max(price * (1 + ret), 0.01)
            high = price * (1 + abs(rng.normal(0, 0.005)))
            low = price * (1 - abs(rng.normal(0, 0.005)))
            open_ = (high + low) / 2
            volume = float(rng.integers(1_000_000, 10_000_000))
            rows.append(
                {
                    "ticker": ticker,
                    "date": base_date + pd.Timedelta(days=i),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": price,
                    "volume": volume,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def sample_features(sample_ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Resultado de ``compute_features`` aplicado ao OHLCV sintético."""
    from src.features.feature_engineering import compute_features

    return compute_features(sample_ohlcv, target_horizon=1)
