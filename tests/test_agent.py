"""Testes das tools de domínio do agente — funcionam offline (sem LLM)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import src.agent.tools as tools_mod
from src.agent.rag_pipeline import Chunk, chunk_text
from src.agent.tools import (
    annual_returns,
    compare_fundamentals,
    portfolio_risk,
    technical_signal,
)


@pytest.fixture(autouse=True)
def _stub_data(tmp_path: Path, sample_features: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aponta as tools para parquets sintéticos isolados por teste."""
    prices_path = tmp_path / "prices.parquet"
    fund_path = tmp_path / "fundamentals.parquet"

    sample_features.to_parquet(prices_path, index=False)
    fundamentals = pd.DataFrame(
        [
            {"ticker": "TEST1.SA", "pe_ratio": 8.5, "roe": 0.18, "dividend_yield": 0.06, "sector": "Energy"},
            {"ticker": "TEST2.SA", "pe_ratio": 12.0, "roe": 0.22, "dividend_yield": 0.04, "sector": "Materials"},
        ]
    )
    fundamentals.to_parquet(fund_path, index=False)

    monkeypatch.setattr(tools_mod, "PRICES_PATH", prices_path)
    monkeypatch.setattr(tools_mod, "FUNDAMENTALS_PATH", fund_path)


def test_annual_returns_ranking() -> None:
    out = annual_returns("year=2024")
    assert "TEST1.SA" in out and "TEST2.SA" in out


def test_annual_returns_unknown_year() -> None:
    out = annual_returns("year=1999")
    assert "Sem dados" in out


def test_compare_fundamentals_table() -> None:
    out = compare_fundamentals("tickers=TEST1,TEST2")
    assert "pe_ratio" in out and "TEST1.SA" in out and "TEST2.SA" in out


def test_compare_fundamentals_missing_ticker() -> None:
    out = compare_fundamentals("tickers=PETR4")
    assert "ausentes" in out.lower()


def test_portfolio_risk_report() -> None:
    out = portfolio_risk("tickers=TEST1,TEST2,weights=0.6,0.4")
    assert "Volatilidade anualizada" in out
    assert "Correlação" in out


def test_portfolio_risk_requires_two_tickers() -> None:
    out = portfolio_risk("tickers=TEST1")
    assert "Erro" in out


def test_technical_signal_known_ticker() -> None:
    out = technical_signal("ticker=TEST1")
    assert "RSI" in out and "MACD" in out and "%B" in out


def test_chunk_text_overlaps_correctly() -> None:
    text = "abcdefghij" * 10
    chunks = chunk_text(text, size=20, overlap=5)
    assert all(len(c) <= 20 for c in chunks)
    assert chunks[0][-5:] == chunks[1][:5]


def test_build_default_tools_has_at_least_three(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langchain")
    from src.agent.tools import build_default_tools

    tool_list = build_default_tools(retriever=None)
    assert len(tool_list) >= 3
    names = {t.name for t in tool_list}
    assert {"annual_returns", "compare_fundamentals", "portfolio_risk"}.issubset(names)


def test_in_memory_retriever_returns_top_k() -> None:
    pytest.importorskip("sentence_transformers")
    from src.agent.rag_pipeline import InMemoryRetriever

    chunks = [
        Chunk(text="A Petrobras reportou aumento de produção no pré-sal.", source="petr.pdf", chunk_id=0),
        Chunk(text="A Vale apresentou receita recorde em minério de ferro.", source="vale.pdf", chunk_id=0),
        Chunk(text="Itaú destacou crescimento da carteira de crédito.", source="itub.pdf", chunk_id=0),
    ]
    retriever = InMemoryRetriever(chunks)
    results = retriever.search("produção de petróleo no pré-sal", top_k=2)
    assert len(results) == 2
    assert "petr.pdf" in results[0]
