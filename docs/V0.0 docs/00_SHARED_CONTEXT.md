# Life System — Shared Context

> **Every agent receives this file.** It is the single source of truth for schema, logic, and contracts.
> Do not deviate from the names, types, or rules defined here.

---

## System overview

The Life System is a personal productivity and life-management system modeled as an RPG. One user. The user earns XP, Gold, and Stats by completing real-world tasks. The system gates workload based on mental health score (MH), applies arc-based pressure and rewards, tracks skill growth over time, and logs daily state snapshots.

**Stack:**
- **Database:** Supabase (Postgres)
- **Inference:** Groq (SLM from Hugging Face — model TBD)
- **Scripts:** Python, Supabase Python SDK
- **Orchestration:** Python cron runner, manages EOD trigger + health-check

---

## Architecture layers

```
┌─────────────────────────────────────────────────────┐
│  EVENT LAYER — things that happen                   │
│  TASKS · TASK_SKILL_LINKS · EVENTS · ANCHORS        │
│  ARCS · EFFECTS                                     │
├─────────────────────────────────────────────────────┤
│  STATE LAYER — running totals + daily ledger        │
│  PLAYER_STATE (singleton) · DAY_SNAPSHOTS           │
│  STREAK_LOG                                         │
├─────────────────────────────────────────────────────┤
│  REFERENCE LAYER — slow-moving definitions          │
│  SKILLS · STATS · LOGIC (doctrine, not stored)      │
└─────────────────────────────────────────────────────┘
```

---

## Canonical schema

### TASKS
| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK, default gen_random_uuid() | |
| task | text | NOT NULL | Name of the task |
| type | text | CHECK IN ('Daily','Weekly','Recurring','Mandatory','Optional','Bonus') | |
| status | text | CHECK IN ('Not started','In progress','Done'), default 'Not started' | |
| priority | text | CHECK IN ('P0','P1','P2','P3') | |
| category | text | CHECK IN ('Health','Study','Work','Social','Maintenance','Hobby') | |
| date | date | NOT NULL | Scheduled date |
| energy_cost | text | CHECK IN ('Low','Medium','High','Very High') | |
| late_rule | text | CHECK IN ('None','Soft','Medium','Hard') | |
| late_rule_behavior | text | CHECK IN ('Penalty','Incentive','Neutral'), default 'Penalty' | Determines which column of the late modifier table to use |
| mandatory | boolean | default false | Hard flag — always show regardless of MH mode |
| blocked | boolean | default false | Task is blocked by a dependency |
| deferred | boolean | default false | Explicitly pushed to a later date |
| xp | integer | default 0 | Base XP reward |
| gold | integer | default 0 | Base Gold reward |
| resolved_xp | integer | | Final XP after modifier stack (written by complete_task) |
| resolved_gold | integer | | Final Gold after modifier stack (written by complete_task) |
| streak_xp | integer | | Bonus XP from streak modifier |
| mh_impact | integer | default 0 | Direct MH delta on completion |
| anchor_id | uuid | FK → anchors(id), nullable | Owning anchor event |
| crossover_level | text | CHECK IN ('Indirect','Partial','Direct'), default 'Direct' | Task-level default only. Per-skill overrides live in TASK_SKILL_LINKS |
| time_block | text | CHECK IN ('Morning','Afternoon','Evening','Night','Flexible') | |
| class_day_fit | text | CHECK IN ('Yes','Light Only','No') | |
| reminder_needed | boolean | default false | |
| reminder_lead | text | CHECK IN ('15 min','30 min','1 hour','2 hours'), nullable | |
| recurring_rule | text | nullable | Plain-language recurrence description |
| impact_notes | text | nullable | Free-form notes |
| anchor_override | boolean | default false | Late Rule was set by an Anchor and is locked |
| created_at | timestamptz | default now() | |

**Indexes:** `idx_tasks_date` on (date), `idx_tasks_status` on (status), `idx_tasks_date_status` on (date, status).

---

### TASK_SKILL_LINKS
Junction table. One row per task–skill pair.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| task_id | uuid | FK → tasks(id) ON DELETE CASCADE, NOT NULL | |
| skill_id | uuid | FK → skills(id), NOT NULL | |
| crossover_level | text | CHECK IN ('Indirect','Partial','Direct'), NOT NULL | Overrides the task-level default for this specific skill |

**Unique constraint:** (task_id, skill_id).

---

### EVENTS
One row per logged non-task event. Replaces the JSON blob columns.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| date | date | NOT NULL | |
| event_type | text | CHECK IN ('steps','substance','leisure','day_off','cheat_day','mh_manual'), NOT NULL | |
| name | text | nullable | e.g. "cigarette", "guitar practice" |
| quantity | numeric | nullable | e.g. step count, cigarette count |
| duration_minutes | integer | nullable | For leisure events |
| gold_delta | integer | default 0 | Gold cost or reward from this event |
| mh_delta | integer | default 0 | MH impact from this event |
| notes | text | nullable | e.g. reason for manual MH change |
| created_at | timestamptz | default now() | |

**Indexes:** `idx_events_date` on (date), `idx_events_type_date` on (event_type, date).

---

### ANCHORS
Scheduled real-world events that generate child tasks.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| anchor | text | NOT NULL | |
| type | text | CHECK IN ('Class','Appointment','Commitment','Other') | |
| date | date | NOT NULL | |
| time | text | | HH:MM format |
| priority_pressure | text | CHECK IN ('None','Elevates Tasks','Locks Day') | |
| created_at | timestamptz | default now() | |

---

### ARCS
Thematic goal windows that apply modifiers while active.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| arc | text | NOT NULL | |
| status | text | CHECK IN ('Active','Paused','Done'), default 'Active' | |
| weight | text | CHECK IN ('Background','Normal','Focused','Critical') | |
| start_date | date | | |
| end_date | date | | |
| created_at | timestamptz | default now() | |

**Relation to tasks:** Many-to-many via `arc_tasks` junction table:

#### ARC_TASKS
| Column | Type | Constraints |
|--------|------|-------------|
| arc_id | uuid | FK → arcs(id) ON DELETE CASCADE |
| task_id | uuid | FK → tasks(id) ON DELETE CASCADE |

**PK:** (arc_id, task_id).

**Relation to skills:** Many-to-many via `arc_skills` junction table:

#### ARC_SKILLS
| Column | Type | Constraints |
|--------|------|-------------|
| arc_id | uuid | FK → arcs(id) ON DELETE CASCADE |
| skill_id | uuid | FK → skills(id) ON DELETE CASCADE |

**PK:** (arc_id, skill_id).

---

### EFFECTS
Active buffs and debuffs. Duration-based.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| effect | text | NOT NULL | |
| type | text | CHECK IN ('Buff','Debuff') | |
| intensity | integer | CHECK (intensity BETWEEN 1 AND 10) | |
| suppresses_arc_pressure | boolean | default false | If true, arc skip penalties suspended |
| duration_days | integer | NOT NULL | |
| created_on | date | default CURRENT_DATE | |
| expires_on | date | NOT NULL | Computed at creation: created_on + duration_days |
| active | boolean | default true | Set false when expired — managed by tick_day |
| stat_offset | integer | default 0 | Flat stat delta applied per day while active |
| created_at | timestamptz | default now() | |

**Relation to stats:** Many-to-many via `effect_stats` junction:

#### EFFECT_STATS
| Column | Type | Constraints |
|--------|------|-------------|
| effect_id | uuid | FK → effects(id) ON DELETE CASCADE |
| stat_id | uuid | FK → stats(id) ON DELETE CASCADE |

**PK:** (effect_id, stat_id).

**Relation to arcs:** Many-to-many via `effect_arcs` junction:

#### EFFECT_ARCS
| Column | Type | Constraints |
|--------|------|-------------|
| effect_id | uuid | FK → effects(id) ON DELETE CASCADE |
| arc_id | uuid | FK → arcs(id) ON DELETE CASCADE |

**PK:** (effect_id, arc_id).

---

### SKILLS
| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| skill | text | NOT NULL | |
| current_level | integer | default 1 | |
| xp_accumulated | integer | default 0 | Running total since last level-up |
| xp_to_next_level | integer | NOT NULL | Threshold for breakthrough validation |
| decay_rate | text | CHECK IN ('Slow','Medium','Fast') | |
| last_active | date | | Clock for decay calculation |
| in_decay | boolean | default false | Computed flag — set by tick_day |
| primary_stat_id | uuid | FK → stats(id), NOT NULL | Stat fed at 100% weight |
| secondary_stat_id | uuid | FK → stats(id), nullable | Stat fed at 50% weight |
| created_at | timestamptz | default now() | |

---

### STATS
| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| stat | text | NOT NULL, UNIQUE | e.g. Intellect, Dexterity, Endurance |
| current_value | numeric | default 0 | Running total |
| last_updated | date | | |
| created_at | timestamptz | default now() | |

---

### PLAYER_STATE
**Singleton.** Exactly one row. Never create a second row.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | integer | PK, CHECK (id = 1) | Enforces singleton |
| mh_score | integer | CHECK (mh_score BETWEEN 0 AND 100) | |
| mh_mode | text | CHECK IN ('Normal','Reduced','Minimum Viable','Recovery Only') | Derived from mh_score — never set directly |
| gold_balance | integer | default 0 | |
| streak_count | integer | default 0 | |
| total_xp | integer | default 0 | |
| last_updated | timestamptz | default now() | |

---

### DAY_SNAPSHOTS
One row per calendar day. Daily ledger.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| date | date | UNIQUE, NOT NULL | One row per day |
| mh_score_open | integer | | MH at day start |
| mh_score_close | integer | nullable | Written by end_day |
| mh_mode | text | | Mode derived from mh_score_open |
| gold_open | integer | | |
| gold_close | integer | nullable | Written by end_day |
| xp_earned | integer | default 0 | |
| steps | integer | default 0 | |
| notes | text | nullable | |
| created_at | timestamptz | default now() | |

**Relation to anchors:** Many-to-many via `snapshot_anchors` junction:

#### SNAPSHOT_ANCHORS
| Column | Type | Constraints |
|--------|------|-------------|
| snapshot_id | uuid | FK → day_snapshots(id) ON DELETE CASCADE |
| anchor_id | uuid | FK → anchors(id) ON DELETE CASCADE |

**PK:** (snapshot_id, anchor_id).

---

### STREAK_LOG
One row per day. Single source of truth for streak state.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | uuid | PK | |
| date | date | UNIQUE, NOT NULL | |
| mandatory_met | boolean | NOT NULL | Was ≥1 mandatory task completed? |
| streak_count | integer | NOT NULL | Streak value at end of this day |
| created_at | timestamptz | default now() | |

---

## Logic doctrine (not stored as rows)

### MH Mode thresholds
| MH Score | Mode | Task filter |
|----------|------|-------------|
| 80–100 | Normal | All tasks available |
| 60–79 | Reduced | Suppress High + Very High energy tasks |
| 40–59 | Minimum Viable | Show mandatory + core only |
| 0–39 | Recovery Only | Rest tasks only; all arc pressure suspended |

### MH Mode derivation function
```
derive_mh_mode(score):
  if score >= 80: return "Normal"
  if score >= 60: return "Reduced"
  if score >= 40: return "Minimum Viable"
  return "Recovery Only"
```

### MH Score clamp
After every MH mutation: `mh_score = clamp(mh_score, 0, 100)`.

### Reward formula
```
final_xp   = base_xp   × arc_modifier × streak_modifier × late_modifier × partial_credit
final_gold = base_gold  × arc_modifier × late_modifier × partial_credit
```
Effects add a **flat offset after the stack** — never a multiplier.

### Arc modifier resolution
When a task belongs to multiple arcs: take the highest weight modifier, add at most +0.1 if a second arc clearly applies. Never fully stack.

| Arc Weight | Modifier |
|------------|----------|
| Background | 0.80 |
| Normal | 1.00 |
| Focused | 1.25 |
| Critical | 1.50 |

### Streak modifier
| Streak | Modifier |
|--------|----------|
| 0 (baseline) | 1.00 |
| 3–6 days | 1.05 |
| 7–13 days | 1.10 |
| 14–29 days | 1.15 |
| 30+ days | 1.20 |
| 60+ days | 1.30 (hard cap) |

### Late modifier
| Timing | Penalty task | Incentive task | Neutral task |
|--------|-------------|----------------|--------------|
| on_time | 1.00 | 1.00 | 1.00 |
| soft | 0.90 | 1.10 | 1.00 |
| meaningful_delay | 0.75 | 1.20 | 0.95 |
| hard_failure | 0.50 | 1.25 (cap) | 0.90 |
| void | 0.00 | — | — |

**Which column to use:** Determined by `tasks.late_rule_behavior` field.

### Crossover credit
| Level | Skill XP factor | Counts as task completion for skill? |
|-------|-----------------|--------------------------------------|
| Indirect | 0.25 | No |
| Partial | 0.50 | No |
| Direct | 1.00 | Yes |

Resolve per TASK_SKILL_LINKS edge, not per task row.

### Skill decay thresholds
| Decay Rate | Days inactive before decay triggers |
|------------|-------------------------------------|
| Slow | 30 |
| Medium | 14 |
| Fast | 7 |

Decay freezes future XP gains on the skill. It does **not** subtract from stats. Accumulated stat contributions are permanent.

### Skill → Stat propagation
On task completion, after updating skill XP:
```
for each task_skill_link:
  xp_gained = final_xp × crossover_factor
  skill.xp_accumulated += xp_gained
  skill.last_active = today
  skill.in_decay = false

  primary_stat.current_value += xp_gained × 1.0
  if skill.secondary_stat:
    secondary_stat.current_value += xp_gained × 0.5
```

### Substance & leisure deltas
| Event | Gold delta | MH delta |
|-------|-----------|----------|
| Cigarette | -2 | -1 |
| Alcohol (1 drink) | -3 | +1 |
| Alcohol (3+ drinks) | -6 | -3 |
| Caffeine (moderate) | 0 | 0 |
| Day Off | -18 | +10 |
| Cheat Day | -24 | +15 |

| Steps band | MH bonus |
|------------|----------|
| 4,000 | +1 |
| 8,000 | +2 |
| 10,000 | +3 |
| 12,000+ | +5 |

---

## Script contracts

Every script takes named arguments and returns a defined shape. The orchestrator calls scripts — scripts call the database. Scripts never call each other directly.

### Read scripts
| Script | Input | Returns |
|--------|-------|---------|
| get_player_state() | — | `{mh_score, mh_mode, gold_balance, streak_count, total_xp}` |
| get_today(date) | date string | `{date, mh_score_open, mh_mode, gold_open, xp_earned, steps, streak_count, anchors_active[], needs_init}` |
| get_tasks(date, mh_mode) | date, MH mode string | `[{id, task, type, priority, energy_cost, late_rule, late_rule_behavior, xp, gold, arcs[], skills[], mandatory, time_block}]` |
| get_task(task_id) | uuid | `{...full task fields, arc_modifier, suppression_active}` |
| get_skill_links(task_id) | uuid | `[{skill_id, skill_name, crossover_level}]` |
| get_active_effects() | — | `[{effect, type, intensity, suppresses_arc_pressure, stat_offset, linked_stats[]}]` |
| get_active_arcs() | — | `[{arc, weight, skills_boosted[]}]` |

### Write scripts
| Script | Input | Side effects | Returns |
|--------|-------|-------------|---------|
| tick_day(date) | date | Creates DAY_SNAPSHOTS row, expires effects, checks skill decay | `{success, snapshot_id}` |
| complete_task(task_id, completion_data) | task_id, {completion_time, partial_credit, mh_mode} | Marks done, runs reward stack, updates PLAYER_STATE, DAY_SNAPSHOTS, SKILLS, STATS | `{final_xp, final_gold, new_mh_score, new_mh_mode, new_gold_balance}` |
| log_event(event_type, payload) | event_type, payload object | Creates EVENTS row, updates PLAYER_STATE + DAY_SNAPSHOTS | `{new_mh_score, new_mh_mode, new_gold_balance, delta_applied}` |
| create_task(task_data) | full task object | Creates TASKS row + TASK_SKILL_LINKS rows | `{task_id, skill_links_created}` |
| create_effect(effect_data) | effect object | Creates EFFECTS row | `{effect_id, expires_on}` |
| update_arc_status(arc_id, status) | arc_id, status string | Updates ARCS row | `{success}` |
| end_day(date) | date | Closes DAY_SNAPSHOTS (mh/gold close), writes STREAK_LOG, updates PLAYER_STATE.streak_count | `{mh_score_close, gold_close, streak_count, mandatory_met}` |

---

## Hard constraints (all agents must respect)

1. Never calculate reward values inline — always use the reward formula via complete_task.
2. Never infer crossover level from the task row alone — always query TASK_SKILL_LINKS.
3. Never overwrite `anchor_override = true` late rules.
4. Never create a second PLAYER_STATE row — singleton enforced by CHECK (id = 1).
5. Never create a second DAY_SNAPSHOTS row for the same date — UNIQUE on date column.
6. MH Mode is always derived from MH Score — never set manually.
7. Skill decay never subtracts from STATS — it only gates future XP gains.
8. Effects never reduce reward modifiers — they add flat offsets after the stack.
9. MH Score is always clamped to 0–100 after every mutation.
10. Streak count is only incremented/reset by end_day — never mid-day.

---

## Naming conventions

- **Tables:** lowercase, underscores (e.g. `task_skill_links`, `day_snapshots`)
- **Columns:** lowercase, underscores (e.g. `mh_score`, `gold_balance`)
- **Functions/scripts:** snake_case (e.g. `complete_task`, `derive_mh_mode`)
- **Check constraints:** named `chk_<table>_<column>` (e.g. `chk_tasks_type`)
- **Foreign keys:** named `fk_<table>_<referenced_table>` (e.g. `fk_tasks_anchors`)
- **Indexes:** named `idx_<table>_<columns>` (e.g. `idx_tasks_date_status`)
- **Junction tables:** `<parent>_<child>` in alphabetical order when symmetric, or `<owner>_<owned>` when directional

---

*End of shared context. This file is versioned — if the schema changes, all agents must receive the updated copy.*
