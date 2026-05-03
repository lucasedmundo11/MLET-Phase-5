"""Avaliação do pipeline RAG com métricas RAGAS-compatíveis — 4 métricas obrigatórias.

Referência: Es et al. (2024) — RAGAS: Automated Evaluation of Retrieval
 Augmented Generation. https://arxiv.org/abs/2309.15217

As 4 métricas (faithfulness, answer_relevancy, context_precision,
context_recall) são calculadas por similaridade de cosseno entre
embeddings de frases, usando o mesmo modelo sentence-transformers do
pipeline RAG. Isso evita a dependência de um LLM capaz de seguir prompts
estruturados complexos.
"""

from __future__ import annotations

import json
import logging

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_CONTEXT_THRESHOLD = 0.45  # limiar para context_precision


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


class _EmbedRAGAS:
    """Métricas RAGAS via embeddings — sem LLM externo."""

    def __init__(self, model_name: str = _EMBED_MODEL) -> None:
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    # ── 4 métricas ──────────────────────────────────────────────────────────

    def faithfulness(self, answer: str, contexts: list[str]) -> float:
        """Máxima similaridade entre a resposta e qualquer chunk de contexto."""
        if not contexts or not answer:
            return 0.0
        vecs = self.encode([answer] + contexts)
        ans_v = vecs[0]
        return float(max(_cosine(ans_v, c) for c in vecs[1:]))

    def answer_relevancy(self, question: str, answer: str) -> float:
        """Similaridade semântica entre pergunta e resposta."""
        if not question or not answer:
            return 0.0
        q_v, a_v = self.encode([question, answer])
        return float(_cosine(q_v, a_v))

    def context_precision(self, answer: str, contexts: list[str]) -> float:
        """Fração de chunks de contexto relevantes para a resposta."""
        if not contexts or not answer:
            return 0.0
        vecs = self.encode([answer] + contexts)
        ans_v = vecs[0]
        sims = [_cosine(ans_v, c) for c in vecs[1:]]
        return float(sum(1 for s in sims if s > _CONTEXT_THRESHOLD) / len(sims))

    def context_recall(self, ground_truth: str, contexts: list[str]) -> float:
        """Máxima similaridade entre o ground truth e qualquer chunk de contexto."""
        if not contexts or not ground_truth:
            return 0.0
        vecs = self.encode([ground_truth] + contexts)
        gt_v = vecs[0]
        return float(max(_cosine(gt_v, c) for c in vecs[1:]))


def evaluate_rag_pipeline(
    golden_set_path: str,
    rag_fn,
) -> tuple[dict[str, float], list[dict]]:
    """Avalia pipeline RAG contra golden set.

    Args:
        golden_set_path: Caminho para JSON com golden set.
        rag_fn: Função que recebe query e retorna (answer, contexts).

    Returns:
        Tupla (métricas, answer_records).
        ``answer_records`` pode ser reutilizado pelo LLM-judge sem nova
        chamada à API do agente.
    """
    with open(golden_set_path) as f:
        golden_set = json.load(f)

    ragas = _EmbedRAGAS()

    answer_records: list[dict] = []
    f_scores, ar_scores, cp_scores, cr_scores = [], [], [], []

    for item in golden_set:
        answer, contexts = rag_fn(item["query"])
        ground_truth = item.get("expected_answer", "")

        answer_records.append(
            {
                "id": item.get("id", ""),
                "query": item["query"],
                "answer": answer,
                "ground_truth": ground_truth,
                "tool_observations": "",
            }
        )

        f_scores.append(ragas.faithfulness(answer, contexts))
        ar_scores.append(ragas.answer_relevancy(item["query"], answer))
        cp_scores.append(ragas.context_precision(answer, contexts))
        cr_scores.append(ragas.context_recall(ground_truth, contexts))

    def _mean(xs: list[float]) -> float:
        return round(float(np.mean(xs)), 4) if xs else 0.0

    metrics = {
        "faithfulness": _mean(f_scores),
        "answer_relevancy": _mean(ar_scores),
        "context_precision": _mean(cp_scores),
        "context_recall": _mean(cr_scores),
    }

    logger.info("RAGAS (embedding-based) scores: %s", metrics)
    return metrics, answer_records
