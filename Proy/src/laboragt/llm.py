"""Cliente mínimo para Ollama (local) con salida estructurada por JSON Schema."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import requests
from pydantic import BaseModel, ValidationError

from . import config


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    parsed: BaseModel | None
    raw: str
    prompt_tokens: int
    output_tokens: int
    latency_s: float
    error: str | None = None


def chat_structured(system: str, user: str, schema: type[BaseModel],
                    model: str = config.LLM_MODEL, retries: int = 1) -> LLMResult:
    """Pide al LLM una respuesta que cumpla `schema`. Reintenta una vez si no valida."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema.model_json_schema(),
        "stream": False,
        "options": {"temperature": config.LLM_TEMPERATURE, "seed": config.LLM_SEED, "num_ctx": 8192,
                    "num_predict": config.LLM_MAX_TOKENS},
    }
    last_err, raw, pt, ot, t0 = None, "", 0, 0, time.perf_counter()
    for _ in range(retries + 1):
        try:
            r = requests.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=config.LLM_TIMEOUT_S)
            r.raise_for_status()
        except requests.RequestException as e:
            raise LLMError(f"Ollama no disponible: {e}") from e
        data = r.json()
        raw = data.get("message", {}).get("content", "")
        pt += data.get("prompt_eval_count", 0)
        ot += data.get("eval_count", 0)
        try:
            parsed = schema.model_validate(json.loads(raw))
            return LLMResult(parsed, raw, pt, ot, time.perf_counter() - t0)
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = str(e)
    return LLMResult(None, raw, pt, ot, time.perf_counter() - t0, error=last_err)
