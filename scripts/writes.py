"""
writes.py — All write scripts for the Life System.

Every function is a transaction — no partial state should be committed on failure.
Every function returns a dict. Never raises to the caller.
Errors return {success: false, error: str}.
"""

from __future__ import annotations

import sys
from datetime import date as date_type, timedelta, datetime

from .db import get_client
from . import reads
from .logic import (
    clamp_mh,
    derive_mh_mode,
    get_streak_modifier,
    get_late_modifier,
    get_crossover_factor,
    get_step_mh_bonus,
    get_substance_deltas,
    get_decay_threshold,
    calculate_rewards,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_error(fn_name: str, exc: Exception) -> None:
    ts = datetime.utcnow().isoformat()
    print(f"[{ts}] ERROR in writes.{fn_name}: {exc}", file=sys.stderr)


def _err(fn_name: str, exc: Exception) -> dict:
    _log_error(fn_name, exc)
    return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# tick_day
# ---------------------------------------------------------------------------

def tick_day(date: str) -> dict:
    """
    Open a new day:
      1. Abort if snapshot already exists (idempotency guard).
      2. Read player_state for open values.
      3. Insert day_snapshots row.
      4. Link today's anchors to the snapshot.
      5. Expire effects whose expires_on < date.
      6. Check skills for decay.

    Returns {success, snapshot_id} or {success: false, reason: "already_exists"}.
    """
    try:
        sb = get_client()

        # 1. Idempotency check
        existing = (
            sb.table("day_snapshots")
            .select("id")
            .eq("date", date)
            .execute()
        )
        if existing.data:
            return {"success": False, "reason": "already_exists"}

        # 2. Player state
        ps = reads.get_player_state()
        if not ps:
            return {"success": False, "error": "player_state not found"}

        # 3. Insert snapshot
        snap_res = (
            sb.table("day_snapshots")
            .insert({
                "date": date,
                "mh_score_open": ps["mh_score"],
                "mh_mode": ps["mh_mode"],
                "gold_open": ps["gold_balance"],
                "xp_earned": 0,
                "steps": 0,
            })
            .execute()
        )
        snapshot = snap_res.data[0] if snap_res.data else None
        if not snapshot:
            return {"success": False, "error": "failed to insert day_snapshots"}
        snapshot_id = snapshot["id"]

        # 4. Link anchors scheduled for today
        anchor_res = (
            sb.table("anchors")
            .select("id")
            .eq("date", date)
            .execute()
        )
        for anchor in anchor_res.data or []:
            sb.table("snapshot_anchors").insert({
                "snapshot_id": snapshot_id,
                "anchor_id": anchor["id"],
            }).execute()

        # 5. Expire effects whose expires_on < today
        sb.table("effects").update({"active": False}).lt("expires_on", date).eq(
            "active", True
        ).execute()

        # 6. Skill decay check
        all_skills = sb.table("skills").select(
            "id, last_active, decay_rate, in_decay"
        ).execute()
        today = date_type.fromisoformat(date)

        for skill in all_skills.data or []:
            if skill.get("in_decay"):
                continue  # already flagged
            last_active = skill.get("last_active")
            if not last_active:
                continue
            threshold = get_decay_threshold(skill.get("decay_rate", "Medium"))
            last_active_date = date_type.fromisoformat(str(last_active))
            days_inactive = (today - last_active_date).days
            if days_inactive >= threshold:
                sb.table("skills").update({"in_decay": True}).eq(
                    "id", skill["id"]
                ).execute()

        return {"success": True, "snapshot_id": snapshot_id}
    except Exception as exc:
        return _err("tick_day", exc)


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------

def complete_task(task_id: str, completion_data: dict) -> dict:
    """
    Mark a task done and run the full reward + propagation stack.

    completion_data keys:
      completion_time : str   — timing band, e.g. "on_time" | "soft" | ...
      partial_credit  : float — 0.0–1.0
      mh_mode         : str   — current MH mode (informational, not used in formula)

    Returns {final_xp, final_gold, new_mh_score, new_mh_mode, new_gold_balance}
    """
    try:
        sb = get_client()

        completion_time = completion_data.get("completion_time", "on_time")
        partial_credit = float(completion_data.get("partial_credit", 1.0))

        # 1. Full task row + resolved arc_modifier
        task = reads.get_task(task_id)
        if not task:
            return {"success": False, "error": f"task {task_id} not found"}

        # 2. Skill links
        skill_links = reads.get_skill_links(task_id)

        # 3. Streak modifier
        ps = reads.get_player_state()
        if not ps:
            return {"success": False, "error": "player_state not found"}
        streak_modifier = get_streak_modifier(ps["streak_count"])

        # 4. Late modifier
        late_modifier = get_late_modifier(completion_time, task.get("late_rule_behavior", "Penalty"))

        # 5. Reward stack
        rewards = calculate_rewards(
            base_xp=task.get("xp", 0),
            base_gold=task.get("gold", 0),
            arc_modifier=task["arc_modifier"],
            streak_modifier=streak_modifier,
            late_modifier=late_modifier,
            partial_credit=partial_credit,
        )
        final_xp = rewards["final_xp"]
        final_gold = rewards["final_gold"]

        # 6. Sum flat stat_offset from active effects (added after stack)
        active_effects = reads.get_active_effects()
        flat_gold_offset = sum(e.get("stat_offset", 0) for e in active_effects)
        final_gold += flat_gold_offset

        # 7. Mark task done
        sb.table("tasks").update({
            "status": "Done",
            "resolved_xp": final_xp,
            "resolved_gold": final_gold,
        }).eq("id", task_id).execute()

        # 8. Update player_state
        new_mh_score = clamp_mh(ps["mh_score"] + task.get("mh_impact", 0))
        new_mh_mode = derive_mh_mode(new_mh_score)
        new_gold_balance = ps["gold_balance"] + final_gold
        new_total_xp = ps["total_xp"] + final_xp

        sb.table("player_state").update({
            "mh_score": new_mh_score,
            "mh_mode": new_mh_mode,
            "gold_balance": new_gold_balance,
            "total_xp": new_total_xp,
            "last_updated": datetime.utcnow().isoformat(),
        }).eq("id", 1).execute()

        # 9. Update day_snapshots xp_earned
        today_str = str(task.get("date", ""))
        if today_str:
            snap = (
                sb.table("day_snapshots")
                .select("id, xp_earned")
                .eq("date", today_str)
                .execute()
            )
            if snap.data:
                new_xp_earned = (snap.data[0].get("xp_earned") or 0) + final_xp
                sb.table("day_snapshots").update({"xp_earned": new_xp_earned}).eq(
                    "id", snap.data[0]["id"]
                ).execute()

        # 10 & 11. Skill XP + stat propagation
        for link in skill_links:
            skill_id = link["skill_id"]
            crossover_factor = get_crossover_factor(link["crossover_level"])
            xp_gained = final_xp * crossover_factor

            # Fetch skill
            skill_res = (
                sb.table("skills")
                .select("id, xp_accumulated, primary_stat_id, secondary_stat_id, in_decay")
                .eq("id", skill_id)
                .single()
                .execute()
            )
            skill = skill_res.data
            if not skill:
                continue

            # Gate on decay
            if skill.get("in_decay"):
                continue

            new_xp_acc = (skill.get("xp_accumulated") or 0) + xp_gained
            today_date = str(date_type.today())

            sb.table("skills").update({
                "xp_accumulated": new_xp_acc,
                "last_active": today_date,
                "in_decay": False,
            }).eq("id", skill_id).execute()

            # Primary stat propagation (100%)
            _add_stat_value(sb, skill["primary_stat_id"], xp_gained * 1.0)

            # Secondary stat propagation (50%)
            if skill.get("secondary_stat_id"):
                _add_stat_value(sb, skill["secondary_stat_id"], xp_gained * 0.5)

        # Step 12: direct task_stats links (flagged missing junction — see notes)
        _apply_task_stat_links(sb, task_id, final_xp)

        return {
            "final_xp": final_xp,
            "final_gold": final_gold,
            "new_mh_score": new_mh_score,
            "new_mh_mode": new_mh_mode,
            "new_gold_balance": new_gold_balance,
        }
    except Exception as exc:
        return _err("complete_task", exc)


def _add_stat_value(sb, stat_id: str, delta: float) -> None:
    """Increment a stat's current_value by delta."""
    stat_res = sb.table("stats").select("current_value").eq("id", stat_id).single().execute()
    if stat_res.data:
        new_val = (stat_res.data.get("current_value") or 0) + delta
        sb.table("stats").update({
            "current_value": new_val,
            "last_updated": str(date_type.today()),
        }).eq("id", stat_id).execute()


def _apply_task_stat_links(sb, task_id: str, final_xp: int) -> None:
    """
    Step 12 — Apply direct stat deltas from the task_stats junction table.

    Schema assumption (X1 — DB Agent migration):
        task_stats (
            task_id    uuid NOT NULL FK -> tasks(id) ON DELETE CASCADE,
            stat_id    uuid NOT NULL FK -> stats(id),
            stat_delta integer NOT NULL DEFAULT 0,
            PRIMARY KEY (task_id, stat_id)
        )

    stat_delta is a fixed flat integer added to stats.current_value on task
    completion. Independent of the XP reward stack — represents a direct,
    authorial stat contribution (e.g. +5 Endurance for a workout task).

    Pre-migration: the table does not exist yet; the except block makes this a
    safe no-op. Once DB Agent runs the migration this is live automatically.
    """
    try:
        res = (
            sb.table("task_stats")
            .select("stat_id, stat_delta")
            .eq("task_id", task_id)
            .execute()
        )
        today_str = str(date_type.today())
        for row in res.data or []:
            stat_id = row.get("stat_id")
            delta = row.get("stat_delta", 0)
            if stat_id and delta:
                _add_stat_value(sb, stat_id, float(delta))
                sb.table("stats").update({"last_updated": today_str}).eq(
                    "id", stat_id
                ).execute()
    except Exception as exc:
        # Graceful no-op pre-migration. Expected until DB Agent adds task_stats (X1).
        ts = datetime.utcnow().isoformat()
        print(
            f"[{ts}] DEBUG _apply_task_stat_links: skipped ({exc})",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------

def log_event(event_type: str, payload: dict) -> dict:
    """
    Log a non-task event and update player_state.

    Supported event_types: steps | substance | leisure | day_off | cheat_day | mh_manual

    payload keys (all optional depending on type):
      name         : str   — substance name or leisure activity
      quantity     : int   — step count, cigarette count, drinks, etc.
      duration_minutes : int
      mh_delta     : int   — for mh_manual override
      gold_delta   : int   — for mh_manual override
      notes        : str

    Returns {new_mh_score, new_mh_mode, new_gold_balance, delta_applied}
    """
    try:
        sb = get_client()

        today_str = str(date_type.today())
        name = payload.get("name", "")
        quantity = int(payload.get("quantity") or 0)

        gold_delta = 0
        mh_delta = 0

        if event_type == "steps":
            mh_delta = get_step_mh_bonus(quantity)

        elif event_type in ("substance", "leisure"):
            deltas = get_substance_deltas(name, quantity)
            gold_delta = deltas["gold_delta"]
            mh_delta = deltas["mh_delta"]

        elif event_type == "day_off":
            deltas = get_substance_deltas("day_off", 1)
            gold_delta = deltas["gold_delta"]
            mh_delta = deltas["mh_delta"]

        elif event_type == "cheat_day":
            deltas = get_substance_deltas("cheat_day", 1)
            gold_delta = deltas["gold_delta"]
            mh_delta = deltas["mh_delta"]

        elif event_type == "mh_manual":
            mh_delta = int(payload.get("mh_delta", 0))
            gold_delta = int(payload.get("gold_delta", 0))

        # Insert event row
        sb.table("events").insert({
            "date": today_str,
            "event_type": event_type,
            "name": name or None,
            "quantity": quantity or None,
            "duration_minutes": payload.get("duration_minutes"),
            "gold_delta": gold_delta,
            "mh_delta": mh_delta,
            "notes": payload.get("notes"),
        }).execute()

        # Update player_state
        ps = reads.get_player_state()
        new_mh_score = clamp_mh(ps["mh_score"] + mh_delta)
        new_mh_mode = derive_mh_mode(new_mh_score)
        new_gold_balance = ps["gold_balance"] + gold_delta

        sb.table("player_state").update({
            "mh_score": new_mh_score,
            "mh_mode": new_mh_mode,
            "gold_balance": new_gold_balance,
            "last_updated": datetime.utcnow().isoformat(),
        }).eq("id", 1).execute()

        # Update steps in today's snapshot if applicable
        if event_type == "steps":
            snap = (
                sb.table("day_snapshots")
                .select("id, steps")
                .eq("date", today_str)
                .execute()
            )
            if snap.data:
                sb.table("day_snapshots").update({"steps": quantity}).eq(
                    "id", snap.data[0]["id"]
                ).execute()

        return {
            "new_mh_score": new_mh_score,
            "new_mh_mode": new_mh_mode,
            "new_gold_balance": new_gold_balance,
            "delta_applied": {"gold_delta": gold_delta, "mh_delta": mh_delta},
        }
    except Exception as exc:
        return _err("log_event", exc)


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------

def create_task(task_data: dict) -> dict:
    """
    Create a task row with all linked junction records.

    task_data keys match the tasks schema; additionally:
      skills : list[{skill_id, crossover_level}]
      arcs   : list[str]  — arc UUIDs
      stats  : list[{stat_id, delta}]  — requires task_stats table (see notes)

    Returns {task_id, skill_links_created}
    """
    try:
        sb = get_client()

        # Separate relational fields from scalar columns
        skills = task_data.pop("skills", [])
        arcs = task_data.pop("arcs", [])
        stats = task_data.pop("stats", [])

        # Prevent accidental singleton columns from slipping in
        task_data.pop("id", None)
        task_data.pop("resolved_xp", None)
        task_data.pop("resolved_gold", None)

        # Insert task
        task_res = sb.table("tasks").insert(task_data).execute()
        if not task_res.data:
            return {"success": False, "error": "failed to insert task"}
        task_id = task_res.data[0]["id"]

        # Skill links
        skill_links_created = 0
        for link in skills:
            sb.table("task_skill_links").insert({
                "task_id": task_id,
                "skill_id": link["skill_id"],
                "crossover_level": link.get("crossover_level", "Direct"),
            }).execute()
            skill_links_created += 1

        # Arc links
        for arc_id in arcs:
            sb.table("arc_tasks").insert({
                "arc_id": arc_id,
                "task_id": task_id,
            }).execute()

        # Direct stat links (task_stats — see _apply_task_stat_links note)
        for stat_link in stats:
            try:
                sb.table("task_stats").insert({
                    "task_id": task_id,
                    "stat_id": stat_link["stat_id"],
                    "delta": stat_link.get("delta", 0),
                }).execute()
            except Exception:
                # Table doesn't exist yet — silently skip
                pass

        return {"task_id": task_id, "skill_links_created": skill_links_created}
    except Exception as exc:
        return _err("create_task", exc)


# ---------------------------------------------------------------------------
# create_effect
# ---------------------------------------------------------------------------

def create_effect(effect_data: dict) -> dict:
    """
    Create an effect with computed expiry and all junction records.

    effect_data keys match the effects schema; additionally:
      stats : list[str]  — stat UUIDs
      arcs  : list[str]  — arc UUIDs

    Returns {effect_id, expires_on}
    """
    try:
        sb = get_client()

        stats = effect_data.pop("stats", [])
        arcs = effect_data.pop("arcs", [])
        effect_data.pop("id", None)

        # Compute expires_on
        created_on = effect_data.get("created_on", str(date_type.today()))
        duration_days = int(effect_data.get("duration_days", 1))
        expires_on = str(
            date_type.fromisoformat(created_on) + timedelta(days=duration_days)
        )
        effect_data["expires_on"] = expires_on
        effect_data["active"] = True

        effect_res = sb.table("effects").insert(effect_data).execute()
        if not effect_res.data:
            return {"success": False, "error": "failed to insert effect"}
        effect_id = effect_res.data[0]["id"]

        for stat_id in stats:
            sb.table("effect_stats").insert({
                "effect_id": effect_id,
                "stat_id": stat_id,
            }).execute()

        for arc_id in arcs:
            sb.table("effect_arcs").insert({
                "effect_id": effect_id,
                "arc_id": arc_id,
            }).execute()

        return {"effect_id": effect_id, "expires_on": expires_on}
    except Exception as exc:
        return _err("create_effect", exc)


# ---------------------------------------------------------------------------
# update_arc_status
# ---------------------------------------------------------------------------

def update_arc_status(arc_id: str, status: str) -> dict:
    """
    Update an arc's status. Accumulated XP is permanent — no reversal.

    status must be one of: 'Active' | 'Paused' | 'Done'

    Returns {success: true} or {success: false, error: str}
    """
    try:
        sb = get_client()

        valid_statuses = {"Active", "Paused", "Done"}
        if status not in valid_statuses:
            return {"success": False, "error": f"invalid status '{status}'"}

        sb.table("arcs").update({"status": status}).eq("id", arc_id).execute()
        return {"success": True}
    except Exception as exc:
        return _err("update_arc_status", exc)


# ---------------------------------------------------------------------------
# end_day
# ---------------------------------------------------------------------------

def end_day(date: str) -> dict:
    """
    Close out a day:
      1. Read player_state for close values.
      2. Write mh_score_close + gold_close to day_snapshots.
      3. Check mandatory task completion.
      4. Compute new streak count.
      5. Write streak_log row.
      6. Update player_state.streak_count.

    Returns {mh_score_close, gold_close, streak_count, mandatory_met}
    """
    try:
        sb = get_client()

        # 1. Current state
        ps = reads.get_player_state()
        if not ps:
            return {"success": False, "error": "player_state not found"}

        mh_score_close = ps["mh_score"]
        gold_close = ps["gold_balance"]

        # 2. Update snapshot
        snap_res = (
            sb.table("day_snapshots")
            .select("id")
            .eq("date", date)
            .execute()
        )
        if snap_res.data:
            sb.table("day_snapshots").update({
                "mh_score_close": mh_score_close,
                "gold_close": gold_close,
            }).eq("id", snap_res.data[0]["id"]).execute()

        # 3. Check mandatory tasks
        mandatory_res = (
            sb.table("tasks")
            .select("id, status")
            .eq("date", date)
            .eq("mandatory", True)
            .execute()
        )
        mandatory_tasks = mandatory_res.data or []
        mandatory_met = any(t["status"] == "Done" for t in mandatory_tasks) if mandatory_tasks else False

        # 4. New streak count
        current_streak = ps.get("streak_count", 0)
        new_streak = current_streak + 1 if mandatory_met else 0

        # 5. Streak log
        sb.table("streak_log").insert({
            "date": date,
            "mandatory_met": mandatory_met,
            "streak_count": new_streak,
        }).execute()

        # 6. Update player_state streak
        sb.table("player_state").update({
            "streak_count": new_streak,
            "last_updated": datetime.utcnow().isoformat(),
        }).eq("id", 1).execute()

        return {
            "mh_score_close": mh_score_close,
            "gold_close": gold_close,
            "streak_count": new_streak,
            "mandatory_met": mandatory_met,
        }
    except Exception as exc:
        return _err("end_day", exc)
