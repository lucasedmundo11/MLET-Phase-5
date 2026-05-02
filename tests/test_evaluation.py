"""Testes da Etapa 3 — golden set + LLM-as-judge (com LLM mockado)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

GOLDEN_PATH = Path("data/golden_set/golden_set.json")


def test_golden_set_has_at_least_20_pairs() -> None:
    """Critério de aceite: golden set ≥ 20 pares relevantes ao domínio."""
    items = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert len(items) >= 20, f"Golden set tem apenas {len(items)} itens (mínimo 20)."
    required_fields = {"id", "category", "query", "expected_answer"}
    for item in items:
        missing = required_fields - set(item.keys())
        assert not missing, f"Item {item.get('id')} sem campos: {missing}"


def test_golden_set_covers_all_tools() -> None:
    """Cobertura: golden set deve exercitar pelo menos as 4 categorias principais."""
    items = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    categories = {item["category"] for item in items}
    expected = {"annual_returns", "fundamentals", "portfolio_risk", "technical_signal"}
    assert expected.issubset(categories), f"Categorias ausentes: {expected - categories}"


def test_judge_parses_valid_output() -> None:
    from evaluation.llm_judge import _parse_judge_output

    raw = (
        '{"correctness": 5, "faithfulness": 4, "actionability": 3, '
        '"risk_awareness": 4, "rationale": "ok"}'
    )
    scores, rationale = _parse_judge_output(raw)
    assert scores == {"correctness": 5, "faithfulness": 4, "actionability": 3, "risk_awareness": 4}
    assert rationale == "ok"


def test_judge_clamps_out_of_range() -> None:
    from evaluation.llm_judge import _parse_judge_output

    raw = (
        '{"correctness": 9, "faithfulness": 0, "actionability": 3, '
        '"risk_awareness": 5, "rationale": "x"}'
    )
    scores, _ = _parse_judge_output(raw)
    assert 1 <= scores["correctness"] <= 5
    assert 1 <= scores["faithfulness"] <= 5


def test_judge_rejects_missing_criterion() -> None:
    from evaluation.llm_judge import _parse_judge_output

    raw = '{"correctness": 5, "faithfulness": 4, "actionability": 3, "rationale": "x"}'
    with pytest.raises(ValueError):
        _parse_judge_output(raw)


def test_judge_batch_aggregates_with_stub_llm() -> None:
    from evaluation.llm_judge import judge_batch

    fake_response = (
        '{"correctness": 4, "faithfulness": 5, "actionability": 4, '
        '"risk_awareness": 3, "rationale": "stub"}'
    )

    def stub_call(_prompt: str) -> str:
        return fake_response

    samples = [
        {"id": "x1", "query": "q1", "answer": "a1", "ground_truth": "gt1"},
        {"id": "x2", "query": "q2", "answer": "a2", "ground_truth": "gt2"},
    ]
    agg = judge_batch(samples, llm_call=stub_call, pass_threshold=4.0)
    assert agg.n == 2
    assert set(agg.per_criterion_mean) == {
        "correctness", "faithfulness", "actionability", "risk_awareness"
    }
    assert agg.overall_mean == pytest.approx((4 + 5 + 4 + 3) / 4)
    assert 0.0 <= agg.pass_rate <= 1.0


def test_judge_includes_business_criterion() -> None:
    """Critério de aceite: ≥ 3 critérios *incluindo critério de negócio*."""
    from evaluation.llm_judge import CRITERIA

    business_criteria = {"actionability", "risk_awareness"}
    assert business_criteria & set(CRITERIA), (
        "LLM-as-judge precisa expor pelo menos 1 critério de negócio."
    )
    assert len(CRITERIA) >= 3
