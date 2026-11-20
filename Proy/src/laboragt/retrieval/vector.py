"""Índice vectorial: embeddings multilingual-e5-base + ChromaDB persistente (HNSW, coseno)."""
from __future__ import annotations

import logging
from functools import lru_cache

from .. import config
from ..schemas import ROLE_ACCESS, Chunk, UserRole

log = logging.getLogger(__name__)
COLLECTION = "laboragt_chunks"


@lru_cache(maxsize=1)
def get_embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config.EMBED_MODEL, device=config.DEVICE)


def embed_passages(texts: list[str]) -> list[list[float]]:
    # e5 requiere los prefijos "passage: " / "query: "
    return get_embedder().encode([f"passage: {t}" for t in texts], batch_size=32,
                                 normalize_embeddings=True, show_progress_bar=False).tolist()


def embed_query(text: str) -> list[float]:
    return get_embedder().encode([f"query: {text}"], normalize_embeddings=True)[0].tolist()


def _client():
    import chromadb
    from chromadb.config import Settings

    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.INDEX_DIR / "chroma"),
                                     settings=Settings(anonymized_telemetry=False))


class VectorIndex:
    def __init__(self, collection):
        self.col = collection

    @classmethod
    def build(cls, chunks: list[Chunk]) -> "VectorIndex":
        client = _client()
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
        col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        embs = embed_passages([c.text for c in chunks])
        metas = [{"doc_id": c.doc_id, "access_level": c.access_level.value, "article": c.article or "",
                  "page": c.page} for c in chunks]
        for i in range(0, len(chunks), 256):
            col.add(ids=[c.chunk_id for c in chunks[i:i + 256]], embeddings=embs[i:i + 256],
                    metadatas=metas[i:i + 256], documents=[c.text for c in chunks[i:i + 256]])
        log.info("Índice vectorial: %d chunks", col.count())
        return cls(col)

    @classmethod
    def load(cls) -> "VectorIndex":
        return cls(_client().get_collection(COLLECTION))

    def search(self, query: str, role: UserRole, k: int = 30) -> list[tuple[str, float]]:
        """Devuelve [(chunk_id, similitud)]. El filtro por rol se aplica dentro del motor vectorial."""
        allowed = [a.value for a in ROLE_ACCESS[role]]
        res = self.col.query(query_embeddings=[embed_query(query)], n_results=k,
                             where={"access_level": {"$in": allowed}})
        ids, dists = res["ids"][0], res["distances"][0]
        return [(i, 1.0 - d) for i, d in zip(ids, dists)]
