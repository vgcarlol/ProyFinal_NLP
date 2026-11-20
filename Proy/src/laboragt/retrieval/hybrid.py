"""Recuperación híbrida (Fase 3).

  1. Análisis de consulta: artículos/decretos citados, año, subconsultas.
  2. Candidatos: BM25 (top 30) + vectorial e5 (top 30) por subconsulta, ambos filtrados por rol.
  3. Fusión por Reciprocal Rank Fusion (k=60).
  4. Candidatos fijados por metadatos si el usuario cita "artículo N" / "Decreto X".
  5. Filtro de vigencia: año pedido o, por defecto, documentos vigentes hoy.
  6. Reranking con cross-encoder bge-reranker-v2-m3 y diversidad (máx. 2 chunks por artículo).
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

from .. import config
from ..schemas import ROLE_ACCESS, Chunk, UserRole
from .bm25 import BM25Index, Hit
from .query_analysis import QueryAnalysis, analyze, in_force
from .vector import VectorIndex


@lru_cache(maxsize=1)
def get_reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(config.RERANK_MODEL, device=config.DEVICE, max_length=512)


def today() -> date:
    return date.fromisoformat(config.TODAY) if config.TODAY else date.today()


class HybridRetriever:
    def __init__(self, bm25: BM25Index | None = None, vec: VectorIndex | None = None,
                 use_vector: bool = True, use_rerank: bool = True, use_filters: bool = True):
        self.bm25 = bm25 or BM25Index.load()
        self.vec = (vec or VectorIndex.load()) if use_vector else None
        self.use_rerank = use_rerank
        self.use_filters = use_filters
        self.by_id: dict[str, Chunk] = {c.chunk_id: c for c in self.bm25.chunks}

    # ---------- piezas ----------
    def _candidates(self, query: str, role: UserRole) -> dict[str, float]:
        """RRF de BM25 + vectorial para una (sub)consulta."""
        scores: dict[str, float] = {}
        for rank, h in enumerate(self.bm25.search(query, role, k=config.CANDIDATES_PER_RETRIEVER), start=1):
            scores[h.chunk.chunk_id] = scores.get(h.chunk.chunk_id, 0) + 1 / (config.RRF_K + rank)
        if self.vec:
            for rank, (cid, _) in enumerate(self.vec.search(query, role, k=config.CANDIDATES_PER_RETRIEVER), start=1):
                scores[cid] = scores.get(cid, 0) + 1 / (config.RRF_K + rank)
        return scores

    def _pinned(self, qa: QueryAnalysis, role: UserRole) -> list[str]:
        """Chunks cuyo artículo/decreto fue citado explícitamente (búsqueda exacta por metadatos)."""
        allowed = ROLE_ACCESS[role]
        out = []
        for c in self.bm25.chunks:
            if c.access_level not in allowed:
                continue
            doc_ok = (not qa.doc_ids) or c.doc_id in qa.doc_ids
            if qa.articles and c.article in qa.articles and doc_ok:
                # sin decreto explícito, el artículo se asume del Código de Trabajo
                if qa.doc_ids or c.doc_id == "codigo_trabajo":
                    out.append(c.chunk_id)
        return out

    def _vigente(self, c: Chunk, qa: QueryAnalysis) -> bool:
        return in_force(c.vigencia_desde, c.vigencia_hasta, qa.year, today())

    # ---------- API ----------
    def search(self, question: str, role: UserRole, k: int = config.TOP_K) -> list[Hit]:
        qa = analyze(question)
        queries = [question] + qa.subqueries
        fused: dict[str, float] = {}
        per_query: list[list[str]] = []
        for q in queries:
            s = self._candidates(q, role)
            per_query.append(sorted(s, key=s.get, reverse=True))
            for cid, v in s.items():
                fused[cid] = fused.get(cid, 0) + v

        pinned = self._pinned(qa, role) if self.use_filters else []
        if self.use_filters:
            fused = {cid: v for cid, v in fused.items() if self._vigente(self.by_id[cid], qa)}

        ranked = sorted(fused, key=fused.get, reverse=True)
        # pool para el reranker: fijados + mejores de cada subconsulta (garantiza cobertura) + fusión
        pool: list[str] = list(pinned)
        if qa.subqueries:
            for lst in per_query[1:]:
                pool += [c for c in lst if c in fused][:5]
        pool += ranked
        pool = list(dict.fromkeys(pool))[: config.RERANK_POOL + len(pinned)]
        if not pool:
            return []

        if self.use_rerank:
            reranker = get_reranker()
            rr_queries = queries if qa.subqueries else [question]
            # una sola pasada por el cross-encoder: matriz (consulta x candidato); predict ya devuelve
            # probabilidades (activación sigmoide incluida en el modelo)
            pairs = [(q, self.by_id[c].text) for q in rr_queries for c in pool]
            probs = reranker.predict(pairs, batch_size=32, show_progress_bar=False)
            n = len(pool)
            matrix = [[float(probs[i * n + j]) for j in range(n)] for i in range(len(rr_queries))]
            best = {cid: max(matrix[i][j] for i in range(len(rr_queries))) for j, cid in enumerate(pool)}
            for cid in pinned:  # el identificador exacto pesa más que la similitud
                best[cid] = max(best[cid], 0.99)
            order = sorted(pool, key=best.get, reverse=True)
            scored = [(cid, best[cid]) for cid in order]
            if qa.subqueries:  # asegurar al menos el mejor chunk de cada subconsulta
                must = list(dict.fromkeys(pool[max(range(n), key=lambda j: matrix[i][j])]
                                          for i in range(1, len(rr_queries))))
                rest = [x for x in scored if x[0] not in must]
                head = [rest.pop(0)] if rest and rest[0][1] > best[must[0]] else []
                scored = head + [(m, best[m]) for m in must] + rest
        else:
            scored = [(cid, fused.get(cid, 1.0)) for cid in pool]

        # diversidad: como máximo N chunks del mismo artículo
        hits, per_art = [], {}
        for cid, sc in scored:
            c = self.by_id[cid]
            key = (c.doc_id, c.article or cid)
            if per_art.get(key, 0) >= config.MAX_CHUNKS_PER_ARTICLE:
                continue
            per_art[key] = per_art.get(key, 0) + 1
            hits.append(Hit(c, float(sc), len(hits) + 1))
            if len(hits) >= k:
                break
        return hits
