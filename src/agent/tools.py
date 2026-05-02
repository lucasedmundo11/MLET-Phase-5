"""Tools customizadas do agente financeiro — Etapa 2 (LLM + Agente).

Cinco ferramentas (≥ 3 exigidas pelo guia do Datathon) cobrem os tipos de
pergunta descritos no problema:

* ``annual_returns``        — "Qual ação teve maior retorno em 2024?"
* ``compare_fundamentals``  — "Compare PETR4 e VALE3 pelo P/L"
* ``portfolio_risk``        — "Gere um relatório de risco da carteira X"
* ``technical_signal``      — situação atual de RSI/MACD/%B
* ``search_reports``        — RAG sobre relatórios financeiros (PDF)

Todas as funções recebem **uma única string** (formato esperado por
``langchain.tools.Tool``) e retornam **string** com a observação para o agente.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PRICES_PATH = Path("data/processed/prices_features.parquet")
FUNDAMENTALS_PATH = Path("data/processed/fundamentals.parquet")


# ---------- helpers --------------------------------------------------------- #


def _load_prices() -> pd.DataFrame:
    if not PRICES_PATH.exists():
        raise FileNotFoundError(
            f"{PRICES_PATH} não encontrado. Rode `make data` (Etapa 1) antes do agente."
        )
    df = pd.read_parquet(PRICES_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _load_fundamentals() -> pd.DataFrame:
    if not FUNDAMENTALS_PATH.exists():
        raise FileNotFoundError(
            f"{FUNDAMENTALS_PATH} não encontrado. Rode `make data` (Etapa 1) antes do agente."
        )
    return pd.read_parquet(FUNDAMENTALS_PATH)


def _normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    if not ticker.endswith(".SA"):
        ticker = f"{ticker}.SA"
    return ticker


def _parse_kv(text: str) -> dict[str, str]:
    """Aceita ``ticker=PETR4,year=2024`` ou JSON ``{"ticker":"PETR4"}``."""
    text = text.strip()
    if text.startswith("{"):
        return {str(k): str(v) for k, v in json.loads(text).items()}
    out: dict[str, str] = {}
    for chunk in text.split(","):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


# ---------- tools ----------------------------------------------------------- #


def annual_returns(query: str) -> str:
    """Retorno por ano-calendário para um ano específico ou todos os anos.

    Input examples:
        ``"year=2024"``        → ranking do ano
        ``"year=2024,ticker=PETR4"`` → retorno do ticker no ano
        ``""``                  → ranking de todos os anos
    """
    args = _parse_kv(query)
    df = _load_prices()
    wide = df.pivot(index="date", columns="ticker", values="close").sort_index()
    annual = wide.resample("YE").last().pct_change().dropna(how="all")
    annual.index = annual.index.year

    year = args.get("year")
    ticker = args.get("ticker")

    if year:
        try:
            year_int = int(year)
        except ValueError:
            return f"Erro: ano inválido '{year}'."
        if year_int not in annual.index:
            return f"Sem dados para {year_int}. Anos disponíveis: {list(annual.index)}."
        row = annual.loc[year_int].dropna().sort_values(ascending=False)
        if ticker:
            t = _normalize_ticker(ticker)
            if t not in row.index:
                return f"Ticker {t} ausente para {year_int}."
            return f"Retorno {t} em {year_int}: {row[t]:.2%}"
        ranking = ", ".join(f"{tk}={ret:.2%}" for tk, ret in row.items())
        return f"Ranking {year_int} (maior→menor): {ranking}"

    summary = annual.idxmax(axis=1).rename("top_ticker").to_frame()
    summary["retorno_top"] = annual.max(axis=1)
    return summary.to_string()


def compare_fundamentals(query: str) -> str:
    """Compara fundamentos (P/L, ROE, Dividend Yield) de 2+ tickers.

    Input examples:
        ``"tickers=PETR4,VALE3"``
        ``"tickers=PETR4,VALE3,metric=pe_ratio"``
    """
    args = _parse_kv(query)
    tickers_raw = args.get("tickers") or args.get("ticker") or query
    tickers = [_normalize_ticker(t) for t in tickers_raw.split(",") if t.strip() and "=" not in t]
    if len(tickers) < 1:
        return "Erro: forneça pelo menos um ticker (ex.: tickers=PETR4,VALE3)."

    fund = _load_fundamentals()
    metric = args.get("metric")
    cols = [metric] if metric else ["pe_ratio", "roe", "dividend_yield", "sector"]

    sub = fund[fund["ticker"].isin(tickers)].set_index("ticker")
    missing = [t for t in tickers if t not in sub.index]
    if missing:
        return f"Tickers ausentes nos fundamentos: {missing}. Disponíveis: {fund['ticker'].tolist()}"

    available = [c for c in cols if c in sub.columns]
    return sub[available].to_string()


def portfolio_risk(query: str) -> str:
    """Calcula relatório de risco para uma carteira ponderada.

    Input examples:
        ``"tickers=PETR4,VALE3,WEGE3,weights=0.4,0.3,0.3"``
        ``"tickers=PETR4,VALE3"`` (pesos iguais)
    """
    args = _parse_kv(query)
    tickers_raw = args.get("tickers", "")
    tickers = [_normalize_ticker(t) for t in tickers_raw.split(",") if t.strip()]
    if len(tickers) < 2:
        return "Erro: forneça pelo menos 2 tickers (ex.: tickers=PETR4,VALE3)."

    weights_raw = args.get("weights")
    if weights_raw:
        weights = np.array([float(w) for w in weights_raw.split(",")])
        if len(weights) != len(tickers):
            return f"Erro: {len(weights)} pesos para {len(tickers)} tickers."
    else:
        weights = np.ones(len(tickers)) / len(tickers)
    weights = weights / weights.sum()

    df = _load_prices()
    wide = df.pivot(index="date", columns="ticker", values="close").sort_index()
    available = [t for t in tickers if t in wide.columns]
    if len(available) != len(tickers):
        missing = set(tickers) - set(available)
        return f"Tickers sem série de preços: {missing}. Disponíveis: {list(wide.columns)}"

    log_ret = np.log(wide[available]).diff().dropna()
    port_ret = log_ret.values @ weights
    vol_annual = port_ret.std() * np.sqrt(252)
    var_95 = float(np.quantile(port_ret, 0.05))
    drawdown = (port_ret.cumsum().min() - port_ret.cumsum().max()).item()
    corr = log_ret.corr()

    lines = [
        f"Carteira: {dict(zip(available, weights.round(3)))}",
        f"Volatilidade anualizada: {vol_annual:.2%}",
        f"VaR 95% (1d): {var_95:.2%}",
        f"Maior drawdown contínuo (log): {drawdown:.2%}",
        "Correlação:",
        corr.round(2).to_string(),
    ]
    return "\n".join(lines)


def technical_signal(query: str) -> str:
    """Sinal técnico atual (RSI, MACD diff, %B) para um ticker."""
    args = _parse_kv(query)
    ticker_raw = args.get("ticker") or query.strip()
    ticker = _normalize_ticker(ticker_raw)

    df = _load_prices()
    sub = df[df["ticker"] == ticker].sort_values("date")
    if sub.empty:
        return f"Sem dados de features para {ticker}."
    last = sub.iloc[-1]
    rsi = float(last["rsi_14"])
    macd_diff = float(last["macd_diff"])
    pctb = float(last["bb_pct_b"])

    rsi_state = "sobrevendido" if rsi < 30 else "sobrecomprado" if rsi > 70 else "neutro"
    macd_state = "alta" if macd_diff > 0 else "baixa"
    bb_state = "abaixo da banda inferior" if pctb < 0 else "acima da banda superior" if pctb > 1 else "dentro das bandas"

    return (
        f"{ticker} em {last['date'].date()}: RSI={rsi:.1f} ({rsi_state}); "
        f"MACD diff={macd_diff:.3f} ({macd_state}); %B={pctb:.2f} ({bb_state})."
    )


def make_rag_search_tool(retriever: Callable[[str, int], list[str]], top_k: int = 4) -> Callable[[str], str]:
    """Cria a tool ``search_reports`` ligada ao retriever do RAG."""

    def search_reports(query: str) -> str:
        chunks = retriever(query, top_k)
        if not chunks:
            return "Nenhum trecho relevante encontrado nos relatórios indexados."
        return "\n---\n".join(f"[trecho {i+1}] {c}" for i, c in enumerate(chunks))

    return search_reports


# ---------- factory --------------------------------------------------------- #


def build_default_tools(retriever: Callable[[str, int], list[str]] | None = None) -> list:
    """Constrói a lista padrão de tools para o agente. Importa LangChain só aqui."""
    from langchain.tools import Tool

    tools = [
        Tool(
            name="annual_returns",
            func=annual_returns,
            description=(
                "Retorno por ano-calendário das ações da carteira. "
                "Use input 'year=2024' para o ranking do ano, "
                "ou 'year=2024,ticker=PETR4' para um ticker específico."
            ),
        ),
        Tool(
            name="compare_fundamentals",
            func=compare_fundamentals,
            description=(
                "Compara fundamentos (P/L, ROE, Dividend Yield) entre tickers. "
                "Use input 'tickers=PETR4,VALE3' ou 'tickers=PETR4,VALE3,metric=pe_ratio'."
            ),
        ),
        Tool(
            name="portfolio_risk",
            func=portfolio_risk,
            description=(
                "Relatório de risco (volatilidade, VaR 95%, correlação) de uma carteira. "
                "Use input 'tickers=PETR4,VALE3,WEGE3,weights=0.4,0.3,0.3'."
            ),
        ),
        Tool(
            name="technical_signal",
            func=technical_signal,
            description=(
                "Situação técnica atual (RSI, MACD diff, %B Bollinger) de um ticker. "
                "Use input 'ticker=PETR4'."
            ),
        ),
    ]
    if retriever is not None:
        tools.append(
            Tool(
                name="search_reports",
                func=make_rag_search_tool(retriever),
                description=(
                    "Busca trechos relevantes dos relatórios financeiros (PDFs) indexados "
                    "para responder perguntas qualitativas. Use input em linguagem natural."
                ),
            )
        )
    return tools
