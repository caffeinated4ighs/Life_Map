"""
validate_output.py — Life System Inference Agent
Validates SLM JSON output before it reaches the Scripts Agent.
"""

import re
import uuid

# ── Schema registry ────────────────────────────────────────────────────────────

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MH_MODES = {"Normal", "Reduced", "Minimum Viable", "Recovery Only"}
COMPLETION_TIMES = {"on_time", "soft", "meaningful_delay", "hard_failure", "void"}
TASK_TYPES = {"Daily", "Weekly", "Recurring", "Mandatory", "Optional", "Bonus"}
PRIORITIES = {"P0", "P1", "P2", "P3"}
CATEGORIES = {"Health", "Study", "Work", "Social", "Maintenance", "Hobby"}
ENERGY_COSTS = {"Low", "Medium", "High", "Very High"}
LATE_RULES = {"None", "Soft", "Medium", "Hard"}
LATE_RULE_BEHAVIORS = {"Penalty", "Incentive", "Neutral"}
TIME_BLOCKS = {"Morning", "Afternoon", "Evening", "Night", "Flexible"}
EVENT_TYPES = {"steps", "substance", "leisure", "day_off", "cheat_day", "mh_manual"}
ARC_STATUSES = {"Active", "Paused", "Done"}
EFFECT_TYPES = {"Buff", "Debuff"}


def _is_uuid(v) -> bool:
    if not isinstance(v, str):
        return False
    return bool(_UUID_RE.match(v))


def _is_date(v) -> bool:
    if not isinstance(v, str):
        return False
    return bool(_DATE_RE.match(v))


def _err(errors: list, msg: str):
    errors.append(msg)


# ── Per-script validators ──────────────────────────────────────────────────────

def _validate_error(args, errors):
    if "reason" not in args:
        _err(errors, "error: missing required field 'reason'")
    elif not isinstance(args["reason"], str):
        _err(errors, "error: 'reason' must be a string")
    unknown = set(args.keys()) - {"reason"}
    if unknown:
        _err(errors, f"error: unexpected fields {sorted(unknown)}")


def _validate_get_player_state(args, errors):
    # no args expected
    pass


def _validate_get_today(args, errors):
    if "date" not in args:
        _err(errors, "get_today: missing required arg 'date'")
    elif not _is_date(args["date"]):
        _err(errors, f"get_today: 'date' must be YYYY-MM-DD, got {args['date']!r}")


def _validate_get_tasks(args, errors):
    if "date" not in args:
        _err(errors, "get_tasks: missing required arg 'date'")
    elif not _is_date(args["date"]):
        _err(errors, f"get_tasks: 'date' must be YYYY-MM-DD, got {args['date']!r}")
    if "mh_mode" not in args:
        _err(errors, "get_tasks: missing required arg 'mh_mode'")
    elif args["mh_mode"] not in MH_MODES:
        _err(errors, f"get_tasks: invalid mh_mode {args['mh_mode']!r}")


def _validate_get_task(args, errors):
    if "task_id" not in args:
        _err(errors, "get_task: missing required arg 'task_id'")
    elif not _is_uuid(args["task_id"]):
        _err(errors, f"get_task: 'task_id' must be a UUID, got {args['task_id']!r}")


def _validate_get_skill_links(args, errors):
    if "task_id" not in args:
        _err(errors, "get_skill_links: missing required arg 'task_id'")
    elif not _is_uuid(args["task_id"]):
        _err(errors, f"get_skill_links: 'task_id' must be a UUID")


def _validate_get_active_effects(args, errors):
    pass


def _validate_get_active_arcs(args, errors):
    pass


def _validate_tick_day(args, errors):
    if "date" not in args:
        _err(errors, "tick_day: missing required arg 'date'")
    elif not _is_date(args["date"]):
        _err(errors, f"tick_day: 'date' must be YYYY-MM-DD")


def _validate_complete_task(args, errors):
    if "task_id" not in args:
        _err(errors, "complete_task: missing required arg 'task_id'")
    elif not _is_uuid(args["task_id"]):
        _err(errors, "complete_task: 'task_id' must be a UUID")

    cd = args.get("completion_data")
    if not isinstance(cd, dict):
        _err(errors, "complete_task: 'completion_data' must be an object")
        return

    if "completion_time" not in cd:
        _err(errors, "complete_task.completion_data: missing 'completion_time'")
    elif cd["completion_time"] not in COMPLETION_TIMES:
        _err(errors, f"complete_task.completion_data: invalid completion_time {cd['completion_time']!r}")

    if "partial_credit" not in cd:
        _err(errors, "complete_task.completion_data: missing 'partial_credit'")
    else:
        pc = cd["partial_credit"]
        if not isinstance(pc, (int, float)) or not (0.0 <= pc <= 1.0):
            _err(errors, f"complete_task.completion_data: 'partial_credit' must be 0.0–1.0, got {pc!r}")

    if "mh_mode" not in cd:
        _err(errors, "complete_task.completion_data: missing 'mh_mode'")
    elif cd["mh_mode"] not in MH_MODES:
        _err(errors, f"complete_task.completion_data: invalid mh_mode {cd['mh_mode']!r}")


def _validate_log_event(args, errors):
    if "event_type" not in args:
        _err(errors, "log_event: missing required arg 'event_type'")
    elif args["event_type"] not in EVENT_TYPES:
        _err(errors, f"log_event: invalid event_type {args['event_type']!r}")

    if "payload" not in args:
        _err(errors, "log_event: missing required arg 'payload'")
    elif not isinstance(args["payload"], dict):
        _err(errors, "log_event: 'payload' must be an object")


def _validate_create_task(args, errors):
    td = args.get("task_data")
    if not isinstance(td, dict):
        _err(errors, "create_task: 'task_data' must be an object")
        return

    required = {
        "task": str,
        "type": None,
        "priority": None,
        "category": None,
        "date": None,
        "energy_cost": None,
        "late_rule": None,
        "late_rule_behavior": None,
        "xp": int,
        "gold": int,
        "time_block": None,
    }
    for field in required:
        if field not in td:
            _err(errors, f"create_task.task_data: missing required field '{field}'")

    if "type" in td and td["type"] not in TASK_TYPES:
        _err(errors, f"create_task.task_data: invalid type {td['type']!r}")
    if "priority" in td and td["priority"] not in PRIORITIES:
        _err(errors, f"create_task.task_data: invalid priority {td['priority']!r}")
    if "category" in td and td["category"] not in CATEGORIES:
        _err(errors, f"create_task.task_data: invalid category {td['category']!r}")
    if "date" in td and not _is_date(td["date"]):
        _err(errors, f"create_task.task_data: 'date' must be YYYY-MM-DD")
    if "energy_cost" in td and td["energy_cost"] not in ENERGY_COSTS:
        _err(errors, f"create_task.task_data: invalid energy_cost {td['energy_cost']!r}")
    if "late_rule" in td and td["late_rule"] not in LATE_RULES:
        _err(errors, f"create_task.task_data: invalid late_rule {td['late_rule']!r}")
    if "late_rule_behavior" in td and td["late_rule_behavior"] not in LATE_RULE_BEHAVIORS:
        _err(errors, f"create_task.task_data: invalid late_rule_behavior {td['late_rule_behavior']!r}")
    if "time_block" in td and td["time_block"] not in TIME_BLOCKS:
        _err(errors, f"create_task.task_data: invalid time_block {td['time_block']!r}")
    if "xp" in td and not isinstance(td["xp"], int):
        _err(errors, "create_task.task_data: 'xp' must be an integer")
    if "gold" in td and not isinstance(td["gold"], int):
        _err(errors, "create_task.task_data: 'gold' must be an integer")


def _validate_create_effect(args, errors):
    ed = args.get("effect_data")
    if not isinstance(ed, dict):
        _err(errors, "create_effect: 'effect_data' must be an object")
        return

    required = ["effect", "type", "intensity", "duration_days", "suppresses_arc_pressure", "stat_offset"]
    for field in required:
        if field not in ed:
            _err(errors, f"create_effect.effect_data: missing required field '{field}'")

    if "type" in ed and ed["type"] not in EFFECT_TYPES:
        _err(errors, f"create_effect.effect_data: invalid type {ed['type']!r}")
    if "intensity" in ed:
        i = ed["intensity"]
        if not isinstance(i, int) or not (1 <= i <= 10):
            _err(errors, f"create_effect.effect_data: 'intensity' must be integer 1–10, got {i!r}")
    if "duration_days" in ed and not isinstance(ed["duration_days"], int):
        _err(errors, "create_effect.effect_data: 'duration_days' must be an integer")
    if "suppresses_arc_pressure" in ed and not isinstance(ed["suppresses_arc_pressure"], bool):
        _err(errors, "create_effect.effect_data: 'suppresses_arc_pressure' must be a boolean")
    if "stat_offset" in ed and not isinstance(ed["stat_offset"], int):
        _err(errors, "create_effect.effect_data: 'stat_offset' must be an integer")


def _validate_update_arc_status(args, errors):
    if "arc_id" not in args:
        _err(errors, "update_arc_status: missing required arg 'arc_id'")
    elif not _is_uuid(args["arc_id"]):
        _err(errors, "update_arc_status: 'arc_id' must be a UUID")
    if "status" not in args:
        _err(errors, "update_arc_status: missing required arg 'status'")
    elif args["status"] not in ARC_STATUSES:
        _err(errors, f"update_arc_status: invalid status {args['status']!r}")


def _validate_end_day(args, errors):
    if "date" not in args:
        _err(errors, "end_day: missing required arg 'date'")
    elif not _is_date(args["date"]):
        _err(errors, "end_day: 'date' must be YYYY-MM-DD")


# ── Dispatch table ─────────────────────────────────────────────────────────────

_VALIDATORS = {
    "error": _validate_error,
    "get_player_state": _validate_get_player_state,
    "get_today": _validate_get_today,
    "get_tasks": _validate_get_tasks,
    "get_task": _validate_get_task,
    "get_skill_links": _validate_get_skill_links,
    "get_active_effects": _validate_get_active_effects,
    "get_active_arcs": _validate_get_active_arcs,
    "tick_day": _validate_tick_day,
    "complete_task": _validate_complete_task,
    "log_event": _validate_log_event,
    "create_task": _validate_create_task,
    "create_effect": _validate_create_effect,
    "update_arc_status": _validate_update_arc_status,
    "end_day": _validate_end_day,
}


# ── Public API ─────────────────────────────────────────────────────────────────

def validate(output: dict) -> dict:
    """
    Validate SLM output dict.

    Returns:
        {"valid": True,  "action": str, "args": dict}  on success
        {"valid": False, "errors": list[str]}           on failure
    """
    errors = []

    if not isinstance(output, dict):
        return {"valid": False, "errors": ["Output must be a JSON object"]}

    action = output.get("action")
    args = output.get("args")

    if not action or not isinstance(action, str):
        errors.append("Missing or invalid 'action' field")

    if args is None or not isinstance(args, dict):
        errors.append("Missing or invalid 'args' field (must be an object)")

    if errors:
        return {"valid": False, "errors": errors}

    if action not in _VALIDATORS:
        return {"valid": False, "errors": [f"Unknown action '{action}'"]}

    _VALIDATORS[action](args, errors)

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True, "action": action, "args": args}
