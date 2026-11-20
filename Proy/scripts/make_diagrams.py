"""Genera los diagramas de arquitectura (PNG) para el informe y la presentación.

Uso: python Proy/scripts/make_diagrams.py  ->  Docs/img/arquitectura_consulta.png, arquitectura_ingesta.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parents[2] / "Docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)

C = {"io": "#E8EEF7", "guard": "#FCE8E6", "core": "#E6F4EA", "tool": "#FEF7E0", "store": "#F1E8FD", "gate": "#FFFFFF"}


def box(ax, x, y, w, h, text, color, fs=8.5, bold=False, style="round,pad=0.02,rounding_size=0.08"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style, fc=color, ec="#3c4043", lw=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, wrap=True,
            fontweight="bold" if bold else "normal")


def arrow(ax, x1, y1, x2, y2, label="", color="#3c4043", ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=11, color=color,
                                 lw=1.1, linestyle=ls))
    if label:
        ax.text((x1 + x2) / 2 + 0.05, (y1 + y2) / 2 + 0.06, label, fontsize=7, color=color, ha="center")


def query_flow():
    fig, ax = plt.subplots(figsize=(14, 8.2))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8.2)
    ax.axis("off")
    ax.text(7, 7.95, "LaboraGT — Flujo de consulta (orquestado con LangGraph, estado compartido por consulta)",
            ha="center", fontsize=12, fontweight="bold")

    box(ax, 0.2, 6.6, 1.9, 0.9, "Usuario\n(pregunta + rol y\nemployee_id de sesión)", C["io"], fs=8)
    box(ax, 2.5, 6.6, 2.0, 0.9, "Validación Pydantic\n(longitud ≤ 500,\nformato)", C["guard"])
    box(ax, 4.9, 6.6, 2.2, 0.9, "Guardrail de entrada\ninyección (es/en), rol\ndeclarado, caracteres", C["guard"])
    box(ax, 7.5, 6.6, 2.2, 0.9, "Router de intención\n(reglas auditables)", C["gate"], bold=True,
        style="round,pad=0.02,rounding_size=0.3")
    arrow(ax, 2.1, 7.05, 2.5, 7.05)
    arrow(ax, 4.5, 7.05, 4.9, 7.05)
    arrow(ax, 7.1, 7.05, 7.5, 7.05)
    box(ax, 10.3, 6.6, 3.4, 0.9, "Respuesta bloqueada\n(abstained=true, needs_human_review)", C["guard"], fs=8)
    ax.annotate("", xy=(10.3, 7.3), xytext=(6.0, 7.5), arrowprops=dict(arrowstyle="-|>", color="#c5221f",
                                                                     connectionstyle="arc3,rad=-0.25"))
    ax.text(8.3, 7.72, "bloqueo", fontsize=7, color="#c5221f")

    # rama RAG
    ax.text(3.3, 6.15, "intención = normativa", fontsize=8, color="#137333", ha="center")
    box(ax, 0.2, 4.7, 2.1, 1.1, "Análisis de consulta\nartículo/decreto citado,\naño, subconsultas", C["core"])
    box(ax, 2.6, 4.7, 2.3, 1.1, "Recuperación híbrida\nBM25 (30) + e5 (30)\nfusión RRF k=60", C["core"])
    box(ax, 5.2, 4.7, 2.2, 1.1, "Control de acceso\nfiltro access_level\npor rol (en el motor)", C["guard"])
    box(ax, 7.7, 4.7, 2.2, 1.1, "Filtro de vigencia\n+ fijados por metadatos\n+ reranker bge-m3", C["core"])
    box(ax, 10.2, 4.7, 1.6, 1.1, "¿score ≥ 0.02?", C["gate"], bold=True, style="round,pad=0.02,rounding_size=0.3")
    box(ax, 12.1, 4.7, 1.7, 1.1, "Abstención\n(sin evidencia)", C["guard"])
    arrow(ax, 8.6, 6.6, 1.25, 5.8, color="#137333")
    for x1, x2 in ((2.3, 2.6), (4.9, 5.2), (7.4, 7.7), (9.9, 10.2)):
        arrow(ax, x1, 5.25, x2, 5.25)
    arrow(ax, 11.8, 5.25, 12.1, 5.25, "no", color="#c5221f")

    box(ax, 7.7, 3.0, 2.6, 1.2, "Generación fundamentada\nqwen2.5-7B (Ollama)\nsalida JSON (LLMDraft)", C["core"], bold=True)
    arrow(ax, 11.0, 4.7, 9.6, 4.2, "sí", color="#137333")

    # rama herramientas
    ax.text(10.9, 6.25, "cálculo / empleado / liquidación", fontsize=8, color="#b06000", ha="center")
    box(ax, 0.2, 2.9, 2.2, 1.2, "Extracción de argumentos\n(LLM -> ToolArgs)\nvalidación Pydantic", C["tool"])
    box(ax, 2.7, 2.9, 2.3, 1.2, "Registro de herramientas\nlista blanca · RBAC ·\n≤3 llamadas · timeout 10 s", C["tool"], bold=True)
    box(ax, 5.3, 2.9, 2.1, 1.2, "¿Acción crítica?\n-> requiere\nconfirmación humana", C["gate"], bold=True,
        style="round,pad=0.02,rounding_size=0.3")
    ax.annotate("", xy=(1.3, 4.1), xytext=(9.4, 6.6), arrowprops=dict(arrowstyle="-|>", color="#b06000",
                                                                    connectionstyle="arc3,rad=0.15"))
    arrow(ax, 2.4, 3.5, 2.7, 3.5)
    arrow(ax, 5.0, 3.5, 5.3, 3.5)
    box(ax, 0.2, 1.2, 2.3, 1.1, "calcular_prestaciones\n(determinista, art. 82,\nDto. 76-78, 42-92, CT 130)", C["tool"], fs=8)
    box(ax, 2.8, 1.2, 2.2, 1.1, "consultar_empleado\nSQLite solo lectura,\nSQL parametrizado", C["tool"], fs=8)
    box(ax, 5.3, 1.2, 2.3, 1.1, "generar_borrador_\nliquidacion (solo RRHH,\nsolo borrador)", C["tool"], fs=8)
    for x in (1.35, 3.9, 6.45):
        arrow(ax, 3.85, 2.9, x, 2.3, color="#b06000")
    box(ax, 7.9, 1.2, 2.4, 1.1, "Evidencia: resultado\n+ artículos de base legal\n(citas por metadatos)", C["core"], fs=8)
    arrow(ax, 7.6, 1.75, 7.9, 1.75)

    box(ax, 10.7, 2.3, 3.1, 1.3, "Guardrail de salida\nesquema · citas ∈ contexto ·\nmontos con respaldo ·\nfuga de prompt", C["guard"], bold=True)
    arrow(ax, 10.3, 3.6, 10.7, 3.2)
    arrow(ax, 10.3, 1.75, 10.7, 2.5)
    box(ax, 10.7, 0.25, 3.1, 1.4, "Respuesta contractual\n{answer, sources[], abstained,\ntool_used, needs_human_review}\n+ traza JSON (PII enmascarada)",
        C["io"], bold=True, fs=8)
    arrow(ax, 12.25, 2.3, 12.25, 1.65)

    box(ax, 0.2, 0.15, 7.4, 0.75, "Excepciones controladas: entrada inválida · LLM no disponible · salida no válida (1 reintento) ·\n"
        "permiso denegado · parámetros fuera de rango · herramienta no disponible (degradación) · límite de llamadas",
        "#F8F9FA", fs=7.5)
    fig.savefig(OUT / "arquitectura_consulta.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def ingest_flow():
    fig, ax = plt.subplots(figsize=(14, 2.9))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 2.9)
    ax.axis("off")
    ax.text(7, 2.65, "LaboraGT — Flujo de ingesta reproducible (scripts/ingest.py)", ha="center", fontsize=12,
            fontweight="bold")
    steps = [("Fuentes + manifiesto\nsources.yaml\n(URL, versión, sha256)", C["store"]),
             ("Extracción\nPyMuPDF por página\nOCR Tesseract (spa)", C["core"]),
             ("Limpieza\nruido, guiones, págs.\nexcluidas, marcadores", C["core"]),
             ("Chunking por\nARTÍCULO (ventanas\n300/40 si es largo)", C["core"]),
             ("Metadatos\nsource, page, chunk_id,\nversión, vigencia, acceso", C["core"]),
             ("Cuarentena\ninyección indirecta\n(chunks con órdenes)", C["guard"]),
             ("Índices\nBM25 (pickle) +\nChromaDB (e5, coseno)", C["store"])]
    w, gap = 1.75, 0.22
    for i, (t, col) in enumerate(steps):
        x = 0.15 + i * (w + gap)
        box(ax, x, 0.7, w, 1.4, t, col, fs=8)
        if i:
            arrow(ax, x - gap, 1.4, x, 1.4)
    ax.text(7, 0.3, "Resultado actual: 11 documentos -> 597 chunks indexados (1 en cuarentena) · OCR cacheado · "
            "base sintética de 50 empleados (SQLite)", ha="center", fontsize=8.5)
    fig.savefig(OUT / "arquitectura_ingesta.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    query_flow()
    ingest_flow()
    print("Diagramas en", OUT)
