"""Pipeline de ingestão e engenharia de features para o Datathon — Etapa 1.

Baixa histórico de preços via yfinance para o universo de ações brasileiras
(PETR4, VALE3, ITUB4, BBDC4, WEGE3), calcula indicadores técnicos
(RSI, MACD, Bollinger Bands), coleta fundamentos (P/L, ROE, Dividend Yield)
e gera o target de classificação (direção do retorno em D+1).

Saída:
    data/processed/prices_features.parquet — painel com features e target.
    data/processed/fundamentals.parquet    — snapshot de fundamentos.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands

logger = logging.getLogger(__name__)

DEFAULT_TICKERS: tuple[str, ...] = (
    "PETR4.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "BBDC4.SA",
    "WEGE3.SA",
)

PRICES_PATH = Path("data/processed/prices_features.parquet")
FUNDAMENTALS_PATH = Path("data/processed/fundamentals.parquet")
RAW_PATH = Path("data/raw/prices_raw.parquet")
CONFIG_PATH = Path("configs/model_config.yaml")


def download_prices(
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    period: str = "5y",
    interval: str = "1d",
) -> pd.DataFrame:
    """Baixa histórico OHLCV via yfinance e devolve em formato long.

    Args:
        tickers: Lista de tickers (ex.: ``PETR4.SA``).
        period: Janela de download (``5y``, ``2y``, ``max`` ...).
        interval: Frequência (``1d``, ``1wk`` ...).

    Returns:
        DataFrame com colunas ``[ticker, date, open, high, low, close, volume]``.
    """
    import yfinance as yf

    logger.info("Baixando preços para %d tickers (period=%s)", len(tickers), period)
    raw = yf.download(
        list(tickers),
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        if ticker not in raw.columns.get_level_values(0):
            logger.warning("Ticker ausente no retorno do yfinance: %s", ticker)
            continue
        sub = raw[ticker].copy()
        sub.columns = [c.lower() for c in sub.columns]
        sub = sub.reset_index().rename(columns={"Date": "date"})
        sub.columns = [c.lower() for c in sub.columns]
        sub["ticker"] = ticker
        frames.append(sub[["ticker", "date", "open", "high", "low", "close", "volume"]])

    if not frames:
        raise RuntimeError("Nenhum ticker retornou dados via yfinance.")

    prices = pd.concat(frames, ignore_index=True)
    prices = prices.dropna(subset=["close"]).sort_values(["ticker", "date"])
    logger.info("Total de linhas baixadas: %d", len(prices))
    return prices


def download_fundamentals(tickers: tuple[str, ...] = DEFAULT_TICKERS) -> pd.DataFrame:
    """Coleta fundamentos snapshot (P/L, ROE, Dividend Yield) via yfinance.

    Args:
        tickers: Lista de tickers a consultar.

    Returns:
        DataFrame com uma linha por ticker.
    """
    import yfinance as yf

    rows: list[dict[str, float | str | None]] = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao obter fundamentos de %s: %s", ticker, exc)
            info = {}
        rows.append(
            {
                "ticker": ticker,
                "pe_ratio": info.get("trailingPE"),
                "roe": info.get("returnOnEquity"),
                "dividend_yield": info.get("dividendYield"),
                "market_cap": info.get("marketCap"),
                "sector": info.get("sector"),
            }
        )
    return pd.DataFrame(rows)


def compute_features(df: pd.DataFrame, target_horizon: int = 1) -> pd.DataFrame:
    """Calcula indicadores técnicos e gera o target binário (direção em D+H).

    Indicadores calculados por ticker:
        - RSI (14)
        - MACD (12, 26, 9) — linha + diferença em relação ao sinal
        - Bollinger Bands (20, 2σ) — banda superior, inferior e %B
        - Retornos log de 1, 5 e 21 dias
        - Volatilidade móvel de 21 dias

    Args:
        df: DataFrame em formato long com colunas ``[ticker, date, open, high,
            low, close, volume]``.
        target_horizon: Horizonte (em dias) para o target de direção.

    Returns:
        DataFrame com colunas adicionais de features e target.
    """
    required = {"ticker", "date", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes em compute_features: {missing}")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    out: list[pd.DataFrame] = []
    for ticker, group in df.groupby("ticker", sort=False):
        g = group.sort_values("date").reset_index(drop=True)

        rsi = RSIIndicator(close=g["close"], window=14, fillna=False).rsi()
        macd = MACD(close=g["close"], window_slow=26, window_fast=12, window_sign=9, fillna=False)
        bb = BollingerBands(close=g["close"], window=20, window_dev=2, fillna=False)

        g["rsi_14"] = rsi
        g["macd"] = macd.macd()
        g["macd_signal"] = macd.macd_signal()
        g["macd_diff"] = macd.macd_diff()
        g["bb_high"] = bb.bollinger_hband()
        g["bb_low"] = bb.bollinger_lband()
        g["bb_pct_b"] = (g["close"] - g["bb_low"]) / (g["bb_high"] - g["bb_low"])

        g["log_return_1d"] = np.log(g["close"]).diff()
        g["log_return_5d"] = np.log(g["close"]).diff(5)
        g["log_return_21d"] = np.log(g["close"]).diff(21)
        g["volatility_21d"] = g["log_return_1d"].rolling(window=21).std()

        future_close = g["close"].shift(-target_horizon)
        g["target"] = (future_close > g["close"]).astype("Int8")

        out.append(g)

    features = pd.concat(out, ignore_index=True)
    features = features.dropna().reset_index(drop=True)
    features["target"] = features["target"].astype(int)
    logger.info("Features calculadas: %d linhas, %d colunas", *features.shape)
    return features


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    """Pipeline DVC: download + features + fundamentos → parquet."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    config = _load_config()
    data_cfg = config.get("data", {})
    tickers = tuple(data_cfg.get("tickers", DEFAULT_TICKERS))
    period = data_cfg.get("period", "5y")
    horizon = int(data_cfg.get("target_horizon", 1))

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)

    prices = download_prices(tickers=tickers, period=period)
    prices.to_parquet(RAW_PATH, index=False)
    logger.info("Preços brutos salvos em %s", RAW_PATH)

    features = compute_features(prices, target_horizon=horizon)
    features.to_parquet(PRICES_PATH, index=False)
    logger.info("Features salvas em %s", PRICES_PATH)

    fundamentals = download_fundamentals(tickers=tickers)
    fundamentals.to_parquet(FUNDAMENTALS_PATH, index=False)
    logger.info("Fundamentos salvos em %s", FUNDAMENTALS_PATH)


if __name__ == "__main__":
    main()
