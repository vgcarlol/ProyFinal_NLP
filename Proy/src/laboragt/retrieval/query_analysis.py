"""Análisis de la consulta: identificadores exactos, vigencia temporal y descomposición.

Se usa para (1) fijar candidatos por metadatos cuando el usuario cita un artículo o decreto,
(2) filtrar por vigencia documental y (3) partir preguntas compuestas en subconsultas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .bm25 import strip_accents

# Decretos/acuerdos del corpus -> doc_id
DECREE_TO_DOC = {
    "1441": "codigo_trabajo", "76-78": "ley_aguinaldo", "42-92": "ley_bono14",
    "78-89": "bonificacion_incentivo", "37-2001": "bonificacion_incentivo_37_2001",
    "307-2023": "salario_minimo_2024", "264-2024": "salario_minimo_2025", "256-2025": "salario_minimo_2026",
}
DOC_ALIASES = [
    (r"codigo de trabajo", "codigo_trabajo"),
    (r"\bley (reguladora )?del aguinaldo\b", "ley_aguinaldo"),
    (r"\bley (de )?bonificacion anual\b|\bbono 14\b", "ley_bono14"),
    (r"reglamento (interno|interior)", "reglamento_interno_demo"),
    (r"politica salarial", "politica_salarial_demo"),
]

ARTICLE_REF_RX = re.compile(r"\bart(?:iculo|\.)?\s*(\d{1,3})(?:\s*(bis|ter))?\b")
DECREE_REF_RX = re.compile(r"\b(?:decreto|acuerdo(?: gubernativo)?|ag)\s*(?:numero|no\.?|n\.?)?\s*(\d{1,4}(?:-\d{2,4})?)")
YEAR_RX = re.compile(r"\b(20[12]\d)\b")
SPLIT_RX = re.compile(r"\s+y\s+(?=(?:cuanto|cuanta|cuantos|cuantas|cuando|cual|cuales|que|como|en que|donde|quien)\b)")

# El salario mínimo es el único tema con versiones anuales en el corpus
VERSIONED_TOPIC_RX = re.compile(r"salario(s)? minimo")


@dataclass
class QueryAnalysis:
    normalized: str
    articles: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)
    year: int | None = None
    versioned_topic: bool = False
    subqueries: list[str] = field(default_factory=list)


def analyze(question: str) -> QueryAnalysis:
    n = strip_accents(question.lower())
    qa = QueryAnalysis(normalized=n)
    for m in ARTICLE_REF_RX.finditer(n):
        art = m.group(1) + (f" {m.group(2).upper()}" if m.group(2) else "")
        qa.articles.append(art)
    for m in DECREE_REF_RX.finditer(n):
        d = DECREE_TO_DOC.get(m.group(1))
        if d:
            qa.doc_ids.append(d)
    for rx, d in DOC_ALIASES:
        if re.search(rx, n):
            qa.doc_ids.append(d)
    if m := YEAR_RX.search(n):
        qa.year = int(m.group(1))
    qa.versioned_topic = bool(VERSIONED_TOPIC_RX.search(n))
    parts = [p.strip(" ?¿,.") for p in SPLIT_RX.split(n) if p.strip(" ?¿,.")]
    qa.subqueries = parts if len(parts) > 1 else []
    qa.doc_ids = list(dict.fromkeys(qa.doc_ids))
    return qa


def in_force(vigencia_desde: str | None, vigencia_hasta: str | None, year: int | None,
             today: date | None = None) -> bool:
    """¿El documento aplica al año pedido (o a hoy si no se pidió año)?"""
    if not vigencia_desde and not vigencia_hasta:
        return True  # normas sin vigencia anual (leyes) siempre aplican
    today = today or date.today()
    if year is not None:
        start = int(vigencia_desde[:4]) if vigencia_desde else 0
        end = int(vigencia_hasta[:4]) if vigencia_hasta else 9999
        return start <= year <= end
    d_from = date.fromisoformat(vigencia_desde) if vigencia_desde else date.min
    d_to = date.fromisoformat(vigencia_hasta) if vigencia_hasta else date.max
    return d_from <= today <= d_to
