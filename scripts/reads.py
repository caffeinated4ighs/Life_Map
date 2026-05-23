"""
reads.py — All read scripts for the Life System.

Every function takes explicit named arguments, makes only SELECT queries,
and returns a dict or list[dict] matching the shapes in 00_SHARED_CONTEXT.md.
Functions never raise — unknown / missing data returns empty structures.
"""

from __future__ import annotations

import sys
from datetime import datetime

from .db import get_client
from .logic import get_arc_modifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_error(fn_name: str, exc: Exception) -> None:
    ts = datetime.utcnow().isoformat()
    print(f"[{ts}] ERROR in reads.{fn_name}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# get_player_state
# ---------------------------------------------------------------------------

def get_player_state() -> dict:
    """
    Return the singleton player_state row.

    Shape: {mh_score, mh_mode, gold_balance, streak_count, total_xp}
    """
    try:
        sb = get_client()
        res = (
            sb.table("player_state")
            .select("mh_score, mh_mode, gold_balance, streak_count, total_xp")
            .eq("id", 1)
            .single()
            .execute()
        )
        return res.data or {}
    except Exception as exc:
        _log_error("get_player_state", exc)
        return {}


# ---------------------------------------------------------------------------
# get_today
# ---------------------------------------------------------------------------

def get_today(date: str) -> dict:
    """
    Return the day_snapshot for the given date, enriched with streak_count
    from player_state and the list of active anchors.

    Adds `needs_init: bool` — True when no snapshot row exists yet for the date.

    Shape: {date, mh_score_open, mh_mode, gold_open, xp_earned, steps,
            streak_count, anchors_active[], needs_init}
    """
    try:
        sb = get_client()

        # Day snapshot
        snap_res = (
            sb.table("day_snapshots")
            .select("id, date, mh_score_open, mh_mode, gold_open, xp_earned, steps")
            .eq("date", date)
            .execute()
        )
        snap_rows = snap_res.data or []

        # Player streak (always fresh)
        ps = get_player_state()
        streak_count = ps.get("streak_count", 0)

        if not snap_rows:
            return {
                "date": date,
                "mh_score_open": None,
                "mh_mode": None,
                "gold_open": None,
                "xp_earned": 0,
                "steps": 0,
                "streak_count": streak_count,
                "anchors_active": [],
                "needs_init": True,
            }

        snap = snap_rows[0]
        snapshot_id = snap["id"]

        # Active anchors linked to this snapshot
        anchors_res = (
            sb.table("snapshot_anchors")
            .select("anchor_id, anchors(anchor, type, time)")
            .eq("snapshot_id", snapshot_id)
            .execute()
        )
        anchors_active = []
        for row in anchors_res.data or []:
            anchor_data = row.get("anchors") or {}
            anchors_active.append({
                "anchor_id": row["anchor_id"],
                "anchor": anchor_data.get("anchor"),
                "type": anchor_data.get("type"),
                "time": anchor_data.get("time"),
            })

        return {
            "date": snap["date"],
            "mh_score_open": snap["mh_score_open"],
            "mh_mode": snap["mh_mode"],
            "gold_open": snap["gold_open"],
            "xp_earned": snap.get("xp_earned", 0),
            "steps": snap.get("steps", 0),
            "streak_count": streak_count,
            "anchors_active": anchors_active,
            "needs_init": False,
        }
    except Exception as exc:
        _log_error("get_today", exc)
        return {
            "date": date,
            "mh_score_open": None,
            "mh_mode": None,
            "gold_open": None,
            "xp_earned": 0,
            "steps": 0,
            "streak_count": 0,
            "anchors_active": [],
            "needs_init": True,
        }


# ---------------------------------------------------------------------------
# get_tasks
# ---------------------------------------------------------------------------

# MH mode → which energy_cost values to SUPPRESS (i.e. hide)
_MH_SUPPRESSED_ENERGY: dict[str, set[str]] = {
    "Normal":          set(),
    "Reduced":         {"High", "Very High"},
    "Minimum Viable":  {"Medium", "High", "Very High"},
    "Recovery Only":   {"Low", "Medium", "High", "Very High"},
}


def get_tasks(date: str, mh_mode: str) -> list[dict]:
    """
    Return non-done, non-blocked, non-deferred tasks for the date,
    filtered by MH mode.

    Mandatory tasks always pass the MH filter regardless of energy_cost.

    Shape per item: {id, task, type, priority, energy_cost, late_rule,
                     late_rule_behavior, xp, gold, arcs[], skills[],
                     mandatory, time_block}
    """
    try:
        sb = get_client()

        res = (
            sb.table("tasks")
            .select(
                "id, task, type, priority, energy_cost, late_rule, "
                "late_rule_behavior, xp, gold, mandatory, time_block, "
                "status, blocked, deferred"
            )
            .eq("date", date)
            .neq("status", "Done")
            .eq("blocked", False)
            .eq("deferred", False)
            .execute()
        )
        rows = res.data or []

        suppressed = _MH_SUPPRESSED_ENERGY.get(mh_mode, set())

        result = []
        for task in rows:
            # Mandatory tasks always show; all others respect MH filter
            if not task.get("mandatory") and task.get("energy_cost") in suppressed:
                continue

            task_id = task["id"]

            # Linked arcs
            arc_res = (
                sb.table("arc_tasks")
                .select("arc_id, arcs(arc, weight)")
                .eq("task_id", task_id)
                .execute()
            )
            arcs = []
            for ar in arc_res.data or []:
                arc_data = ar.get("arcs") or {}
                arcs.append({
                    "arc_id": ar["arc_id"],
                    "arc": arc_data.get("arc"),
                    "weight": arc_data.get("weight"),
                })

            # Linked skills
            skill_res = (
                sb.table("task_skill_links")
                .select("skill_id, crossover_level, skills(skill)")
                .eq("task_id", task_id)
                .execute()
            )
            skills = []
            for sr in skill_res.data or []:
                skill_data = sr.get("skills") or {}
                skills.append({
                    "skill_id": sr["skill_id"],
                    "skill": skill_data.get("skill"),
                    "crossover_level": sr["crossover_level"],
                })

            result.append({
                "id": task_id,
                "task": task["task"],
                "type": task["type"],
                "priority": task["priority"],
                "energy_cost": task["energy_cost"],
                "late_rule": task["late_rule"],
                "late_rule_behavior": task["late_rule_behavior"],
                "xp": task["xp"],
                "gold": task["gold"],
                "mandatory": task.get("mandatory", False),
                "time_block": task.get("time_block"),
                "arcs": arcs,
                "skills": skills,
            })

        return result
    except Exception as exc:
        _log_error("get_tasks", exc)
        return []


# ---------------------------------------------------------------------------
# get_task
# ---------------------------------------------------------------------------

def get_task(task_id: str) -> dict:
    """
    Return full task fields plus resolved arc_modifier and suppression_active.

    arc_modifier: resolved by calling logic.get_arc_modifier() with the
                  weights of all active arcs linked to this task.
    suppression_active: True if any active effect has suppresses_arc_pressure=True.

    Returns {} when task not found.
    """
    try:
        sb = get_client()

        task_res = (
            sb.table("tasks")
            .select("*")
            .eq("id", task_id)
            .single()
            .execute()
        )
        task = task_res.data
        if not task:
            return {}

        # Active arcs for this task
        arc_res = (
            sb.table("arc_tasks")
            .select("arcs(weight, status)")
            .eq("task_id", task_id)
            .execute()
        )
        arc_weights = []
        for ar in arc_res.data or []:
            arc_data = ar.get("arcs") or {}
            if arc_data.get("status") == "Active":
                weight = arc_data.get("weight")
                if weight:
                    arc_weights.append(weight)

        arc_modifier = get_arc_modifier(arc_weights)

        # Check if any active effect suppresses arc pressure
        effect_res = (
            sb.table("effects")
            .select("suppresses_arc_pressure")
            .eq("active", True)
            .eq("suppresses_arc_pressure", True)
            .execute()
        )
        suppression_active = bool(effect_res.data)

        return {
            **task,
            "arc_modifier": arc_modifier,
            "suppression_active": suppression_active,
        }
    except Exception as exc:
        _log_error("get_task", exc)
        return {}


# ---------------------------------------------------------------------------
# get_skill_links
# ---------------------------------------------------------------------------

def get_skill_links(task_id: str) -> list[dict]:
    """
    Return skill links for a task.

    Shape per item: {skill_id, skill_name, crossover_level}
    """
    try:
        sb = get_client()

        res = (
            sb.table("task_skill_links")
            .select("skill_id, crossover_level, skills(skill)")
            .eq("task_id", task_id)
            .execute()
        )
        result = []
        for row in res.data or []:
            skill_data = row.get("skills") or {}
            result.append({
                "skill_id": row["skill_id"],
                "skill_name": skill_data.get("skill"),
                "crossover_level": row["crossover_level"],
            })
        return result
    except Exception as exc:
        _log_error("get_skill_links", exc)
        return []


# ---------------------------------------------------------------------------
# get_active_effects
# ---------------------------------------------------------------------------

def get_active_effects() -> list[dict]:
    """
    Return all currently active effects.

    Shape per item: {effect, type, intensity, suppresses_arc_pressure,
                     stat_offset, linked_stats[]}
    """
    try:
        sb = get_client()

        res = (
            sb.table("effects")
            .select(
                "id, effect, type, intensity, suppresses_arc_pressure, stat_offset"
            )
            .eq("active", True)
            .execute()
        )
        effects = res.data or []

        result = []
        for eff in effects:
            eff_id = eff["id"]

            # Linked stats
            stat_res = (
                sb.table("effect_stats")
                .select("stat_id, stats(stat)")
                .eq("effect_id", eff_id)
                .execute()
            )
            linked_stats = []
            for sr in stat_res.data or []:
                stat_data = sr.get("stats") or {}
                linked_stats.append({
                    "stat_id": sr["stat_id"],
                    "stat": stat_data.get("stat"),
                })

            result.append({
                "effect": eff["effect"],
                "type": eff["type"],
                "intensity": eff["intensity"],
                "suppresses_arc_pressure": eff.get("suppresses_arc_pressure", False),
                "stat_offset": eff.get("stat_offset", 0),
                "linked_stats": linked_stats,
            })

        return result
    except Exception as exc:
        _log_error("get_active_effects", exc)
        return []


# ---------------------------------------------------------------------------
# get_active_arcs
# ---------------------------------------------------------------------------

def get_active_arcs() -> list[dict]:
    """
    Return all currently active arcs with their boosted skills.

    Shape per item: {arc, weight, skills_boosted[]}
    """
    try:
        sb = get_client()

        res = (
            sb.table("arcs")
            .select("id, arc, weight")
            .eq("status", "Active")
            .execute()
        )
        arcs = res.data or []

        result = []
        for arc in arcs:
            arc_id = arc["id"]

            skill_res = (
                sb.table("arc_skills")
                .select("skill_id, skills(skill)")
                .eq("arc_id", arc_id)
                .execute()
            )
            skills_boosted = []
            for sr in skill_res.data or []:
                skill_data = sr.get("skills") or {}
                skills_boosted.append({
                    "skill_id": sr["skill_id"],
                    "skill": skill_data.get("skill"),
                })

            result.append({
                "arc": arc["arc"],
                "weight": arc["weight"],
                "skills_boosted": skills_boosted,
            })

        return result
    except Exception as exc:
        _log_error("get_active_arcs", exc)
        return []

# ---------------------------------------------------------------------------
# get_skills
# ---------------------------------------------------------------------------

def get_skills() -> list[dict]:
    """
    Return all skills ordered by skill name.
    """
    try:
        sb = get_client()
        res = (
            sb.table("skills")
            .select(
                "id, skill, current_level, xp_accumulated, xp_to_next_level, "
                "decay_rate, last_active, in_decay, primary_stat_id, secondary_stat_id"
            )
            .order("skill")
            .execute()
        )
        return res.data or []
    except Exception as exc:
        _log_error("get_skills", exc)
        return []


# ---------------------------------------------------------------------------
# get_skill
# ---------------------------------------------------------------------------

def get_skill(skill_id: str) -> dict:
    """
    Return a single skill by UUID. Return {} if not found.
    """
    try:
        sb = get_client()
        res = (
            sb.table("skills")
            .select(
                "id, skill, current_level, xp_accumulated, xp_to_next_level, "
                "decay_rate, last_active, in_decay, primary_stat_id, secondary_stat_id"
            )
            .eq("id", skill_id)
            .execute()
        )
        data = res.data or []
        return data[0] if data else {}
    except Exception as exc:
        _log_error("get_skill", exc)
        return {}


# ---------------------------------------------------------------------------
# get_arcs
# ---------------------------------------------------------------------------

def get_arcs() -> list[dict]:
    """
    Return all arcs regardless of status, ordered by start_date desc.
    """
    try:
        sb = get_client()
        res = (
            sb.table("arcs")
            .select("id, arc, status, weight, start_date, end_date")
            .order("start_date", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        _log_error("get_arcs", exc)
        return []


# ---------------------------------------------------------------------------
# get_arc
# ---------------------------------------------------------------------------

def get_arc(arc_id: str) -> dict:
    """
    Return a single arc by UUID with its linked tasks and linked skills.
    Return {} if not found.
    """
    try:
        sb = get_client()

        res = (
            sb.table("arcs")
            .select("id, arc, status, weight, start_date, end_date")
            .eq("id", arc_id)
            .execute()
        )
        data = res.data or []
        if not data:
            return {}
        arc = data[0]

        # Linked tasks
        task_res = (
            sb.table("arc_tasks")
            .select("task_id, tasks(task, status)")
            .eq("arc_id", arc_id)
            .execute()
        )
        tasks = []
        for row in task_res.data or []:
            task_data = row.get("tasks") or {}
            tasks.append({
                "task_id": row["task_id"],
                "task": task_data.get("task"),
                "status": task_data.get("status"),
            })

        # Linked skills
        skill_res = (
            sb.table("arc_skills")
            .select("skill_id, skills(skill)")
            .eq("arc_id", arc_id)
            .execute()
        )
        skills = []
        for row in skill_res.data or []:
            skill_data = row.get("skills") or {}
            skills.append({
                "skill_id": row["skill_id"],
                "skill": skill_data.get("skill"),
            })

        arc["tasks"] = tasks
        arc["skills"] = skills
        return arc
    except Exception as exc:
        _log_error("get_arc", exc)
        return {}


# ---------------------------------------------------------------------------
# get_arc_tasks
# ---------------------------------------------------------------------------

def get_arc_tasks(arc_id: str) -> list[dict]:
    """
    Return all tasks linked to a given arc.
    """
    try:
        sb = get_client()
        res = (
            sb.table("arc_tasks")
            .select("task_id, tasks(task, status, date, priority)")
            .eq("arc_id", arc_id)
            .execute()
        )
        result = []
        for row in res.data or []:
            task_data = row.get("tasks") or {}
            result.append({
                "task_id": row["task_id"],
                "task": task_data.get("task"),
                "status": task_data.get("status"),
                "date": task_data.get("date"),
                "priority": task_data.get("priority"),
            })
        return result
    except Exception as exc:
        _log_error("get_arc_tasks", exc)
        return []


# ---------------------------------------------------------------------------
# get_effects
# ---------------------------------------------------------------------------

def get_effects() -> list[dict]:
    """
    Return all effects (active and inactive), ordered by created_on desc.
    """
    try:
        sb = get_client()
        res = (
            sb.table("effects")
            .select(
                "id, effect, type, intensity, active, suppresses_arc_pressure, "
                "duration_days, created_on, expires_on, stat_offset"
            )
            .order("created_on", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        _log_error("get_effects", exc)
        return []


# ---------------------------------------------------------------------------
# get_effect
# ---------------------------------------------------------------------------

def get_effect(effect_id: str) -> dict:
    """
    Return a single effect by UUID with its linked stats and linked arcs.
    Return {} if not found.
    """
    try:
        sb = get_client()

        res = (
            sb.table("effects")
            .select(
                "id, effect, type, intensity, active, suppresses_arc_pressure, "
                "duration_days, created_on, expires_on, stat_offset"
            )
            .eq("id", effect_id)
            .execute()
        )
        data = res.data or []
        if not data:
            return {}
        effect = data[0]

        # Linked stats
        stat_res = (
            sb.table("effect_stats")
            .select("stat_id, stats(stat)")
            .eq("effect_id", effect_id)
            .execute()
        )
        linked_stats = []
        for row in stat_res.data or []:
            stat_data = row.get("stats") or {}
            linked_stats.append({
                "stat_id": row["stat_id"],
                "stat": stat_data.get("stat"),
            })

        # Linked arcs
        arc_res = (
            sb.table("effect_arcs")
            .select("arc_id, arcs(arc)")
            .eq("effect_id", effect_id)
            .execute()
        )
        linked_arcs = []
        for row in arc_res.data or []:
            arc_data = row.get("arcs") or {}
            linked_arcs.append({
                "arc_id": row["arc_id"],
                "arc": arc_data.get("arc"),
            })

        effect["linked_stats"] = linked_stats
        effect["linked_arcs"] = linked_arcs
        return effect
    except Exception as exc:
        _log_error("get_effect", exc)
        return {}


# ---------------------------------------------------------------------------
# get_anchors
# ---------------------------------------------------------------------------

def get_anchors(date: str) -> list[dict]:
    """
    Return all anchors for a given date.
    """
    try:
        sb = get_client()
        res = (
            sb.table("anchors")
            .select("id, anchor, type, date, time, priority_pressure")
            .eq("date", date)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        _log_error("get_anchors", exc)
        return []


# ---------------------------------------------------------------------------
# get_snapshot
# ---------------------------------------------------------------------------

def get_snapshot(date: str) -> dict:
    """
    Return the day_snapshots row for a given date. Return {} if none exists.
    """
    try:
        sb = get_client()
        res = (
            sb.table("day_snapshots")
            .select(
                "id, date, mh_score_open, mh_score_close, mh_mode, "
                "gold_open, gold_close, xp_earned, steps"
            )
            .eq("date", date)
            .execute()
        )
        data = res.data or []
        return data[0] if data else {}
    except Exception as exc:
        _log_error("get_snapshot", exc)
        return {}


# ---------------------------------------------------------------------------
# get_streak_log
# ---------------------------------------------------------------------------

def get_streak_log(limit: int = 7) -> list[dict]:
    """
    Return the most recent `limit` rows from streak_log, ordered by date desc.
    """
    try:
        sb = get_client()
        res = (
            sb.table("streak_log")
            .select("date, streak_count, mandatory_met")
            .order("date", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        _log_error("get_streak_log", exc)
        return []


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

def get_stats() -> list[dict]:
    """
    Return all stat rows ordered by stat name.
    """
    try:
        sb = get_client()
        res = (
            sb.table("stats")
            .select("id, stat, current_value, last_updated")
            .order("stat")
            .execute()
        )
        return res.data or []
    except Exception as exc:
        _log_error("get_stats", exc)
        return []


# ---------------------------------------------------------------------------
# get_stat
# ---------------------------------------------------------------------------

def get_stat(stat_id: str) -> dict:
    """
    Return a single stat by UUID. Return {} if not found.
    """
    try:
        sb = get_client()
        res = (
            sb.table("stats")
            .select("id, stat, current_value, last_updated")
            .eq("id", stat_id)
            .execute()
        )
        data = res.data or []
        return data[0] if data else {}
    except Exception as exc:
        _log_error("get_stat", exc)
        return {}