"""End-to-end RAGAS + LLM-as-judge sobre o golden set — Etapa 3.

Executa o agente em todas as perguntas do golden set, calcula as 4 métricas
RAGAS e as 4 notas do juiz, persiste em ``metrics/evaluation.json`` e empurra
para Prometheus (gauges ``ragas_metric`` / ``judge_metric``).

Uso:
    python -m scripts.run_evaluation --url http://localhost:8000/agent/chat
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import httpx

GOLDEN_PATH = Path("data/golden_set/golden_set.json")
METRICS_PATH = Path("metrics/evaluation.json")


def _agent_call(url: str, question: str, timeout: float = 120.0) -> dict[str, Any]:
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json={"question": question})
        r.raise_for_status()
        return r.json()


def _build_rag_fn(url: str):
    """Adapter para o RAGAS: ``query → (answer, contexts)``."""
    def rag_fn(query: str) -> tuple[str, list[str]]:
        body = _agent_call(url, query)
        answer = str(body.get("answer", ""))
        contexts = body.get("contexts", []) or [body.get("answer", "")]
        return answer, contexts

    return rag_fn


def _push_to_prometheus(ragas_scores: dict[str, float], judge_agg) -> None:
    try:
        from src.monitoring.metrics import judge_metric, ragas_metric
    except Exception:  # noqa: BLE001
        return
    for k, v in ragas_scores.items():
        ragas_metric.labels(metric=k).set(float(v))
    for k, v in judge_agg.per_criterion_mean.items():
        judge_metric.labels(criterion=k).set(float(v))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/agent/chat")
    parser.add_argument("--golden", default=str(GOLDEN_PATH))
    parser.add_argument("--skip-ragas", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    summary: dict[str, Any] = {"golden_path": args.golden}

    if not args.skip_ragas:
        from evaluation.ragas_eval import evaluate_rag_pipeline

        rag_fn = _build_rag_fn(args.url)
        ragas_scores = evaluate_rag_pipeline(args.golden, rag_fn)
        summary["ragas"] = {k: float(v) for k, v in ragas_scores.items()}
        logging.info("RAGAS: %s", summary["ragas"])
    else:
        ragas_scores = {}

    if not args.skip_judge:
        from evaluation.llm_judge import judge_batch

        with open(args.golden, encoding="utf-8") as f:
            golden = json.load(f)

        samples = []
        for item in golden:
            try:
                resp = _agent_call(args.url, item["query"])
                answer = str(resp.get("answer", ""))
            except Exception as exc:  # noqa: BLE001
                logging.warning("Falha em '%s': %s", item.get("id"), exc)
                answer = ""
            samples.append(
                {
                    "id": item.get("id"),
                    "query": item["query"],
                    "answer": answer,
                    "ground_truth": item.get("expected_answer", ""),
                }
            )
        agg = judge_batch(samples)
        summary["judge"] = agg.to_dict()
        logging.info("Judge: %s", summary["judge"])
        _push_to_prometheus(ragas_scores, agg)

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Métricas salvas em %s", METRICS_PATH)


if __name__ == "__main__":
    main()
