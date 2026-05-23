# Life System — Scripts Agent Handoff

## Your role

You are the **Scripts Agent**. You implement every read and write script defined in the script contracts. Your code is the only thing that touches the database — the orchestrator calls your functions, your functions execute queries and return structured results. You are **step 3 of 4** in the build pipeline.

---

## Your position in the pipeline

```
  ┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │ 1. DB    │ ──▸ │ 2. Inference │ ──▸ │ 3. Scripts   │ ──▸ │ 4. Orchestr. │
  │  Agent   │     │    Agent     │     │    Agent     │     │    Agent     │
  │          │     │              │     │   (you)      │     │              │
  └──────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

**You depend on:**
- The DB Agent's schema (live tables in Supabase you query against).
- The Inference Agent's output shape (`{action, args}` dicts that the orchestrator will unpack and pass to your functions).

**Who depends on you:** The Orchestrator imports your modules and calls your functions directly.

---

## What you own

### Project structure

```
scripts/
├── __init__.py
├── db.py               # Supabase client singleton
├── reads.py            # All read scripts
├── writes.py           # All write scripts
├── logic.py            # Pure functions: reward formula, MH derivation, modifier lookups
└── tests/
    ├── test_reads.py
    ├── test_writes.py
    └── test_logic.py
```

### 1. `db.py` — Supabase client

- Use `supabase-py` (`pip install supabase`).
- Read `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from environment variables.
- Export a singleton `get_client()` that returns a configured Supabase client.
- Use the **service role key** (not anon key) since this is a backend agent, not a browser client. RLS is still enabled — the service role bypasses it.

### 2. `logic.py` — Pure computation (no DB calls)

This module contains every formula and lookup table from `00_SHARED_CONTEXT.md`. No database access — pure functions only.

**Must implement:**

```python
def derive_mh_mode(mh_score: int) -> str
    # Returns one of: "Normal", "Reduced", "Minimum Viable", "Recovery Only"

def clamp_mh(mh_score: int) -> int
    # Returns mh_score clamped to 0–100

def get_arc_modifier(arc_weights: list[str]) -> float
    # Takes list of arc weight strings, returns resolved single modifier
    # Highest weight + max +0.1 for secondary

def get_streak_modifier(streak_count: int) -> float
    # Returns modifier based on streak tier

def get_late_modifier(completion_time: str, late_rule_behavior: str) -> float
    # Returns modifier from the late table

def get_crossover_factor(crossover_level: str) -> float
    # "Indirect" → 0.25, "Partial" → 0.50, "Direct" → 1.00

def get_step_mh_bonus(step_count: int) -> int
    # Returns MH bonus for highest completed band

def get_substance_deltas(name: str, quantity: int) -> dict
    # Returns {"gold_delta": int, "mh_delta": int}

def get_decay_threshold(decay_rate: str) -> int
    # "Slow" → 30, "Medium" → 14, "Fast" → 7

def calculate_rewards(
    base_xp: int,
    base_gold: int,
    arc_modifier: float,
    streak_modifier: float,
    late_modifier: float,
    partial_credit: float
) -> dict
    # Returns {"final_xp": int, "final_gold": int}
    # Applies: final_xp = round(base_xp * arc * streak * late * partial)
    # Applies: final_gold = round(base_gold * arc * late * partial)
```

**All these functions must be fully tested in `test_logic.py`.** They encode the core game rules — a bug here cascades everywhere.

### 3. `reads.py` — Read scripts

Every function takes explicit arguments (no *args, no **kwargs) and returns a dict or list of dicts matching the output shapes in `00_SHARED_CONTEXT.md`.

**Must implement all 7 read scripts:**

- `get_player_state()` → dict
- `get_today(date: str)` → dict (includes `needs_init: bool`)
- `get_tasks(date: str, mh_mode: str)` → list[dict]
- `get_task(task_id: str)` → dict (includes resolved `arc_modifier` and `suppression_active`)
- `get_skill_links(task_id: str)` → list[dict]
- `get_active_effects()` → list[dict]
- `get_active_arcs()` → list[dict]

**Query guidelines:**
- Use the Supabase Python client's query builder, not raw SQL. Example: `supabase.table("tasks").select("*").eq("date", date).neq("status", "Done").execute()`
- For junction table joins, use Supabase's `select("*, arcs(*)")` syntax for foreign key joins.
- `get_tasks` must apply the MH mode filter logic exactly as defined in the shared context. The filtering happens in code, not in the query (simpler, more testable).
- `get_task` must resolve the arc modifier by calling `logic.get_arc_modifier()` with the weights of all active arcs linked to that task.
- All functions must handle "not found" gracefully — return empty structures, never raise.

### 4. `writes.py` — Write scripts

Every write function is a transaction — if any step fails, no partial state should be committed.

**Must implement all 7 write scripts:**

#### `tick_day(date: str) -> dict`
1. Check `day_snapshots` for existing row with this date — abort with `{success: false, reason: "already_exists"}` if found.
2. Read `player_state` for current values.
3. Insert `day_snapshots` row with open values.
4. Query `anchors` where date matches — insert `snapshot_anchors` junction rows.
5. Query `effects` where `expires_on < date` and `active = true` — set `active = false`.
6. Query `skills` — for each, check if `last_active` is older than its decay threshold. If so, set `in_decay = true`.
7. Return `{success: true, snapshot_id: str}`.

#### `complete_task(task_id: str, completion_data: dict) -> dict`
This is the most complex script. Follow the steps exactly as defined in `00_SHARED_CONTEXT.md`:
1. Fetch task via `reads.get_task(task_id)` — gives you base values + arc_modifier.
2. Fetch skill links via `reads.get_skill_links(task_id)`.
3. Read `player_state.streak_count` → `logic.get_streak_modifier()`.
4. Call `logic.get_late_modifier(completion_time, task.late_rule_behavior)`.
5. Call `logic.calculate_rewards(...)`.
6. Fetch active effects — sum any applicable `stat_offset` values.
7. Update `tasks` row: status = 'Done', resolved_xp, resolved_gold.
8. Update `player_state`: total_xp +=, gold_balance +=, mh_score += task.mh_impact. **Clamp MH.** Re-derive MH mode.
9. Update `day_snapshots` for today: xp_earned +=.
10. For each skill link:
    - `xp_gained = final_xp * crossover_factor`
    - Update `skills.xp_accumulated +=`, `skills.last_active = today`, `skills.in_decay = false`
    - Propagate to stats: `primary_stat += xp_gained * 1.0`, `secondary_stat += xp_gained * 0.5`
11. Update any `stats` directly linked via `task.stats` relation.
12. Return `{final_xp, final_gold, new_mh_score, new_mh_mode, new_gold_balance}`.

#### `log_event(event_type: str, payload: dict) -> dict`
1. Look up deltas from `logic.py` functions.
2. Insert `events` row.
3. Update `player_state`: gold_balance +=, mh_score +=. **Clamp MH.** Re-derive MH mode.
4. If steps: update `day_snapshots.steps`.
5. Return `{new_mh_score, new_mh_mode, new_gold_balance, delta_applied}`.

#### `create_task(task_data: dict) -> dict`
1. Insert `tasks` row.
2. For each skill in `task_data.skills`: insert `task_skill_links` row.
3. If `anchor_id` provided: the FK on the tasks row handles the link.
4. If `arcs` provided: insert `arc_tasks` junction rows.
5. If `stats` provided: handle direct stat relations (if you add a `task_stats` junction — see notes below).
6. Return `{task_id, skill_links_created}`.

**Note:** The shared context mentions `tasks.stats` as a relation, but the schema doesn't define a `task_stats` junction table. You should add one following the same pattern as `arc_tasks`. Flag this in your output so the DB Agent can add it to the migration.

#### `create_effect(effect_data: dict) -> dict`
1. Compute `expires_on = created_on + duration_days`.
2. Insert `effects` row with `active = true`.
3. Insert `effect_stats` and `effect_arcs` junction rows.
4. Return `{effect_id, expires_on}`.

#### `update_arc_status(arc_id: str, status: str) -> dict`
1. Update `arcs.status`.
2. No XP reversal — accumulated XP is permanent.
3. Return `{success: true}`.

#### `end_day(date: str) -> dict`
1. Read current `player_state` for mh_score and gold_balance.
2. Update `day_snapshots` for this date: `mh_score_close`, `gold_close`.
3. Check if any task with `mandatory = true` and `date = date` has `status = 'Done'`.
4. Compute new streak: if mandatory_met → streak_count + 1, else → 0.
5. Insert `streak_log` row: `{date, mandatory_met, streak_count}`.
6. Update `player_state.streak_count`.
7. Return `{mh_score_close, gold_close, streak_count, mandatory_met}`.

---

## Error handling

- Every function returns a dict. Never raise exceptions to the caller.
- On failure: `{success: false, error: str}`.
- On success: the documented return shape (success is implicit).
- Log errors to stderr with timestamp and function name.

---

## What you do NOT own

- Schema creation or migrations (DB Agent).
- The Groq client or system prompt (Inference Agent).
- Cron scheduling, sequencing, or retry logic (Orchestrator Agent).
- Any user-facing messaging or decision-making.

---

## Deliverables checklist

| File | Format | Purpose |
|------|--------|---------|
| `scripts/__init__.py` | Python | Package init |
| `scripts/db.py` | Python | Supabase client singleton |
| `scripts/logic.py` | Python | Pure formula/lookup functions |
| `scripts/reads.py` | Python | All 7 read scripts |
| `scripts/writes.py` | Python | All 7 write scripts |
| `scripts/tests/test_logic.py` | Python | Full test coverage for logic.py |
| `scripts/tests/test_reads.py` | Python | Tests against live DB (requires seed data) |
| `scripts/tests/test_writes.py` | Python | Tests against live DB |

---

## Validation criteria

Before handing off, verify:
- [ ] `get_player_state()` returns the seeded singleton row.
- [ ] `get_tasks(today, "Normal")` returns all non-done, non-blocked, non-deferred tasks.
- [ ] `get_tasks(today, "Recovery Only")` returns only mandatory + low energy tasks.
- [ ] `tick_day(today)` creates a snapshot and idempotently refuses a second call.
- [ ] `complete_task(...)` correctly applies the full modifier stack and updates all downstream tables.
- [ ] `end_day(today)` writes close values, streak log, and updates player state streak count.
- [ ] MH score never goes below 0 or above 100 after any write.
- [ ] MH mode is always consistent with MH score after any write.
- [ ] All logic.py functions match the tables in shared context exactly.

---

## Critical note on missing junction table

The shared context defines `tasks.stats` as a relation (direct stat delta on task completion), but no `task_stats` junction table exists in the schema. When you encounter this during implementation:
1. Implement `complete_task` step 12 using a `task_stats` junction table.
2. Document the missing table in your handoff output.
3. The DB Agent should add `task_stats` (task_id FK, stat_id FK, composite PK) to the migration.

Do not skip this step — direct stat changes from tasks are a core mechanic.

---

*Read `00_SHARED_CONTEXT.md` before starting. Every function signature, return shape, and formula is defined there. Do not improvise.*
