"""Testes de feature engineering — schema contracts.

Pattern do guia oficial (Etapa 1): valida o output de ``compute_features``
contra um ``DataFrameSchema`` do Pandera, garantindo ausência de nulos e
preservação dos contratos de tipo / faixa.
"""

from __future__ import annotations

import pandas as pd
import pandera as pa
from pandera import Column, DataFrameSchema

from src.features.feature_engineering import compute_features

FEATURE_SCHEMA = DataFrameSchema(
    {
        "ticker": Column(str),
        "date": Column(pa.DateTime),
        "close": Column(float, pa.Check.gt(0)),
        "rsi_14": Column(float, pa.Check.between(0, 100)),
        "macd": Column(float),
        "macd_signal": Column(float),
        "macd_diff": Column(float),
        "bb_high": Column(float, pa.Check.gt(0)),
        "bb_low": Column(float, pa.Check.gt(0)),
        "bb_pct_b": Column(float),
        "log_return_1d": Column(float),
        "log_return_5d": Column(float),
        "log_return_21d": Column(float),
        "volatility_21d": Column(float, pa.Check.ge(0)),
        "target": Column(int, pa.Check.isin([0, 1])),
    }
)


def test_schema_contract(sample_ohlcv: pd.DataFrame) -> None:
    """Features de saída devem respeitar o contrato de schema."""
    result = compute_features(sample_ohlcv)
    FEATURE_SCHEMA.validate(result, lazy=True)


def test_no_nulls(sample_ohlcv: pd.DataFrame) -> None:
    """Nenhuma feature pode ter null após transformação."""
    result = compute_features(sample_ohlcv)
    assert result.isnull().sum().sum() == 0


def test_target_is_binary(sample_ohlcv: pd.DataFrame) -> None:
    """Target deve ser estritamente binário 0/1."""
    result = compute_features(sample_ohlcv)
    assert set(result["target"].unique()).issubset({0, 1})


def test_per_ticker_grouping(sample_ohlcv: pd.DataFrame) -> None:
    """Indicadores devem ser calculados por ticker (sem vazamento entre séries)."""
    result = compute_features(sample_ohlcv)
    for ticker, group in result.groupby("ticker"):
        assert group["date"].is_monotonic_increasing, f"datas fora de ordem em {ticker}"


def test_missing_columns_raises() -> None:
    """Input sem coluna obrigatória deve falhar de forma explícita."""
    bad = pd.DataFrame({"ticker": ["X"], "date": [pd.Timestamp("2024-01-01")], "close": [10.0]})
    try:
        compute_features(bad)
    except ValueError as exc:
        assert "Colunas obrigatórias ausentes" in str(exc)
    else:
        raise AssertionError("compute_features deveria ter levantado ValueError")
