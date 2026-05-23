"""
sequencer.py — Core flow logic: morning, EOD, task completion.

This module sequences calls to scripts and the SLM.
It does NOT implement business logic — that lives in the scripts layer.
"""

import logging
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from orchestrator.error_handler import (
    AlreadyExistsError,
    MissingSnapshotError,
    ScriptFailureError,
    SLMInvalidOutputError,
    SupabaseUnreachableError,
    UnknownActionError,
    handle_script_result,
    retry_groq_rate_limit,
    retry_groq_server_error,
    retry_supabase,
    validate_action,
)
from orchestrator.health import health_check
from orchestrator.logger import log_run, log_script_call, log_slm_call

if TYPE_CHECKING:
    from orchestrator.config import Config

logger = logging.getLogger("orchestrator")

# ---------------------------------------------------------------------------
# Lazy imports of sibling packages (scripts + inference).
# These are built by other agents and must exist at runtime.
# ---------------------------------------------------------------------------

def _import_reads():
    try:
        from scripts import reads
        return reads
    except ImportError as e:
        raise ImportError(
            "scripts.reads is not importable. "
            "Ensure the Scripts Agent output is on PYTHONPATH."
        ) from e


def _import_writes():
    try:
        from scripts import writes
        return writes
    except ImportError as e:
        raise ImportError(
            "scripts.writes is not importable. "
            "Ensure the Scripts Agent output is on PYTHONPATH."
        ) from e


def _import_inference():
    try:
        from inference.groq_client import call_agent
        from inference.validate_output import validate_output
        return call_agent, validate_output
    except ImportError as e:
        raise ImportError(
            "groq_client or validate_output is not importable. "
            "Ensure the Inference Agent output is on PYTHONPATH."
        ) from e


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today_str(config: "Config") -> str:
    """Return today's date string in YYYY-MM-DD using the configured timezone."""
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(config.timezone)
    except Exception:
        tz = None
    return date.today().isoformat() if tz is None else datetime.now(tz).date().isoformat()


def _call_script(fn, fn_name: str, *args, **kwargs) -> Any:
    """Call a script function, time it, log it, and handle failure results."""
    start = time.monotonic()
    result = fn(*args, **kwargs)
    duration_ms = (time.monotonic() - start) * 1000
    log_script_call(logger, fn_name, args or kwargs or None, result, duration_ms)
    return handle_script_result(result if isinstance(result, dict) else {"data": result}, fn_name)


# ---------------------------------------------------------------------------
# Routing table: action → script function resolver
# ---------------------------------------------------------------------------

def _route(action: str, args: dict, reads, writes) -> Any:
    """Route an SLM-produced action to the correct script function."""
    validate_action(action)

    routes = {
        "get_player_state": lambda: reads.get_player_state(),
        "get_today": lambda: reads.get_today(args["date"]),
        "get_tasks": lambda: reads.get_tasks(args["date"], args["mh_mode"]),
        "get_task": lambda: reads.get_task(args["task_id"]),
        "get_skill_links": lambda: reads.get_skill_links(args["task_id"]),
        "get_active_effects": lambda: reads.get_active_effects(),
        "get_active_arcs": lambda: reads.get_active_arcs(),
        "tick_day": lambda: writes.tick_day(args["date"]),
        "complete_task": lambda: writes.complete_task(args["task_id"], args),
        "log_event": lambda: writes.log_event(args["event_type"], args["payload"]),
        "create_task": lambda: writes.create_task(args),
        "create_effect": lambda: writes.create_effect(args),
        "update_arc_status": lambda: writes.update_arc_status(args["arc_id"], args["status"]),
        "end_day": lambda: writes.end_day(args["date"]),
    }

    fn = routes[action]
    start = time.monotonic()
    result = fn()
    duration_ms = (time.monotonic() - start) * 1000
    log_script_call(logger, action, args, result, duration_ms)
    return result


# ---------------------------------------------------------------------------
# Morning flow
# ---------------------------------------------------------------------------

def run_morning(config: "Config") -> dict:
    """
    Morning flow:
      1. health_check
      2. get_today → check needs_init
      3. tick_day if needs_init
      4. get_player_state
      5. get_tasks
      6. get_active_arcs
      7. get_active_effects
      → return assembled day briefing
    """
    reads = _import_reads()
    writes = _import_writes()
    today = _today_str(config)

    logger.info(f"morning flow started date={today}")

    # 1. Health check
    if not health_check(config):
        log_run("morning", False, {"error": "supabase_unreachable", "date": today})
        raise SupabaseUnreachableError("Supabase health check failed — aborting morning flow.")

    # 2. Get today snapshot
    snapshot = reads.get_today(today)
    log_script_call(logger, "get_today", {"date": today}, snapshot, 0)

    # 3. Init if needed
    if snapshot.get("needs_init", True):
        logger.info(f"Snapshot missing for {today} — running tick_day.")
        tick_result = writes.tick_day(today)
        log_script_call(logger, "tick_day", {"date": today}, tick_result, 0)

        if tick_result.get("already_exists"):
            logger.debug("tick_day: snapshot already existed — continuing.")
        else:
            handle_script_result(tick_result, "tick_day")

        # Re-fetch snapshot after init
        snapshot = reads.get_today(today)

    # 4. Player state
    player_state = reads.get_player_state()
    log_script_call(logger, "get_player_state", None, player_state, 0)

    # 5. Task list (filtered by MH mode)
    mh_mode = player_state.get("mh_mode", "Normal")
    tasks = reads.get_tasks(today, mh_mode)
    log_script_call(logger, "get_tasks", {"date": today, "mh_mode": mh_mode}, f"{len(tasks)} tasks", 0)

    # 6. Active arcs
    active_arcs = reads.get_active_arcs()
    log_script_call(logger, "get_active_arcs", None, active_arcs, 0)

    # 7. Active effects
    active_effects = reads.get_active_effects()
    log_script_call(logger, "get_active_effects", None, active_effects, 0)

    briefing = {
        "date": today,
        "snapshot": snapshot,
        "player_state": player_state,
        "tasks": tasks,
        "active_arcs": active_arcs,
        "active_effects": active_effects,
    }

    log_run("morning", True, {"date": today, "task_count": len(tasks), "mh_mode": mh_mode})
    return briefing


# ---------------------------------------------------------------------------
# EOD flow
# ---------------------------------------------------------------------------

def run_eod(config: "Config") -> dict:
    """
    EOD flow:
      1. health_check
      2. get_today → verify snapshot exists
      3. end_day
      4. get_player_state (final state)
      5. log to run_history.json
      → return EOD summary
    """
    reads = _import_reads()
    writes = _import_writes()
    today = _today_str(config)

    logger.info(f"eod flow started date={today}")

    # 1. Health check
    if not health_check(config):
        log_run("eod", False, {"error": "supabase_unreachable", "date": today})
        raise SupabaseUnreachableError("Supabase health check failed — aborting EOD flow.")

    # 2. Verify snapshot exists
    snapshot = reads.get_today(today)
    log_script_call(logger, "get_today", {"date": today}, snapshot, 0)

    if snapshot.get("needs_init", True):
        msg = f"No snapshot found for {today} — morning flow never ran. Aborting EOD."
        logger.warning(msg)
        log_run("eod", False, {"error": "missing_snapshot", "date": today})
        raise MissingSnapshotError(msg)

    # 3. Close the day
    eod_result = writes.end_day(today)
    log_script_call(logger, "end_day", {"date": today}, eod_result, 0)
    handle_script_result(eod_result, "end_day")

    # 4. Final player state
    player_state = reads.get_player_state()
    log_script_call(logger, "get_player_state", None, player_state, 0)

    summary = {
        "date": today,
        "eod_result": eod_result,
        "player_state": player_state,
    }

    log_run(
        "eod",
        True,
        {
            "date": today,
            "streak_count": eod_result.get("streak_count"),
            "mandatory_met": eod_result.get("mandatory_met"),
            "mh_score_close": eod_result.get("mh_score_close"),
            "gold_close": eod_result.get("gold_close"),
        },
    )
    return summary


# ---------------------------------------------------------------------------
# Task completion flow (SLM-routed)
# ---------------------------------------------------------------------------

def run_complete_task(config: "Config", user_message: str) -> dict:
    """
    Task completion flow:
      1. call_agent(user_message, context)
      2. validate_output
      3. Retry once on invalid output
      4. If action == "error": return graceful decline (no-op, no crash)
      5. Route to script via action table
      → return script result
    """
    call_agent, validate_output = _import_inference()
    reads = _import_reads()
    writes = _import_writes()
    today = _today_str(config)

    logger.info(f"complete_task flow started message='{user_message[:80]}'")

    # Build context for the SLM
    player_state = reads.get_player_state()
    context = {
        "date": today,
        "player_state": player_state,
    }

    # 1 + 2. Call SLM, validate, retry once on failure
    slm_result = None
    for attempt in range(1, 3):
        start = time.monotonic()
        try:
            raw = retry_groq_rate_limit(
                lambda: retry_groq_server_error(
                    lambda: call_agent(user_message, context)
                )
            )
            latency_ms = (time.monotonic() - start) * 1000
            tokens = raw.get("usage", {}).get("total_tokens", 0) if isinstance(raw, dict) else 0
            log_slm_call(logger, config.groq_model_id, tokens, latency_ms, success=True)

            validated = validate_output(raw)
            slm_result = validated
            break

        except (SLMInvalidOutputError, ValueError, KeyError) as e:
            latency_ms = (time.monotonic() - start) * 1000
            log_slm_call(logger, config.groq_model_id, 0, latency_ms, success=False)
            logger.warning(f"SLM output invalid (attempt {attempt}/2): {e}")
            if attempt == 2:
                log_run("complete_task", False, {"error": "slm_invalid_output", "detail": str(e)})
                raise SLMInvalidOutputError(
                    f"SLM returned invalid output after 2 attempts: {e}"
                ) from e

    # 3. Intercept SLM refusals before the routing table.
    #    The Inference Agent returns {"action": "error", "args": {"reason": "..."}}
    #    when the request is out of scope. This is a graceful no-op, not a crash.
    action = slm_result["action"]
    args = slm_result.get("args", {})

    if action == "error":
        reason = args.get("reason", "no reason given")
        logger.warning("SLM declined request: %s", reason)
        log_run("complete_task", True, {"action": "error", "reason": reason})
        return {"status": "declined", "reason": reason}

    # 4. Validate action against approved routing table
    try:
        validate_action(action)
    except UnknownActionError:
        log_run("complete_task", False, {"error": "unknown_action", "action": action})
        raise

    # 5. Route to script
    result = _route(action, args, reads, writes)

    log_run(
        "complete_task",
        True,
        {"action": action, "date": today},
    )
    return result
