"""Fase 4 de ingesta: segmentación por artículo (unidad semántica de la norma).

- Cada 'ARTÍCULO N.' inicia un fragmento; se conserva el número de artículo y la sección.
- Artículos largos se parten en ventanas con solapamiento (manteniendo el número).
- Documentos sin artículos (p. ej. boletines) se agrupan por párrafos hasta CHUNK_MAX_WORDS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import config

# En mayúsculas para no confundir con referencias internas ("del Artículo 82").
# Se toleran hasta 4 fragmentos cortos de ruido de OCR antes del encabezado ("Ú A e ARTÍCULO 3.").
_UPPER_RX = re.compile(
    r"^(?:\S{1,2}\s+){0,4}ART[IÍ]CULO\s+((?:\d+)(?:\s*(?:BIS|TER|QUATER))?|[IVXLC]+)\s*[.,:\-–]?\s*(.*)$"
)
# Variante "Artículo 9o. Texto..." (leyes del aguinaldo y Bono 14): el punto tras el número es
# obligatorio para no confundir con una línea que empieza con una referencia ("Artículo 82 del...").
_MIXED_RX = re.compile(r"^Art[ií]culo\s+(\d+)\s*(?:o|º|°)?\s*\.\s*(.*)$")


class _ArticleMatcher:
    def match(self, line: str):
        return _UPPER_RX.match(line) or _MIXED_RX.match(line)


ARTICLE_RX = _ArticleMatcher()
SECTION_RX = re.compile(r"^(T[IÍ]TULO|CAP[IÍ]TULO)\b.*$")


@dataclass
class Unit:
    """Unidad lógica antes de partir: un artículo, un preámbulo o un bloque de párrafos."""

    lines: list[tuple[int, str]] = field(default_factory=list)
    article: str | None = None
    section: str | None = None

    @property
    def text(self) -> str:
        paras, cur = [], []
        for _, l in self.lines:
            if l:
                cur.append(l)
            elif cur:
                paras.append(" ".join(cur))
                cur = []
        if cur:
            paras.append(" ".join(cur))
        return "\n".join(paras).strip()

    @property
    def page(self) -> int:
        return self.lines[0][0] if self.lines else 1

    @property
    def page_end(self) -> int:
        return self.lines[-1][0] if self.lines else 1


def split_units(lines: list[tuple[int, str]]) -> list[Unit]:
    units: list[Unit] = []
    section: str | None = None
    cur = Unit(section=None)
    found_article = False
    expect_section_name = False
    for pg, line in lines:
        # "CAPÍTULO TERCERO" suele ir seguido de su nombre en mayúsculas ("VACACIONES")
        if expect_section_name and line:
            expect_section_name = False
            if line.isupper() and len(line.split()) <= 12 and not ARTICLE_RX.match(line):
                section = f"{section} — {line}"
                continue
        m = ARTICLE_RX.match(line)
        if m:
            found_article = True
            if cur.text:
                units.append(cur)
            art = re.sub(r"\s+", " ", m.group(1)).strip()
            cur = Unit(article=art, section=section)
            rest = m.group(2).strip()
            if rest:
                cur.lines.append((pg, rest))
            else:
                cur.lines.append((pg, ""))  # marca de página de inicio
            continue
        if SECTION_RX.match(line) and found_article:
            section = line.strip()
            expect_section_name = True
            continue
        cur.lines.append((pg, line))
    if cur.text:
        units.append(cur)

    if not found_article:
        return _group_paragraphs(lines)
    return units


def _group_paragraphs(lines: list[tuple[int, str]]) -> list[Unit]:
    """Para documentos sin artículos: agrupa párrafos completos hasta el máximo de palabras."""
    paras: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    for pg, l in lines:
        if l:
            cur.append((pg, l))
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)

    units, acc, words = [], [], 0
    for p in paras:
        n = sum(len(l.split()) for _, l in p)
        if acc and words + n > config.CHUNK_MAX_WORDS:
            units.append(Unit(lines=acc))
            acc, words = [], 0
        acc = acc + p + [(p[-1][0], "")]
        words += n
    if acc:
        units.append(Unit(lines=acc))
    return units


def windows(text: str) -> list[str]:
    words = text.split()
    if len(words) <= config.CHUNK_MAX_WORDS:
        return [text]
    step = config.CHUNK_MAX_WORDS - config.CHUNK_OVERLAP_WORDS
    out = []
    for start in range(0, len(words), step):
        out.append(" ".join(words[start:start + config.CHUNK_MAX_WORDS]))
        if start + config.CHUNK_MAX_WORDS >= len(words):
            break
    return out
