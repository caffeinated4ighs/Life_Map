# Life Map — Mapping Team Handoff
> **Date:** 2026-05-24
> **Repo:** https://github.com/caffeinated4ighs/Life_Map
> **Issued by:** Supervisor
> **Your job:** Understand and map the entire project. Produce a living document that any new agent can read to get fully up to speed in one pass.

---

## What this project is

Life Map is a personal productivity system built as an RPG. One user. The user earns XP, Gold, and Stats by completing real-world tasks. Mental health score (MH) gates what work they're allowed to take on. Skills decay without practice. Goals are tracked as time-windowed Arcs with modifiers. The system is operated primarily through natural language — the user texts it like a capable assistant who knows their life.

**The north star:** *"The system should feel like texting someone who knows your life and just handles things. Not a form. Not a chatbot."*

It started as a Notion prototype. We migrated it to a real stack: Postgres on Supabase, Python scripts, Groq LLM inference, FastAPI web backend, single-file HTML frontend.

---

## Why decisions were made the way they were

**Supabase over local Postgres:** Free tier, auto-REST, edge functions, no self-hosting.

**Groq over OpenAI/Anthropic for inference:** LPU hardware = fast, generous free tier, HuggingFace model ecosystem. Model: `meta-llama/llama-4-scout-17b-16e-instruct` (swappable via env var).

**Tool-calling agent over JSON router:** First attempt used the LLM as a pure JSON router (send message → get structured action back). Broke on anything conversational. Moved to tool-calling: model holds conversation, calls scripts as tools when it needs DB access. This mirrors the original Notion MCP pattern.

**GitHub Actions for cron:** User can't leave a laptop running. Morning snapshot, EOD close, health ping all run on free-tier cron. No always-on machine needed.

**Single-file HTML frontend:** No build step, no framework, no node_modules. Works on desktop and Android Chrome. Bookmarkable.

**FastAPI over the CLI orchestrator for web chat:** The CLI orchestrator uses a JSON router (`groq_client.py`). The web chat uses Groq's tool-calling SDK directly (`api.py`). These are two separate inference paths — the CLI path is not used by the web UI.

---

## Current architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Actions (free tier)                                     │
│  Morning 07:30 EST · EOD 23:30 EST · Health ping 12:00         │
└────────────────────────────┬────────────────────────────────────┘
                             │ python -m orchestrator [flow]
┌────────────────────────────▼────────────────────────────────────┐
│  Orchestrator — CLI flows only                                  │
│  orchestrator/main.py · sequencer.py · config.py               │
│  Three flows: morning · eod · complete_task (CLI)              │
└──────┬─────────────────────────────────────────┬────────────────┘
       │                                         │
┌──────▼──────────┐                   ┌──────────▼──────────────┐
│  Groq (cloud)   │                   │  Supabase (cloud)        │
│  Tool-calling   │                   │  Postgres — 17 tables    │
│  LLM inference  │                   │  Edge function (health)  │
└──────┬──────────┘                   └──────────┬──────────────┘
       │                                         │
┌──────▼─────────────────────────────────────────▼──────────────┐
│  Web UI (local uvicorn, port 8000)                             │
│  web_ui/api.py — FastAPI, tool-calling loop                    │
│  web_ui/index.html — dark RPG UI, stat bar, chat              │
│  Endpoints: /health · /morning · /state · /chat · /eod        │
└────────────────────────────────────────────────────────────────┘
```

---

## Database — 17 tables across 3 layers

```
EVENT LAYER     tasks · task_skill_links · task_stats · events
                anchors · arcs · arc_tasks · arc_skills
                effects · effect_stats · effect_arcs

STATE LAYER     player_state (singleton, id=1) · day_snapshots · streak_log

REFERENCE       skills · stats
```

**Key constraints that must never be violated:**
1. `player_state` is a singleton — one row, `id = 1`, DB-enforced
2. `mh_mode` always derived from `mh_score` via `logic.derive_mh_mode()` — never set directly
3. `mh_score` always clamped 0–100 after every mutation
4. `streak_count` only updated by `end_day` — never mid-day
5. Effects add flat offsets after the reward stack — never multipliers
6. `logic.py` is frozen — all formulas live there, nothing reimplements them inline

---

## Script library — complete

All scripts live in `scripts/`. Two files: `reads.py` (14 functions) and `writes.py` (16 functions). All formulas in `logic.py` (frozen, 87 tests passing).

**Reads:** `get_player_state` · `get_today` · `get_tasks` · `get_task` · `get_skill_links` · `get_active_effects` · `get_active_arcs` · `get_skills` · `get_skill` · `get_arcs` · `get_arc` · `get_arc_tasks` · `get_effects` · `get_effect` · `get_anchors` · `get_snapshot` · `get_streak_log` · `get_stats` · `get_stat`

**Writes:** `tick_day` · `complete_task` · `log_event` · `create_task` · `create_effect` · `update_arc_status` · `end_day` · `create_skill` · `update_skill` · `create_arc` · `update_arc` · `link_arc_task` · `link_arc_skill` · `update_effect` · `update_task` · `delete_task` · `create_anchor` · `generate_recurring_tasks` · `update_stat` · `create_skill_link` · `delete_skill_link` · `manual_mh_adjust`

**Error contract:** every function returns a dict. Never raises. Reads return `{}` or `[]` on not-found. Writes return `{"success": False, "error": str}` on failure.

---

## Web chat — how it works

`web_ui/api.py` is the conversational engine. The `/chat` endpoint runs a tool-calling loop:

1. User message + context block → Groq
2. Groq returns tool calls → execute via `_execute_tool()`
3. Tool results appended → Groq again
4. Loop until Groq returns text (no tool calls) → return reply
5. Max 5 rounds, warning logged if hit

**Key architectural decisions in `api.py`:**
- `_resolve_and_complete()` — intercepts every `complete_task` call, validates task_id against live DB before executing. Prevents model hallucinating UUIDs.
- `_resolve_task_id()` — same pattern for `update_task` and `delete_task`.
- `_execute_tool()` — catches `success: False` from scripts, short-circuits with direct error reply (bypasses model rephrasing).
- Context block injected into every user message with live player state + task counts.
- `SYSTEM_PROMPT` — conversational, warm tone. Key rules: fuzzy task matching, inference defaults, two-step tool sequencing, no schema leakage to user.

**The two inference paths (do not confuse):**
- `inference/groq_client.py` + `inference/system_prompt.txt` → CLI orchestrator only (JSON router, structured output)
- `web_ui/api.py` → web chat only (tool-calling, conversational)
These are completely separate. Never cross-wire them.

---

## What's working in production

- ✅ Daily snapshot via morning cron
- ✅ EOD close and streak tracking
- ✅ Supabase health ping (keeps free tier alive)
- ✅ Task creation from natural language with full inference (priority, energy, mandatory flag, category, date)
- ✅ Task completion with fuzzy name matching and partial credit inference
- ✅ Task rescheduling and deferral
- ✅ Event logging (steps, substances, leisure)
- ✅ Multi-day task queries
- ✅ Stat bar live with XP/gold animations
- ✅ 32 tools wired to full script library

---

## Open bugs (as of 2026-05-24)

| ID | Severity | Description | File |
|---|---|---|---|
| CORE-013 | HIGH | Model confuses creation intent with completion — "cant miss it" triggered complete_task on wrong task | `SYSTEM_PROMPT` in `api.py` |
| CORE-014 | MEDIUM | Scheduled events with times created as tasks instead of anchors — anchor queries return nothing | `SYSTEM_PROMPT` in `api.py` |
| CORE-015 | LOW | Task list query sometimes incomplete — non-mandatory tasks filtered or not described | `SYSTEM_PROMPT` / `get_tasks` |

**Previously fixed (for context):**
- CORE-001 through CORE-012 — all resolved. See `PROBLEM_LOG.md` for full history.

---

## Planned but not built

| Feature | Status | Notes |
|---|---|---|
| Cloud hosting (Railway/Render) | Deferred | uvicorn runs locally for now |
| Token optimisation — tool pruning | Queued | 32 tools sent every request (~1600 tokens). Split into READ/WRITE/ADMIN groups, route by intent |
| System prompt compression | Queued | Current prompt ~650 tokens. Strip examples, compress context block |
| Non-LLM interface | Designed, not built | Direct task manager / calendar / stat sheet views calling `reads.py` without LLM. Script library already supports all views |
| Native Android app | Future | WebView wrapper around the web UI |
| PWA / push notifications | Future | Needs service worker |
| `task_stats` migration | Pending | Junction table exists in schema, not live yet. Two known bugs in the write path gated behind it |

---

## Files to read (in order)

1. `docs/00_SHARED_CONTEXT.md` — canonical schema, logic doctrine, all constraints. The single source of truth.
2. `web_ui/api.py` — the live system heart. Tool definitions, executor map, system prompt, chat loop.
3. `scripts/reads.py` + `scripts/writes.py` — the full script library.
4. `scripts/logic.py` — all game formulas. Frozen.
5. `orchestrator/sequencer.py` — the three CLI flows (morning, eod, complete_task).
6. `PROBLEM_LOG.md` — full bug history and current open issues.
7. `SUPERVISOR_LOG.md` — all architectural decisions and session history.

---

## What this mapping team should produce

A single document (or set of documents) that answers:

1. **Data flow map** — for any user action (e.g. "i did the gym"), trace the exact path: UI → API → tool call → script → DB tables touched → response
2. **State mutation map** — which scripts mutate which tables, and what invariants must hold after each mutation
3. **Tool routing map** — which tools exist, when the model should call each, what the model needs to have done before calling each (e.g. must call `get_tasks` before `complete_task`)
4. **Dependency graph** — which components depend on which. What breaks if X changes.
5. **Gap analysis** — what's in the schema but not yet reachable via the chat interface, what's in the UI but not yet wired to real data
6. **Risk register** — load-bearing decisions that, if changed, would cascade. The five invariants above are a start.

The output feeds directly into the next build phase. Every agent after you will reference your map before touching anything.

---

*The system is clean, well-documented, and moving fast. Your job is to make sure the next team never has to reverse-engineer anything.*
