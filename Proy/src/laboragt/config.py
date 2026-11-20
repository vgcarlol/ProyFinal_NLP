"""Configuración central. Los valores se pueden sobrescribir con variables de entorno (.env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROY_DIR = Path(__file__).resolve().parents[2]  # .../Proy
load_dotenv(PROY_DIR / ".env")

import logging as _logging

for _name in ("httpx", "huggingface_hub", "sentence_transformers", "chromadb", "urllib3"):
    _logging.getLogger(_name).setLevel(_logging.WARNING)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


# Rutas
DATA_DIR = PROY_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
PROCESSED_DIR = DATA_DIR / "processed"
INDEX_DIR = DATA_DIR / "index"
LOGS_DIR = PROY_DIR / "logs"
MANIFEST = DATA_DIR / "sources.yaml"
CHUNKS_FILE = PROCESSED_DIR / "chunks.jsonl"
TESSDATA_DIR = Path(_env("TESSDATA_DIR", str(PROY_DIR / "tessdata")))

# OCR
OCR_DPI = int(_env("OCR_DPI", "250"))
OCR_LANG = _env("OCR_LANG", "spa")
OCR_MIN_CHARS = 50  # si una página trae menos texto que esto, se asume escaneada

# Chunking
CHUNK_MAX_WORDS = int(_env("CHUNK_MAX_WORDS", "300"))
CHUNK_OVERLAP_WORDS = int(_env("CHUNK_OVERLAP_WORDS", "40"))
CHUNK_MIN_WORDS = 25

# LLM (Ollama local)
OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = _env("LLM_MODEL", "qwen2.5:7b-instruct")
JUDGE_MODEL = _env("JUDGE_MODEL", "qwen2.5:7b-instruct")  # fijo para comparar sistemas con el mismo juez
LLM_TEMPERATURE = float(_env("LLM_TEMPERATURE", "0.0"))
LLM_TIMEOUT_S = int(_env("LLM_TIMEOUT_S", "120"))
LLM_SEED = 42
LLM_MAX_TOKENS = int(_env("LLM_MAX_TOKENS", "400"))  # acota latencia y evita generaciones desbocadas

# Recuperación / abstención (línea base)
TOP_K = int(_env("TOP_K", "5"))
BM25_MIN_SCORE = float(_env("BM25_MIN_SCORE", "4.0"))  # calibrar con el banco de pruebas

# Recuperación mejorada (Fase 3)
EMBED_MODEL = _env("EMBED_MODEL", "intfloat/multilingual-e5-base")
RERANK_MODEL = _env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
DEVICE = _env("DEVICE", "mps")  # "cpu" si no hay Apple Silicon / CUDA
CANDIDATES_PER_RETRIEVER = int(_env("CANDIDATES_PER_RETRIEVER", "30"))
RRF_K = 60
RERANK_POOL = int(_env("RERANK_POOL", "20"))
RERANK_MIN_SCORE = float(_env("RERANK_MIN_SCORE", "0.02"))  # calibrado en eval (ver informe)
LOW_CONFIDENCE_SCORE = float(_env("LOW_CONFIDENCE_SCORE", "0.30"))  # bajo esto -> needs_human_review
MAX_CHUNKS_PER_ARTICLE = 2  # diversidad del contexto
# Fecha de referencia para vigencia (fijable para reproducibilidad del benchmark)
TODAY = _env("TODAY", "")

# Herramientas
TOOL_MAX_CALLS = 3
TOOL_TIMEOUT_S = 10
EMPLOYEES_DB = DATA_DIR / "synthetic" / "empleados_demo.sqlite"

# Seguridad básica
MAX_QUESTION_CHARS = 500
