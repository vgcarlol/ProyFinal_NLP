"""Ejecuta el pipeline de ingesta completo a partir de data/sources.yaml.

Uso:  python Proy/scripts/ingest.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # sin depender del .pth

import logging
import time
from collections import Counter

from laboragt import config
from laboragt.ingest.pipeline import run
from laboragt.tools.empleados import build_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    t0 = time.perf_counter()
    chunks = run()
    build_db()
    by_doc = Counter(c.doc_id for c in chunks)
    by_access = Counter(c.access_level.value for c in chunks)
    words = [len(c.text.split()) for c in chunks]
    print(f"\n{len(chunks)} chunks de {len(by_doc)} documentos en {time.perf_counter() - t0:.1f}s")
    print("Por nivel de acceso:", dict(by_access))
    print(f"Palabras por chunk: min={min(words)} media={sum(words) / len(words):.0f} max={max(words)}")
    print(f"Cuarentena (inyección indirecta): {config.PROCESSED_DIR / 'quarantine.jsonl'}")
    print(f"Empleados sintéticos: {config.EMPLOYEES_DB}")
    print(f"Chunks: {config.CHUNKS_FILE}\nÍndice BM25: {config.INDEX_DIR / 'bm25.pkl'}")
