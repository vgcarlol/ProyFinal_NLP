"""Trazabilidad: un registro JSON por consulta, con PII enmascarada."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from . import config

PII_PATTERNS = [
    (re.compile(r"\b\d{4}\s?\d{5}\s?\d{4}\b"), "[DPI]"),  # DPI: 13 dígitos (4-5-4)
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[EMAIL]"),
    (re.compile(r"(?<![\w-])\d{6,8}-[\dkK](?![\w-])"), "[NIT]"),
    (re.compile(r"(?<![\w-])(?:\+?502[\s-]?)?\d{4}[\s-]?\d{4}(?![\w-])"), "[TEL]"),
]


def mask_pii(text: str) -> str:
    for rx, repl in PII_PATTERNS:
        text = rx.sub(repl, text)
    return text


def _mask(obj: Any) -> Any:
    if isinstance(obj, str):
        return mask_pii(obj)
    if isinstance(obj, dict):
        return {k: _mask(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask(v) for v in obj]
    return obj


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def write_trace(record: dict) -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **_mask(record)}
    with open(config.LOGS_DIR / "trace.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
