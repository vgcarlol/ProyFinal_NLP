"""Sistema mejorado (Fase 3): flujo con estado orquestado con LangGraph.

  usuario -> input_guard -> router -> {retrieve | tool_plan -> tool_exec} -> evidencia
          -> generate (LLM para normativa / plantilla determinista para herramientas)
          -> output_guard -> respuesta JSON + traza

Cada nodo puede desviar a 'finalize' con una abstención o un error controlado.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from . import config
from .baseline import ABSTAIN_LLM_DOWN, ABSTAIN_NO_EVIDENCE, RunInfo
from .guardrails import input_guard, leaks_system_prompt, unsupported_amounts
from .llm import LLMError, chat_structured
from .prompts import SYSTEM_GROUNDED, build_user_prompt, resolve_citations
from .retrieval.bm25 import BM25Index, Hit
from .retrieval.hybrid import HybridRetriever, today
from .router import Intent, classify, extract_tool_args
from .schemas import LaboraResponse, LLMDraft, Query, SourceRef, UserRole
from .tools.registry import ToolContext, ToolOutcome, run_tool
from .trace import new_trace_id, write_trace

BLOCKED_MSG = ("No puedo procesar esta solicitud porque contiene instrucciones que intentan modificar mi "
               "comportamiento o acceder a información protegida. Reformule su consulta sobre legislación laboral.")
CONFIRM_MSG = ("Generar un borrador de liquidación es una acción crítica. Para continuar, un analista de RRHH debe "
               "confirmar explícitamente la solicitud (botón 'Confirmar' o parámetro confirmed=True).")


class State(TypedDict, total=False):
    question: str
    role: UserRole
    employee_id: str | None
    confirmed: bool
    simulate_unavailable: set[str]
    intent: Intent
    flags: list[str]
    hits: list[Hit]
    tool: ToolOutcome | None
    tool_args: dict
    response: LaboraResponse
    info: RunInfo
    decision: str


def _sources_from_chunks(chunks) -> list[SourceRef]:
    return [SourceRef(source=c.source, page=c.page, chunk_id=c.chunk_id, article=c.article,
                      doc_title=c.doc_title) for c in chunks]


class LaboraAgent:
    name = "laboragt_hybrid_agent"

    def __init__(self, retriever: HybridRetriever | None = None, top_k: int = config.TOP_K,
                 min_rerank: float = config.RERANK_MIN_SCORE):
        self.retriever = retriever or HybridRetriever()
        self.top_k = top_k
        self.min_rerank = min_rerank
        self.by_art = {(c.doc_id, c.article): c for c in reversed(self.retriever.bm25.chunks)}
        self.graph = self._build()

    # ------------------------------------------------------------------ nodos
    def n_input_guard(self, s: State) -> State:
        g = input_guard(s["question"])
        s["flags"] = g.flags
        if not g.allowed:
            s["decision"] = "bloqueado_input_guard"
            s["response"] = LaboraResponse(answer=BLOCKED_MSG, abstained=True, needs_human_review=True)
        return s

    def n_router(self, s: State) -> State:
        s["intent"] = classify(s["question"])
        return s

    def n_retrieve(self, s: State) -> State:
        t = time.perf_counter()
        s["hits"] = self.retriever.search(s["question"], s["role"], k=self.top_k)
        s["info"].retrieval_s = time.perf_counter() - t
        s["info"].hits = s["hits"]
        if not s["hits"] or s["hits"][0].score < self.min_rerank:
            s["decision"] = "abstencion_umbral_reranker"
            s["response"] = LaboraResponse(answer=ABSTAIN_NO_EVIDENCE, abstained=True)
        return s

    def n_generate(self, s: State) -> State:
        try:
            res = chat_structured(SYSTEM_GROUNDED, build_user_prompt(s["question"], s["hits"]), LLMDraft)
        except LLMError:
            s["decision"] = "llm_no_disponible"
            s["response"] = LaboraResponse(answer=ABSTAIN_LLM_DOWN, abstained=True, needs_human_review=True)
            return s
        info = s["info"]
        info.llm_calls += 1
        info.prompt_tokens += res.prompt_tokens
        info.output_tokens += res.output_tokens
        draft: LLMDraft | None = res.parsed  # type: ignore[assignment]
        if draft is None:
            s["decision"] = "salida_invalida"
            s["response"] = LaboraResponse(answer=ABSTAIN_NO_EVIDENCE, abstained=True, needs_human_review=True)
            return s
        by_id = {h.chunk.chunk_id: h.chunk for h in s["hits"]}
        draft.answer, valid = resolve_citations(draft.answer, draft.cited_chunk_ids, set(by_id))
        if draft.insufficient_evidence or not valid:
            s["decision"] = "abstencion_llm" if draft.insufficient_evidence else "sin_citas_validas"
            s["response"] = LaboraResponse(answer=ABSTAIN_NO_EVIDENCE, abstained=True)
            return s
        s["decision"] = "respuesta"
        s["response"] = LaboraResponse(answer=draft.answer, sources=_sources_from_chunks([by_id[c] for c in valid]),
                                       abstained=False,
                                       needs_human_review=(len(valid) < len(draft.cited_chunk_ids)
                                                           or s["hits"][0].score < config.LOW_CONFIDENCE_SCORE))
        if s["hits"][0].score < config.LOW_CONFIDENCE_SCORE:
            s["flags"] = s.get("flags", []) + ["baja_confianza_recuperacion"]
        return s

    def n_tool_plan(self, s: State) -> State:
        args: dict[str, Any] = {}
        if s["intent"] in (Intent.CALCULO, Intent.LIQUIDACION) or not _emp_id(s["question"]):
            parsed, pt, ot = extract_tool_args(s["question"], today())
            s["info"].llm_calls += 1
            s["info"].prompt_tokens += pt
            s["info"].output_tokens += ot
            if parsed:
                args = {k: v for k, v in parsed.model_dump().items() if v not in (None, "")}
                args.pop("employee_id", None)  # solo se acepta si aparece literalmente en el texto
        if eid := _emp_id(s["question"]):
            args["employee_id"] = eid
        elif s["intent"] != Intent.CALCULO and s.get("employee_id"):
            args.setdefault("employee_id", s["employee_id"])  # "mi salario" -> registro propio de la sesión
        elif s["intent"] == Intent.CALCULO and "mi registro" in s["question"].lower() and s.get("employee_id"):
            args["employee_id"] = s["employee_id"]
        s["tool_args"] = args
        return s

    def n_tool_exec(self, s: State) -> State:
        ctx = ToolContext(role=s["role"], session_employee_id=s.get("employee_id"),
                          confirmed=s.get("confirmed", False),
                          simulate_unavailable=s.get("simulate_unavailable") or set())
        intent, args = s["intent"], s["tool_args"]
        if intent == Intent.EMPLEADO:
            out = run_tool("consultar_empleado", {"employee_id": args.get("employee_id", "")}, ctx)
        elif intent == Intent.LIQUIDACION:
            out = run_tool("generar_borrador_liquidacion",
                           {k: args[k] for k in ("employee_id", "fecha_fin", "motivo") if k in args}
                           | ({"fecha_fin": today().isoformat()} if "fecha_fin" not in args else {}), ctx)
        else:
            args.setdefault("tipo", "liquidacion")
            out = run_tool("calcular_prestaciones", args, ctx)
        s["tool"] = out
        s["response"] = self._tool_response(out, s)
        s["decision"] = "herramienta_ok" if out.ok else f"herramienta_{out.error_type}"
        return s

    def n_output_guard(self, s: State) -> State:
        r = s["response"]
        if r.abstained:
            return s
        if leaks_system_prompt(r.answer):
            s["decision"] = "bloqueado_fuga_prompt"
            s["response"] = LaboraResponse(answer=ABSTAIN_NO_EVIDENCE, abstained=True, needs_human_review=True)
            return s
        evidence = [h.chunk.text for h in s.get("hits", [])]
        if s.get("tool") and s["tool"].ok:
            evidence.append(str(s["tool"].data))
        bad = unsupported_amounts(r.answer, evidence)
        if bad:
            s["decision"] = "bloqueado_montos_sin_respaldo"
            s["flags"] = s.get("flags", []) + [f"monto_sin_respaldo:{b}" for b in bad]
            s["response"] = LaboraResponse(
                answer=ABSTAIN_NO_EVIDENCE + " (Se detectaron cifras sin respaldo documental.)",
                abstained=True, needs_human_review=True)
        return s

    # ------------------------------------------------------------- respuestas
    def _legal_sources(self, refs) -> list[SourceRef]:
        chunks = [self.by_art[(d, a)] for d, a in refs if (d, a) in self.by_art]
        return _sources_from_chunks(chunks)

    def _tool_response(self, out: ToolOutcome, s: State) -> LaboraResponse:
        if out.needs_confirmation:
            return LaboraResponse(answer=CONFIRM_MSG, abstained=True, tool_used=out.tool, needs_human_review=True)
        if not out.ok:
            msgs = {
                "permiso": f"Acceso denegado: {out.error}",
                "validacion": f"No pude ejecutar el cálculo. {out.error}. Verifique los datos ingresados.",
                "no_encontrado": f"{out.error}.",
                "no_disponible": (f"La herramienta '{out.tool}' no está disponible en este momento ({out.error}). "
                                  "Puedo responder consultas normativas, pero el cálculo deberá hacerse más tarde o "
                                  "manualmente por RRHH."),
                "limite": out.error,
            }
            return LaboraResponse(answer=msgs.get(out.error_type, out.error or "Error de herramienta."),
                                  abstained=True, tool_used=out.tool,
                                  needs_human_review=out.error_type in ("no_disponible", "permiso"))
        if out.tool == "consultar_empleado":
            d = out.data
            ans = (f"Registro de {d['nombre']} ({d['employee_id']}): puesto {d['puesto']}, fecha de ingreso "
                   f"{d['fecha_ingreso']}, salario base {d['salario_base']} mensuales, circunscripción "
                   f"{d['circunscripcion']}.")
            return LaboraResponse(answer=ans, abstained=False, tool_used=out.tool)
        result = out.data["result"]
        lines = [f"- {c['concepto']}: Q{float(c['monto']):,.2f} = {c['formula']} [{c['base_legal']}]"
                 for c in result["conceptos"]]
        head = "BORRADOR de liquidación (no enviado ni registrado). " if out.tool == "generar_borrador_liquidacion" else ""
        inp = out.data.get("input", {})
        ctx_line = ""
        uses_motive = inp.get("tipo") in ("indemnizacion", "liquidacion")
        if inp:
            ctx_line = (f"Datos usados: tipo {inp['tipo']}, salario Q{float(inp['salario_mensual']):,.2f}, del "
                        f"{inp['fecha_inicio']} al {inp['fecha_fin']}"
                        + (f", motivo {inp['motivo']}" if uses_motive else "") + ". ")
        ans = (f"{head}{ctx_line}Resultado del cálculo determinista:\n" + "\n".join(lines) +
               f"\nTotal: Q{float(result['total']):,.2f}. Supuestos: " + " ".join(result["supuestos"]) +
               " Este cálculo es referencial y debe ser revisado por RRHH antes de cualquier pago.")
        if not result["conceptos"]:
            ans = "Con los datos indicados no corresponde ninguna prestación calculable. " + " ".join(result["supuestos"])
        # indemnizaciones y liquidaciones por despido son de alto riesgo -> revisión humana obligatoria
        high_risk = (uses_motive and inp.get("motivo") == "despido_injustificado") \
            or out.tool == "generar_borrador_liquidacion"
        return LaboraResponse(answer=ans, sources=self._legal_sources(result["base_legal_refs"]), abstained=False,
                              tool_used=out.tool, needs_human_review=high_risk)

    # ------------------------------------------------------------------ grafo
    def _build(self):
        g = StateGraph(State)
        for name in ("input_guard", "router", "retrieve", "generate", "tool_plan", "tool_exec", "output_guard"):
            g.add_node(name, getattr(self, f"n_{name}"))
        g.set_entry_point("input_guard")
        g.add_conditional_edges("input_guard", lambda s: "end" if "response" in s else "router",
                                {"end": END, "router": "router"})
        g.add_conditional_edges("router", lambda s: "rag" if s["intent"] == Intent.NORMATIVA else "tool",
                                {"rag": "retrieve", "tool": "tool_plan"})
        g.add_conditional_edges("retrieve", lambda s: "end" if "response" in s else "gen",
                                {"end": END, "gen": "generate"})
        g.add_edge("generate", "output_guard")
        g.add_edge("tool_plan", "tool_exec")
        g.add_edge("tool_exec", "output_guard")
        g.add_edge("output_guard", END)
        return g.compile()

    # -------------------------------------------------------------------- API
    def answer(self, question: str, role: UserRole | str = UserRole.COLABORADOR, employee_id: str | None = None,
               confirmed: bool = False, simulate_unavailable: set[str] | None = None):
        info = RunInfo(trace_id=new_trace_id())
        t0 = time.perf_counter()
        try:
            q = Query(question=question, role=role)
        except ValidationError as e:
            info.decision = "entrada_invalida"
            resp = LaboraResponse(answer=f"La consulta no es válida: {e.errors()[0]['msg']}", abstained=True)
            return self._finish(resp, info, t0, question, str(role), {}, [])
        state: State = {"question": q.question, "role": q.role, "employee_id": employee_id, "confirmed": confirmed,
                        "simulate_unavailable": simulate_unavailable or set(), "info": info, "flags": []}
        out = self.graph.invoke(state)
        info.decision = out.get("decision", "")
        info.hits = out.get("hits", [])
        tool = out.get("tool")
        return self._finish(out["response"], info, t0, q.question, q.role.value,
                            {"intent": out.get("intent").value if out.get("intent") else None,
                             "tool": tool.tool if tool else None, "tool_ok": tool.ok if tool else None,
                             "tool_error": tool.error if tool else None, "tool_args": out.get("tool_args")},
                            out.get("flags", []))

    def _finish(self, resp, info, t0, question, role, extra, flags):
        info.latency_s = time.perf_counter() - t0
        write_trace({"trace_id": info.trace_id, "system": self.name, "role": role, "question": question,
                     "decision": info.decision, "flags": flags, **extra,
                     "candidates": [{"chunk_id": h.chunk.chunk_id, "score": round(h.score, 4)} for h in info.hits],
                     "llm_calls": info.llm_calls, "prompt_tokens": info.prompt_tokens,
                     "output_tokens": info.output_tokens, "latency_s": round(info.latency_s, 3),
                     "response": resp.model_dump()})
        return resp, info


def _emp_id(text: str) -> str | None:
    import re

    m = re.search(r"\bE-\d{3}\b", text, re.IGNORECASE)
    return m.group(0).upper() if m else None
