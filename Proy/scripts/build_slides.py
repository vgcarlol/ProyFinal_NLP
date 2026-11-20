"""Genera la presentación de la defensa (Docs/Presentacion_LaboraGT.pptx) con métricas reales.

Uso: python Proy/scripts/build_slides.py   (requiere haber corrido benchmark y security_tests)
"""
import csv
import glob
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "Proy" / "eval" / "results"
IMG = ROOT / "Docs" / "img"
OUT = ROOT / "Docs" / "Presentacion_LaboraGT.pptx"

NAVY = RGBColor(0x1A, 0x3D, 0x6D)
BLUE = RGBColor(0x1A, 0x73, 0xE8)
GRAY = RGBColor(0x5F, 0x63, 0x68)
LIGHT = RGBColor(0xF1, 0xF3, 0xF4)
GREEN = RGBColor(0x13, 0x73, 0x33)
RED = RGBColor(0xC5, 0x22, 0x1F)


def latest(pattern):
    return Path(sorted(glob.glob(str(RES / pattern)))[-1])


def summ(prefix):
    return json.loads(latest(f"{prefix}_2*_summary.json").read_text())


B, A = summ("baseline_bm25"), summ("laboragt_hybrid_agent")
SEC = json.loads(latest("security_agent_*_summary.json").read_text())
SECB = json.loads(latest("security_baseline_*_summary.json").read_text())
SEC_rows = list(csv.DictReader(open(str(latest("security_agent_*_summary.json")).replace("_summary.json", ".csv"))))


def f(x, pct=False):
    if x is None:
        return "—"
    return f"{x:.0%}" if pct else f"{x:.2f}"


prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def text(slide, x, y, w, h, s, size=18, bold=False, color=GRAY, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    lines = s if isinstance(s, list) else [s]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = "Calibri"
        p.space_after = Pt(6)
    return tb


def header(slide, kicker, title, minutes=None):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.12))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    text(slide, 0.6, 0.35, 9, 0.4, kicker.upper(), 12, True, BLUE)
    text(slide, 0.6, 0.7, 12, 0.8, title, 30, True, NAVY)
    if minutes:
        text(slide, 11.3, 0.35, 1.6, 0.4, minutes, 12, True, GRAY, PP_ALIGN.RIGHT)


def card(slide, x, y, w, h, title, body, color=NAVY, size=14):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    box.fill.solid()
    box.fill.fore_color.rgb = LIGHT
    box.line.color.rgb = RGBColor(0xDA, 0xDC, 0xE0)
    box.adjustments[0] = 0.06
    text(slide, x + 0.2, y + 0.12, w - 0.4, 0.5, title, 16, True, color)
    text(slide, x + 0.2, y + 0.62, w - 0.4, h - 0.7, body, size, False, GRAY)


def code(slide, x, y, w, h, lines, size=13):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0x20, 0x21, 0x24)
    box.line.fill.background()
    box.adjustments[0] = 0.04
    tb = slide.shapes.add_textbox(Inches(x + 0.2), Inches(y + 0.12), Inches(w - 0.4), Inches(h - 0.24))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.name = "Menlo"
        r.font.color.rgb = RGBColor(0x8A, 0xB4, 0xF8) if line.startswith("#") else RGBColor(0xE8, 0xEA, 0xED)
        p.space_after = Pt(3)


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def metric(slide, x, y, label, before, after, goal):
    card(slide, x, y, 2.9, 1.7, label, [], NAVY)
    text(slide, x + 0.2, y + 0.55, 2.6, 0.7, after, 32, True, BLUE)
    text(slide, x + 0.2, y + 1.2, 2.6, 0.4, f"línea base {before} · meta {goal}", 11, False, GRAY)


def table(slide, x, y, w, rows, col_w, size=11):
    shp = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(0.35 * len(rows)))
    t = shp.table
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            c = t.cell(i, j)
            c.text = str(v)
            p = c.text_frame.paragraphs[0]
            p.runs[0].font.size = Pt(size)
            p.runs[0].font.bold = i == 0
            p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF) if i == 0 else GRAY
            c.fill.solid()
            c.fill.fore_color.rgb = NAVY if i == 0 else (LIGHT if i % 2 else RGBColor(0xFF, 0xFF, 0xFF))


# 1. Portada
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
bg.fill.solid()
bg.fill.fore_color.rgb = NAVY
bg.line.fill.background()
text(s, 0.8, 1.6, 11, 0.5, "CC3103 · PROCESAMIENTO DE LENGUAJE NATURAL · UVG 2026", 14, True, RGBColor(0x8A, 0xB4, 0xF8))
text(s, 0.8, 2.2, 11, 1.2, "LaboraGT", 60, True, RGBColor(0xFF, 0xFF, 0xFF))
text(s, 0.8, 3.4, 11, 1.2, "Asistente RAG agéntico para consultas de legislación laboral guatemalteca y cálculo "
     "verificable de prestaciones", 24, False, RGBColor(0xE8, 0xEA, 0xED))
text(s, 0.8, 5.6, 11, 0.9, ["Carlos Valladares · 221164", "Docente: Luis Esturbán"], 16, False, RGBColor(0xE8, 0xEA, 0xED))

# 2. Problema, usuario e hipótesis (2 min)
s = prs.slides.add_slide(BLANK)
header(s, "Bloque 1 · Problema, usuario e hipótesis", "RRHH en PYMEs responde sin base legal citada", "2 min")
card(s, 0.6, 1.8, 4.0, 4.6, "Usuario", ["Analista de RRHH de una PYME guatemalteca, sin abogado laboral de planta.",
     "Secundario: colaborador (solo sus datos)."])
card(s, 4.75, 1.8, 4.0, 4.6, "Problema", ["431 artículos del Código + leyes de prestaciones + salario mínimo que cambia "
     "cada año.", "Liquidaciones en Excel hechas a mano.", "Chatbots: persuasivos, sin citas, cifras viejas."])
card(s, 8.9, 1.8, 3.9, 4.6, "Hipótesis", ["Recuperación híbrida + citas por artículo + herramientas deterministas "
     "superan a un RAG léxico y nunca inventan montos.", "Costo de error: multas, demandas → abstención y revisión humana."])

# 3. Arquitectura (3 min)
s = prs.slides.add_slide(BLANK)
header(s, "Bloque 2 · Arquitectura y flujo de datos", "Flujo con estado, compuertas y validaciones", "3 min")
pic = s.shapes.add_picture(str(IMG / "arquitectura_consulta.png"), Inches(0.5), Inches(1.5), height=Inches(5.85))
pic.left = int((prs.slide_width - pic.width) / 2)

s = prs.slides.add_slide(BLANK)
header(s, "Bloque 2 · Arquitectura y flujo de datos", "Ingesta reproducible y decisiones técnicas", "")
s.shapes.add_picture(str(IMG / "arquitectura_ingesta.png"), Inches(0.5), Inches(1.5), width=Inches(12.3))
card(s, 0.6, 4.3, 4.0, 2.8, "¿Por qué por artículo?", ["El artículo es la unidad de sentido y de cita de la norma.",
     "431/431 artículos del Código recuperables, incluidos los derogados."], size=13)
card(s, 4.75, 4.3, 4.0, 2.8, "¿Por qué híbrido + reranker?", ["BM25 falla en paráfrasis; e5 falla en '82'.",
     "RRF + fijación por metadatos + bge-reranker (score calibrable para abstención)."], size=13)
card(s, 8.9, 4.3, 3.9, 2.8, "¿Por qué herramientas?", ["Los LLM se equivocan en aritmética de fechas y montos.",
     "Cálculo determinista con fórmula y base legal citada."], size=13)

# 4a. Cómo levantar el proyecto (para el video)
s = prs.slides.add_slide(BLANK)
header(s, "Bloque 3 · Demostración en vivo", "Cómo levantar el proyecto", "")
text(s, 0.6, 1.55, 6, 0.4, "Terminal 1 · servidor del LLM", 15, True, NAVY)
code(s, 0.6, 1.95, 6.0, 1.55, ["# deja esta terminal abierta", "ollama serve", "",
     "# (otra pestaña) verificar modelo", "ollama list   # qwen2.5:7b-instruct"])
text(s, 0.6, 3.7, 6, 0.4, "Terminal 2 · interfaz de demo", 15, True, NAVY)
code(s, 0.6, 4.1, 6.0, 1.5, ["cd ~/Documents/GitHub/ProyFinal_NLP", "source .venv/bin/activate",
     "streamlit run Proy/app/streamlit_app.py", "# abre http://localhost:8501"])
text(s, 0.6, 5.8, 6, 0.4, "Terminal 3 (opcional) · trazabilidad en vivo", 15, True, NAVY)
code(s, 0.6, 6.2, 6.0, 0.75, ["tail -f Proy/logs/trace.jsonl"])
card(s, 6.9, 1.55, 5.9, 3.0, "En la app", [
     "1. Primera consulta de calentamiento (~30 s: carga e5, reranker y LLM).",
     "2. Barra lateral → «Escenarios de demo» → elegir escenario.",
     "3. Ajustar Rol (colaborador / rrhh) e ID de empleado si aplica.",
     "4. Expandir fuentes y traza para mostrar citas y scores."], size=13)
card(s, 6.9, 4.7, 5.9, 2.25, "Plan B (si falla la interfaz)", [
     "python Proy/scripts/ask.py \"¿Qué dice el artículo 82?\" --debug",
     "Los índices ya están construidos; solo si se borran: python Proy/scripts/ingest.py"], size=12)
notes(s, "Para grabar el video: abrir tres terminales. En la primera correr ollama serve y dejarla abierta. "
         "En la segunda activar el entorno virtual y lanzar Streamlit; el navegador abre localhost:8501. "
         "Hacer una consulta de calentamiento antes de empezar a grabar porque la primera tarda unos 30 segundos. "
         "La tercera terminal con tail -f del log sirve para mostrar la trazabilidad con PII enmascarada.")

# 4. Demo (4 min)
s = prs.slides.add_slide(BLANK)
header(s, "Bloque 3 · Demostración en vivo", "Guion de la demo (http://localhost:8501)", "4 min")
table(s, 0.6, 1.7, 12.1, [
    ["#", "Escenario (barra lateral)", "Qué mostrar"],
    ["01", "Consulta nominal: vacaciones", "Respuesta + cita art. 130, pág. 68; abrir «Fragmento recuperado»"],
    ["02", "Identificador exacto: artículo 82", "Ranking: art. 82 en 1.º lugar por fijación de metadatos"],
    ["04", "Abstención: jubilación IGSS", "Ruta se detiene en retrieve; score < 0.02; 0 llamadas al LLM"],
    ["05", "Cálculo de liquidación", "Tabla con fórmula y base legal; total Q34,413.23; revisión humana"],
    ["07", "Acción crítica", "Pide confirmación → activar «Confirmar acción crítica» → Consultar"],
    ["09", "Inyección de instrucciones", "Bloqueada en input_guard (nodo en rojo)"],
    ["10", "Documento confidencial", "La política salarial ni aparece en candidatos: filtro por rol"],
    ["12", "Diagnóstico: falla real P02", "Scores ≈ 0.02 (al borde del umbral), mezcla de fuentes"],
], [0.5, 4.0, 7.6], 13)

# 5. Evaluación (3 min)
s = prs.slides.add_slide(BLANK)
header(s, "Bloque 4 · Evaluación y métricas", f"Línea base vs. LaboraGT ({A['n_cases']} casos)", "3 min")
metric(s, 0.6, 1.7, "Recall@5", f(B["retrieval"]["recall@k"]), f(A["retrieval"]["recall@k"]), "≥ 0.80")
metric(s, 3.7, 1.7, "MRR", f(B["retrieval"]["mrr"]), f(A["retrieval"]["mrr"]), "≥ 0.65")
metric(s, 6.8, 1.7, "Precisión de citas", f(B["answer"]["citation_precision"]), f(A["answer"]["citation_precision"]), "≥ 0.90")
metric(s, 9.9, 1.7, "Casos de herramienta", f(B["tools"]["tool_case_accuracy"], True), f(A["tools"]["tool_case_accuracy"], True), "100%")
s.shapes.add_picture(str(IMG / "comparacion_metricas.png"), Inches(0.6), Inches(3.6), height=Inches(3.6))
card(s, 8.9, 3.6, 3.9, 3.6, "Operación", [f"Latencia P95: {f(A['operation']['latency_p95_s'])} s "
     f"(línea base {f(B['operation']['latency_p95_s'])} s)", f"Abstención correcta: {f(A['answer']['abstention_accuracy'], True)}",
     f"Fidelidad (juez): {f(A['answer'].get('faithfulness'))}", "Costo de API: $0 (todo local)"], size=13)

s = prs.slides.add_slide(BLANK)
header(s, "Bloque 4 · Evaluación y métricas", "Autopsia de fallas: de la línea base a la mejora", "")
table(s, 0.6, 1.7, 12.1, [
    ["Falla observada (línea base)", "Causa raíz", "Mejora implementada"],
    ["'¿Qué dice el artículo 82?' no recupera el art. 82", "BM25: '82' aparece en cientos de chunks", "Detección de identificador + fijación por metadatos"],
    ["'días de descanso pagado' → art. 127 (descanso semanal)", "Paráfrasis sin solapamiento léxico", "Embeddings e5 + reranker"],
    ["'¿Cuánto es el salario mínimo?' → responde con 2025", "Sin noción de vigencia", "Filtro de vigencia (vigente hoy por defecto)"],
    ["Pregunta por jubilación IGSS respondida con art. 82", "Score BM25 no separa casos sin respuesta", "Umbral sobre score calibrado del reranker"],
    ["Pregunta compuesta responde solo una parte", "Un solo ranking para dos necesidades", "Subconsultas + cobertura garantizada"],
], [4.4, 3.6, 4.1], 12)

# 6. Seguridad (2 min)
s = prs.slides.add_slide(BLANK)
header(s, "Bloque 5 · Seguridad, guardrails y limitaciones", f"{SEC['passed']}/{SEC['total']} ataques mitigados "
       f"(línea base {SECB['passed']}/{SECB['total']})", "2 min")
rows = [["Vector", "Amenaza", "Resultado"]] + [[r["vector"], r["amenaza"][:58], r["resultado"]] for r in SEC_rows]
table(s, 0.6, 1.6, 8.2, rows, [2.0, 5.0, 1.2], 10)
card(s, 9.0, 1.6, 3.8, 5.6, "Limitaciones", [f"LLM local de 7B: P95 {f(A['operation']['latency_p95_s'])} s (meta 15 s no cumplida; 3B es más rápido pero se abstiene de más).",
     "Detector de inyección por patrones: evadible con paráfrasis creativas.",
     "Juez LLM = mismo modelo (sesgo); se complementa con revisión manual.",
     "Salario mínimo 2025 de fuente secundaria.", "Banco de 27 casos: umbral calibrado con margen estrecho."], size=12)

# 7. Cierre (1 min)
s = prs.slides.add_slide(BLANK)
header(s, "Bloque 6 · Conclusiones y cierre", "Lo que demuestra LaboraGT", "1 min")
text(s, 0.8, 1.8, 11.8, 4.5, [
    "✔ Problema claro y usuario definido, con costo de error explícito.",
    "✔ Datos autorizados y versionados (manifiesto con hash, vigencia y nivel de acceso).",
    f"✔ Recuperación híbrida que supera metas: Recall@5 {f(A['retrieval']['recall@k'])}, MRR {f(A['retrieval']['mrr'])}.",
    "✔ Herramientas necesarias (no decorativas): cálculo exacto, RBAC y confirmación humana.",
    f"✔ Seguridad verificable: {SEC['passed']}/{SEC['total']} pruebas adversarias superadas.",
    "→ Trabajo futuro: modelo más rápido o cuantización agresiva, detector de inyección entrenado, más casos de prueba.",
], 20, False, NAVY)

# Notas del orador (guion del video)
SPEAKER = {
    0: "Presentarse: Carlos Valladares, 221164. LaboraGT es un asistente RAG agéntico que responde dudas de legislación "
       "laboral guatemalteca citando artículo y página, y calcula prestaciones con código determinista. Todo corre local.",
    1: "El usuario es el analista de RRHH de una PYME sin abogado de planta. El problema: normativa dispersa, salario mínimo "
       "que cambia cada año y liquidaciones a mano. Un error cuesta multas o demandas, por eso el sistema debe citar, "
       "abstenerse cuando no sabe y nunca inventar montos. Hipótesis: híbrido + citas + herramientas supera a un RAG léxico.",
    2: "Recorrer el flujo: input_guard filtra inyección; el router por reglas decide si es consulta normativa, cálculo, "
       "consulta de empleado o liquidación. La rama normativa recupera, reordena y genera JSON validado con Pydantic; "
       "la rama de herramientas ejecuta código determinista con permisos. Al final output_guard verifica citas y montos.",
    3: "La ingesta: PDFs oficiales con OCR en español, limpieza por reglas del manifiesto, chunking por artículo y "
       "cuarentena de documentos con inyección. Explicar las tres decisiones: artículo como unidad de cita, híbrido por "
       "las fallas complementarias de BM25 y embeddings, y herramientas porque el LLM falla en aritmética de fechas.",
    5: "Seguir la tabla en orden con los escenarios precargados. Lo clave en cada uno: mostrar la cita expandida, el score "
       "del reranker y la decisión en la traza. En el escenario 6 marcar la casilla de confirmación para generar el borrador.",
    6: "Comparar línea base y LaboraGT sobre los mismos 27 casos. Recall@5 y MRR superan la meta; herramientas 100 %. "
       "Ser honesto: precisión de citas, fidelidad y latencia P95 no llegan a la meta, y explicar por qué (ver informe).",
    7: "Cada mejora responde a una falla medida de la línea base: identificadores, paráfrasis, vigencia, abstención y "
       "preguntas compuestas. Mencionar las fallas que siguen abiertas: P02 (aguinaldo vs. Bono 14) y A02 (ambigua).",
    8: "Doce pruebas adversarias: inyección directa e indirecta, evasión de permisos, SQL, acciones críticas y alucinación "
       "forzada. Los controles importantes son estructurales: el rol viene de la sesión, el filtro de acceso está en el "
       "motor y la acción crítica pide confirmación humana. Cerrar con las limitaciones.",
    9: "Resumir: problema claro, datos versionados, recuperación que supera metas, herramientas necesarias y seguridad "
       "verificable. Trabajo futuro: modelo más rápido, detector de inyección entrenado y más casos. Agradecer.",
}
for i, n in SPEAKER.items():
    notes(prs.slides[i], n)

# Anexo. Instalación desde cero
s = prs.slides.add_slide(BLANK)
header(s, "Anexo", "Instalación desde cero (macOS / Apple Silicon)", "")
code(s, 0.6, 1.6, 6.0, 5.4, [
    "# 1. Dependencias del sistema", "brew install ollama tesseract poppler", "ollama serve &",
    "ollama pull qwen2.5:7b-instruct", "",
    "# 2. Modelo OCR en español", "mkdir -p Proy/tessdata", "curl -L -o Proy/tessdata/spa.traineddata \\",
    "  https://github.com/tesseract-ocr/\\", "  tessdata_fast/raw/main/spa.traineddata", "",
    "# 3. Entorno Python", "uv venv --python 3.12 .venv", "uv pip install --python .venv/bin/python \\",
    "  -r Proy/requirements.txt"], 12)
code(s, 6.8, 1.6, 6.0, 5.4, [
    "# 4. Ingesta (OCR + índices + base sintética)", ".venv/bin/python Proy/scripts/ingest.py", "",
    "# 5. Demo", ".venv/bin/streamlit run Proy/app/streamlit_app.py", "",
    "# 6. Evaluación", ".venv/bin/python Proy/scripts/benchmark.py \\", "  --system agent --judge",
    ".venv/bin/python Proy/scripts/security_tests.py \\", "  --system agent",
    ".venv/bin/python -m pytest Proy/tests -q", "",
    "# Embeddings y reranker se bajan de", "# Hugging Face la primera vez (~3 GB)"], 12)
notes(s, "Diapositiva de respaldo: instalación completa desde un equipo limpio. Igual que el README.")

prs.save(OUT)
print("Presentación:", OUT)
