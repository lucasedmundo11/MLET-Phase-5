"""RAG: indexação + recuperação sobre relatórios financeiros em PDF.

Pipeline:
    1. Lê PDFs em ``data/raw/reports/`` (pypdf).
    2. Chunka por janelas de N caracteres com overlap.
    3. Gera embeddings com ``sentence-transformers``.
    4. Indexa em FAISS (``data/processed/rag_index/``).
    5. Expõe ``Retriever`` com método ``search(query, top_k)``.
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("data/raw/reports")
INDEX_DIR = Path("data/processed/rag_index")
INDEX_FILE = INDEX_DIR / "faiss.index"
CHUNKS_FILE = INDEX_DIR / "chunks.pkl"
META_FILE = INDEX_DIR / "meta.json"

DEFAULT_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120


@dataclass
class Chunk:
    text: str
    source: str
    chunk_id: int


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def chunk_text(text: str, size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Janela deslizante por caracteres com overlap."""
    text = " ".join(text.split())
    if not text:
        return []
    if size <= overlap:
        raise ValueError("chunk size deve ser maior que overlap")
    step = size - overlap
    return [text[i : i + size] for i in range(0, len(text), step) if text[i : i + size].strip()]


def load_corpus(reports_dir: Path = REPORTS_DIR, size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[Chunk]:
    """Lê todos os PDFs do diretório e devolve a lista de chunks."""
    if not reports_dir.exists():
        logger.warning("Diretório de relatórios ausente: %s", reports_dir)
        return []
    chunks: list[Chunk] = []
    for pdf_path in sorted(reports_dir.glob("*.pdf")):
        logger.info("Lendo %s", pdf_path.name)
        text = _read_pdf(pdf_path)
        for i, piece in enumerate(chunk_text(text, size=size, overlap=overlap)):
            chunks.append(Chunk(text=piece, source=pdf_path.name, chunk_id=i))
    logger.info("Corpus carregado: %d chunks de %d arquivos", len(chunks), len(set(c.source for c in chunks)))
    return chunks


def build_index(
    chunks: list[Chunk],
    embed_model: str = DEFAULT_EMBED_MODEL,
    out_dir: Path = INDEX_DIR,
) -> None:
    """Gera embeddings, salva FAISS index + chunks + metadata."""
    if not chunks:
        raise ValueError("Nenhum chunk para indexar (diretório de PDFs vazio?).")

    import faiss
    from sentence_transformers import SentenceTransformer

    logger.info("Carregando modelo de embedding: %s", embed_model)
    model = SentenceTransformer(embed_model)
    texts = [c.text for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype="float32")

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    out_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(out_dir / "faiss.index"))
    with open(out_dir / "chunks.pkl", "wb") as f:
        pickle.dump(chunks, f)
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "embed_model": embed_model,
                "n_chunks": len(chunks),
                "dim": int(embeddings.shape[1]),
                "sources": sorted({c.source for c in chunks}),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info("Índice salvo em %s (%d chunks, dim=%d)", out_dir, len(chunks), embeddings.shape[1])


class Retriever:
    """Wrapper sobre FAISS + sentence-transformers para top-k."""

    def __init__(self, index_dir: Path = INDEX_DIR) -> None:
        import faiss
        from sentence_transformers import SentenceTransformer

        if not (index_dir / "faiss.index").exists():
            raise FileNotFoundError(
                f"Índice ausente em {index_dir}. Rode `python -m scripts.build_rag_index`."
            )
        with open(index_dir / "meta.json", encoding="utf-8") as f:
            meta = json.load(f)
        self.model = SentenceTransformer(meta["embed_model"])
        self.index = faiss.read_index(str(index_dir / "faiss.index"))
        with open(index_dir / "chunks.pkl", "rb") as f:
            self.chunks: list[Chunk] = pickle.load(f)
        self.meta = meta

    def search(self, query: str, top_k: int = 4) -> list[str]:
        emb = self.model.encode([query], normalize_embeddings=True).astype("float32")
        _, idx = self.index.search(emb, top_k)
        results: list[str] = []
        for i in idx[0]:
            if 0 <= i < len(self.chunks):
                c = self.chunks[i]
                results.append(f"({c.source} #{c.chunk_id}) {c.text}")
        return results


class InMemoryRetriever:
    """Fallback sem FAISS: cosseno em numpy, útil para testes e bootstrap."""

    def __init__(self, chunks: list[Chunk], embed_model: str = DEFAULT_EMBED_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self.chunks = chunks
        self.model = SentenceTransformer(embed_model)
        texts = [c.text for c in chunks]
        emb = self.model.encode(texts, normalize_embeddings=True)
        self.embeddings = np.asarray(emb, dtype="float32")

    def search(self, query: str, top_k: int = 4) -> list[str]:
        if not self.chunks:
            return []
        q = self.model.encode([query], normalize_embeddings=True).astype("float32")
        scores = (self.embeddings @ q.T).ravel()
        top = np.argsort(-scores)[:top_k]
        return [f"({self.chunks[i].source} #{self.chunks[i].chunk_id}) {self.chunks[i].text}" for i in top]


def get_retriever(top_k: int = 4):
    """Factory: tenta carregar FAISS; se ausente, retorna ``None`` (RAG opcional)."""
    try:
        return Retriever()
    except (FileNotFoundError, ImportError) as exc:
        logger.warning("Retriever indisponível: %s", exc)
        return None
