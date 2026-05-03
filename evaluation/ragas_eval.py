"""Avaliação do pipeline RAG com RAGAS — 4 métricas obrigatórias.

Referência: Es et al. (2024) — RAGAS: Automated Evaluation of Retrieval
 Augmented Generation. https://arxiv.org/abs/2309.15217

Implementação replicada da seção *RAGAS Evaluation (Etapa 3)* do guia
oficial do Datathon — Fase 05.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

logger = logging.getLogger(__name__)

_API_BASE = os.environ.get("RAG_API_URL", "http://localhost:8000")
_MAX_PROMPT_CHARS = 4000  # CompletionRequest.prompt max_length = 4096


def _build_ragas_llm():
    """LLM para RAGAS: usa /llm/complete local (sem OpenAI API key)."""
    import httpx
    from langchain_core.callbacks.manager import CallbackManagerForLLMRun
    from langchain_core.language_models.llms import LLM
    from ragas.llms import LangchainLLMWrapper

    class _LocalCompletionLLM(LLM):
        api_url: str = f"{_API_BASE}/llm/complete"

        def _call(
            self,
            prompt: str,
            stop: list[str] | None = None,
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> str:
            # Trunca se o prompt exceder o limite do endpoint
            truncated = prompt[:_MAX_PROMPT_CHARS]
            try:
                resp = httpx.post(
                    self.api_url,
                    json={"prompt": truncated, "max_tokens": 512, "temperature": 0.0},
                    timeout=120.0,
                )
                resp.raise_for_status()
                return resp.json().get("completion", "")
            except Exception as exc:
                logger.warning("_LocalCompletionLLM falhou: %s", exc)
                return ""

        @property
        def _llm_type(self) -> str:
            return "local-llm-complete"

    return LangchainLLMWrapper(_LocalCompletionLLM())


def _build_ragas_embeddings():
    """Embeddings para RAGAS: sentence-transformers local (sem OpenAI)."""
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    hf = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    return LangchainEmbeddingsWrapper(hf)


def evaluate_rag_pipeline(
    golden_set_path: str,
    rag_fn,
) -> dict[str, float]:
    """Avalia pipeline RAG contra golden set.

    Args:
        golden_set_path: Caminho para JSON com golden set.
        rag_fn: Função que recebe query e retorna
                (answer, contexts).

    Returns:
        Dicionário com 4 métricas RAGAS.
    """
    with open(golden_set_path) as f:
        golden_set = json.load(f)

    # Gera respostas do pipeline
    results = []
    for item in golden_set:
        answer, contexts = rag_fn(item["query"])
        results.append(
            {
                "question": item["query"],
                "answer": answer,
                "contexts": contexts,
                "ground_truth": item["expected_answer"],
            }
        )

    dataset = Dataset.from_list(results)

    ragas_llm = _build_ragas_llm()
    ragas_embeddings = _build_ragas_embeddings()

    # Avaliação RAGAS — 4 métricas obrigatórias
    scores = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        raise_exceptions=False,
    )

    def _safe(key: str) -> float:
        v = scores[key]
        try:
            f = float(v)
            return f if f == f else 0.0  # NaN → 0.0
        except (TypeError, ValueError):
            return 0.0

    metrics = {
        "faithfulness": _safe("faithfulness"),
        "answer_relevancy": _safe("answer_relevancy"),
        "context_precision": _safe("context_precision"),
        "context_recall": _safe("context_recall"),
    }

    logger.info("RAGAS scores: %s", metrics)
    return metrics
