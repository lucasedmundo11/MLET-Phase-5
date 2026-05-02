"""Constrói o índice FAISS a partir dos PDFs em ``data/raw/reports/``.

Uso:
    python -m scripts.build_rag_index
"""

from __future__ import annotations

import argparse
import logging

from src.agent.rag_pipeline import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_EMBED_MODEL,
    INDEX_DIR,
    REPORTS_DIR,
    build_index,
    load_corpus,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexador RAG (PDF → FAISS).")
    parser.add_argument("--reports-dir", type=str, default=str(REPORTS_DIR))
    parser.add_argument("--out-dir", type=str, default=str(INDEX_DIR))
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--embed-model", type=str, default=DEFAULT_EMBED_MODEL)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    from pathlib import Path

    chunks = load_corpus(
        reports_dir=Path(args.reports_dir),
        size=args.chunk_size,
        overlap=args.chunk_overlap,
    )
    if not chunks:
        raise SystemExit(
            f"Nenhum PDF encontrado em {args.reports_dir}. "
            "Adicione relatórios financeiros antes de indexar."
        )
    build_index(chunks, embed_model=args.embed_model, out_dir=Path(args.out_dir))


if __name__ == "__main__":
    main()
