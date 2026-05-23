# Life Map — Web UI Agent Handoff

## Your role

You are the **Web UI Agent**. You build the conversational front end for the Life Map
system — a FastAPI backend that wraps the orchestrator, and a chat-based web interface
that works on any device. This is the layer the user actually talks to every day.

---

## Catch up on the project

Read the repo first: **https://github.com/caffeinated4ighs/Life_Map**

Key files to read before writing a single line:
- `docs/00_SHARED_CONTEXT.md` — full schema, script contracts, logic doctrine
- `orchestrator/sequencer.py` — the three flows you'll be calling (morning, eod, complete)
- `orchestrator/main.py` — how the CLI currently works (you're replacing this with HTTP)
- `env.example` — all env vars already in use

The system is fully operational. DB is live on Supabase, SLM inference runs on Groq,
cron jobs run on GitHub Actions. Your job is to put a face on it.

---

## What you own

```
web_ui/
├── api.py          ← FastAPI app — HTTP wrapper around the orchestrator
└── index.html      ← Single-file chat UI — calls the API, works on all devices
```

Two files. That's the entire deliverable.

---

## Part 1 — `api.py` (FastAPI backend)

### Purpose
Exposes the orchestrator flows as HTTP endpoints so the web UI can call them.
Loads `.env` on startup. Handles CORS so the HTML file can call it from any origin.

### Dependencies
```
fastapi
uvicorn
python-dotenv
```
These go into `requirements.txt` alongside the existing ones.

### Endpoints

#### `GET /health`
Calls `orchestrator.sequencer.run_health()`.
Returns the Supabase edge function response.
```json
{ "status": "ok" }
```

#### `GET /morning`
Calls `orchestrator.sequencer.run_morning()`.
Returns today's full briefing — snapshot, player state, tasks, arcs, effects.
The UI calls this on first load each day to populate the dashboard.

#### `GET /state`
Calls `scripts.reads.get_player_state()` and `scripts.reads.get_today(date)`.
Lightweight — used to refresh the stats bar without a full morning run.
```json
{
  "mh_score": 75,
  "mh_mode": "Reduced",
  "gold_balance": 52,
  "streak_count": 0,
  "total_xp": 5
}
```

#### `POST /chat`
This is the main endpoint. Takes a plain-language message from the user and
routes it through the SLM → validator → scripts pipeline.

Request body:
```json
{
  "message": "finished gym, was tired, only did half",
  "context": {
    "mh_score": 75,
    "mh_mode": "Reduced",
    "gold_balance": 52,
    "streak_count": 0,
    "date": "2026-05-23"
  }
}
```

Response:
```json
{
  "reply": "Logged workout with partial credit (0.5x). +3 XP, +1 Gold. MH +2.",
  "state_delta": {
    "xp_earned": 3,
    "gold_delta": 1,
    "mh_delta": 2,
    "new_mh_score": 77,
    "new_gold_balance": 53
  },
  "action_taken": "complete_task",
  "declined": false
}
```

If the SLM returns `{"action": "error"}` (out of scope or ambiguous):
```json
{
  "reply": "I didn't quite catch that — could you be more specific? For example: 'completed workout' or 'add a task for reviewing notes tonight'.",
  "declined": true
}
```

#### `POST /eod`
Calls `orchestrator.sequencer.run_eod()`.
Returns the day close summary. The UI can expose a manual EOD button.

### Conversational context injection

The `/chat` endpoint passes the `context` object to `call_agent()` so the SLM
knows the current player state when interpreting vague messages. This is what
allows "only did half" to resolve to `partial_credit: 0.5` — the model knows
the current state and can make sensible defaults.

**Default filling rules for vague input** — instruct the SLM via the system prompt
context block:
- Completion time not stated → assume `on_time`
- Partial credit not stated → assume `1.0` (full)
- If user says "tired", "rough", "only half" → `partial_credit: 0.5`
- Task not identified by UUID → SLM should ask for clarification rather than guess
- Multiple actions in one message → handle the first, acknowledge the rest

### Startup
```python
from dotenv import load_dotenv
load_dotenv()
```
At the very top, before any other imports.

### CORS
Allow all origins during development:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
```

### Running locally
```bash
uvicorn web_ui.api:app --reload --port 8000
```

---

## Part 2 — `index.html` (Web UI)

### Purpose
A single self-contained HTML file. No build step, no framework, no node_modules.
Opens in any browser on any device. The user bookmarks it and uses it daily.

### Device targets
- **Windows laptop** — full browser, 1080p+, keyboard input, mouse hover states
- **Android phone** — Chrome mobile, touch input, ~390px viewport, thumb-friendly tap targets
- **Future** — the HTML/JS structure should be clean enough that a native Android wrapper
  (WebView-based) could wrap it later without changes to the UI logic

### Design direction
This is an RPG life system — it should feel like a game interface, not a productivity app.
Think dark theme, stat bars, character sheet energy. Not fantasy kitsch — more like
a clean tactical RPG UI. Minimal, intentional, slightly futuristic.

Specific requirements:
- **Dark background** — deep charcoal or near-black, not pure #000
- **Stat bar at the top** — MH score (with color that shifts: green 80+, amber 60-79,
  red below 60), Gold, Streak, XP. Compact, always visible.
- **Chat area** — messages from user on the right, system responses on the left.
  System responses should feel like game feedback, not assistant chat bubbles.
- **Today's tasks** — collapsible panel above the chat showing today's task list
  with status indicators. Tapping a task should pre-fill the chat input with
  "Complete [task name]".
- **Input bar** — fixed at bottom, large enough for thumb use on mobile.
  Send on Enter (desktop) and tap (mobile).
- **No scrollbar on mobile** — use `overflow: hidden` on body, scroll only inside
  the chat area.
- Typography: pick something with character — not Inter, not Roboto.
  Something that fits the RPG-adjacent aesthetic without being unreadable.

### API calls from the UI

The HTML file calls `http://localhost:8000` by default. Make the base URL
a variable at the top of the script block so it's easy to swap when deployed:

```javascript
const API_BASE = "http://localhost:8000"; // change to deployed URL when hosted
```

**On page load:**
1. Call `GET /morning` — populate stats bar and task list
2. Show a welcome message in chat: today's date, MH mode, task count

**On message send:**
1. Show user message in chat immediately (optimistic)
2. Call `POST /chat` with message + current context
3. Show system response
4. If `state_delta` present — animate the stat bar updating
5. If `declined: true` — show the clarification prompt in a distinct style

**Stat bar refresh:**
After every `/chat` response that includes `state_delta`, update the displayed
values without a full page reload. Animate the number changes.

### Mobile-specific requirements
- Minimum tap target: 44px height on all interactive elements
- Input bar must not be covered by the Android soft keyboard —
  use `height: 100dvh` and `position: fixed` on the input bar
- Font size minimum 16px on inputs (prevents iOS/Android zoom on focus)
- Task list panel should be swipeable or collapsible to give chat more space

---

## Deployment target

For now: **local only**. The user runs `uvicorn web_ui.api:app --reload --port 8000`
on their laptop and opens `index.html` in the browser (or serves it via uvicorn's
static files).

Later: Railway or Render free tier for the API, with `index.html` served as a
static file from the same app. Design for this from the start — don't hardcode
localhost in ways that can't be changed with a single variable.

Structure `api.py` to also serve `index.html` as the root route:
```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

@app.get("/")
def serve_ui():
    return FileResponse("web_ui/index.html")
```

So when deployed, the user just goes to the Railway/Render URL and the UI loads.
No separate static hosting needed.

---

## What you do NOT own

- Database schema or migrations — already live on Supabase, do not touch
- Script logic or formulas — `scripts/` package is complete, import and call only
- SLM system prompt — `inference/system_prompt.txt` is the source of truth,
  do not modify it. The `/chat` endpoint passes context alongside it.
- Cron jobs or GitHub Actions — already configured, do not touch
- Any env var not already in `env.example` — you may add `PORT` and `API_BASE_URL`
  but nothing else

---

## Deliverables checklist

| File | Purpose |
|------|---------|
| `web_ui/api.py` | FastAPI backend, 5 endpoints |
| `web_ui/index.html` | Single-file chat UI, all devices |

Also update:
| File | Change |
|------|--------|
| `requirements.txt` | Add `fastapi`, `uvicorn[standard]` |
| `README.md` | Add "Running the web UI" section |

---

## Validation criteria

Before handing off, verify:
- [ ] `uvicorn web_ui.api:app --reload` starts without errors
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `GET /morning` returns snapshot + player state + tasks
- [ ] `POST /chat` with `"finished my workout"` routes through SLM and returns a reply
- [ ] `POST /chat` with `"what's the meaning of life"` returns `declined: true`
- [ ] `index.html` opens in Chrome on desktop — stats bar visible, chat works
- [ ] `index.html` opens in Chrome on Android — no layout breaks, input not covered by keyboard
- [ ] Tapping a task in the task list pre-fills the chat input
- [ ] Stat bar animates after a successful complete_task response
- [ ] The single variable `API_BASE` controls where all API calls go

---

## Local run instructions (include these in README)

```bash
# 1. Activate env
conda activate life_system

# 2. Load env vars (PowerShell)
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.+)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}

# 3. Start the API
uvicorn web_ui.api:app --reload --port 8000

# 4. Open the UI
# Navigate to http://localhost:8000 in your browser
# Or open web_ui/index.html directly (set API_BASE = "http://localhost:8000")
```

---

*Supervisor note: the backend and DB are fully operational — this agent's job is
purely the interface layer. Keep `api.py` thin: it receives, routes, and responds.
All business logic stays in `orchestrator/` and `scripts/`. If you find yourself
writing reward calculations or modifier logic in `api.py`, you are in the wrong lane.*
