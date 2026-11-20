"""Pipeline de ingesta reproducible:
carga (manifiesto) -> extracción (+OCR) -> limpieza -> chunking -> metadatos -> indexación.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import yaml

from .. import config
from ..retrieval.bm25 import BM25Index
from ..schemas import AccessLevel, Chunk
from .chunker import split_units, windows
from .clean import clean_pages
from .extract import extract, file_sha256

log = logging.getLogger(__name__)


def load_manifest(path: Path = config.MANIFEST) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["documentos"]


def _short_title(doc: dict) -> str:
    return doc.get("titulo_corto") or doc["titulo"].split("(")[0].split("—")[0].strip()


def process_document(doc: dict) -> list[Chunk]:
    path = config.DATA_DIR / doc["archivo"]
    if not path.exists():
        raise FileNotFoundError(path)
    sha = file_sha256(path)
    if doc.get("sha256") and doc["sha256"] != sha:
        log.warning("El hash de %s no coincide con el manifiesto (¿documento actualizado?)", path.name)

    limpieza = doc.get("limpieza") or {}
    excluded = set(limpieza.get("paginas_excluir") or [])
    pages = [p for p in extract(path, sha) if p.page not in excluded]
    lines = clean_pages(pages, limpieza.get("inicio"), limpieza.get("fin"))
    units = split_units(lines)

    title = _short_title(doc)
    chunks: list[Chunk] = []
    n = 0
    for u in units:
        body = u.text.lstrip("* ").strip()
        # se conservan artículos cortos como "Derogado." (responder que está derogado es útil)
        if not body or (len(body.split()) < 3 and not u.article):
            continue
        parts = windows(body)
        for j, part in enumerate(parts):
            header = title + (f" — Artículo {u.article}" if u.article else "")
            if len(parts) > 1:
                header += f" (parte {j + 1}/{len(parts)})"
            text = f"{header}\n{part}"
            n += 1
            chunks.append(Chunk(
                chunk_id=f"{doc['id']}-{n:04d}",
                text=text,
                source=path.name,
                doc_id=doc["id"],
                doc_title=doc["titulo"],
                page=u.page,
                page_end=u.page_end,
                article=u.article,
                section=u.section,
                version=str(doc.get("version", "")),
                vigencia_desde=str(doc["vigencia_desde"]) if doc.get("vigencia_desde") else None,
                vigencia_hasta=str(doc["vigencia_hasta"]) if doc.get("vigencia_hasta") else None,
                access_level=AccessLevel(doc.get("access_level", "publico")),
                hash=hashlib.sha256(text.encode()).hexdigest()[:16],
            ))
    return chunks


def run(manifest: Path = config.MANIFEST, build_vectors: bool = True) -> list[Chunk]:
    from ..guardrails import detect_injection

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks: list[Chunk] = []
    quarantined: list[dict] = []
    for doc in load_manifest(manifest):
        chunks = process_document(doc)
        # Defensa contra inyección indirecta: chunks con instrucciones embebidas no se indexan
        clean = []
        for c in chunks:
            hits = detect_injection(c.text)
            if hits:
                quarantined.append({"chunk_id": c.chunk_id, "source": c.source, "page": c.page,
                                    "patterns": hits, "text": c.text[:300]})
            else:
                clean.append(c)
        log.info("%-32s %4d chunks (%d en cuarentena)", doc["id"], len(clean), len(chunks) - len(clean))
        all_chunks.extend(clean)
    with open(config.PROCESSED_DIR / "quarantine.jsonl", "w", encoding="utf-8") as f:
        for q in quarantined:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    with open(config.CHUNKS_FILE, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(c.model_dump_json() + "\n")

    BM25Index.build(all_chunks).save()
    if build_vectors:
        from ..retrieval.vector import VectorIndex

        VectorIndex.build(all_chunks)
    return all_chunks


def load_chunks(path: Path = config.CHUNKS_FILE) -> list[Chunk]:
    with open(path, encoding="utf-8") as f:
        return [Chunk(**json.loads(l)) for l in f if l.strip()]
