"""Router de intención + extracción de argumentos de herramientas.

La intención se decide con reglas explícitas y auditables (deterministas, sin costo de LLM).
Solo cuando la ruta requiere una herramienta se usa el LLM para extraer argumentos
estructurados, que luego se validan con Pydantic antes de ejecutar nada.
"""
from __future__ import annotations

import re
from datetime import date
from enum import Enum

from pydantic import BaseModel

from .llm import chat_structured
from .retrieval.bm25 import strip_accents


class Intent(str, Enum):
    NORMATIVA = "normativa"            # pregunta sobre la ley o documentos -> RAG
    CALCULO = "calculo"                # cálculo de prestaciones con datos concretos -> calculadora
    EMPLEADO = "consulta_empleado"     # datos de un registro de empleado -> SQL
    LIQUIDACION = "borrador_liquidacion"  # acción crítica -> requiere confirmación humana


EMP_ID_RX = re.compile(r"\bE-\d{3}\b", re.IGNORECASE)
CALC_VERB_RX = re.compile(r"\b(calcul\w*|cuanto (me|le|te) (toca|corresponde|deben|tocaria|corresponderia)|"
                          r"a cuanto asciende|monto de (mi|su|la) (indemnizacion|liquidacion|aguinaldo|bono)|"
                          r"cuanto (seria|es) (mi|su|la) (indemnizacion|liquidacion))")
CALC_DATA_RX = re.compile(r"(q\.?\s?\d[\d,.]*|\d{3,}[\d,.]*\s*(quetzales|mensuales|al mes)|salario de|gano|ganaba|"
                          r"desde (el )?\d|ingrese|ingreso el|del \d{1,2} de|\b(19|20)\d{2}\b.*\b(19|20)\d{2}\b|"
                          r"mi registro|mis datos|e-\d{3})")
LIQ_ACTION_RX = re.compile(r"\b(genera|generar|elabora|elaborar|prepara|preparar|emite|emitir|registra|registrar|haz|hacer|crea|crear)\b"
                           r".{0,40}\b(liquidacion|finiquito)")
EMP_QUERY_RX = re.compile(r"\b(cual|cuanto) es (mi|su) (salario|sueldo|fecha de ingreso|puesto)\b|"
                          r"\b(mi|su) (salario|sueldo|puesto) registrado\b|\b(mi|su) fecha de ingreso\b|"
                          r"\b(mis|sus) datos\b|\bmi registro\b|"
                          r"\b(datos|registro|salario|sueldo|fecha de ingreso|puesto) (de|del) (empleado|colaborador)")


def classify(question: str) -> Intent:
    n = strip_accents(question.lower())
    if LIQ_ACTION_RX.search(n):
        return Intent.LIQUIDACION
    if CALC_VERB_RX.search(n) and CALC_DATA_RX.search(n):
        return Intent.CALCULO
    if EMP_ID_RX.search(question) or EMP_QUERY_RX.search(n):
        return Intent.EMPLEADO if not CALC_VERB_RX.search(n) else Intent.CALCULO
    return Intent.NORMATIVA


class ToolArgs(BaseModel):
    """Argumentos que el LLM extrae del texto. Todo es opcional: la validación real ocurre en la herramienta."""

    tipo: str | None = None  # indemnizacion | aguinaldo | bono14 | vacaciones | liquidacion
    salario_mensual: float | None = None
    fecha_inicio: str | None = None  # AAAA-MM-DD
    fecha_fin: str | None = None
    motivo: str | None = None  # despido_injustificado | despido_justificado | renuncia
    employee_id: str | None = None
    ultima_fecha_vacaciones: str | None = None


EXTRACT_SYSTEM = """Extrae parámetros para una herramienta de cálculo de prestaciones laborales de Guatemala.
Devuelve SOLO los campos presentes en el texto; deja null lo que no se mencione. No inventes valores.
- tipo: indemnizacion | aguinaldo | bono14 | vacaciones | liquidacion (si pide "todo", "liquidación" o "finiquito": liquidacion)
- salario_mensual: número en quetzales, sin símbolo ni comas.
- fechas en formato AAAA-MM-DD. Si dice "hoy" usa la fecha de hoy indicada.
- motivo: despido_injustificado (despido sin causa justa) | despido_justificado | renuncia.
- employee_id: con formato E-000 si se menciona.
Fecha de hoy: {today}."""


def extract_tool_args(question: str, today: date) -> tuple[ToolArgs | None, int, int]:
    res = chat_structured(EXTRACT_SYSTEM.format(today=today.isoformat()), question, ToolArgs)
    return res.parsed, res.prompt_tokens, res.output_tokens  # type: ignore[return-value]
