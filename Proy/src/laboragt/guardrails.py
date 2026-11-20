"""Guardrails de entrada, de ingesta (inyección indirecta) y de salida."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .retrieval.bm25 import strip_accents

# ---------- detección de inyección de instrucciones (es / en) ----------
INJECTION_PATTERNS = [
    r"ignor(a|e|ar|en)\s+(todas?\s+)?(las|tus|sus|mis|the|all|any)?\s*(instrucciones|reglas|indicaciones|instructions|rules)",
    r"olvid(a|e|ar)\s+(todo|tus|las)\s*(instrucciones|reglas|lo anterior)?",
    r"(prompt|mensaje|instrucciones?)\s+(del|de)\s+sistema",
    r"system\s*prompt",
    r"(revela|muestra|imprime|repite|dime|ensena)\s+(tu|tus|el|las|la)\s+(prompt|instrucciones|reglas|configuracion|directrices)",
    r"(a partir de ahora|desde ahora)\s+(eres|actua|responde|ignora)",
    r"\b(actua|comportate)\s+como\s+(si|un|una)\b",
    r"\b(you are now|act as|pretend to be|ignore (all|previous|prior))\b",
    r"\b(modo|mode)\s+(desarrollador|developer|dios|god|dan)\b",
    r"\bjailbreak\b|\bsin restricciones\b|\bno tienes restricciones\b",
    r"</?\s*(fragmento|system|instrucciones)\s*>",
    r"nueva(s)?\s+instruccion(es)?\s*:",
]
_INJ = [re.compile(p) for p in INJECTION_PATTERNS]

# Intentos de escalar privilegios desde el texto (el rol real viene de la sesión)
ROLE_CLAIM_RX = re.compile(r"\b(soy|como)\s+(el\s+|la\s+)?(gerente|analista de (rrhh|recursos humanos)|administrador|admin|de rrhh|de recursos humanos)\b|"
                           r"\btengo (permiso|autorizacion|acceso)\b")


@dataclass
class GuardResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def detect_injection(text: str) -> list[str]:
    n = strip_accents(text.lower())
    return [p.pattern[:40] for p in _INJ if p.search(n)]


def input_guard(question: str) -> GuardResult:
    res = GuardResult(allowed=True)
    hits = detect_injection(question)
    if hits:
        res.allowed = False
        res.reasons.append("posible inyección de instrucciones")
        res.flags += hits
    n = strip_accents(question.lower())
    if ROLE_CLAIM_RX.search(n):
        res.flags.append("reclamo_de_rol_en_texto")  # no bloquea: se ignora y se registra
    if len(re.findall(r"[^\w\s¿?¡!.,;:()\-/$%Q]", question)) > 0.3 * max(len(question), 1):
        res.allowed = False
        res.reasons.append("entrada con caracteres anómalos")
    return res


# ---------- verificación de salida ----------
AMOUNT_RX = re.compile(r"Q\.?\s?\d[\d,]*(?:\.\d{1,2})?|\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b|\b\d+\.\d{2}\b")
LEAK_MARKERS = ["REGLAS OBLIGATORIAS", "Eres LaboraGT", "cited_chunk_ids", "insufficient_evidence"]


NUM_TOKEN_RX = re.compile(r"\d[\d.,]*\d|\d")


def _amount_key(s: str) -> str:
    """Clave canónica en centavos: 'Q. 4,002.28', '4,002,28' (OCR) y '4002.28' -> '400228'; 'Q250' -> '25000'."""
    s = re.sub(r"[^\d.,]", "", s)
    m = re.match(r"^(.*?)[.,](\d{1,2})$", s)  # 1-2 decimales = centavos ('5000.0', '4,002,28')
    whole, cents = (m.group(1), m.group(2).ljust(2, "0")) if m else (s, "00")
    whole = re.sub(r"\D", "", whole).lstrip("0") or "0"
    return whole + cents


def unsupported_amounts(answer: str, evidence_texts: list[str]) -> list[str]:
    """Montos del answer que no aparecen en la evidencia (contexto o resultado de herramienta)."""
    ev_keys = {_amount_key(t) for t in NUM_TOKEN_RX.findall(" ".join(evidence_texts))}
    return [a for a in AMOUNT_RX.findall(answer) if _amount_key(a) not in ev_keys]


def leaks_system_prompt(answer: str) -> bool:
    return any(m.lower() in answer.lower() for m in LEAK_MARKERS)
