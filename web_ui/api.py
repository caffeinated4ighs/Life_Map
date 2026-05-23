from dotenv import load_dotenv
load_dotenv()

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

# Serve the single-file UI at root so Railway/Render deployments just work
@app.get("/")
def serve_ui():
    return FileResponse("web_ui/index.html")


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ChatContext(BaseModel):
    mh_score: Optional[int] = None
    mh_mode: Optional[str] = None
    gold_balance: Optional[int] = None
    streak_count: Optional[int] = None
    date: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    context: Optional[ChatContext] = None


class ChatResponse(BaseModel):
    reply: str
    state_delta: Optional[dict] = None
    action_taken: Optional[str] = None
    declined: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Ping the orchestrator health check (Supabase edge function)."""
    try:
        from orchestrator.sequencer import run_health
        result = await run_health() if hasattr(run_health, "__await__") else run_health()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/morning")
async def morning():
    """
    Run the morning briefing flow.
    Returns snapshot, player state, tasks, arcs, and effects for today.
    """
    try:
        from orchestrator.sequencer import run_morning
        result = run_morning()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state")
async def state():
    """
    Lightweight stat refresh — player state + today's record only.
    Use this to update the stats bar without a full morning run.
    """
    try:
        from scripts.reads import get_player_state, get_today
        today = date.today().isoformat()
        player = get_player_state()
        today_record = get_today(today)
        return {
            "mh_score": player.get("mh_score"),
            "mh_mode": player.get("mh_mode"),
            "gold_balance": player.get("gold_balance"),
            "streak_count": player.get("streak_count"),
            "total_xp": player.get("total_xp"),
            "today": today_record,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main conversational endpoint. Routes a natural-language message through
    the SLM → validator → scripts pipeline and returns a structured reply.

    The context object is injected into the SLM system prompt so vague inputs
    ("only did half") resolve correctly against the current player state.
    """
    try:
        from orchestrator.main import call_agent

        # Build the context block that gets prepended to the system prompt
        ctx = req.context
        context_block = ""
        if ctx:
            context_block = (
                f"\n\n## Current player state\n"
                f"- MH Score: {ctx.mh_score} ({ctx.mh_mode} mode)\n"
                f"- Gold: {ctx.gold_balance}\n"
                f"- Streak: {ctx.streak_count} days\n"
                f"- Date: {ctx.date or date.today().isoformat()}\n\n"
                "## Default filling rules\n"
                "- Completion time not stated → assume on_time\n"
                "- Partial credit not stated → assume 1.0 (full credit)\n"
                "- User says 'tired', 'rough', or 'only half' → partial_credit: 0.5\n"
                "- Task not identified by UUID → ask for clarification, do not guess\n"
                "- Multiple actions in one message → handle the first, acknowledge the rest\n"
            )

        result = call_agent(req.message, context_block=context_block)

        # call_agent returns a dict; normalise into our response shape
        if not result or result.get("action") == "error":
            return ChatResponse(
                reply=(
                    "I didn't quite catch that — could you be more specific? "
                    "For example: 'completed workout' or 'add a task for reviewing notes tonight'."
                ),
                declined=True,
            )

        return ChatResponse(
            reply=result.get("reply", "Done."),
            state_delta=result.get("state_delta"),
            action_taken=result.get("action_taken"),
            declined=False,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/eod")
async def eod():
    """
    Run the end-of-day close flow manually.
    Returns the day-close summary.
    """
    try:
        from orchestrator.sequencer import run_eod
        result = run_eod()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
