"""Línea base (Fase 2): BM25 + prompt estructurado, sin memoria, sin herramientas.

Flujo: validar entrada -> BM25 filtrado por rol -> umbral de abstención -> LLM (JSON) ->
verificar citas -> respuesta contractual + traza.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from . import config
from .llm import LLMError, chat_structured
from .prompts import SYSTEM_GROUNDED, build_user_prompt, resolve_citations
from .retrieval.bm25 import BM25Index, Hit
from .schemas import LaboraResponse, LLMDraft, Query, SourceRef, UserRole
from .trace import new_trace_id, write_trace

ABSTAIN_NO_EVIDENCE = ("No encontré evidencia suficiente en los documentos autorizados para responder "
                       "esta pregunta. Le sugiero consultarla con un profesional en derecho laboral.")
ABSTAIN_INVALID = "La consulta no es válida: {reason}"
ABSTAIN_LLM_DOWN = "El servicio de generación no está disponible en este momento. Intente más tarde."


@dataclass
class RunInfo:
    """Métricas internas de una consulta (para benchmark y trazas)."""

    trace_id: str
    hits: list[Hit] = field(default_factory=list)
    latency_s: float = 0.0
    retrieval_s: float = 0.0
    llm_calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    decision: str = ""


class BaselineRAG:
    name = "baseline_bm25"

    def __init__(self, index: BM25Index | None = None, top_k: int = config.TOP_K,
                 min_score: float = config.BM25_MIN_SCORE):
        self.index = index or BM25Index.load()
        self.top_k = top_k
        self.min_score = min_score

    def retrieve(self, question: str, role: UserRole) -> list[Hit]:
        return self.index.search(question, role, k=self.top_k)

    def answer(self, question: str, role: UserRole | str = UserRole.COLABORADOR) -> tuple[LaboraResponse, RunInfo]:
        info = RunInfo(trace_id=new_trace_id())
        t0 = time.perf_counter()
        try:
            q = Query(question=question, role=role)
        except ValidationError as e:
            reason = e.errors()[0]["msg"]
            resp = LaboraResponse(answer=ABSTAIN_INVALID.format(reason=reason), abstained=True)
            info.decision = "entrada_invalida"
            return self._finish(resp, info, t0, question, str(role))

        t1 = time.perf_counter()
        info.hits = self.retrieve(q.question, q.role)
        info.retrieval_s = time.perf_counter() - t1

        if not info.hits or info.hits[0].score < self.min_score:
            info.decision = "abstencion_umbral"
            return self._finish(LaboraResponse(answer=ABSTAIN_NO_EVIDENCE, abstained=True),
                                info, t0, q.question, q.role.value)

        try:
            res = chat_structured(SYSTEM_GROUNDED, build_user_prompt(q.question, info.hits), LLMDraft)
        except LLMError:
            info.decision = "llm_no_disponible"
            return self._finish(LaboraResponse(answer=ABSTAIN_LLM_DOWN, abstained=True, needs_human_review=True),
                                info, t0, q.question, q.role.value)
        info.llm_calls += 1
        info.prompt_tokens += res.prompt_tokens
        info.output_tokens += res.output_tokens

        draft: LLMDraft | None = res.parsed  # type: ignore[assignment]
        if draft is None:
            info.decision = "salida_invalida"
            return self._finish(LaboraResponse(answer=ABSTAIN_NO_EVIDENCE, abstained=True, needs_human_review=True),
                                info, t0, q.question, q.role.value)

        # Guardrail de salida mínimo: las citas deben existir en el contexto recuperado.
        by_id = {h.chunk.chunk_id: h.chunk for h in info.hits}
        draft.answer, valid = resolve_citations(draft.answer, draft.cited_chunk_ids, set(by_id))
        if draft.insufficient_evidence or not valid:
            info.decision = "abstencion_llm" if draft.insufficient_evidence else "sin_citas_validas"
            return self._finish(LaboraResponse(answer=ABSTAIN_NO_EVIDENCE, abstained=True),
                                info, t0, q.question, q.role.value)

        sources = [SourceRef(source=by_id[c].source, page=by_id[c].page, chunk_id=c,
                             article=by_id[c].article, doc_title=by_id[c].doc_title) for c in valid]
        info.decision = "respuesta"
        resp = LaboraResponse(answer=draft.answer, sources=sources, abstained=False,
                              needs_human_review=len(valid) < len(draft.cited_chunk_ids))
        return self._finish(resp, info, t0, q.question, q.role.value)

    def _finish(self, resp: LaboraResponse, info: RunInfo, t0: float, question: str, role: str):
        info.latency_s = time.perf_counter() - t0
        write_trace({
            "trace_id": info.trace_id, "system": self.name, "role": role, "question": question,
            "decision": info.decision,
            "candidates": [{"chunk_id": h.chunk.chunk_id, "score": round(h.score, 3)} for h in info.hits],
            "llm_calls": info.llm_calls, "prompt_tokens": info.prompt_tokens,
            "output_tokens": info.output_tokens, "latency_s": round(info.latency_s, 3),
            "response": resp.model_dump(),
        })
        return resp, info
