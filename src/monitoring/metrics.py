"""Métricas Prometheus customizadas — Etapa 3 (Avaliação + Observabilidade).

Conforme o guia (GAP 01), o critério de aceite "Telemetria e dashboard
funcionando end-to-end" exige métricas operacionais (latência, throughput,
erros) instrumentadas no serving e expostas em ``/metrics`` para scrape do
Prometheus.

As métricas seguem a convenção *prometheus_client* e são reutilizáveis entre
o middleware HTTP e os componentes do agente (tools, RAG, drift checker).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)


# ---------- HTTP layer ------------------------------------------------------ #

http_requests_total = Counter(
    "agent_http_requests_total",
    "Total de requisições HTTP por endpoint e status",
    ["endpoint", "status"],
)
http_request_latency_seconds = Histogram(
    "agent_http_request_latency_seconds",
    "Latência por endpoint (s)",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)


# ---------- Agente / tools -------------------------------------------------- #

agent_tool_calls_total = Counter(
    "agent_tool_calls_total",
    "Total de chamadas a tools pelo agente ReAct",
    ["tool"],
)
agent_iterations = Histogram(
    "agent_iterations",
    "Iterações Thought→Action por pergunta",
    buckets=(1, 2, 3, 4, 5, 7, 10),
)
agent_question_failures_total = Counter(
    "agent_question_failures_total",
    "Perguntas que falharam (timeout, parse error, etc.)",
    ["reason"],
)


# ---------- LLM ------------------------------------------------------------- #

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Tokens consumidos por endpoint do LLM",
    ["endpoint", "kind"],  # kind: prompt | completion | total
)
llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "Latência do LLM (s)",
    ["endpoint"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)


# ---------- Drift / qualidade ----------------------------------------------- #

drift_share_of_drifted_columns = Gauge(
    "drift_share_of_drifted_columns",
    "Proporção de colunas com drift detectado pelo Evidently",
)
drift_psi_max = Gauge(
    "drift_psi_max",
    "Maior PSI observado entre features monitoradas",
)
ragas_metric = Gauge(
    "ragas_metric",
    "Métrica RAGAS reportada (faithfulness, answer_relevancy, ...)",
    ["metric"],
)
judge_metric = Gauge(
    "judge_metric",
    "Métrica média do LLM-as-judge por critério",
    ["criterion"],
)


# ---------- helpers --------------------------------------------------------- #


def render_metrics() -> tuple[bytes, str]:
    """Devolve ``(payload, content_type)`` prontos para resposta HTTP."""
    return generate_latest(), CONTENT_TYPE_LATEST


def time_block(histogram: Histogram, **labels) -> Callable[[], None]:
    """Context manager-like utilitário para timing inline.

    Exemplo::

        stop = time_block(http_request_latency_seconds, endpoint='/agent/chat')
        # ... trabalho ...
        stop()
    """
    start = time.perf_counter()

    def _stop() -> None:
        histogram.labels(**labels).observe(time.perf_counter() - start)

    return _stop
