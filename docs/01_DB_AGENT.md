# Life System — DB Agent Handoff

## Your role

You are the **Database Agent**. You build and maintain the Postgres schema on Supabase. You are **step 1 of 4** in the build pipeline — every other agent depends on your output.

---

## Your position in the pipeline

```
  ┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │ 1. DB    │ ──▸ │ 2. Inference │ ──▸ │ 3. Scripts   │ ──▸ │ 4. Orchestr. │
  │  Agent   │     │    Agent     │     │    Agent     │     │    Agent     │
  │ (you)    │     │              │     │              │     │              │
  └──────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

**Nothing else can be tested until you produce a working schema.** The Scripts Agent will write directly to the tables you create. The Inference Agent needs to know the table names and column types for its system prompt. The Orchestrator calls everything in sequence.

---

## What you own

### 1. Schema creation (SQL migration file)

Produce a single `001_schema.sql` file that creates all tables, constraints, indexes, and junction tables defined in `00_SHARED_CONTEXT.md`. This file must be idempotent — running it twice should not error.

**Requirements:**
- Use `CREATE TABLE IF NOT EXISTS` for all tables.
- All CHECK constraints must be explicitly named using the `chk_<table>_<column>` convention.
- All foreign keys must be explicitly named using the `fk_<table>_<referenced>` convention.
- All indexes must be explicitly named using the `idx_<table>_<columns>` convention.
- Use `gen_random_uuid()` for UUID defaults (native to Postgres 13+, which Supabase uses).
- Junction tables must have composite primary keys, not surrogate UUIDs.
- The `player_state` table must enforce its singleton with `CHECK (id = 1)`.
- The `day_snapshots` table must have a UNIQUE constraint on `date`.
- The `streak_log` table must have a UNIQUE constraint on `date`.

**Table creation order** (respects FK dependencies):
1. `stats` — no FKs
2. `skills` — FKs to stats
3. `arcs` — no FKs
4. `effects` — no FKs
5. `anchors` — no FKs
6. `tasks` — FK to anchors
7. `task_skill_links` — FKs to tasks, skills
8. `arc_tasks` — FKs to arcs, tasks
9. `arc_skills` — FKs to arcs, skills
10. `effect_stats` — FKs to effects, stats
11. `effect_arcs` — FKs to effects, arcs
12. `events` — no FKs (references date, not other tables)
13. `player_state` — no FKs
14. `day_snapshots` — no FKs
15. `snapshot_anchors` — FKs to day_snapshots, anchors
16. `streak_log` — no FKs

### 2. Seed data (SQL file)

Produce a `002_seed.sql` file that inserts the initial data the system needs to function:

**STATS** — create the core stat rows:
- Intellect
- Dexterity
- Endurance
- Strength
- Coding
- Admin
- Charisma
- Social
- Discipline

All with `current_value = 0`.

**PLAYER_STATE** — create the singleton row:
- `id = 1`
- `mh_score = 75`
- `mh_mode = 'Reduced'`
- `gold_balance = 50`
- `streak_count = 0`
- `total_xp = 0`

**SKILLS** — do NOT seed skills. The user will create those through the system. Skills are personal and vary per user.

**ARCS** — do NOT seed arcs. Same reason.

### 3. Row-Level Security (RLS)

Since this is a single-user system on Supabase, RLS should:
- Be **enabled** on all tables (Supabase requires it for API access).
- Use a single policy per table that allows all operations for the `authenticated` role.
- Name policies `policy_<table>_authenticated`.

Produce this as `003_rls.sql`.

### 4. Health-check endpoint

Produce a Supabase Edge Function (Deno/TypeScript) at `004_health_check.ts` that:
- Reads the `player_state` row.
- Returns `{ status: "ok", mh_score: <value>, last_updated: <value> }` on success.
- Returns `{ status: "error", message: <error> }` on failure.
- This will be called daily by the Orchestrator to keep the Supabase project alive.

---

## What you do NOT own

- Script logic (that's the Scripts Agent).
- System prompt for the SLM (that's the Inference Agent).
- Cron scheduling, secrets management, or sequencing (that's the Orchestrator Agent).
- Any decision about what tasks to create, which arcs to activate, or how to interpret user behavior.

---

## Deliverables checklist

| File | Format | Purpose |
|------|--------|---------|
| `001_schema.sql` | SQL | Full schema, idempotent |
| `002_seed.sql` | SQL | Initial stats + player state |
| `003_rls.sql` | SQL | RLS policies for all tables |
| `004_health_check.ts` | TypeScript | Supabase Edge Function |

All files should be self-contained — no external dependencies, no references to other agent deliverables. The Scripts Agent will import supabase-py and query your tables directly.

---

## Validation criteria

Before handing off, verify:
- [ ] All tables from `00_SHARED_CONTEXT.md` exist with correct column types.
- [ ] All CHECK constraints fire on invalid inserts.
- [ ] All FKs cascade correctly on DELETE.
- [ ] `player_state` rejects a second row insert.
- [ ] `day_snapshots` rejects duplicate dates.
- [ ] `streak_log` rejects duplicate dates.
- [ ] All junction tables have composite PKs, not surrogate UUIDs.
- [ ] All indexes are created.
- [ ] RLS is enabled and the authenticated role can CRUD all tables.
- [ ] Health-check endpoint returns 200 with valid player state.

---

*Read `00_SHARED_CONTEXT.md` before starting. Do not deviate from the schema defined there.*
