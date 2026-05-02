"""LLM-as-judge — Etapa 3 (Avaliação + Observabilidade).

Avalia respostas do agente em **4 critérios** (≥ 3 exigidos pelo guia,
incluindo um critério de negócio):

1. ``correctness``        — a resposta está factualmente correta vs. ground truth?
2. ``faithfulness``       — a resposta se apoia nas observações das tools (sem
   inventar números)?
3. ``actionability``      — **critério de negócio**: a resposta ajuda um
   investidor a tomar uma decisão?
4. ``risk_awareness``     — **critério de negócio**: a resposta sinaliza
   incertezas, premissas e limitações relevantes?

Cada critério é pontuado de 1 a 5 por um LLM-juiz (mesmo backend do agente,
configurável via ``OPENAI_API_BASE`` / ``OPENAI_API_KEY``).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


JUDGE_PROMPT = """Você é um juiz especializado em avaliar respostas de um
agente financeiro sobre o universo PETR4, VALE3, ITUB4, BBDC4, WEGE3.

Avalie a resposta abaixo nos 4 critérios e devolva **somente** um JSON
válido, sem comentários, no formato:
{{"correctness": int, "faithfulness": int, "actionability": int,
  "risk_awareness": int, "rationale": str}}

Cada critério recebe nota de 1 (muito ruim) a 5 (excelente):
- correctness: a resposta está factualmente correta em relação ao ground truth?
- faithfulness: a resposta se apoia nos números/observações das tools, sem inventar?
- actionability (negócio): ajuda um investidor a tomar uma decisão?
- risk_awareness (negócio): aponta incertezas, premissas e limitações?

Pergunta: {query}

Resposta do agente:
{answer}

Ground truth (referência humana):
{ground_truth}

Observações das tools usadas:
{tool_observations}
"""


CRITERIA: tuple[str, ...] = (
    "correctness",
    "faithfulness",
    "actionability",
    "risk_awareness",
)


@dataclass
class JudgeResult:
    sample_id: str
    scores: dict[str, int]
    rationale: str
    raw: str = ""

    def mean(self) -> float:
        return sum(self.scores.values()) / max(len(self.scores), 1)


@dataclass
class JudgeAggregate:
    n: int
    per_criterion_mean: dict[str, float]
    overall_mean: float
    pass_rate: float
    samples: list[JudgeResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "per_criterion_mean": self.per_criterion_mean,
            "overall_mean": self.overall_mean,
            "pass_rate": self.pass_rate,
        }


def _default_llm_call(prompt: str) -> str:
    """Cliente LLM padrão — mesma rota OpenAI-compatible usada pelo agente."""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", "sk-local-quantized"),
        base_url=os.environ.get("OPENAI_API_BASE"),
    )
    resp = client.chat.completions.create(
        model=os.environ.get("JUDGE_MODEL", "qwen2.5-3b-instruct"),
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content or ""


def _parse_judge_output(raw: str) -> tuple[dict[str, int], str]:
    """Extrai JSON da resposta do juiz, robusto a texto extra."""
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Saída do juiz sem JSON válido: {raw[:200]}")
    payload = json.loads(match.group(0))
    scores: dict[str, int] = {}
    for c in CRITERIA:
        v = payload.get(c)
        if v is None:
            raise ValueError(f"Critério '{c}' ausente na saída do juiz: {payload}")
        scores[c] = max(1, min(5, int(v)))
    rationale = str(payload.get("rationale", ""))
    return scores, rationale


def judge_sample(
    sample: dict[str, Any],
    llm_call=_default_llm_call,
) -> JudgeResult:
    """Avalia uma única amostra ``{id, query, answer, ground_truth, tool_observations}``."""
    prompt = JUDGE_PROMPT.format(
        query=sample["query"],
        answer=sample["answer"],
        ground_truth=sample.get("ground_truth", ""),
        tool_observations=sample.get("tool_observations", ""),
    )
    raw = llm_call(prompt)
    scores, rationale = _parse_judge_output(raw)
    return JudgeResult(
        sample_id=str(sample.get("id", "?")),
        scores=scores,
        rationale=rationale,
        raw=raw,
    )


def judge_batch(
    samples: list[dict[str, Any]],
    llm_call=_default_llm_call,
    pass_threshold: float = 4.0,
) -> JudgeAggregate:
    """Avalia uma lista de amostras e agrega métricas.

    Args:
        samples: cada item deve conter ``query``, ``answer``, ``ground_truth``.
        llm_call: função que recebe prompt e retorna texto. Por padrão usa
            o LLM local quantizado servido em ``OPENAI_API_BASE``.
        pass_threshold: nota média mínima por amostra para contar como
            *aprovada* no ``pass_rate``.

    Returns:
        ``JudgeAggregate`` com médias por critério, média geral e pass rate.
    """
    results: list[JudgeResult] = []
    for sample in samples:
        try:
            results.append(judge_sample(sample, llm_call=llm_call))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao avaliar %s: %s", sample.get("id"), exc)

    if not results:
        return JudgeAggregate(
            n=0, per_criterion_mean={c: 0.0 for c in CRITERIA}, overall_mean=0.0, pass_rate=0.0
        )

    per_criterion_mean = {
        c: sum(r.scores[c] for r in results) / len(results) for c in CRITERIA
    }
    overall_mean = sum(r.mean() for r in results) / len(results)
    pass_rate = sum(1 for r in results if r.mean() >= pass_threshold) / len(results)

    return JudgeAggregate(
        n=len(results),
        per_criterion_mean=per_criterion_mean,
        overall_mean=round(overall_mean, 3),
        pass_rate=round(pass_rate, 3),
        samples=results,
    )
