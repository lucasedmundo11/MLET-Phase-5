"""FastAPI servindo o LLM quantizado e o agente ReAct — Etapas 2, 3 e 4.

Endpoints:
    GET  /health         — liveness/readiness.
    GET  /metrics        — exposição Prometheus (Etapa 3).
    POST /llm/complete   — completion direta no LLM local quantizado (GGUF Q4_K_M).
    POST /agent/chat     — pergunta → input guardrail → agente ReAct →
                           output guardrail (PII redacted) → resposta.

O LLM é carregado via ``llama-cpp-python`` a partir de um arquivo GGUF
quantizado (variável de ambiente ``LLM_MODEL_PATH``), satisfazendo o critério
de aceite "LLM servido via API com quantização aplicada".

Instrumentação (Etapa 3):
* Middleware mede latência e contagem por ``endpoint`` e ``status``.
* Tokens do LLM e iterações do agente vão para Prometheus.

Segurança (Etapa 4):
* ``InputGuardrail`` bloqueia prompt injection / context stuffing antes do LLM.
* ``OutputGuardrail`` anonimiza PII na resposta antes de devolver ao usuário.
"""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.monitoring.metrics import (
    agent_iterations,
    agent_question_failures_total,
    http_request_latency_seconds,
    http_requests_total,
    llm_latency_seconds,
    llm_tokens_total,
    render_metrics,
)

logger = logging.getLogger(__name__)

CONFIG_PATH = "configs/llm_config.yaml"


class CompletionRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096)
    max_tokens: int = Field(256, ge=1, le=2048)
    temperature: float = Field(0.0, ge=0.0, le=2.0)


class CompletionResponse(BaseModel):
    completion: str
    model: str
    tokens_used: int


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2048)


class ChatResponse(BaseModel):
    answer: str
    intermediate_steps: int
    guardrail_action: str = "none"  # none | blocked | sanitized


def _load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_llm():
    """Carrega o LLM GGUF quantizado uma única vez por processo."""
    from llama_cpp import Llama

    cfg = _load_config().get("llm", {})
    model_path = os.environ.get("LLM_MODEL_PATH") or cfg.get("model_path")
    if not model_path:
        raise RuntimeError(
            "LLM_MODEL_PATH não definido. Aponte para um arquivo GGUF quantizado "
            "(ex.: Qwen2.5-3B-Instruct-Q4_K_M.gguf)."
        )
    logger.info("Carregando LLM quantizado: %s", model_path)
    return Llama(
        model_path=model_path,
        n_ctx=cfg.get("n_ctx", 4096),
        n_threads=cfg.get("n_threads", 4),
        n_gpu_layers=cfg.get("n_gpu_layers", 0),
        verbose=False,
    )


@lru_cache(maxsize=1)
def get_agent():
    """Constrói o agente ReAct + tools + retriever uma única vez."""
    from src.agent.rag_pipeline import get_retriever
    from src.agent.react_agent import create_datathon_agent
    from src.agent.tools import build_default_tools

    retriever = get_retriever()
    tools = build_default_tools(retriever=retriever.search if retriever else None)

    cfg = _load_config().get("agent", {})
    return create_datathon_agent(
        tools=tools,
        model_name=cfg.get("model_name", "qwen2.5-3b-instruct"),
        temperature=cfg.get("temperature", 0.0),
    )


@lru_cache(maxsize=1)
def get_input_guardrail():
    from src.security.guardrails import InputGuardrail

    return InputGuardrail()


@lru_cache(maxsize=1)
def get_output_guardrail():
    from src.security.guardrails import OutputGuardrail

    return OutputGuardrail(language="pt")


app = FastAPI(
    title="Datathon Fase 5 — LLM + Agente",
    version="0.3.0",
    description="API do agente financeiro com LLM quantizado, RAG e telemetria.",
)


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    endpoint = request.url.path
    http_requests_total.labels(endpoint=endpoint, status=str(response.status_code)).inc()
    http_request_latency_seconds.labels(endpoint=endpoint).observe(elapsed)
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


@app.post("/llm/complete", response_model=CompletionResponse)
def llm_complete(req: CompletionRequest) -> CompletionResponse:
    try:
        llm = get_llm()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    start = time.perf_counter()
    out = llm(prompt=req.prompt, max_tokens=req.max_tokens, temperature=req.temperature)
    llm_latency_seconds.labels(endpoint="/llm/complete").observe(time.perf_counter() - start)

    choice = out["choices"][0]
    usage = out.get("usage", {})
    for kind in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if kind in usage:
            llm_tokens_total.labels(
                endpoint="/llm/complete",
                kind=kind.replace("_tokens", ""),
            ).inc(int(usage[kind]))

    return CompletionResponse(
        completion=choice["text"],
        model=os.path.basename(os.environ.get("LLM_MODEL_PATH", "gguf-quantized")),
        tokens_used=int(usage.get("total_tokens", 0)),
    )


@app.post("/agent/chat", response_model=ChatResponse)
def agent_chat(req: ChatRequest) -> ChatResponse:
    # Etapa 4 — input guardrail (prompt injection / context stuffing).
    try:
        input_guard = get_input_guardrail()
        ok, reason = input_guard.validate(req.question)
        if not ok:
            agent_question_failures_total.labels(reason="input_guardrail").inc()
            return ChatResponse(answer=reason, intermediate_steps=0, guardrail_action="blocked")
    except ImportError:
        # Presidio/spaCy ausente — degrada com aviso, não falha hard.
        logger.warning("InputGuardrail indisponível; seguindo sem validação prévia.")

    try:
        agent = get_agent()
    except (RuntimeError, ImportError) as exc:
        agent_question_failures_total.labels(reason="agent_unavailable").inc()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        result = agent.invoke({"input": req.question})
    except Exception as exc:  # noqa: BLE001
        agent_question_failures_total.labels(reason=type(exc).__name__).inc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    steps = len(result.get("intermediate_steps", []) or [])
    agent_iterations.observe(steps)

    # Etapa 4 — output guardrail (PII redacted).
    raw_answer = str(result.get("output", ""))
    guardrail_action = "none"
    try:
        sanitized = get_output_guardrail().sanitize(raw_answer)
        if sanitized != raw_answer:
            guardrail_action = "sanitized"
        answer = sanitized
    except ImportError:
        answer = raw_answer

    return ChatResponse(
        answer=answer,
        intermediate_steps=steps,
        guardrail_action=guardrail_action,
    )
