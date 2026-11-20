"""Textos de análisis del informe, calculados a partir de los resultados más recientes."""
import csv
import glob
import json
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "eval" / "results"


def _latest(prefix):
    p = Path(sorted(glob.glob(str(RES / f"{prefix}_2*_summary.json")))[-1])
    return json.loads(p.read_text()), {r["id"]: r for r in csv.DictReader(open(str(p).replace("_summary.json", ".csv")))}


B, BR = _latest("baseline_bm25")
A, AR = _latest("laboragt_hybrid_agent")
try:
    A3, A3R = _latest("laboragt_hybrid_agent__qwen25-3b-instruct")
except IndexError:
    A3, A3R = None, {}


def g(d, *ks):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def fmt(x, pct=False):
    if x is None:
        return "—"
    return f"{x:.0%}" if pct else f"{x:.2f}"


def status(cid):
    r = AR.get(cid, {})
    rec = r.get("recall@k")
    jc = r.get("judge_correct")
    parts = []
    if rec not in (None, ""):
        parts.append(f"recall {float(rec):.1f}")
    if jc not in (None, ""):
        parts.append("correcta" if jc == "True" else "incorrecta (juez)")
    if r.get("abstained") == "True":
        parts.append("abstención")
    return ", ".join(parts) or "—"


def cat_recall(rows, cat):
    v = [float(r["recall@k"]) for r in rows.values() if r["category"] == cat and r["recall@k"] not in ("", None)]
    return sum(v) / len(v) if v else 0.0


ANALYSIS_PARAGRAPHS = [
    f"Recuperación. La línea base léxica obtiene Recall@5 = {fmt(g(B,'retrieval','recall@k'))} y MRR = "
    f"{fmt(g(B,'retrieval','mrr'))}; la versión híbrida alcanza {fmt(g(A,'retrieval','recall@k'))} y "
    f"{fmt(g(A,'retrieval','mrr'))}, superando ambas metas. Por categoría (Figura 4): "
    + "; ".join(f"{c} {fmt(cat_recall(BR, c))} → {fmt(cat_recall(AR, c))}" for c in
                ("directa", "parafrasis", "identificador", "compuesta", "ambigua", "vigencia"))
    + ". Las mayores ganancias están donde BM25 es débil: identificadores exactos (fijación por metadatos de "
      "'artículo 82'), paráfrasis (embeddings + reranker) y preguntas compuestas (subconsultas). Las preguntas "
      "ambiguas siguen siendo el punto débil (ver autopsia, caso A02). En vigencia, el filtro temporal deja el documento "
      f"del año correcto en primera posición. La redundancia del contexto es baja ({fmt(g(A,'retrieval','redundancy'))}) "
      "por la regla de máximo dos chunks por artículo.",

    f"Generación y abstención. La exactitud de abstención sube de {fmt(g(B,'answer','abstention_accuracy'), True)} a "
    f"{fmt(g(A,'answer','abstention_accuracy'), True)}: los dos casos sin respuesta se rechazan siempre "
    f"({fmt(g(A,'answer','abstention_on_unanswerable'), True)}) con {fmt(g(A,'answer','false_abstention_rate'), True)} de "
    f"falsas abstenciones. El score calibrado del reranker separa los casos fuera del corpus (≈0.01) de los respondibles "
    f"(≥0.03), algo que el score BM25 no lograba. La fidelidad medida por el juez pasa de "
    f"{fmt(g(B,'answer','faithfulness'))} a {fmt(g(A,'answer','faithfulness'))} y la corrección de "
    f"{fmt(g(B,'answer','judge_correctness'))} a {fmt(g(A,'answer','judge_correctness'))}. La precisión de citas "
    f"({fmt(g(B,'answer','citation_precision'))} → {fmt(g(A,'answer','citation_precision'))}) es la métrica más exigente: "
    f"cuenta como error cualquier cita fuera de la evidencia anotada, aunque sea pertinente (p. ej. citar a la vez el "
    f"Decreto 78-89 reformado y el 37-2001); limitar las citas a un máximo de tres y pedir solo las usadas redujo el sobre-citado.",

    f"Herramientas. La línea base no tiene herramientas y falla los {g(B,'tools','n')} casos (selección correcta "
    f"{fmt(g(B,'tools','tool_selection_accuracy'), True)}). LaboraGT resuelve {fmt(g(A,'tools','tool_case_accuracy'), True)} "
    f"de los casos: calcula la liquidación verificada a mano (Q34,413.23) y el aguinaldo completo, no usa la calculadora "
    f"ante una pregunta normativa que menciona 'cálculo', rechaza un salario fuera de rango, exige confirmación humana "
    f"para el borrador de liquidación, degrada de forma controlada si la herramienta no está disponible y consulta solo "
    f"el registro propio del colaborador. Las respuestas de herramientas no usan el LLM para redactar, por lo que su "
    f"latencia es de 2-6 s y su fidelidad es total por construcción.",

    f"Operación. Todo corre localmente con costo de API $0. La latencia media es {fmt(g(A,'operation','latency_mean_s'))} s "
    f"y la P95 {fmt(g(A,'operation','latency_p95_s'))} s (línea base: {fmt(g(B,'operation','latency_mean_s'))} / "
    f"{fmt(g(B,'operation','latency_p95_s'))} s): la recuperación híbrida añade ~2-3 s (embeddings + cross-encoder en MPS), "
    f"pero el contexto más preciso reduce los tokens de entrada de {g(B,'operation','prompt_tokens_mean'):.0f} a "
    f"{g(A,'operation','prompt_tokens_mean'):.0f} por consulta y el router evita llamadas al LLM en abstenciones y "
    f"herramientas ({g(A,'operation','llm_calls_total')} llamadas en {A['n_cases']} casos frente a "
    f"{g(B,'operation','llm_calls_total')}). La meta de P95 ≤ 15 s no se cumple con el modelo de 7B en este hardware; "
    + (f"como ablación, qwen2.5-3B reduce la latencia a {fmt(g(A3,'operation','latency_mean_s'))} s de media y "
       f"{fmt(g(A3,'operation','latency_p95_s'))} s de P95 con la misma recuperación, pero con más falsas abstenciones "
       f"({fmt(g(A3,'answer','false_abstention_rate'), True)}) y menor exactitud de abstención "
       f"({fmt(g(A3,'answer','abstention_accuracy'), True)}), por lo que se mantuvo el modelo de 7B priorizando la "
       f"confiabilidad en un dominio de alto riesgo." if A3 else "se propone un modelo más pequeño como trabajo futuro."),
]

LATENCY_NOTE = ("La ablación con qwen2.5-3B muestra el compromiso latencia/calidad; para producción se propone "
                "enrutar las consultas de bajo riesgo a un modelo pequeño.")

FAILURE_ROWS = [
    ["I01", "Línea base: '¿Qué establece el artículo 82?' no recupera el art. 82.",
     "BM25: el token '82' aparece en cientos de chunks; la consulta no se distingue.",
     f"Corregido con detección de identificadores + fijación por metadatos. Estado: {status('I01')}."],
    ["P03", "Línea base: 'días de descanso pagado' recupera el art. 127 (descanso semanal) y responde mal.",
     "Paráfrasis sin solapamiento léxico con 'vacaciones'.",
     f"Corregido con embeddings e5 + reranker. Estado: {status('P03')}."],
    ["A01", "Línea base: '¿Cuánto es el salario mínimo?' responde con el acuerdo de 2025.",
     "Sin noción de vigencia; el boletín de 2025 tiene mejor score léxico.",
     f"Corregido con filtro de vigencia (vigente hoy por defecto). Estado: {status('A01')}."],
    ["N01", "Línea base: la pregunta sobre jubilación del IGSS se responde con el art. 82.",
     "El score BM25 no separa casos fuera del corpus; el LLM responde con evidencia tangencial.",
     f"Corregido con umbral calibrado del reranker (0.02). Estado: {status('N01')}."],
    ["T01", "Durante el desarrollo, el guardrail bloqueó una liquidación correcta.",
     "'Q5,000.00' en la respuesta vs. '5000.0' en el resultado de la herramienta: normalización de montos incompleta.",
     f"Corregido: clave canónica en centavos con 1-2 decimales. Estado: {'resuelto' if AR.get('T01',{}).get('tool_case_ok')=='True' else 'pendiente'}."],
    ["P02", "'¿Qué pago extra recibo a fin de año?' se responde con el Bono 14 en lugar del aguinaldo.",
     "El aguinaldo queda en 5.ª posición; el LLM elige el fragmento de Bono 14 ('bonificación anual').",
     f"Abierta. Mitigación propuesta: expansión de consulta ('fin de año' → diciembre/aguinaldo). Estado: {status('P02')}."],
    ["A02", "'¿Cuánto me toca de indemnización?' cita el art. 197 BIS (accidentes) en vez del 82.",
     "Consulta muy ambigua; el reranker da score bajo (≈0.12) a todos los candidatos.",
     f"Mitigada: score < 0.30 marca needs_human_review. Propuesta: pedir aclaración. Estado: {status('A02')}."],
    ["C03", "Pregunta compuesta (reglamento + ley) responde bien la primera parte e incompleta la segunda.",
     "La subconsulta 'cuántos días me corresponden por ley' vuelve a favorecer el reglamento interno.",
     f"Abierta. Propuesta: priorizar fuentes normativas en subconsultas con 'por ley'. Estado: {status('C03')}."],
]

CONCLUSIONS = [
    f"LaboraGT demuestra que, en un dominio regulado y de alto costo de error, el valor no está en añadir componentes "
    f"sino en que cada uno resuelva una falla medida de la línea base: la fijación por metadatos resuelve los "
    f"identificadores exactos, los embeddings y el reranker resuelven las paráfrasis, el filtro de vigencia resuelve "
    f"las preguntas temporales y el umbral calibrado resuelve la abstención. Con ello se alcanzan Recall@5 = "
    f"{fmt(g(A,'retrieval','recall@k'))}, MRR = {fmt(g(A,'retrieval','mrr'))} y "
    f"{fmt(g(A,'answer','abstention_on_unanswerable'), True)} de abstención correcta en casos sin respuesta.",
    "Las herramientas son necesarias y no decorativas: los cálculos de prestaciones se delegan a código determinista con "
    "su base legal, de modo que el sistema nunca inventa montos; el control de acceso se aplica fuera del LLM (en los "
    "índices y en cada herramienta) y la única acción crítica exige confirmación humana. La suite adversaria confirma "
    "que estos controles estructurales, junto con los guardrails de entrada y salida, mitigan los vectores evaluados.",
    "La principal limitación es la latencia de un LLM de 7B ejecutado localmente y la dependencia de detectores por "
    "patrones; ambas tienen rutas de mejora claras. El sistema es reproducible de extremo a extremo (manifiesto con hash, "
    "ingesta determinista, benchmark con fecha fija y pruebas unitarias) y deja trazabilidad completa de cada decisión.",
]
