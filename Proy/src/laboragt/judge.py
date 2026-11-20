"""LLM-as-a-judge (local): fidelidad al contexto y corrección frente al comportamiento esperado.

Limitación declarada: el juez es el mismo modelo base que genera (sesgo de autoevaluación).
Por eso el informe complementa con revisión manual de una muestra.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from . import config
from .llm import chat_structured


class Judgement(BaseModel):
    claims_total: int = Field(ge=0)
    claims_supported: int = Field(ge=0)
    correct: bool
    rationale: str


JUDGE_SYSTEM = """Eres un evaluador estricto de sistemas RAG. Recibirás: CONTEXTO (fragmentos citados), \
PREGUNTA, RESPUESTA del sistema y COMPORTAMIENTO ESPERADO.
1. Divide la RESPUESTA en afirmaciones fácticas atómicas. claims_total = cuántas hay.
2. claims_supported = cuántas están respaldadas explícitamente por el CONTEXTO (no por tu conocimiento).
3. correct = true si la RESPUESTA cumple lo esencial del COMPORTAMIENTO ESPERADO (cifras, artículo, \
abstención) sin contradecirlo; false en otro caso.
4. rationale: una oración en español.
Responde solo en JSON."""


def judge(question: str, answer: str, context: list[str], expected: str) -> tuple[Judgement | None, int, int]:
    ctx = "\n---\n".join(context) if context else "(sin contexto)"
    user = f"CONTEXTO:\n{ctx}\n\nPREGUNTA: {question}\n\nRESPUESTA: {answer}\n\nCOMPORTAMIENTO ESPERADO: {expected}"
    res = chat_structured(JUDGE_SYSTEM, user, Judgement, model=config.JUDGE_MODEL)
    return res.parsed, res.prompt_tokens, res.output_tokens  # type: ignore[return-value]
