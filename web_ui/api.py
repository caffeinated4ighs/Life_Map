from dotenv import load_dotenv
load_dotenv()
 
from datetime import date
from typing import Optional
 
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
 
# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
 
app = FastAPI(title="Life Map API", version="1.0.0")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
 
 
@app.get("/")
def serve_ui():
    return FileResponse("web_ui/index.html")
 
 
# ---------------------------------------------------------------------------
# Shared config loader — lazy so dotenv runs first
# ---------------------------------------------------------------------------
 
def _config():
    from orchestrator.config import load_config
    return load_config()
 
 
# ---------------------------------------------------------------------------
# Read intent router
#
# Intercepts natural-language read queries before they hit the SLM.
# Returns a ChatResponse-shaped dict on match, or None to fall through to SLM.
#
# Design rules:
#   - Match on normalised lowercase tokens only (no regex, no NLP)
#   - Err on the side of NOT matching — ambiguous input goes to the SLM
#   - Format read results as terse game-terminal output, not assistant prose
# ---------------------------------------------------------------------------
 
# Keyword sets — a message matches if it contains ANY of these tokens
_TASK_TOKENS    = {"tasks", "task", "todo", "todos", "queue", "queued", "today"}
_STATE_TOKENS   = {"stats", "state", "score", "status", "mh", "gold", "xp", "streak", "balance"}
_ARC_TOKENS     = {"arc", "arcs", "quest", "quests", "storyline", "story"}
_EFFECT_TOKENS  = {"effect", "effects", "buff", "buffs", "debuff", "debuffs", "modifier", "active"}
 
# Exclusion tokens — if the message contains any of these it's probably a write
_WRITE_TOKENS   = {
    "complete", "done", "finish", "finished", "add", "create", "new",
    "log", "skip", "update", "cancel", "delete", "remove", "mark",
    "half", "partial", "late", "tired", "sick",
}
 
 
def _normalise(msg: str) -> set:
    """Lowercase, strip punctuation, return token set."""
    import re
    return set(re.sub(r"[^\w\s]", "", msg.lower()).split())
 
 
def _format_tasks(tasks: list, mh_mode: str) -> str:
    if not tasks:
        return "No tasks scheduled for today."
    lines = [f"Tasks · {mh_mode} mode ({len(tasks)} queued)"]
    for t in tasks:
        status_sym = {"Done": "✓", "Skipped": "—"}.get(t.get("status", ""), "·")
        name   = t.get("name") or t.get("task_name") or "Unnamed"
        xp_str = f"  {t['base_xp']} XP" if t.get("base_xp") else ""
        lines.append(f"  {status_sym} {name}{xp_str}")
    return "\n".join(lines)
 
 
def _format_state(ps: dict) -> str:
    return (
        f"MH {ps.get('mh_score', '?')} · {ps.get('mh_mode', '?')} mode\n"
        f"Gold {ps.get('gold_balance', '?')} · "
        f"XP {ps.get('total_xp', '?')} · "
        f"Streak {ps.get('streak_count', '?')} days"
    )
 
 
def _format_arcs(arcs: list) -> str:
    if not arcs:
        return "No active arcs."
    lines = [f"Active arcs ({len(arcs)})"]
    for a in arcs:
        name     = a.get("arc") or a.get("name") or "Unnamed arc"
        pressure = a.get("pressure_level") or a.get("intensity") or ""
        pstr     = f"  [{pressure}]" if pressure else ""
        lines.append(f"  · {name}{pstr}")
    return "\n".join(lines)
 
 
def _format_effects(effects: list) -> str:
    if not effects:
        return "No active effects."
    lines = [f"Active effects ({len(effects)})"]
    for e in effects:
        name      = e.get("effect") or e.get("name") or "Unnamed effect"
        intensity = e.get("intensity") or ""
        istr      = f"  [{intensity}]" if intensity else ""
        lines.append(f"  · {name}{istr}")
    return "\n".join(lines)
 
 
def _try_read_route(msg: str, ctx: Optional["ChatContext"]) -> Optional[dict]:
    """
    Returns a ChatResponse-shaped dict if the message is a clear read intent,
    otherwise returns None (caller should proceed to SLM).
    """
    tokens = _normalise(msg)
 
    # If any write token is present, don't intercept — let SLM handle it
    if tokens & _WRITE_TOKENS:
        return None
 
    today_str  = (ctx.date if ctx and ctx.date else None) or date.today().isoformat()
    mh_mode    = (ctx.mh_mode if ctx else None) or "Normal"
 
    try:
        from scripts.reads import (
            get_player_state,
            get_tasks,
            get_active_arcs,
            get_active_effects,
        )
    except ImportError as e:
        # reads not available — fall through to SLM
        return None
 
    # ── tasks ──────────────────────────────────────────────────────────────
    if tokens & _TASK_TOKENS:
        tasks = get_tasks(today_str, mh_mode)
        return {
            "reply":       _format_tasks(tasks, mh_mode),
            "state_delta": None,
            "action_taken": "get_tasks",
            "declined":    False,
        }
 
    # ── player state / stats ───────────────────────────────────────────────
    if tokens & _STATE_TOKENS:
        ps = get_player_state()
        return {
            "reply":        _format_state(ps),
            "state_delta":  None,
            "action_taken": "get_player_state",
            "declined":     False,
        }
 
    # ── arcs ───────────────────────────────────────────────────────────────
    if tokens & _ARC_TOKENS:
        arcs = get_active_arcs()
        return {
            "reply":        _format_arcs(arcs),
            "state_delta":  None,
            "action_taken": "get_active_arcs",
            "declined":     False,
        }
 
    # ── effects ────────────────────────────────────────────────────────────
    if tokens & _EFFECT_TOKENS:
        effects = get_active_effects()
        return {
            "reply":        _format_effects(effects),
            "state_delta":  None,
            "action_taken": "get_active_effects",
            "declined":     False,
        }
 
    return None  # no match — proceed to SLM
 
 
# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------
 
class ChatContext(BaseModel):
    mh_score:     Optional[int] = None
    mh_mode:      Optional[str] = None
    gold_balance: Optional[int] = None
    streak_count: Optional[int] = None
    date:         Optional[str] = None
 
 
class ChatRequest(BaseModel):
    message: str
    context: Optional[ChatContext] = None
 
 
class ChatResponse(BaseModel):
    reply:        str
    state_delta:  Optional[dict] = None
    action_taken: Optional[str]  = None
    declined:     bool           = False
 
 
# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
 
@app.get("/health")
def health():
    """Ping Supabase via the orchestrator health check."""
    try:
        from orchestrator.health import health_check
        ok = health_check(_config())
        if ok:
            return {"status": "ok"}
        raise HTTPException(status_code=503, detail="Supabase health check failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/morning")
def morning():
    """
    Run the morning briefing flow.
    Returns: {date, snapshot, player_state, tasks, active_arcs, active_effects}
    """
    try:
        from orchestrator.sequencer import run_morning
        return run_morning(_config())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/state")
def state():
    """Lightweight stat refresh — player state only, no full morning flow."""
    try:
        from scripts.reads import get_player_state
        ps = get_player_state()
        return {
            "mh_score":     ps.get("mh_score"),
            "mh_mode":      ps.get("mh_mode"),
            "gold_balance": ps.get("gold_balance"),
            "streak_count": ps.get("streak_count"),
            "total_xp":     ps.get("total_xp"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Main conversational endpoint.
 
    Flow:
      1. Read router — intercept obvious read intents (tasks, stats, arcs, effects)
         without touching the SLM. Fast, cheap, reliable.
      2. SLM route — everything else goes through run_complete_task.
      3. Build a human reply from the script result dict.
    """
    # ── 1. Read router ───────────────────────────────────────────────────
    read_result = _try_read_route(req.message, req.context)
    if read_result is not None:
        return ChatResponse(**read_result)
 
    # ── 2. SLM route ─────────────────────────────────────────────────────
    try:
        from orchestrator.sequencer import run_complete_task
        from scripts.reads import get_player_state
 
        # Enrich context with defaults if frontend didn't send them
        today = date.today().isoformat()
        mh_mode = req.context.mh_mode if req.context and req.context.mh_mode else None
 
        if not mh_mode:
            ps = get_player_state()
            mh_mode = ps.get("mh_mode", "Normal")
 
        context_prefix = (
            f"[Context: date={today}, "
            f"MH {req.context.mh_score if req.context else 75} "
            f"({mh_mode}), "
            f"Gold {req.context.gold_balance if req.context else 0}, "
            f"Streak {req.context.streak_count if req.context else 0}] "
        )
 
        result = run_complete_task(_config(), context_prefix + req.message)
 
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    # ── Declined / out-of-scope ──────────────────────────────────────────
    if not result or result.get("status") == "declined":
        return ChatResponse(
            reply=(
                "I didn't quite catch that — could you be more specific? "
                "For example: 'completed workout' or 'add a task for reviewing notes tonight'."
            ),
            declined=True,
        )
 
    # ── 3. Build reply from script result dict ───────────────────────────
    # complete_task → {final_xp, final_gold, new_mh_score, new_mh_mode, new_gold_balance}
    # create_task, log_event, etc. → their own shapes
    reply_parts = []
 
    final_xp   = result.get("final_xp")
    final_gold = result.get("final_gold")
    new_mh     = result.get("new_mh_score")
    new_mode   = result.get("new_mh_mode")
    new_gold   = result.get("new_gold_balance")
 
    if final_xp is not None or final_gold is not None:
        gains = []
        if final_xp   is not None: gains.append(f"+{final_xp} XP")
        if final_gold is not None: gains.append(f"+{final_gold} Gold")
        reply_parts.append(", ".join(gains))
 
    if new_mh is not None:
        reply_parts.append(f"MH → {new_mh} ({new_mode or ''})")
 
    if not reply_parts:
        action = result.get("action") or result.get("status", "done")
        reply_parts.append(f"Done. ({action})")
 
    reply = " · ".join(reply_parts) + "." if reply_parts else "Done."
 
    # ── state_delta for UI animation ─────────────────────────────────────
    ctx_mh   = req.context.mh_score    if req.context else None
    state_delta = None
    if final_xp is not None or final_gold is not None or new_mh is not None:
        mh_delta = (new_mh - ctx_mh) if (new_mh is not None and ctx_mh is not None) else None
        state_delta = {
            "xp_earned":        final_xp,
            "gold_delta":       final_gold,
            "mh_delta":         mh_delta,
            "new_mh_score":     new_mh,
            "new_mh_mode":      new_mode,
            "new_gold_balance": new_gold,
        }
 
    return ChatResponse(
        reply=reply,
        state_delta=state_delta,
        action_taken=result.get("action", "complete_task"),
        declined=False,
    )
 
 
@app.post("/eod")
def eod():
    """Run the end-of-day close flow manually."""
    try:
        from orchestrator.sequencer import run_eod
        return run_eod(_config())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 