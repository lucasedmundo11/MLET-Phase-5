"""FastAPI servindo o LLM quantizado e o agente ReAct — Etapa 2.

Endpoints:
    GET  /health         — liveness/readiness.
    POST /llm/complete   — completion direta no LLM local quantizado (GGUF Q4_K_M).
    POST /agent/chat     — pergunta → agente ReAct → ferramentas → resposta.

O LLM é carregado via ``llama-cpp-python`` a partir de um arquivo GGUF
quantizado (variável de ambiente ``LLM_MODEL_PATH``), satisfazendo o critério
de aceite "LLM servido via API com quantização aplicada".
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

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


app = FastAPI(
    title="Datathon Fase 5 — LLM + Agente",
    version="0.2.0",
    description="API do agente financeiro com LLM quantizado e RAG sobre relatórios PDF.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/llm/complete", response_model=CompletionResponse)
def llm_complete(req: CompletionRequest) -> CompletionResponse:
    try:
        llm = get_llm()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    out = llm(prompt=req.prompt, max_tokens=req.max_tokens, temperature=req.temperature)
    choice = out["choices"][0]
    return CompletionResponse(
        completion=choice["text"],
        model=os.path.basename(os.environ.get("LLM_MODEL_PATH", "gguf-quantized")),
        tokens_used=int(out.get("usage", {}).get("total_tokens", 0)),
    )


@app.post("/agent/chat", response_model=ChatResponse)
def agent_chat(req: ChatRequest) -> ChatResponse:
    try:
        agent = get_agent()
    except (RuntimeError, ImportError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result = agent.invoke({"input": req.question})
    return ChatResponse(
        answer=str(result.get("output", "")),
        intermediate_steps=len(result.get("intermediate_steps", []) or []),
    )
