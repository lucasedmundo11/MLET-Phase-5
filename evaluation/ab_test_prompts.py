"""A/B test entre dois prompts ReAct usando o golden set + LLM-as-judge.

Recebe duas variantes de ``PromptTemplate`` (A e B), roda ambas contra o
mesmo subconjunto do golden set, e compara a média de notas do juiz por
critério. O vencedor é o prompt com maior ``overall_mean``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.llm_judge import JudgeAggregate, judge_batch

logger = logging.getLogger(__name__)


@dataclass
class ABResult:
    name_a: str
    name_b: str
    agg_a: JudgeAggregate
    agg_b: JudgeAggregate

    @property
    def winner(self) -> str:
        if self.agg_a.overall_mean == self.agg_b.overall_mean:
            return "tie"
        return self.name_a if self.agg_a.overall_mean > self.agg_b.overall_mean else self.name_b

    def to_dict(self) -> dict[str, Any]:
        return {
            "name_a": self.name_a,
            "name_b": self.name_b,
            "agg_a": self.agg_a.to_dict(),
            "agg_b": self.agg_b.to_dict(),
            "winner": self.winner,
        }


def run_variant(
    prompt_template,
    golden_set: list[dict[str, Any]],
    agent_factory,
    judge_call=None,
) -> JudgeAggregate:
    """Executa uma variante e devolve as métricas agregadas do juiz.

    Args:
        prompt_template: ``PromptTemplate`` LangChain a usar nessa variante.
        golden_set: lista de pares ``{id, query, expected_answer}``.
        agent_factory: callable ``(prompt) -> AgentExecutor``.
        judge_call: função opcional do juiz (default = LLM local).
    """
    agent = agent_factory(prompt_template)
    samples: list[dict[str, Any]] = []
    for item in golden_set:
        try:
            res = agent.invoke({"input": item["query"]})
            answer = str(res.get("output", ""))
            tool_obs = "\n".join(
                f"- {step[0].tool}: {step[1]}" for step in res.get("intermediate_steps", []) or []
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha em '%s': %s", item.get("id"), exc)
            answer, tool_obs = "", ""
        samples.append(
            {
                "id": item.get("id"),
                "query": item["query"],
                "answer": answer,
                "ground_truth": item.get("expected_answer", ""),
                "tool_observations": tool_obs,
            }
        )
    return judge_batch(samples) if judge_call is None else judge_batch(samples, llm_call=judge_call)


def compare_prompts(
    prompt_a,
    prompt_b,
    golden_set_path: str | Path,
    agent_factory,
    name_a: str = "A",
    name_b: str = "B",
    judge_call=None,
) -> ABResult:
    """Roda A vs B no mesmo golden set e devolve vencedor."""
    with open(golden_set_path, encoding="utf-8") as f:
        golden_set = json.load(f)

    logger.info("A/B test: %d perguntas, variantes %s vs %s", len(golden_set), name_a, name_b)
    agg_a = run_variant(prompt_a, golden_set, agent_factory, judge_call=judge_call)
    agg_b = run_variant(prompt_b, golden_set, agent_factory, judge_call=judge_call)
    return ABResult(name_a=name_a, name_b=name_b, agg_a=agg_a, agg_b=agg_b)
