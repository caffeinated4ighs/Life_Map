"""
logger.py — Structured logging to stderr + run_history.json.
Format: [TIMESTAMP] [LEVEL] [MODULE] message
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_HISTORY_PATH = Path(__file__).parent / "run_history.json"

_REDACTED = {"supabase_service_key", "groq_api_key", "password", "token", "secret", "key"}


def _redact(obj: Any) -> Any:
    """Recursively redact sensitive keys from dicts."""
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if any(r in k.lower() for r in _REDACTED) else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [_redact(i) for i in obj]
    return obj


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        return f"[{ts}] [{record.levelname}] [{record.module}] {record.getMessage()}"


def setup_logger(level_str: str = "INFO") -> logging.Logger:
    level = getattr(logging, level_str.upper(), logging.INFO)
    logger = logging.getLogger("orchestrator")
    if logger.handlers:
        return logger  # already set up
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    return logger


def _append_run_history(entry: dict) -> None:
    try:
        with open(RUN_HISTORY_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logging.getLogger("orchestrator").warning(f"Could not write run_history.json: {e}")


# ── Convenience wrappers used by sequencer ─────────────────────────────────

def log_script_call(logger: logging.Logger, fn_name: str, args: Any, result: Any, duration_ms: float) -> None:
    safe_args = _redact(args) if args is not None else None
    result_summary = str(result)[:200] if result is not None else None
    msg = f"script_call fn={fn_name} args={safe_args} result={result_summary} duration_ms={duration_ms:.1f}"
    logger.debug(msg)


def log_slm_call(logger: logging.Logger, model: str, tokens: int, latency_ms: float, success: bool) -> None:
    status = "ok" if success else "fail"
    logger.info(f"slm_call model={model} tokens={tokens} latency_ms={latency_ms:.1f} status={status}")


def log_health_check(logger: logging.Logger, healthy: bool, detail: str = "") -> None:
    level = logging.DEBUG if healthy else logging.ERROR
    logger.log(level, f"health_check healthy={healthy} {detail}".strip())


def log_run(flow: str, success: bool, detail: dict | None = None) -> None:
    logger = logging.getLogger("orchestrator")
    ts = datetime.now(tz=timezone.utc).isoformat()
    entry = {
        "timestamp": ts,
        "flow": flow,
        "success": success,
        **(detail or {}),
    }
    level = logging.INFO if success else logging.ERROR
    logger.log(level, f"run_complete flow={flow} success={success}")
    _append_run_history(entry)
