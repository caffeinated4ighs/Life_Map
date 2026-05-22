"""
groq_client.py — Life System Inference Agent
Wraps the Groq SDK for structured DB agent calls.
"""

import json
import os
import time
from pathlib import Path

from groq import Groq, RateLimitError, APIStatusError

# ── Config ────────────────────────────────────────────────────────────────────
_MODEL_ID = os.environ.get("GROQ_MODEL_ID", "meta-llama/llama-4-scout-17b-16e-instruct")
_TEMPERATURE = 0.1
_MAX_TOKENS = 512
_SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.txt").read_text()

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise EnvironmentError(
                "GROQ_API_KEY must be set in environment. "
                "Add it to your .env file or export it before running."
            )
        _client = Groq(api_key=key)
    return _client


def _build_user_message(user_message: str, context: dict | None) -> str:
    if context:
        context_block = json.dumps(context, default=str)
        return f"CONTEXT:\n{context_block}\n\nINSTRUCTION:\n{user_message}"
    return user_message


def _extract_json(raw: str) -> dict:
    """Strip markdown fences if present, then parse JSON."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first line (```json or ```) and last line (```)
        text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)


def _call_once(messages: list[dict]) -> str:
    response = _get_client().chat.completions.create(
        model=_MODEL_ID,
        messages=messages,
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS,
    )
    return response.choices[0].message.content


def call_agent(user_message: str, context: dict | None = None) -> dict:
    """
    Send a natural-language instruction to the SLM and return a parsed call spec.

    Returns:
        {"action": str, "args": dict}  on success
        {"error": str, "raw": str}     on parse failure after retries
    """
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(user_message, context)},
    ]

    last_error = None

    for attempt in range(2):  # 1 retry
        try:
            raw = _call_once(messages)
        except RateLimitError:
            if attempt == 0:
                time.sleep(10)
                continue
            raise
        except APIStatusError as e:
            if attempt == 0 and e.status_code >= 500:
                time.sleep(2)
                continue
            raise

        try:
            parsed = _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
            if attempt == 0:
                continue
            return {"error": f"JSON parse failed: {last_error}", "raw": raw}

        if "action" not in parsed or "args" not in parsed:
            last_error = "Missing 'action' or 'args' keys"
            if attempt == 0:
                continue
            return {"error": last_error, "raw": raw}

        return parsed

    return {"error": last_error or "Unknown failure", "raw": ""}
