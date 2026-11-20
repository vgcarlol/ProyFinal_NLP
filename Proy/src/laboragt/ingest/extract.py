"""Fase 2 de ingesta: extracción de texto por página (PyMuPDF) con OCR para páginas escaneadas."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

from .. import config

log = logging.getLogger(__name__)
OCR_CACHE = config.PROCESSED_DIR / "ocr_cache"


@dataclass
class PageText:
    page: int  # 1-based
    text: str  # párrafos separados por línea en blanco
    ocr: bool


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _ocr_page(page: pymupdf.Page, cache_key: str) -> str:
    OCR_CACHE.mkdir(parents=True, exist_ok=True)
    cached = OCR_CACHE / f"{cache_key}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    pix = page.get_pixmap(dpi=config.OCR_DPI, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    text = pytesseract.image_to_string(
        img, lang=config.OCR_LANG, config=f'--tessdata-dir "{config.TESSDATA_DIR}" --psm 3'
    )
    cached.write_text(text, encoding="utf-8")
    return text


def extract_pdf(path: Path, sha: str) -> list[PageText]:
    pages: list[PageText] = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            blocks = page.get_text("blocks", sort=True)
            text = "\n\n".join(b[4].strip() for b in blocks if b[6] == 0 and b[4].strip())
            if len(text.strip()) >= config.OCR_MIN_CHARS:
                pages.append(PageText(i, text, ocr=False))
            else:
                log.info("OCR %s pág. %d", path.name, i)
                pages.append(PageText(i, _ocr_page(page, f"{sha[:16]}_p{i}"), ocr=True))
    return pages


def extract_markdown(path: Path) -> list[PageText]:
    """Los documentos sintéticos (.md) usan '<!-- pagina -->' como salto de página."""
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("<!-- pagina -->")
    return [PageText(i, p, ocr=False) for i, p in enumerate(parts, start=1) if p.strip()]


def extract(path: Path, sha: str) -> list[PageText]:
    if path.suffix.lower() == ".pdf":
        return extract_pdf(path, sha)
    if path.suffix.lower() in {".md", ".txt"}:
        return extract_markdown(path)
    raise ValueError(f"Formato no soportado: {path.suffix}")
