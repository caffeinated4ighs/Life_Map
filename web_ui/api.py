from dotenv import load_dotenv
load_dotenv()

import json
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Life Map API", version="2.0.0")

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
# Groq client — initialised once at module load
# ---------------------------------------------------------------------------

from groq import Groq

_groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
_model = os.environ.get("GROQ_MODEL_ID", "meta-llama/llama-4-scout-17b-16e-instruct")

# ---------------------------------------------------------------------------
# Config loader — lazy, used by non-chat endpoints only
# ---------------------------------------------------------------------------

def _config():
    from orchestrator.config import load_config
    return load_config()


# ---------------------------------------------------------------------------
# Tool definitions — exposed to the LLM
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "Get today's task list filtered by MH mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date":    {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "mh_mode": {
                        "type": "string",
                        "enum": ["Normal", "Reduced", "Minimum Viable", "Recovery Only"]
                    }
                },
                "required": ["date", "mh_mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_state",
            "description": "Get current player stats: MH score, gold, XP, streak.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as done and apply XP/gold rewards.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "UUID of the task"},
                    "completion_time": {
                        "type": "string",
                        "enum": ["on_time", "soft", "meaningful_delay", "hard_failure", "void"]
                    },
                    "partial_credit": {
                        "type": "number",
                        "description": "0.0 to 1.0. Use 0.5 if user says tired/only half/rough."
                    },
                    "mh_mode": {
                        "type": "string",
                        "enum": ["Normal", "Reduced", "Minimum Viable", "Recovery Only"]
                    }
                },
                "required": ["task_id", "completion_time", "partial_credit", "mh_mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task. Fill in sensible defaults for any fields the user didn't specify.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task":               {"type": "string"},
                    "type":               {"type": "string", "enum": ["Daily", "Weekly", "Recurring", "Mandatory", "Optional", "Bonus"],"description": "Recurrence pattern only. One-off tasks → 'Optional'. Use priority and mandatory fields for importance."},
                    "priority":           {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                    "category":           {"type": "string", "enum": ["Health", "Study", "Work", "Social", "Maintenance", "Hobby"],"description": "Life area. Admin/paperwork/government tasks → 'Work' or 'Maintenance'. Never use task type values here."},
                    "date":               {"type": "string", "description": "YYYY-MM-DD. Use tomorrow's date if user says 'tomorrow'."},
                    "energy_cost":        {"type": "string", "enum": ["Low", "Medium", "High", "Very High"]},
                    "late_rule":          {"type": "string", "enum": ["None", "Soft", "Medium", "Hard"]},
                    "late_rule_behavior": {"type": "string", "enum": ["Penalty", "Incentive", "Neutral"]},
                    "mandatory":          {"type": "boolean"},
                    "xp":                 {"type": "integer"},
                    "gold":               {"type": "integer"},
                    "time_block":         {"type": "string", "enum": ["Morning", "Afternoon", "Evening", "Night", "Flexible"]}
                },
                "required": ["task", "priority", "category", "date", "energy_cost",
                             "late_rule", "late_rule_behavior", "mandatory", "xp", "gold", "time_block"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_event",
            "description": "Log a lifestyle event: steps walked, substance use, leisure, day off, cheat day.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "enum": ["steps", "substance", "leisure", "day_off", "cheat_day", "mh_manual"]
                    },
                    "name":               {"type": "string",  "description": "e.g. 'cigarette', 'guitar practice'"},
                    "quantity":           {"type": "number",  "description": "Step count, cigarette count, etc."},
                    "duration_minutes":   {"type": "integer", "description": "For leisure events"}
                },
                "required": ["event_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_arcs",
            "description": "Get currently active goal arcs and their weights.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_effects",
            "description": "Get active buffs and debuffs currently affecting the player.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "end_day",
            "description": "Close out the current day — finalise snapshot, update streak.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["date"]
            }
        }
    }
]

# ---------------------------------------------------------------------------
# System prompt — conversational tool-use mode
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Life Map assistant. You help the user manage their daily tasks,
track habits, and maintain their life system through natural conversation.

You have access to tools that read from and write to the user's database.
Use them when the user asks you to do something that requires data — looking
up tasks, completing them, creating new ones, logging events, or closing the day.

For casual conversation, greetings, or questions about what things mean —
just reply naturally without calling any tools.

Default filling rules when creating tasks:
- Priority not stated → P1
- Energy not stated → Medium
- Time block not stated → Flexible
- XP not stated → 30
- Gold not stated → 5
- Late rule not stated → Soft, Penalty
- Mandatory not stated → false
- "without fail" or "must do" → mandatory: true, priority: P0, late_rule: Hard
- "tomorrow" → use tomorrow's date
- "tonight" → time_block: Evening, use today's date

When completing tasks:
- "tired", "rough", "only half" → partial_credit: 0.5
- Timing not stated → on_time
- Always use the current mh_mode from context

Keep replies short and direct. You're a productivity assistant, not a chatbot.
After tool calls, confirm what you did in one sentence and state the reward if relevant."""

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def _execute_tool(name: str, args: dict) -> dict:
    """
    Map tool names to script functions. All imports are lazy so startup is fast.
    Each executor wraps its call and normalises errors into a dict.
    """
    from scripts.reads import (
        get_player_state, get_tasks, get_active_arcs, get_active_effects
    )
    from scripts.writes import complete_task, create_task, log_event, end_day

    executors = {
        "get_player_state":  lambda a: get_player_state(),
        "get_tasks":         lambda a: get_tasks(a["date"], a["mh_mode"]),
        "get_active_arcs":   lambda a: get_active_arcs(),
        "get_active_effects":lambda a: get_active_effects(),
        "complete_task":     lambda a: complete_task(
            a["task_id"],
            {
                "completion_time": a["completion_time"],
                "partial_credit":  a["partial_credit"],
                "mh_mode":         a["mh_mode"],
            }
        ),
        # create_task takes the args dict directly as task_data
        "create_task":       lambda a: create_task(a),
        "log_event":         lambda a: log_event(a["event_type"], a),
        "end_day":           lambda a: _end_day_safe(end_day, a["date"]),
    }

    fn = executors.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}

    return fn(args)


def _end_day_safe(end_day_fn, today: str) -> dict:
    """
    Wrap end_day to catch the duplicate-key error when EOD has already run.
    Returns a friendly message instead of propagating the Postgres constraint error.
    """
    try:
        return end_day_fn(today)
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "duplicate" in err_str or "already exists" in err_str:
            return {"message": "Day already closed for today.", "already_closed": True}
        raise


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ContextBlock(BaseModel):
    mh_score:     int = 75
    mh_mode:      str = "Reduced"
    gold_balance: int = 0
    streak_count: int = 0
    date:         Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    context: Optional[ContextBlock] = None


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
    """Lightweight stat refresh — player state only."""
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
    Conversational LLM endpoint with tool calling.

    Flow:
      1. Build context block + inject into first user message
      2. Agentic loop: LLM replies OR calls tools (up to MAX_TOOL_ROUNDS)
      3. On each tool call: execute script, append tool_result, continue loop
      4. When LLM produces a text reply with no tool calls: return it
    """
    today    = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    ctx      = req.context or ContextBlock()

    context_block = (
        f"[Current state — Date: {today}, Tomorrow: {tomorrow}, "
        f"MH: {ctx.mh_score} ({ctx.mh_mode}), "
        f"Gold: {ctx.gold_balance}, "
        f"Streak: {ctx.streak_count}]"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"{context_block}\n\n{req.message}"}
    ]

    state_delta:  dict         = {}
    action_taken: Optional[str] = None
    MAX_TOOL_ROUNDS = 5

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            response = _groq_client.chat.completions.create(
                model=_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=1024,
            )

            msg = response.choices[0].message

            # No tool call — LLM is done
            if not msg.tool_calls:
                return ChatResponse(
                    reply=msg.content or "Done.",
                    state_delta=state_delta if state_delta else None,
                    action_taken=action_taken,
                    declined=False,
                )

            # Append assistant turn (content may be None when there are tool calls)
            messages.append({
                "role":       "assistant",
                "content":    msg.content,
                "tool_calls": msg.tool_calls,
            })

            # Execute each tool call in this round
            for tool_call in msg.tool_calls:
                name         = tool_call.function.name
                args         = json.loads(tool_call.function.arguments)
                action_taken = name

                try:
                    result = _execute_tool(name, args)

                    # Capture state changes for frontend stat bar animation
                    if name == "complete_task" and isinstance(result, dict):
                        state_delta.update({
                            "new_mh_score":     result.get("new_mh_score"),
                            "new_mh_mode":      result.get("new_mh_mode"),
                            "new_gold_balance": result.get("new_gold_balance"),
                            "xp_earned":        result.get("final_xp"),
                            "gold_delta":       result.get("final_gold"),
                        })
                    elif name == "log_event" and isinstance(result, dict):
                        state_delta.update({
                            "new_mh_score":     result.get("new_mh_score"),
                            "new_mh_mode":      result.get("new_mh_mode"),
                            "new_gold_balance": result.get("new_gold_balance"),
                        })

                except Exception as e:
                    result = {"error": str(e)}

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      json.dumps(result, default=str),
                })

        # Exceeded tool rounds — shouldn't normally happen
        return ChatResponse(
            reply="Done.",
            state_delta=state_delta if state_delta else None,
            action_taken=action_taken,
            declined=False,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/eod")
def eod():
    """Run the end-of-day close flow manually."""
    try:
        from orchestrator.sequencer import run_eod
        return run_eod(_config())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
