# Life Map — Advance Team Handoff

> **Repo:** https://github.com/caffeinated4ighs/Life_Map
> **Date:** 2026-05-23
> **Status:** Core system operational. Conversational UI live. Ready for feature expansion.

---

## The idea

Life Map started as a Notion-based personal productivity system with RPG elements.
The user wanted a system that *felt* like a game — earning XP and Gold for completing
real-world tasks, tracking skills that decay without practice, managing mental health
as a first-class mechanic that gates what work you're allowed to take on.

The original Notion prototype worked but had limits: no real querying, JSON blobs
instead of proper relational data, no agent-accessible structure, no multi-device support.

The goal of this build was to move it from Notion to a proper stack:
a real database, a hosted SLM for natural language interaction, scripted business logic,
and a web interface the user can open on any device and just talk to.

The system should feel like texting a capable assistant who knows your life,
not filling out a form.

---

## What was explored and decided

### Database
Started from a Notion schema handoff doc. Went through a full architecture review —
the original schema had several gaps (streak logic missing, JSON blobs for events,
missing junction tables, no end_day script). Redesigned into a proper three-layer
relational schema. Chose **Supabase** (Postgres) for hosting — free tier, full SQL,
auto-generated REST API, edge functions built in.

### Inference
Explored local models (VRAM overhead, no multi-device), AWS Lambda + model instances
(~$15/month before inference costs), and settled on **Groq** for SLM inference.
Fast LPU hardware, generous free tier, supports the HuggingFace model ecosystem.
Model: `meta-llama/llama-4-scout-17b-16e-instruct` (swappable via env var).

### Architecture pattern
First attempt used the SLM as a pure JSON router — send a message, get a structured
action back. This broke on anything conversational. Moved to the correct pattern:
**tool-calling conversational agent**. The model holds a conversation and calls
scripts as tools when it needs to interact with the database. This mirrors the
original Notion MCP pattern that the user started from.

### Passive scripts
User has a laptop, can't leave it running. All passive triggers (morning snapshot,
EOD close, health ping) run on **GitHub Actions** free tier cron. No always-on
machine needed. The web UI requires uvicorn running locally for now — cloud
deployment on Railway/Render is the next infrastructure step.

### Interface
WhatsApp API requires Meta business approval — too much friction. Telegram felt wrong.
Built a **single-file web UI** (`index.html`) served by FastAPI. Dark RPG aesthetic,
stat bar always visible, chat-first interaction, works on desktop and Android Chrome.
Native Android app is a future consideration (WebView wrapper is the likely path).

---

## Current architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Actions (free tier)                                     │
│  Morning cron 07:30 EST · EOD cron 23:30 EST · Health 12:00    │
└────────────────────────────┬────────────────────────────────────┘
                             │ python -m orchestrator [flow]
┌────────────────────────────▼────────────────────────────────────┐
│  Orchestrator (local / Actions runner)                          │
│  orchestrator/main.py · sequencer.py · config.py               │
│  Three flows: morning · eod · complete_task (CLI)              │
└──────┬─────────────────────────────────────────┬────────────────┘
       │                                         │
┌──────▼──────────┐                   ┌──────────▼──────────────┐
│  Groq (cloud)   │                   │  Supabase (cloud)        │
│  SLM inference  │                   │  Postgres DB             │
│  Tool-calling   │                   │  17 tables               │
│  chat mode      │                   │  Edge function (health)  │
└──────┬──────────┘                   └──────────┬──────────────┘
       │                                         │
┌──────▼─────────────────────────────────────────▼──────────────┐
│  Web UI (local uvicorn, port 8000)                             │
│  web_ui/api.py (FastAPI) · web_ui/index.html                   │
│  /health · /morning · /state · /chat · /eod                   │
└────────────────────────────────────────────────────────────────┘
```

### Database layer (17 tables)
```
EVENT LAYER:    tasks · task_skill_links · task_stats · events
                anchors · arcs · arc_tasks · arc_skills
                effects · effect_stats · effect_arcs

STATE LAYER:    player_state (singleton) · day_snapshots · streak_log

REFERENCE:      skills · stats
```

### Script layer (`scripts/`)
```
logic.py    — pure formulas: reward stack, MH derivation, modifier tables
reads.py    — 7 read functions: get_player_state, get_today, get_tasks,
              get_task, get_skill_links, get_active_effects, get_active_arcs
writes.py   — 7 write functions: tick_day, complete_task, log_event,
              create_task, create_effect, update_arc_status, end_day
```

### Inference layer (`inference/`)
```
groq_client.py      — CLI SLM client (JSON router, used by orchestrator CLI)
validate_output.py  — validates CLI SLM output against script contracts
system_prompt.txt   — system prompt for CLI mode only
```

### Web UI layer (`web_ui/`)
```
api.py      — FastAPI app. /chat uses Groq tool-calling directly (not groq_client.py)
              Tool-calling loop: model → tool call → script → result → model → reply
index.html  — Single-file chat UI. Dark RPG aesthetic. Stat bar. Task panel. Chat.
```

---

## Current capabilities (confirmed working in production)

- ✅ Daily snapshot creation via `morning` flow
- ✅ Day close, streak tracking via `eod` flow
- ✅ Supabase health ping keeping free tier alive
- ✅ GitHub Actions cron running all three flows automatically
- ✅ Conversational task creation from natural language
  - "tomorrow i need to file my SSN by EOD without fail"
  - → mandatory: true, P0, Hard late rule, tomorrow's date, correct category
- ✅ Task completion via natural language
  - "ssn support letter done"
  - → model fetches UUID from task list autonomously, calls complete_task
  - → reward stack applied, stat bar animates with XP/gold gained
- ✅ Natural read queries
  - "any tasks today?" / "what about tomorrow?" / "stat check"
- ✅ Lifestyle event logging (steps, substances, leisure) via log_event tool
- ✅ Multi-turn conversation with state context maintained per session
- ✅ Stat bar live: MH score with mode color, Gold, XP, Streak
- ✅ Task panel showing today's tasks with status indicators
- ✅ 87/87 logic tests passing locally

---

## Known gaps and next features

### Infrastructure (do first)
| Gap | Detail | Effort |
|-----|--------|--------|
| Web UI not cloud-hosted | uvicorn runs locally — user must keep a terminal open | Low — deploy api.py to Railway/Render free tier, serve index.html from same app |
| No HTTPS on local dev | API runs on http://localhost:8000 | Resolved by cloud deployment |
| GitHub Actions has no Groq key yet | `complete_task` CLI flow untested in Actions | Low — add GROQ_API_KEY to repo secrets |

### Conversational improvements
| Gap | Detail | Effort |
|-----|--------|--------|
| Fuzzy task name matching | "complete ssn task" fails, "ssn support letter done" works — model matches too literally | Low — one line in system prompt: match on key terms, ignore filler words |
| "and tomorrow?" ambiguity | Without explicit "tasks" the model sometimes calls get_player_state instead of get_tasks | Low — system prompt example |
| No conversation memory across sessions | Refreshing the page loses chat history | Medium — store messages in Supabase or localStorage |
| No task disambiguation | If two tasks match a name, model picks one silently | Medium — add clarification step |

### Missing tools (model can't do these yet)
| Feature | What's needed |
|---------|--------------|
| Skill tree visibility | Add `get_skills()` read script + tool definition in api.py |
| Arc management | Add `get_active_arcs` display + `create_arc` tool |
| Effect creation via chat | `create_effect` tool already scripted, just needs adding to TOOLS list |
| Task editing | No `update_task` script exists yet — needs script + tool |
| Task deletion | No `delete_task` script — needs script + tool (with confirmation) |
| Recurring task generation | `recurring_rule` field exists but no script generates future instances |

### UI features
| Feature | Detail | Effort |
|---------|--------|--------|
| Task completion from task panel | Tapping a task should trigger completion flow, not just pre-fill chat | Medium |
| MH color shifting | Stat bar MH dot should go green/amber/red based on score | Low — CSS only |
| Day summary on EOD | After EOD runs, show a daily summary card in chat | Medium |
| Push notifications | Web app can't push — needs PWA service worker or native app | High |
| Mobile PWA | Add manifest.json + service worker so it installs as an app on Android | Medium |
| Native Android app | WebView wrapper around the web UI | Future |

### Game mechanics not yet active
| Mechanic | Status | What's needed |
|----------|--------|--------------|
| Skills and skill XP | Tables exist, seed empty | User needs to create skills; add `create_skill` tool |
| Stat propagation | Script written, tested | Blocked on skills existing |
| Arcs and arc modifiers | Tables exist, no arcs created | Add `create_arc` tool |
| Effects / buffs / debuffs | Tables exist, no effects created | Add `create_effect` to TOOLS |
| Streak rewards | Streak tracked, modifier in logic.py | Working once streak > 0 |
| Skill decay | `in_decay` flag logic written | Needs skills to exist to trigger |
| Late modifiers | Logic written | Working — `late_rule_behavior` per task |

---

## Files to read first (in order)

1. `docs/00_SHARED_CONTEXT.md` — canonical schema, logic doctrine, script contracts, constraints
2. `web_ui/api.py` — the conversational engine, tool definitions, tool executor map
3. `scripts/logic.py` — all game formulas, pure functions
4. `scripts/reads.py` + `scripts/writes.py` — the full script library
5. `orchestrator/sequencer.py` — the three CLI flows

Everything else is supporting infrastructure.

---

## Things that must not change

These decisions are load-bearing. Changing them breaks the system.

1. **`player_state` is a singleton** — exactly one row, `id = 1`, enforced by DB constraint
2. **MH mode is always derived from MH score** — never set directly
3. **MH score always clamped 0–100** — after every mutation
4. **Streak count only updated by `end_day`** — never mid-day
5. **Effects add flat offsets after the reward stack** — never multipliers
6. **`inference/system_prompt.txt` is for the CLI orchestrator only** — do not use for web chat
7. **`scripts/` contains no business logic beyond what's in `00_SHARED_CONTEXT.md`** — all formulas live in `logic.py`
8. **`web_ui/api.py` /chat uses Groq SDK directly** — not `groq_client.py`

---

## Environment variables (all required)

```
SUPABASE_URL              Supabase project URL
SUPABASE_SERVICE_KEY      Service role key (not anon)
GROQ_API_KEY              Groq API key
GROQ_MODEL_ID             Model identifier (default: meta-llama/llama-4-scout-17b-16e-instruct)
TIMEZONE                  User timezone (America/New_York)
LOG_LEVEL                 INFO / DEBUG
HEALTH_CHECK_PATH         /functions/v1/health
```

Local: `.env` file at repo root (gitignored).
Production: GitHub Actions secrets + Railway/Render env vars.

---

## Immediate next recommended actions

In priority order:

1. **Deploy `web_ui/` to Railway** — removes the "keep uvicorn running" friction entirely
2. **Add `get_skills` read script + tool** — the model currently can't answer "skill tree?"
3. **Add `create_arc` tool** — lets the user define goal windows via chat
4. **Fuzzy task name matching** — one system prompt line, unblocks smoother completions
5. **Recurring task generation** — `recurring_rule` field exists, needs a daily script
   that creates tomorrow's instances of recurring tasks during the `eod` flow

---

## The team

This system was built across one session by a coordinated agent team:

- **DB Agent** — schema design, migrations, RLS, Supabase edge function
- **Inference Agent** — Groq client, system prompt, output validator
- **Scripts Agent** — full logic and read/write script library, 87 tests
- **Orchestrator Agent** — CLI flows, cron, error handling, sequencing
- **Web UI Agent** — FastAPI backend, conversational tool-calling loop, frontend
- **Debug Agent** — three targeted bug fixes post-integration
- **Supervisor** — cross-agent coordination, architecture decisions, handoffs

The codebase is clean, well-documented, and ready for feature work.
Welcome to the team — the foundation is solid.

---

*"The system should feel like texting a capable assistant who knows your life,
not filling out a form."*

*— original brief, and the standard everything is held to.*
