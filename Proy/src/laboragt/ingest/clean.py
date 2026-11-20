"""Fase 3 de ingesta: limpieza y normalización del texto extraído."""
from __future__ import annotations

import re
import unicodedata

from .extract import PageText

# Encabezados/pies repetidos en las fuentes que no aportan contenido
NOISE_LINE_PATTERNS = [
    r"^\d{1,4}$",  # números de página
    r"^OFICINA NACIONAL DE SERVICIO CIVIL$",
    r"^LEGAL AMBIENTAL GT$",
    r"^V[ée]rtice Financiero$",
    r"^DIARIO DE CENTRO\.?\s*AM[EÉ]RICA.*$",
    r"^NUMERO \d+$",
    r"^#{1,6}\s*$",
]
_NOISE = [re.compile(p, re.IGNORECASE) for p in NOISE_LINE_PATTERNS]

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "­": "", "​": ""}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    text = text.replace("\r", "")
    text = re.sub(r"[ \t ]+", " ", text)
    # palabra cortada con guion al final de línea: "traba-\njador" -> "trabajador"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return text


def is_noise(line: str) -> bool:
    s = line.strip()
    return any(p.match(s) for p in _NOISE)


def clean_pages(pages: list[PageText], start_regex: str | None = None,
                end_regex: str | None = None) -> list[tuple[int, str]]:
    """Devuelve una lista de (página, línea). Las líneas vacías marcan separación de párrafo.

    start_regex / end_regex (opcionales, desde el manifiesto) recortan contenido ajeno,
    p. ej. otro decreto publicado en la misma página del diario oficial.
    """
    lines: list[tuple[int, str]] = []
    for p in pages:
        for line in normalize(p.text).split("\n"):
            line = line.strip()
            if line and is_noise(line):
                continue
            lines.append((p.page, line))

    if start_regex:
        rx = re.compile(start_regex, re.IGNORECASE)
        idx = next((i for i, (_, l) in enumerate(lines) if rx.search(l)), None)
        if idx is not None:
            lines = lines[idx:]
    if end_regex:
        rx = re.compile(end_regex, re.IGNORECASE)
        idx = next((i for i, (_, l) in enumerate(lines) if rx.search(l)), None)
        if idx is not None:
            lines = lines[:idx]

    # colapsar líneas vacías consecutivas
    out: list[tuple[int, str]] = []
    for pg, l in lines:
        if not l and (not out or not out[-1][1]):
            continue
        out.append((pg, l))
    return out
