# Life Map — Scripts Agent Handoff (v1)
> **Session date:** 2026-05-23
> **Issued by:** Supervisor
> **Repo:** https://github.com/caffeinated4ighs/Life_Map

---

## Supervisor context

Core system is operational. DB is live on Supabase, inference runs on Groq, cron runs on GitHub Actions, web chat UI is live. The original script library (`reads.py` / `writes.py`) was built for the initial 7+7 function set and is working in production.

**Your job this session:** Expand the script library with the full set of missing functions listed below. Nothing else — no changes to logic, orchestrator, inference, or UI.

**Priority order:** UI and hosting are deferred. Backend is being hardened. The Inference Agent is blocked on your function signatures before it can wire new tools into the chat. Complete this first.

---

## What already exists (do not rewrite)

The following functions are live and tested. Append to these files — do not restructure or rewrite what's there.

### `scripts/reads.py` — existing
- `get_player_state()`
- `get_today(date)`
- `get_tasks(date, mh_mode)`
- `get_task(task_id)`
- `get_skill_links(task_id)`
- `get_active_effects()`
- `get_active_arcs()`

### `scripts/writes.py` — existing
- `tick_day(date)`
- `complete_task(task_id, completion_data)`
- `log_event(event_type, payload)`
- `create_task(task_data)`
- `create_effect(effect_data)`
- `update_arc_status(arc_id, status)`
- `end_day(date)`

### `scripts/logic.py` — frozen
Do not touch. All formulas are pure functions tested against 87 test cases.

---

## Your deliverable

Append the following functions to `reads.py` and `writes.py`. Follow the exact patterns already established — same error handling, same return-dict convention, same `_log_error` / `_err` helpers, same lazy Supabase client via `get_client()`.

**Rules:**
- Every function returns a `dict` or `list[dict]`. Never raises.
- Reads return empty `{}` or `[]` on not-found or error.
- Writes return `{"success": False, "error": str}` on failure.
- Log all errors to stderr via `_log_error(fn_name, exc)`.
- No new files. Append only.

---

## Functions to add — `reads.py`

### `get_skills() -> list[dict]`
Return all skills ordered by `skill` name.

Return shape per item:
```python
{
    "id": str,
    "skill": str,
    "current_level": int,
    "xp_accumulated": int,
    "xp_to_next_level": int,
    "decay_rate": str | None,
    "last_active": str | None,   # date ISO string
    "in_decay": bool,
    "primary_stat_id": str,
    "secondary_stat_id": str | None,
}
```

---

### `get_skill(skill_id: str) -> dict`
Return a single skill by UUID. Return `{}` if not found.

Same shape as one item from `get_skills()`.

---

### `get_arcs() -> list[dict]`
Return all arcs regardless of status, ordered by `start_date` desc.

Return shape per item:
```python
{
    "id": str,
    "arc": str,
    "status": str,       # Active | Paused | Done
    "weight": str | None,
    "start_date": str | None,
    "end_date": str | None,
}
```

---

### `get_arc(arc_id: str) -> dict`
Return a single arc by UUID with its linked tasks and linked skills.

Return shape:
```python
{
    "id": str,
    "arc": str,
    "status": str,
    "weight": str | None,
    "start_date": str | None,
    "end_date": str | None,
    "tasks": [{"task_id": str, "task": str, "status": str}],
    "skills": [{"skill_id": str, "skill": str}],
}
```

---

### `get_arc_tasks(arc_id: str) -> list[dict]`
Return all tasks linked to a given arc.

Return shape per item:
```python
{
    "task_id": str,
    "task": str,
    "status": str,
    "date": str,
    "priority": str | None,
}
```

---

### `get_effects() -> list[dict]`
Return all effects (active and inactive), ordered by `created_on` desc.

Return shape per item:
```python
{
    "id": str,
    "effect": str,
    "type": str,           # Buff | Debuff
    "intensity": int,
    "active": bool,
    "suppresses_arc_pressure": bool,
    "duration_days": int,
    "created_on": str,
    "expires_on": str,
    "stat_offset": int,
}
```

---

### `get_effect(effect_id: str) -> dict`
Return a single effect by UUID with its linked stats and linked arcs.

Return shape:
```python
{
    "id": str,
    "effect": str,
    "type": str,
    "intensity": int,
    "active": bool,
    "suppresses_arc_pressure": bool,
    "duration_days": int,
    "created_on": str,
    "expires_on": str,
    "stat_offset": int,
    "linked_stats": [{"stat_id": str, "stat": str}],
    "linked_arcs": [{"arc_id": str, "arc": str}],
}
```

---

### `get_anchors(date: str) -> list[dict]`
Return all anchors for a given date.

Return shape per item:
```python
{
    "id": str,
    "anchor": str,
    "type": str | None,
    "date": str,
    "time": str | None,
    "priority_pressure": str | None,
}
```

---

### `get_snapshot(date: str) -> dict`
Return the `day_snapshots` row for a given date. Return `{}` if none exists.

Return shape:
```python
{
    "id": str,
    "date": str,
    "mh_score_open": int,
    "mh_score_close": int | None,
    "mh_mode": str,
    "gold_open": int,
    "gold_close": int | None,
    "xp_earned": int,
    "steps": int,
}
```

---

### `get_streak_log(limit: int = 7) -> list[dict]`
Return the most recent `limit` rows from `streak_log`, ordered by `date` desc.

Return shape per item:
```python
{
    "date": str,
    "streak_count": int,
    "mandatory_met": bool,
}
```

---

### `get_stats() -> list[dict]`
Return all stat rows ordered by `stat` name.

Return shape per item:
```python
{
    "id": str,
    "stat": str,
    "current_value": float,
    "last_updated": str | None,
}
```

---

### `get_stat(stat_id: str) -> dict`
Return a single stat by UUID. Return `{}` if not found.

Same shape as one item from `get_stats()`.

---

## Functions to add — `writes.py`

### `create_skill(skill_data: dict) -> dict`
Insert a new skill row.

Required fields in `skill_data`:
```python
{
    "skill": str,
    "primary_stat_id": str,        # UUID — must exist in stats
    "xp_to_next_level": int,
    # optional
    "secondary_stat_id": str,      # UUID
    "decay_rate": str,             # Slow | Medium | Fast
    "current_level": int,          # default 1
    "xp_accumulated": int,         # default 0
}
```

Return `{"success": True, "skill_id": str}` on success.

---

### `update_skill(skill_id: str, updates: dict) -> dict`
Patch mutable fields on a skill row.

Allowed update keys: `skill`, `current_level`, `xp_accumulated`, `xp_to_next_level`, `decay_rate`, `last_active`, `in_decay`, `secondary_stat_id`.

Do not allow updating `primary_stat_id` or `id`.

Return `{"success": True}` on success.

---

### `create_arc(arc_data: dict) -> dict`
Insert a new arc row.

Required fields:
```python
{
    "arc": str,
    # optional
    "weight": str,        # Background | Normal | Focused | Critical
    "start_date": str,    # YYYY-MM-DD
    "end_date": str,      # YYYY-MM-DD
    "status": str,        # default Active
}
```

Return `{"success": True, "arc_id": str}` on success.

---

### `update_arc(arc_id: str, updates: dict) -> dict`
Patch mutable fields on an arc row.

Allowed update keys: `arc`, `status`, `weight`, `start_date`, `end_date`.

Return `{"success": True}` on success.

---

### `link_arc_task(arc_id: str, task_id: str) -> dict`
Insert a row into `arc_tasks`. Idempotent — if the link already exists, return success without error.

Return `{"success": True}` on success.

---

### `link_arc_skill(arc_id: str, skill_id: str) -> dict`
Insert a row into `arc_skills`. Idempotent — if the link already exists, return success without error.

Return `{"success": True}` on success.

---

### `update_effect(effect_id: str, updates: dict) -> dict`
Patch mutable fields on an effect row.

Allowed update keys: `effect`, `active`, `intensity`, `stat_offset`, `suppresses_arc_pressure`, `expires_on`.

Return `{"success": True}` on success.

---

### `update_task(task_id: str, updates: dict) -> dict`
Patch mutable fields on a task row.

Allowed update keys: `task`, `type`, `status`, `priority`, `category`, `date`, `energy_cost`, `late_rule`, `late_rule_behavior`, `mandatory`, `blocked`, `deferred`, `xp`, `gold`, `mh_impact`, `time_block`, `recurring_rule`, `impact_notes`.

Do not allow updating `id`, `resolved_xp`, `resolved_gold`, `streak_xp`, `anchor_override`, `anchor_id`.

Return `{"success": True}` on success.

---

### `delete_task(task_id: str) -> dict`
Soft delete: set `deferred = true` and `status = 'Not started'` rather than a hard delete, unless the task status is already `'Done'` — in that case return `{"success": False, "error": "cannot delete a completed task"}`.

Return `{"success": True}` on success.

---

### `create_anchor(anchor_data: dict) -> dict`
Insert a new anchor row.

Required fields:
```python
{
    "anchor": str,
    "date": str,           # YYYY-MM-DD
    # optional
    "type": str,           # Class | Appointment | Commitment | Other
    "time": str,           # HH:MM
    "priority_pressure": str,  # None | Elevates Tasks | Locks Day
}
```

Return `{"success": True, "anchor_id": str}` on success.

---

### `generate_recurring_tasks(date: str) -> dict`
For each task where `recurring_rule IS NOT NULL` and `status = 'Done'` and `date = yesterday`, create a new task row for `date` (today) with identical fields except: `status = 'Not started'`, `resolved_xp = None`, `resolved_gold = None`, `streak_xp = None`.

Skip if a task with the same `task` name already exists for `date`.

Return `{"success": True, "created": int}` — count of new rows inserted.

---

### `update_stat(stat_id: str, delta: int) -> dict`
Add `delta` to `stats.current_value` for the given stat. Update `last_updated` to today.

`delta` can be negative.

Return `{"success": True, "new_value": float}` on success.

---

### `create_skill_link(task_id: str, skill_id: str, crossover_level: str) -> dict`
Insert a row into `task_skill_links`.

`crossover_level` must be one of: `Indirect`, `Partial`, `Direct`.

Idempotent — if the link already exists, return success without error.

Return `{"success": True}` on success.

---

### `delete_skill_link(task_id: str, skill_id: str) -> dict`
Delete a row from `task_skill_links` matching both `task_id` and `skill_id`.

Return `{"success": True}` on success. Return `{"success": False, "error": "not found"}` if no matching row.

Note: the supervisor log originally named this `delete_skill_link(link_id)` but the table uses a composite key `(task_id, skill_id)` — there is no surrogate `link_id`. Use both FKs.

---

### `manual_mh_adjust(delta: int, reason: str) -> dict`
Apply a flat MH delta directly to `player_state.mh_score`. Clamp to 0–100. Re-derive `mh_mode`.

Log the event to the `events` table with `event_type = 'mh_manual'`, `mh_delta = delta`, `notes = reason`.

Return:
```python
{
    "success": True,
    "new_mh_score": int,
    "new_mh_mode": str,
    "delta_applied": int,
}
```

---

## Constraints that must never be violated

These are load-bearing system rules. Any write function that touches `player_state` must respect all of them:

1. `player_state` is a singleton — one row, `id = 1`. Never insert a second row.
2. `mh_mode` is always derived from `mh_score` via `logic.derive_mh_mode()` — never set directly.
3. `mh_score` is always clamped 0–100 via `logic.clamp_mh()` after every mutation.
4. `streak_count` is only updated by `end_day` — no other function touches it.
5. Effects add flat offsets after the reward stack — never multipliers. Don't implement reward logic here.
6. `logic.py` is frozen — call its functions, never re-implement their formulas inline.

---

## Files to read before starting

From the repo (in order):
1. `docs/00_SHARED_CONTEXT.md` — canonical schema, all column names/types, all constraints
2. `scripts/reads.py` — match every pattern exactly
3. `scripts/writes.py` — match every pattern exactly
4. `scripts/logic.py` — understand what's available to call
5. `db/001_schema.sql` — ground truth for table/column names if anything is ambiguous

---

## Validation before handoff

For each new function, confirm:
- [ ] Follows the exact return-shape documented above
- [ ] Returns empty structure (not an exception) on not-found
- [ ] Returns `{"success": False, "error": str}` on DB failure
- [ ] All enum values match the CHECK constraints in `001_schema.sql`
- [ ] No new files created — appended to existing `reads.py` / `writes.py` only
- [ ] `logic.py` untouched

When done, produce a one-line status per function:
```
get_skills()          ✓ appended to reads.py
create_arc()          ✓ appended to writes.py
...
```

That list is what the supervisor uses to update the log before the next agent session.
