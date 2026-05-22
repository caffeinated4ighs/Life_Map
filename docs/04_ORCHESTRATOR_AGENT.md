# Life System — Orchestrator Agent Handoff

## Your role

You are the **Orchestrator Agent**. You wire everything together — the database, the SLM inference, and the scripts — into a single runnable system. You own the cron trigger, secrets management, call sequencing, error handling, and logging. You are **step 4 of 4** in the build pipeline, built last when all other parts are stable.

---

## Your position in the pipeline

```
  ┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │ 1. DB    │ ──▸ │ 2. Inference │ ──▸ │ 3. Scripts   │ ──▸ │ 4. Orchestr. │
  │  Agent   │     │    Agent     │     │    Agent     │     │    Agent     │
  │          │     │              │     │              │     │   (you)      │
  └──────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

**You depend on everything:**
- DB Agent → live Supabase schema + health-check endpoint
- Inference Agent → `groq_client.py` (call_agent function) + `validate_output.py`
- Scripts Agent → `scripts/reads.py`, `scripts/writes.py`, `scripts/logic.py`

**Nothing depends on you** — you are the top of the call stack.

---

## What you own

### Project structure

```
orchestrator/
├── __init__.py
├── main.py              # Entry point — the daily runner
├── config.py            # Environment + secrets loading
├── sequencer.py         # Call sequencing logic
├── health.py            # Supabase keep-alive ping
├── logger.py            # Structured logging
├── error_handler.py     # Retry logic + failure modes
└── run_history.json     # Append-only log of each run (gitignored)
```

### 1. `config.py` — Environment and secrets

Load all secrets from environment variables. Never hardcode.

**Required env vars:**
```
SUPABASE_URL            # Supabase project URL
SUPABASE_SERVICE_KEY    # Service role key (not anon)
GROQ_API_KEY            # Groq API key
GROQ_MODEL_ID           # Model identifier on Groq
LOG_LEVEL               # DEBUG / INFO / WARN / ERROR (default: INFO)
TIMEZONE                # User's timezone for date resolution (e.g. "America/New_York")
```

Expose a `Config` dataclass or dict that the rest of the system imports. Validate on startup — fail fast if any required var is missing.

### 2. `sequencer.py` — Call sequencing

This is the core logic of the orchestrator. It defines the two primary flows:

#### Morning flow (`run_morning`)
Called at day start (or first interaction of the day).

```
1. health_check()                          → abort if Supabase is down
2. get_today(today)                        → check if snapshot exists
3. IF needs_init: tick_day(today)          → create snapshot, expire effects, check decay
4. get_player_state()                      → read current state
5. get_tasks(today, player_state.mh_mode)  → build today's task list
6. get_active_arcs()                       → context for the user
7. get_active_effects()                    → context for the user
8. Return assembled day briefing to caller
```

#### EOD flow (`run_eod`)
Called by cron at end of day.

```
1. health_check()                          → abort if Supabase is down
2. get_today(today)                        → verify snapshot exists
3. IF NOT exists: abort with error         → morning never ran
4. end_day(today)                          → close snapshot, write streak
5. get_player_state()                      → read final state for logging
6. Log run result to run_history.json
7. Return EOD summary
```

#### Task completion flow (`run_complete_task`)
Called when the user completes a task (via SLM interaction or direct API).

```
1. call_agent(user_message, context)       → SLM produces {action, args}
2. validate_output(result)                 → check structure
3. IF invalid: retry call_agent once       → SLM may self-correct
4. IF still invalid: abort, log error
5. Route to correct script function based on action
6. Return script result
```

**Routing table for step 5:**
| action | function |
|--------|----------|
| get_player_state | reads.get_player_state() |
| get_today | reads.get_today(args.date) |
| get_tasks | reads.get_tasks(args.date, args.mh_mode) |
| get_task | reads.get_task(args.task_id) |
| get_skill_links | reads.get_skill_links(args.task_id) |
| get_active_effects | reads.get_active_effects() |
| get_active_arcs | reads.get_active_arcs() |
| tick_day | writes.tick_day(args.date) |
| complete_task | writes.complete_task(args.task_id, args) |
| log_event | writes.log_event(args.event_type, args.payload) |
| create_task | writes.create_task(args) |
| create_effect | writes.create_effect(args) |
| update_arc_status | writes.update_arc_status(args.arc_id, args.status) |
| end_day | writes.end_day(args.date) |

Any `action` not in this table is rejected — never execute unknown script names.

### 3. `health.py` — Supabase keep-alive

- Call the Supabase Edge Function health-check endpoint (produced by DB Agent).
- If healthy: return True, log at DEBUG level.
- If unhealthy: return False, log at ERROR level.
- This runs as the first step of every flow AND as a standalone daily cron job to keep the Supabase free-tier project alive.

### 4. `logger.py` — Structured logging

- Use Python's `logging` module.
- Format: `[TIMESTAMP] [LEVEL] [MODULE] message`
- Log every script call with: function name, arguments (redacted if sensitive), result summary, duration.
- Log every SLM call with: model used, token count, latency, success/failure.
- Log every health check result.
- Write to both stderr and `run_history.json` (append-only, one JSON object per line).

### 5. `error_handler.py` — Failure modes

Define explicit failure modes and what to do:

| Failure | Action |
|---------|--------|
| Supabase unreachable | Abort flow, log, retry in 5 min (max 3 retries) |
| Groq API 429 (rate limit) | Wait 30s, retry once |
| Groq API 500 | Retry once after 5s, then abort |
| SLM returns invalid JSON | Retry inference once, then abort |
| SLM returns valid JSON but unknown action | Reject, log, abort |
| Script returns {success: false} | Log error, do NOT retry (script failures are not transient) |
| tick_day returns already_exists | Not an error — skip silently, continue flow |
| end_day called but no snapshot exists | Log warning, abort EOD flow |
| Config var missing on startup | Fail fast with clear error message |

Never silently swallow errors. Every failure must appear in logs.

### 6. `main.py` — Entry point

```python
# Usage:
#   python -m orchestrator morning     → run morning flow
#   python -m orchestrator eod         → run EOD flow
#   python -m orchestrator health      → run health check only
#   python -m orchestrator complete "user message here"  → task completion via SLM
```

Parse CLI args, load config, call the appropriate sequencer function, print result to stdout, exit with 0 (success) or 1 (failure).

### 7. Cron setup

Document (in a `cron_setup.md`) how to set up the two cron jobs:

- **EOD trigger:** runs `python -m orchestrator eod` every day at 23:30 in the user's timezone.
- **Health ping:** runs `python -m orchestrator health` every day at 12:00 (keeps Supabase alive).

Provide both:
- A `crontab -e` entry for local Unix/Mac.
- A GitHub Actions workflow YAML for cloud-hosted cron (free tier supports scheduled workflows).

---

## What you do NOT own

- Database schema or migrations (DB Agent).
- Groq client internals or system prompt (Inference Agent).
- Script logic or formula implementation (Scripts Agent).
- Any decision about what tasks to assign, arc priority, or user behavior interpretation.

---

## Deliverables checklist

| File | Format | Purpose |
|------|--------|---------|
| `orchestrator/__init__.py` | Python | Package init |
| `orchestrator/main.py` | Python | CLI entry point |
| `orchestrator/config.py` | Python | Env var loading + validation |
| `orchestrator/sequencer.py` | Python | Morning / EOD / complete flows |
| `orchestrator/health.py` | Python | Supabase keep-alive |
| `orchestrator/logger.py` | Python | Structured logging |
| `orchestrator/error_handler.py` | Python | Retry + failure mode handling |
| `cron_setup.md` | Markdown | Cron job setup instructions |
| `.env.example` | Dotenv | Template of required env vars |

---

## Validation criteria

Before considering this done, verify:
- [ ] `python -m orchestrator health` returns success against live Supabase.
- [ ] `python -m orchestrator morning` creates a snapshot and returns a task list.
- [ ] Running morning twice on the same day does not create a duplicate snapshot.
- [ ] `python -m orchestrator eod` closes the snapshot and writes streak log.
- [ ] Running eod before morning on a given day aborts cleanly.
- [ ] `python -m orchestrator complete "Complete task X on time"` routes through SLM → validator → script → DB correctly.
- [ ] An invalid SLM response triggers one retry, then aborts with a logged error.
- [ ] All env vars missing on startup produces a clear, actionable error message.
- [ ] `run_history.json` captures every run with timestamp, flow type, and result.
- [ ] The cron job keeps the Supabase project alive over a 7-day test period.

---

## Integration test sequence

After all four agents have delivered, run this sequence end-to-end:

```
1. python -m orchestrator health        → expect "ok"
2. python -m orchestrator morning       → expect snapshot + task list
3. python -m orchestrator complete "Complete task <id> on time with full credit"
                                         → expect reward calculation + state update
4. python -m orchestrator complete "Log 8000 steps"
                                         → expect MH bonus + gold unchanged
5. python -m orchestrator eod           → expect close values + streak update
6. python -m orchestrator morning       → next day, expect new snapshot
7. Verify player_state reflects all changes
8. Verify streak_log has entries for both days
9. Verify skills and stats were updated by task completion
```

---

*Read `00_SHARED_CONTEXT.md` before starting. You do not implement business logic — you sequence calls and handle failures. If you find yourself calculating XP or deriving MH mode, you are in the wrong lane.*
