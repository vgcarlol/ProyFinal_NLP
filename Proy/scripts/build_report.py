"""Genera el informe técnico (Docs/Informe_Tecnico_LaboraGT.docx) con las métricas reales
leídas de Proy/eval/results (último resumen de cada sistema).

Uso: python Proy/scripts/build_report.py
"""
import csv
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Proy" / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

RES = ROOT / "Proy" / "eval" / "results"
IMG = ROOT / "Docs" / "img"
OUT = ROOT / "Docs" / "Informe_Tecnico_LaboraGT.docx"


def latest(pattern: str) -> Path:
    files = sorted(glob.glob(str(RES / pattern)))
    if not files:
        raise SystemExit(f"No hay resultados para {pattern}; ejecute benchmark.py / security_tests.py")
    return Path(files[-1])


def load_summary(prefix):
    p = latest(f"{prefix}_2*_summary.json")
    return json.loads(p.read_text()), list(csv.DictReader(open(str(p).replace("_summary.json", ".csv"))))


B, B_rows = load_summary("baseline_bm25")
A, A_rows = load_summary("laboragt_hybrid_agent")
SEC = json.loads(latest("security_agent_*_summary.json").read_text())
SEC_rows = list(csv.DictReader(open(str(latest("security_agent_*_summary.json")).replace("_summary.json", ".csv"))))
SECB = json.loads(latest("security_baseline_*_summary.json").read_text())
N_CHUNKS = sum(1 for _ in open(ROOT / "Proy" / "data" / "processed" / "chunks.jsonl"))


def f(x, pct=False, nd=2):
    if x is None or x == "":
        return "—"
    x = float(x)
    return f"{x:.0%}" if pct else f"{x:.{nd}f}"


# ------------------------------------------------------------------ gráficas
def chart_comparison():
    labels = ["Recall@5", "MRR", "Precisión\ncitas", "Abstención\ncorrecta", "Fidelidad", "Corrección\n(juez)"]
    b = [B["retrieval"]["recall@k"], B["retrieval"]["mrr"], B["answer"]["citation_precision"],
         B["answer"]["abstention_accuracy"], B["answer"].get("faithfulness"), B["answer"].get("judge_correctness")]
    a = [A["retrieval"]["recall@k"], A["retrieval"]["mrr"], A["answer"]["citation_precision"],
         A["answer"]["abstention_accuracy"], A["answer"].get("faithfulness"), A["answer"].get("judge_correctness")]
    b = [v or 0 for v in b]
    a = [v or 0 for v in a]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], b, 0.4, label="Línea base (BM25)", color="#9aa0a6")
    ax.bar([i + 0.2 for i in x], a, 0.4, label="LaboraGT (híbrido + agente)", color="#1a73e8")
    for i, (vb, va) in enumerate(zip(b, a)):
        ax.text(i - 0.2, vb + 0.02, f"{vb:.2f}", ha="center", fontsize=7)
        ax.text(i + 0.2, va + 0.02, f"{va:.2f}", ha="center", fontsize=7)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.12)
    ax.legend(fontsize=8, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(IMG / "comparacion_metricas.png", dpi=170)
    plt.close(fig)


def chart_by_category():
    cats = ["directa", "parafrasis", "identificador", "compuesta", "ambigua", "vigencia"]
    def rec(rows, c):
        v = [float(r["recall@k"]) for r in rows if r["category"] == c and r["recall@k"] not in ("", None)]
        return sum(v) / len(v) if v else 0
    fig, ax = plt.subplots(figsize=(8, 3))
    x = range(len(cats))
    ax.bar([i - 0.2 for i in x], [rec(B_rows, c) for c in cats], 0.4, label="Línea base", color="#9aa0a6")
    ax.bar([i + 0.2 for i in x], [rec(A_rows, c) for c in cats], 0.4, label="LaboraGT", color="#1a73e8")
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats, fontsize=8)
    ax.set_ylabel("Recall@5", fontsize=8)
    ax.set_ylim(0, 1.1)
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(IMG / "recall_por_categoria.png", dpi=170)
    plt.close(fig)


# ------------------------------------------------------------------ docx helpers
doc = Document()
st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(10.5)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
for s in doc.sections:
    s.top_margin = s.bottom_margin = Cm(2.2)
    s.left_margin = s.right_margin = Cm(2.3)
for lvl, size in ((1, 15), (2, 12.5), (3, 11)):
    h = doc.styles[f"Heading {lvl}"]
    h.font.name = "Calibri"
    h.font.size = Pt(size)
    h.font.color.rgb = RGBColor(0x1A, 0x3D, 0x6D)


def H(t, l=1):
    doc.add_heading(t, level=l)


def P(t, bold_prefix=None, italic=False, size=None, align=None):
    p = doc.add_paragraph()
    if bold_prefix:
        r = p.add_run(bold_prefix)
        r.bold = True
    r = p.add_run(t)
    r.italic = italic
    if size:
        r.font.size = Pt(size)
    if align:
        p.alignment = align
    p.paragraph_format.space_after = Pt(5)
    return p


VIDEO_URL = "https://youtu.be/8lSEhY-4do0"
REPO_URL = "https://github.com/vgcarlol/ProyFinal_NLP"


def link(paragraph, url, text=None, size=None):
    """Hipervínculo real (clicable) dentro de un párrafo."""
    r_id = paragraph.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                                    is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "1A73E8")
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rpr.extend([color, u])
    if size:
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), str(int(size * 2)))
        rpr.append(sz)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text or url
    run.append(t)
    h.append(run)
    paragraph._p.append(h)


def LP(label, url, size=None, align=None):
    p = doc.add_paragraph()
    r = p.add_run(label)
    r.bold = True
    if size:
        r.font.size = Pt(size)
    link(p, url, size=size)
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(3)
    return p


def BL(items, style="List Bullet"):
    for it in items:
        p = doc.add_paragraph(style=style)
        if isinstance(it, tuple):
            p.add_run(it[0]).bold = True
            p.add_run(it[1])
        else:
            p.add_run(it)
        p.paragraph_format.space_after = Pt(2)


def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexcolor)
    tcPr.append(shd)


def T(headers, rows, widths=None, size=8.5):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(size)
        shade(c, "DCE6F2")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(v))
            r.font.size = Pt(size)
    if widths:
        t.autofit = False
        tblPr = t._tbl.tblPr
        lay = OxmlElement("w:tblLayout")
        lay.set(qn("w:type"), "fixed")
        tblPr.append(lay)
        for i, w in enumerate(widths):
            t.columns[i].width = Cm(w)
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def FIG(path, caption, width=16):
    doc.add_picture(str(path), width=Cm(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    P(caption, italic=True, size=9, align=WD_ALIGN_PARAGRAPH.CENTER)


chart_comparison()
chart_by_category()

# ================================================================== PORTADA
for _ in range(5):
    doc.add_paragraph()
P("Universidad del Valle de Guatemala · CC3103 Procesamiento de Lenguaje Natural · Ciclo 2 - 2026",
  size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
t = doc.add_paragraph()
t.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t.add_run("LaboraGT")
r.bold = True
r.font.size = Pt(30)
r.font.color.rgb = RGBColor(0x1A, 0x3D, 0x6D)
P("Asistente RAG agéntico para consultas de legislación laboral guatemalteca y cálculo verificable de prestaciones",
  size=14, align=WD_ALIGN_PARAGRAPH.CENTER)
P("Informe técnico — Proyecto final", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
for _ in range(4):
    doc.add_paragraph()
P("Carlos Valladares — Carné 221164", size=12, align=WD_ALIGN_PARAGRAPH.CENTER)
P("Docente: Luis Esturbán", size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
P("Guatemala, noviembre de 2026", size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_paragraph()
LP("Video de la presentación: ", VIDEO_URL, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
LP("Repositorio: ", REPO_URL, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_page_break()

# ================================================================== 1 RESUMEN
H("1. Resumen ejecutivo")
P("LaboraGT es un sistema de Procesamiento de Lenguaje Natural que ayuda a analistas de Recursos Humanos de PYMEs "
  "guatemaltecas a responder consultas sobre el Código de Trabajo, las leyes de prestaciones (aguinaldo, Bono 14, "
  "bonificación incentivo) y los acuerdos gubernativos de salario mínimo, con citas verificables a documento, "
  "artículo, página y chunk. Combina un pipeline de ingesta reproducible con OCR, recuperación híbrida (BM25 + "
  "embeddings multilingual-e5 + fusión RRF) con reranking por cross-encoder y filtros por metadatos (rol, vigencia "
  "e identificadores exactos), generación fundamentada con un LLM local (qwen2.5-7B vía Ollama) restringida a un "
  "esquema Pydantic, y un flujo agéntico orquestado con LangGraph que enruta los cálculos a herramientas "
  "deterministas con control de acceso, límites de llamadas y confirmación humana para acciones críticas.")
P(f"Sobre un banco de {A['n_cases']} casos (20 núcleo + 7 de herramientas), la versión mejorada eleva el "
  f"Recall@5 de {f(B['retrieval']['recall@k'])} a {f(A['retrieval']['recall@k'])} y el MRR de "
  f"{f(B['retrieval']['mrr'])} a {f(A['retrieval']['mrr'])} frente a la línea base léxica; la precisión de citas "
  f"pasa de {f(B['answer']['citation_precision'])} a {f(A['answer']['citation_precision'])} y la exactitud de "
  f"abstención de {f(B['answer']['abstention_accuracy'], True)} a {f(A['answer']['abstention_accuracy'], True)}. "
  f"Los casos de herramientas se resuelven correctamente en un {f(A['tools']['tool_case_accuracy'], True)} "
  f"(línea base: {f(B['tools']['tool_case_accuracy'], True)}), y la suite adversaria bloquea "
  f"{SEC['passed']}/{SEC['total']} ataques ({f(SEC['block_rate'], True)}; línea base {SECB['passed']}/{SECB['total']}). "
  f"Todo se ejecuta localmente en una laptop Apple M4 de 16 GB, sin costo de API y sin enviar datos a terceros.")

# ================================================================== 2 PROBLEMA
H("2. Problema y alcance")
H("2.1 Situación actual y problema", 2)
P("En una PYME típica el analista de RRHH resuelve consultas laborales buscando en PDFs extensos —el Código de "
  "Trabajo tiene 431 artículos—, en portales gubernamentales o en foros no oficiales, y calcula liquidaciones en "
  "hojas de cálculo hechas a mano. La normativa está dispersa en varias leyes y en acuerdos de salario mínimo que "
  "cambian cada año y por circunscripción económica. Los chatbots generales responden de forma persuasiva pero sin "
  "citas, con artículos inexistentes o cifras desactualizadas.")
H("2.2 Costo de una respuesta incorrecta", 2)
P("Un error en una liquidación o en el salario mínimo aplicado puede derivar en reclamos ante la Inspección General "
  "de Trabajo, multas y demandas laborales; por ello el sistema prioriza la abstención sobre la respuesta dudosa, "
  "delega toda aritmética a herramientas deterministas y marca para revisión humana las indemnizaciones y liquidaciones.")
H("2.3 Pregunta principal, alcance y criterio de éxito", 2)
P("¿Qué establece la normativa laboral guatemalteca vigente sobre esta situación, en qué documento, artículo y "
  "página está respaldado y —cuando aplica— cuánto le corresponde exactamente al colaborador?", italic=True)
BL([("Incluye: ", "consultas en español sobre el Código de Trabajo, aguinaldo, Bono 14, bonificación incentivo y "
      "salarios mínimos 2024-2026; cálculo de indemnización, aguinaldo, Bono 14 y vacaciones; consulta de registros "
      "de empleados ficticios; borradores de liquidación con aprobación humana."),
    ("No incluye: ", "asesoría legal vinculante, jurisprudencia, sector público, pactos colectivos, escritura en "
     "sistemas de nómina, datos personales reales ni soporte multiidioma."),
    ("Criterio de éxito: ", "Recall@5 ≥ 0.80, MRR ≥ 0.65, precisión de citas ≥ 0.90, abstención correcta en el 100 % "
     "de los casos sin respuesta, exactitud de cálculo del 100 % y ≥ 90 % de ataques bloqueados.")])

# ================================================================== 3 USUARIOS
H("3. Perfiles de usuario")
T(["Rol", "Necesidad", "Permisos en el sistema", "Riesgo de error"],
  [["Analista de RRHH (primario)", "Consultas normativas citadas; cálculos y liquidaciones de cualquier colaborador",
    "Corpus público, interno y confidencial; todos los registros; borradores de liquidación (con confirmación)",
    "Alto: pagos incorrectos, multas"],
   ["Colaborador (secundario)", "Conocer sus derechos y estimar sus prestaciones",
    "Corpus público e interno; solo su propio registro (employee_id de sesión)", "Medio: expectativas erróneas; fuga de datos de terceros"],
   ["Administrador", "Ingesta, versionado, revisión de logs", "Corpus público e interno; sin datos personales",
    "Medio: indexar versiones obsoletas"]],
  widths=[3.2, 4.4, 5.4, 3.4])
P("El rol y el employee_id provienen siempre de la sesión autenticada; cualquier rol declarado en el texto de la "
  "pregunta se ignora y se registra como bandera en la traza.")

# ================================================================== 4 FUENTES
H("4. Caracterización de fuentes y gobernanza")
P(f"Todas las fuentes están registradas en el manifiesto Proy/data/sources.yaml con URL de origen, fecha de "
  f"descarga, versión, vigencia, nivel de acceso, reglas de limpieza y hash SHA-256 del archivo. El corpus final "
  f"genera {N_CHUNKS} chunks indexados.")
T(["Documento", "Origen", "Formato", "Versión / vigencia", "Acceso"],
  [["Código de Trabajo, Decreto 1441 (ed. oct-2024, 188 págs.)", "mintrabajo.gob.gt", "PDF texto", "2024-10", "Público"],
   ["Ley del Aguinaldo, Decreto 76-78", "mintrabajo.gob.gt", "PDF texto", "76-78", "Público"],
   ["Ley de Bonificación Anual (Bono 14), Decreto 42-92", "mintrabajo.gob.gt", "PDF texto", "42-92", "Público"],
   ["Bonificación Incentivo, Decreto 78-89 (reformado)", "Recopilación legislativa", "PDF texto", "78-89 / 37-2001", "Público"],
   ["Decreto 37-2001 (Diario de Centro América)", "congreso.gob.gt", "PDF escaneado (OCR)", "06-08-2001", "Público"],
   ["AG 307-2023, salario mínimo 2024", "mintrabajo.gob.gt", "PDF escaneado (OCR)", "2024-01-01 a 2024-12-31", "Público"],
   ["AG 264-2024, salario mínimo 2025 (boletín Crowe)", "crowe.com (secundaria)", "PDF texto", "2025-01-01 a 2025-12-31", "Público"],
   ["AG 256-2025, salario mínimo 2026", "mintrabajo.gob.gt", "PDF escaneado (OCR)", "desde 2026-01-01", "Público"],
   ["Reglamento interno — Comercial Demo (ficticio)", "Sintético (autor)", "Markdown", "2026-1", "Interno"],
   ["Política salarial — Comercial Demo (ficticio)", "Sintético (autor)", "Markdown", "2026-1", "Confidencial (RRHH)"],
   ["Boletín RRHH (ficticio, con inyección de prueba)", "Sintético (autor)", "Markdown", "2026-11", "Interno"],
   ["Registro de 50 empleados ficticios", "Sintético (semilla fija)", "SQLite", "—", "RBAC por rol"]],
  widths=[5.6, 3.0, 2.6, 3.2, 2.2], size=8)
BL([("Permiso de uso: ", "las normas son de publicación oficial y libre acceso; los documentos de la empresa y los "
     "empleados son sintéticos, por lo que no se usa información confidencial real."),
    ("Calidad de fuente: ", "el AG 264-2024 no está publicado en el portal del MINTRAB; se usa un boletín profesional "
     "que reproduce los montos y se marca como fuente secundaria en el manifiesto."),
    ("Versionado: ", "los acuerdos de salario mínimo conservan vigencia_desde / vigencia_hasta; las versiones "
     "anteriores no se borran para poder responder preguntas históricas."),
    ("Información sensible: ", "los logs enmascaran DPI, NIT, teléfonos y correos; el DPI del registro de empleados "
     "nunca se entrega completo al LLM.")])

# ================================================================== 5 ESTADO DEL ARTE
H("5. Estado del arte")
P("Retrieval-Augmented Generation (Lewis et al., 2020) combina un recuperador con un generador para responder con "
  "conocimiento externo y actualizable, reduciendo alucinaciones en dominios cerrados. La recuperación léxica BM25 "
  "(Robertson y Zaragoza, 2009) sigue siendo una línea base fuerte para identificadores exactos, mientras que los "
  "embeddings densos multilingües como E5 (Wang et al., 2024) o BGE-M3 (Chen et al., 2024) capturan paráfrasis. "
  "La fusión de rankings por Reciprocal Rank Fusion (Cormack et al., 2009) es simple y robusta para combinar ambos, "
  "y los cross-encoders (Nogueira y Cho, 2019) reordenan con mayor precisión a costa de cómputo. MMR (Carbonell y "
  "Goldstein, 1998) introduce diversidad en el contexto.")
P("En el plano agéntico, ReAct (Yao et al., 2023) alterna razonamiento y acción con herramientas; frameworks como "
  "LangGraph modelan estos flujos como grafos de estado explícitos y auditables. Para evaluación, RAGAS (Es et al., "
  "2024) popularizó métricas de fidelidad y relevancia con LLM-as-a-judge. En seguridad, la inyección indirecta "
  "(Greshake et al., 2023) y el OWASP Top 10 para aplicaciones LLM (2025) identifican la inyección de prompts, la "
  "divulgación de información sensible y la agencia excesiva como riesgos principales; LaboraGT adopta controles "
  "específicos para cada uno.")

# ================================================================== 6 ARQUITECTURA
H("6. Arquitectura detallada")
FIG(IMG / "arquitectura_ingesta.png", "Figura 1. Flujo de ingesta reproducible.", 16.5)
H("6.1 Ingesta", 2)
BL([("Carga: ", "lectura del manifiesto y verificación del hash de cada archivo."),
    ("Extracción: ", "PyMuPDF por página (bloques ordenados); si una página trae < 50 caracteres se aplica OCR con "
     "Tesseract (modelo español, 250 dpi) con caché por hash de archivo y página."),
    ("Limpieza: ", "normalización Unicode, ligaduras, guiones de fin de línea, números de página y encabezados "
     "repetidos; reglas por documento en el manifiesto (inicio en 'DECRETO NÚMERO 1441', 29 páginas biográficas "
     "excluidas de la edición conmemorativa, recorte del Decreto 36-2001 que comparte página con el 37-2001)."),
    ("Chunking: ", "un chunk por ARTÍCULO —unidad semántica y de cita de la norma—, con tolerancia a ruido de OCR y "
     "a la variante 'Artículo 9o.'; artículos largos en ventanas de 300 palabras con solapamiento de 40; documentos "
     "sin artículos agrupados por párrafos. Se conservan los artículos derogados para poder responder que lo están."),
    ("Metadatos: ", "text, source, doc_id, doc_title, page, page_end, chunk_id, article, section, version, "
     "vigencia_desde, vigencia_hasta, access_level y hash."),
    ("Cuarentena: ", "los chunks con instrucciones embebidas (inyección indirecta) no se indexan y quedan registrados."),
    ("Indexación: ", "BM25Okapi (tokenización sin tildes, stopwords y plurales) y ChromaDB persistente con "
     "multilingual-e5-base (768 dimensiones, coseno).")])
FIG(IMG / "arquitectura_consulta.png", "Figura 2. Flujo de consulta con estado, compuertas, validaciones y excepciones.", 17)
H("6.2 Consulta", 2)
P("El grafo LangGraph comparte un estado por consulta (pregunta, rol, employee_id de sesión, intención, banderas, "
  "candidatos con scores, resultado de herramienta, respuesta y métricas). Sus nodos son:")
BL([("input_guard: ", "validación Pydantic (≤ 500 caracteres) y detector de inyección en español e inglés; registra "
     "intentos de declarar un rol en el texto."),
    ("router: ", "reglas explícitas que distinguen normativa, cálculo (requiere verbo de cálculo y datos concretos), "
     "consulta de empleado y borrador de liquidación. Se eligió un router por reglas por ser determinista, auditable y "
     "sin costo de inferencia; el LLM solo extrae argumentos de herramientas."),
    ("retrieve: ", "análisis de consulta (artículos y decretos citados, año, subconsultas en preguntas compuestas), "
     "BM25 y vectorial (30 candidatos cada uno) filtrados por rol dentro del motor, fusión RRF (k = 60), candidatos "
     "fijados por metadatos ante identificadores exactos, filtro de vigencia (año pedido o vigente hoy) y reranking "
     "con BAAI/bge-reranker-v2-m3 sobre 20 candidatos, con diversidad de máximo 2 chunks por artículo."),
    ("Compuerta de abstención: ", "si el mejor score del reranker es < 0.02 el sistema se abstiene sin llamar al LLM."),
    ("generate: ", "qwen2.5-7B-instruct (temperatura 0, semilla fija) con salida JSON forzada al esquema LLMDraft "
     "(answer, cited_chunk_ids, insufficient_evidence) y un reintento si no valida."),
    ("tool_plan / tool_exec: ", "extracción de argumentos con el LLM, validación Pydantic y ejecución en el registro de "
     "herramientas; la respuesta de herramientas se redacta con una plantilla determinista (sin LLM) y cita los "
     "artículos de su base legal."),
    ("output_guard: ", "verifica que las citas existan en el contexto, que todo monto mencionado tenga respaldo en la "
     "evidencia o en el resultado de la herramienta y que no haya fuga del prompt.")])
H("6.3 Herramientas", 2)
T(["Herramienta", "Propósito", "Parámetros (validados)", "Permisos", "Controles"],
  [["calcular_prestaciones", "Indemnización, aguinaldo, Bono 14, vacaciones o liquidación", "tipo, salario (0-100 000), fechas ordenadas, motivo", "RRHH; colaborador con sus datos", "Determinista, fórmula y base legal en la salida"],
   ["consultar_empleado", "Leer salario, ingreso y puesto", "employee_id (E-000)", "RRHH: todos; colaborador: propio; admin: ninguno", "SQL parametrizado, solo lectura, DPI enmascarado"],
   ["generar_borrador_liquidacion", "Borrador de liquidación (acción crítica)", "employee_id, fecha_fin, motivo", "Solo RRHH", "Confirmación humana obligatoria; nunca envía ni registra"]],
  widths=[3.4, 3.6, 3.6, 3.2, 3.6], size=8)
P("Reglas de cálculo: indemnización = (salario × 14/12) × días/365, incorporando la proporción de aguinaldo y Bono 14 "
  "que exigen el art. 9 del Decreto 76-78 y el art. 4 del Decreto 42-92; aguinaldo y Bono 14 proporcionales a sus "
  "períodos (1-dic a 30-nov y 1-jul a 30-jun); vacaciones de 15 días hábiles por año (arts. 130 y 133). Límites "
  "globales: lista blanca, máximo 3 llamadas por consulta, timeout de 10 s y degradación controlada.")
H("6.4 Formato de salida", 2)
P("Toda respuesta cumple el contrato Pydantic LaboraResponse: answer (string), sources (lista de fuente, página, "
  "chunk_id, artículo), abstained (bool), tool_used (string o null) y needs_human_review (bool). Las fuentes se "
  "reconstruyen desde los metadatos, nunca desde el texto generado. Cada consulta deja una traza JSON con intención, "
  "filtros, candidatos y scores, herramienta, tokens, latencia y decisión final, con PII enmascarada.")

# ================================================================== 7 BANCO
H("7. Banco de pruebas")
P("El conjunto Proy/eval/dataset.jsonl contiene 27 casos con los atributos id, question, role, expected_behavior, "
  "expected_sources (grupos de alternativas aceptables), expected_pages, answerable y risk_level. Los 20 casos núcleo "
  "siguen la composición exigida: 5 directas, 3 paráfrasis, 3 identificadores exactos, 3 compuestas, 2 ambiguas, "
  "2 sin respuesta y 2 de vigencia (salario mínimo 2024 y 2025). Los 7 casos de herramientas cubren ejecución nominal "
  "(liquidación, aguinaldo y consulta del registro propio), selección errónea de herramienta, parámetros fuera de "
  "rango, confirmación humana y degradación ante indisponibilidad. Los montos esperados se verificaron a mano y "
  "están replicados en pruebas unitarias. La suite adversaria (Proy/eval/security_tests.jsonl) añade 12 casos.")

# ================================================================== 8 METRICAS
H("8. Análisis de métricas")
FIG(IMG / "comparacion_metricas.png", "Figura 3. Línea base vs. LaboraGT (casos núcleo).", 15.5)
T(["Dimensión", "Métrica", "Línea base (BM25)", "LaboraGT", "Meta"],
  [["Recuperación", "Recall@5", f(B["retrieval"]["recall@k"]), f(A["retrieval"]["recall@k"]), "≥ 0.80"],
   ["", "Hit@5", f(B["retrieval"]["hit@k"]), f(A["retrieval"]["hit@k"]), "—"],
   ["", "MRR", f(B["retrieval"]["mrr"]), f(A["retrieval"]["mrr"]), "≥ 0.65"],
   ["", "Redundancia del contexto", f(B["retrieval"]["redundancy"]), f(A["retrieval"]["redundancy"]), "baja"],
   ["Respuesta", "Precisión de citas", f(B["answer"]["citation_precision"]), f(A["answer"]["citation_precision"]), "≥ 0.90"],
   ["", "Fidelidad (LLM-as-judge)", f(B["answer"].get("faithfulness")), f(A["answer"].get("faithfulness")), "≥ 0.85"],
   ["", "Corrección (LLM-as-judge)", f(B["answer"].get("judge_correctness")), f(A["answer"].get("judge_correctness")), "—"],
   ["", "Exactitud de abstención", f(B["answer"]["abstention_accuracy"]), f(A["answer"]["abstention_accuracy"]), "—"],
   ["", "Abstención en casos sin respuesta", f(B["answer"]["abstention_on_unanswerable"]), f(A["answer"]["abstention_on_unanswerable"]), "1.00"],
   ["", "Tasa de falsas abstenciones", f(B["answer"]["false_abstention_rate"]), f(A["answer"]["false_abstention_rate"]), "≤ 0.10"],
   ["Herramientas", "Selección correcta de herramienta", f(B["tools"]["tool_selection_accuracy"]), f(A["tools"]["tool_selection_accuracy"]), "—"],
   ["", "Casos de herramienta resueltos", f(B["tools"]["tool_case_accuracy"]), f(A["tools"]["tool_case_accuracy"]), "1.00"],
   ["Operación", "Latencia media (s)", f(B["operation"]["latency_mean_s"]), f(A["operation"]["latency_mean_s"]), "—"],
   ["", "Latencia P95 (s)", f(B["operation"]["latency_p95_s"]), f(A["operation"]["latency_p95_s"]), "≤ 15"],
   ["", "Llamadas al LLM (total)", B["operation"]["llm_calls_total"], A["operation"]["llm_calls_total"], "—"],
   ["", "Tokens de entrada / salida (media)", f"{f(B['operation']['prompt_tokens_mean'], nd=0)} / {f(B['operation']['output_tokens_mean'], nd=0)}",
    f"{f(A['operation']['prompt_tokens_mean'], nd=0)} / {f(A['operation']['output_tokens_mean'], nd=0)}", "—"],
   ["", "Costo de API", "$0.00", "$0.00", "$0"],
   ["Seguridad", "Ataques bloqueados", f"{SECB['passed']}/{SECB['total']}", f"{SEC['passed']}/{SEC['total']}", "≥ 90 %"]],
  widths=[2.6, 5.0, 3.0, 3.0, 2.2])
FIG(IMG / "recall_por_categoria.png", "Figura 4. Recall@5 por categoría de pregunta.", 14.5)
A3 = json.loads(latest("laboragt_hybrid_agent__qwen25-3b-instruct_2*_summary.json").read_text())
P("Ablación del modelo generador (misma recuperación y herramientas; corrida sin juez para no mezclar modelos en GPU):",
  bold_prefix="Tabla 3. ")
T(["Métrica", "qwen2.5-7B (elegido)", "qwen2.5-3B"],
  [["Latencia media / P95 (s)", f"{f(A['operation']['latency_mean_s'])} / {f(A['operation']['latency_p95_s'])}",
    f"{f(A3['operation']['latency_mean_s'])} / {f(A3['operation']['latency_p95_s'])}"],
   ["Exactitud de abstención", f(A["answer"]["abstention_accuracy"], True), f(A3["answer"]["abstention_accuracy"], True)],
   ["Falsas abstenciones", f(A["answer"]["false_abstention_rate"], True), f(A3["answer"]["false_abstention_rate"], True)],
   ["Precisión de citas", f(A["answer"]["citation_precision"]), f(A3["answer"]["citation_precision"])],
   ["Casos de herramienta", f(A["tools"]["tool_case_accuracy"], True), f(A3["tools"]["tool_case_accuracy"], True)]],
  widths=[5.5, 4.5, 4.5])
P("Nota: el Recall@5 puede variar ±0.05 entre corridas por no determinismo numérico del cross-encoder en GPU (MPS) "
  "en casos con scores muy cercanos; las métricas de respuesta usan temperatura 0 y semilla fija.", italic=True, size=9)
from report_analysis import ANALYSIS_PARAGRAPHS, FAILURE_ROWS, CONCLUSIONS, LATENCY_NOTE

# ---------- análisis por caso (generado desde los CSV) ----------
H("8.1 Discusión de resultados", 2)
for par in ANALYSIS_PARAGRAPHS:
    P(par)
H("8.2 Autopsia de fallas", 2)
T(["Caso", "Falla observada", "Causa raíz", "Acción / estado"], FAILURE_ROWS, widths=[1.3, 5.2, 4.6, 5.3], size=8)

# ================================================================== 9 SEGURIDAD
H("9. Auditoría de seguridad")
P(f"La suite adversaria ejecuta {SEC['total']} pruebas sobre los vectores exigidos (inyección directa e indirecta, "
  f"evasión de permisos, acciones críticas, alucinación forzada) más inyección SQL y exfiltración de reglas. "
  f"LaboraGT supera {SEC['passed']}/{SEC['total']} ({f(SEC['block_rate'], True)}); la línea base, sin guardrails ni "
  f"herramientas, supera {SECB['passed']}/{SECB['total']}. Detalle por prueba en "
  f"Proy/eval/results/security_agent_*.md.")
T(["ID", "Vector / amenaza", "Componente", "Esperado", "Observado", "Mitigación", "Res."],
  [[r["id"], f"{r['vector']}: {r['amenaza']}", r["componente"], r["esperado"],
    r["observado"][:95] + ("…" if len(r["observado"]) > 95 else ""), r["mitigacion"], r["resultado"]] for r in SEC_rows],
  widths=[0.9, 3.1, 2.1, 2.5, 3.3, 3.5, 1.2], size=7)
BL([("Defensa en profundidad: ", "ningún control es único: la inyección indirecta se detiene en la ingesta (cuarentena), "
     "pero el prompt además delimita el contexto como datos y el guardrail de salida detecta fugas."),
    ("Permisos fuera del LLM: ", "el filtro de acceso se aplica dentro de BM25 y ChromaDB y en cada herramienta, por lo que "
     "un prompt manipulado no puede hacer que el modelo vea lo que el rol no permite."),
    ("Acciones críticas: ", "el registro de herramientas exige confirmed=True para el borrador de liquidación y verifica el "
     "rol RRHH de forma independiente; la herramienta nunca escribe en sistemas externos."),
    ("Logs: ", "cada traza enmascara DPI, NIT, correos y teléfonos; los registros de empleados se entregan al LLM sin DPI completo.")])

# ================================================================== 10 LIMITACIONES
H("10. Limitaciones operativas")
BL([("Latencia: ", f"el LLM local de 7B en un M4 tarda ~8-15 s por generación; la P95 medida es "
     f"{f(A['operation']['latency_p95_s'])} s. " + LATENCY_NOTE),
    ("Detector de inyección por patrones: ", "es transparente y sin costo, pero puede evadirse con paráfrasis creativas u "
     "otros idiomas; se mitiga con controles estructurales (permisos fuera del LLM, citas verificadas)."),
    ("Juez LLM: ", "la fidelidad la evalúa el mismo modelo base que genera (sesgo de autoevaluación); se complementó con "
     "la revisión manual de los casos discrepantes (sección 8.2); se recomienda ampliar la revisión manual a una muestra aleatoria."),
    ("Tamaño del banco: ", "27 casos + 12 adversarios permiten comparar sistemas, pero el umbral de abstención (0.02) se "
     "calibró con un margen estrecho y podría requerir recalibración con más datos."),
    ("Fuentes: ", "el salario mínimo 2025 proviene de un boletín secundario; el texto del Decreto 37-2001 y los acuerdos "
     "2024/2026 dependen de OCR (con errores menores como 'Q.' leído como '0.')."),
    ("Alcance jurídico: ", "el cálculo asume año de 365 días, salario diario = mensual/30 y base de indemnización con 1/12 "
     "de aguinaldo y de Bono 14; no cubre salarios variables, horas extra ni jurisprudencia.")])

# ================================================================== 11 FUTURO
H("11. Trabajo futuro")
BL(["Reducir latencia con un modelo más pequeño o cuantización agresiva para la generación, manteniendo el de 7B solo "
    "para casos de alto riesgo (enrutamiento por costo).",
    "Sustituir el detector de inyección por patrones por un clasificador entrenado y añadir pruebas de red teaming automatizadas.",
    "Ampliar el corpus (reglamentos del IGSS, acuerdos de feriados, jurisprudencia de la Corte de Constitucionalidad) y el banco de pruebas a 100+ casos con anotación de dos revisores.",
    "Detectar automáticamente nuevas publicaciones de salario mínimo en el portal del MINTRAB y versionarlas.",
    "Memoria de conversación acotada y aclaraciones interactivas para preguntas ambiguas (p. ej. actividad y circunscripción)."])

# ================================================================== 12 CONCLUSIONES
H("12. Conclusiones")
for par in CONCLUSIONS:
    P(par)

# ================================================================== 13 BIBLIOGRAFIA
H("13. Bibliografía")
for ref in [
    "Carbonell, J., y Goldstein, J. (1998). The use of MMR, diversity-based reranking for reordering documents and producing summaries. SIGIR.",
    "Chen, J., et al. (2024). BGE M3-Embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings. arXiv:2402.03216.",
    "Congreso de la República de Guatemala. Código de Trabajo, Decreto 1441 (edición MINTRAB, 2024).",
    "Congreso de la República de Guatemala. Decreto 76-78, Ley Reguladora de la Prestación del Aguinaldo para los Trabajadores del Sector Privado.",
    "Congreso de la República de Guatemala. Decreto 42-92, Ley de Bonificación Anual para Trabajadores del Sector Privado y Público.",
    "Congreso de la República de Guatemala. Decreto 78-89 y Decreto 37-2001, Bonificación Incentivo.",
    "Cormack, G., Clarke, C., y Büttcher, S. (2009). Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. SIGIR.",
    "Crowe Guatemala (2024). Salarios mínimos para las actividades económicas 2025 — Acuerdo Gubernativo 264-2024.",
    "Es, S., James, J., Espinosa-Anke, L., y Schockaert, S. (2024). RAGAS: Automated evaluation of retrieval augmented generation. EACL.",
    "Greshake, K., et al. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. AISec.",
    "Lewis, P., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. NeurIPS.",
    "Ministerio de Trabajo y Previsión Social. Acuerdos Gubernativos 307-2023 y 256-2025 (salarios mínimos 2024 y 2026).",
    "Nogueira, R., y Cho, K. (2019). Passage re-ranking with BERT. arXiv:1901.04085.",
    "OWASP Foundation (2025). OWASP Top 10 for Large Language Model Applications.",
    "Qwen Team (2024). Qwen2.5 technical report. arXiv:2412.15115.",
    "Robertson, S., y Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. Foundations and Trends in IR.",
    "Smith, R. (2007). An overview of the Tesseract OCR engine. ICDAR.",
    "Wang, L., et al. (2024). Multilingual E5 text embeddings: A technical report. arXiv:2402.05672.",
    "Yao, S., et al. (2023). ReAct: Synergizing reasoning and acting in language models. ICLR.",
    "Documentación técnica: Ollama, LangGraph, ChromaDB, Sentence-Transformers, PyMuPDF, Pydantic, Streamlit.",
]:
    p = doc.add_paragraph(ref, style="List Bullet")
    p.paragraph_format.space_after = Pt(1)
    for r in p.runs:
        r.font.size = Pt(9)

H("Anexo A. Uso de herramientas de IA", 2)
P("Se utilizaron herramientas de IA generativa como apoyo puntual en la revisión de redacción y en la consulta de "
  "documentación técnica de bibliotecas. El detalle de su uso se declara conforme a la sección 15 de las reglas del curso.",
  italic=True)
H("Anexo B. Reproducibilidad", 2)
LP("Repositorio de código: ", REPO_URL)
LP("Video de presentación y demostración: ", VIDEO_URL)
BL(["Repositorio: README.md con instalación, ingesta, demo, benchmark y pruebas (pytest).",
    "Dependencias fijadas en Proy/requirements.txt; configuración en Proy/.env.example sin credenciales.",
    "Benchmark con fecha de referencia fija (TODAY=2026-11-19), temperatura 0 y semilla 42.",
    "Resultados por caso en Proy/eval/results/*.csv y resúmenes en *_summary.json; este informe se regenera con "
    "Proy/scripts/build_report.py a partir de ellos."])
P("Ejecución de la demo (con los índices ya construidos):", bold_prefix=None)
for line in ["ollama serve                                   # terminal 1, dejar abierta",
             "source .venv/bin/activate                      # terminal 2, en la raíz del repositorio",
             "streamlit run Proy/app/streamlit_app.py        # abre http://localhost:8501",
             "python Proy/scripts/ingest.py                  # solo si se borraron los índices",
             "python Proy/scripts/benchmark.py --system agent --judge",
             "python Proy/scripts/security_tests.py --system agent"]:
    cp = doc.add_paragraph()
    cr = cp.add_run(line)
    cr.font.name = "Courier New"
    cr.font.size = Pt(8)
    cp.paragraph_format.space_after = Pt(0)
    cp.paragraph_format.left_indent = Cm(0.5)

doc.save(OUT)
print("Informe:", OUT)
