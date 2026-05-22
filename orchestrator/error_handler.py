"""
error_handler.py — Retry logic and explicit failure mode handling.

Failure modes (from spec):
  - Supabase unreachable          → abort, log, retry up to 3x with 5-min backoff
  - Groq 429                      → wait 30s, retry once
  - Groq 500                      → wait 5s, retry once, then abort
  - SLM invalid JSON              → retry inference once, then abort
  - SLM valid JSON but unknown action → reject, log, abort
  - Script returns {success: false}   → log, do NOT retry
  - tick_day already_exists           → silent skip, continue
  - end_day missing snapshot          → log warning, abort EOD
  - Config var missing                → fail fast (handled in config.py)
"""

import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger("orchestrator")

T = TypeVar("T")


class LifeSystemError(Exception):
    """Base error for all orchestrator failures."""


class SupabaseUnreachableError(LifeSystemError):
    pass


class GroqRateLimitError(LifeSystemError):
    pass


class GroqServerError(LifeSystemError):
    pass


class SLMInvalidOutputError(LifeSystemError):
    pass


class UnknownActionError(LifeSystemError):
    pass


class ScriptFailureError(LifeSystemError):
    pass


class MissingSnapshotError(LifeSystemError):
    pass


class AlreadyExistsError(LifeSystemError):
    """Raised by tick_day when snapshot already exists — NOT a real error."""


def retry_supabase(fn: Callable[[], T], max_retries: int = 3, wait_seconds: int = 300) -> T:
    """Retry a Supabase call up to max_retries times with wait_seconds between attempts."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except SupabaseUnreachableError as e:
            last_exc = e
            logger.error(
                f"Supabase unreachable (attempt {attempt}/{max_retries}). "
                f"Retrying in {wait_seconds}s..."
            )
            if attempt < max_retries:
                time.sleep(wait_seconds)
    raise SupabaseUnreachableError(
        f"Supabase unreachable after {max_retries} attempts."
    ) from last_exc


def retry_groq_rate_limit(fn: Callable[[], T]) -> T:
    """On 429, wait 30s and retry once."""
    try:
        return fn()
    except GroqRateLimitError:
        logger.warning("Groq 429 rate limit. Waiting 30s before retry...")
        time.sleep(30)
        return fn()


def retry_groq_server_error(fn: Callable[[], T]) -> T:
    """On Groq 500, wait 5s and retry once, then abort."""
    try:
        return fn()
    except GroqServerError:
        logger.warning("Groq 500 server error. Waiting 5s before retry...")
        time.sleep(5)
        try:
            return fn()
        except GroqServerError as e:
            logger.error("Groq 500 on retry — aborting.")
            raise


def handle_script_result(result: dict, fn_name: str) -> dict:
    """
    Inspect a script result dict. Raises ScriptFailureError if success==False.
    tick_day 'already_exists' is silently allowed through.
    """
    if result.get("already_exists"):
        logger.debug(f"{fn_name}: snapshot already exists — skipping silently.")
        return result

    if result.get("success") is False:
        msg = result.get("error", "unknown script error")
        logger.error(f"Script {fn_name} returned failure: {msg}")
        raise ScriptFailureError(f"{fn_name} failed: {msg}")

    return result


KNOWN_ACTIONS = frozenset({
    "get_player_state",
    "get_today",
    "get_tasks",
    "get_task",
    "get_skill_links",
    "get_active_effects",
    "get_active_arcs",
    "tick_day",
    "complete_task",
    "log_event",
    "create_task",
    "create_effect",
    "update_arc_status",
    "end_day",
})


def validate_action(action: str) -> None:
    """Reject any action not in the approved routing table."""
    if action not in KNOWN_ACTIONS:
        logger.error(f"Unknown action '{action}' returned by SLM — rejecting.")
        raise UnknownActionError(f"Action '{action}' is not in the approved routing table.")
