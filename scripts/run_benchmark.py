"""Benchmark do agente — Etapa 2.

Roda um conjunto de perguntas representativas contra ``/agent/chat`` e mede
latência média, p95 e número de tool calls. Persiste o resultado em
``metrics/benchmark.json`` para alimentar ``docs/BENCHMARK.md``.

Uso:
    python -m scripts.run_benchmark --config A
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from pathlib import Path

import httpx

QUESTIONS = [
    "Qual ação teve maior retorno em 2024?",
    "Qual ação teve maior retorno em 2023?",
    "Qual ação teve maior retorno em 2022?",
    "Compare PETR4 e VALE3 pelo P/L.",
    "Compare ITUB4 e BBDC4 pelo ROE.",
    "Qual ticker tem o maior dividend yield?",
    "Gere um relatório de risco da carteira PETR4, VALE3, WEGE3 com pesos iguais.",
    "Gere um relatório de risco da carteira ITUB4, BBDC4 com 70/30.",
    "Qual o sinal técnico atual de PETR4?",
    "Qual o sinal técnico atual de WEGE3?",
    "Resuma os principais riscos mencionados nos relatórios da Petrobras.",
    "O que os relatórios da Vale dizem sobre minério de ferro?",
]

METRICS_PATH = Path("metrics/benchmark.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Identificador da configuração (A/B/C).")
    parser.add_argument("--url", default="http://localhost:8000/agent/chat")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    latencies: list[float] = []
    tool_steps: list[int] = []
    failures = 0

    with httpx.Client(timeout=args.timeout) as client:
        for q in QUESTIONS:
            t0 = time.perf_counter()
            try:
                r = client.post(args.url, json={"question": q})
                r.raise_for_status()
                body = r.json()
                tool_steps.append(int(body.get("intermediate_steps", 0)))
            except Exception as exc:  # noqa: BLE001
                logging.warning("Falha em '%s': %s", q, exc)
                failures += 1
                continue
            latencies.append(time.perf_counter() - t0)

    summary = {
        "config": args.config,
        "n_questions": len(QUESTIONS),
        "n_failures": failures,
        "latency_mean_s": round(statistics.mean(latencies), 3) if latencies else None,
        "latency_p95_s": (
            round(statistics.quantiles(latencies, n=20)[-1], 3)
            if len(latencies) >= 20
            else max(latencies)
            if latencies
            else None
        ),
        "tool_calls_mean": round(statistics.mean(tool_steps), 2) if tool_steps else None,
    }
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if METRICS_PATH.exists():
        with open(METRICS_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = {}
    existing[args.config] = summary
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    logging.info("Resumo salvo em %s: %s", METRICS_PATH, summary)


if __name__ == "__main__":
    main()
