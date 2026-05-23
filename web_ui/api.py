from dotenv import load_dotenv
load_dotenv()

import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("api")

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


import os
@app.get("/")
def serve_ui():
    path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(path)


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
    # ── Reads (existing) ────────────────────────────────────────────────────
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
            "name": "get_active_arcs",
            "description": "Get all currently active arcs (goals/focus windows).",
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
    # ── Reads (new) ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_task",
            "description": "Get full details for a specific task including its arc modifier and suppression status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "UUID of the task"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill_links",
            "description": "Get the skills linked to a task and their crossover levels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "UUID of the task"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_skills",
            "description": "Get all skills — levels, XP, decay status. Use when the user asks about their skill tree or a specific skill.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill",
            "description": "Get details for a single skill by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "UUID of the skill"}
                },
                "required": ["skill_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_arcs",
            "description": "Get all arcs regardless of status. Use when the user asks to see their goals or arcs.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_arc",
            "description": "Get full details for a specific arc including linked tasks and skills.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arc_id": {"type": "string", "description": "UUID of the arc"}
                },
                "required": ["arc_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_arc_tasks",
            "description": "Get all tasks linked to a specific arc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arc_id": {"type": "string", "description": "UUID of the arc"}
                },
                "required": ["arc_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_effects",
            "description": "Get all effects — both active and expired. Use when the user asks about buffs, debuffs, or effect history.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_effect",
            "description": "Get full details for a single effect including linked stats and arcs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "effect_id": {"type": "string", "description": "UUID of the effect"}
                },
                "required": ["effect_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_anchors",
            "description": "Get scheduled anchors (appointments, commitments) for a given date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_snapshot",
            "description": "Get the day snapshot for a given date — open/close MH, gold, XP earned, steps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_streak_log",
            "description": "Get the recent streak history. Use when the user asks about their streak, consistency, or recent performance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent days to return (default 7)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Get all stats and their current values. Use when the user asks for a stat sheet or stat check.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stat",
            "description": "Get a single stat by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stat_id": {"type": "string", "description": "UUID of the stat"}
                },
                "required": ["stat_id"]
            }
        }
    },
    # ── Writes (existing) ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as done and apply XP/gold rewards.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id":        {"type": "string", "description": "UUID of the task"},
                    "completion_time": {
                        "type": "string",
                        "enum": ["on_time", "soft", "meaningful_delay", "hard_failure", "void"]
                    },
                    "partial_credit": {"type": "number", "description": "0.0–1.0, default 1.0"},
                    "mh_mode":        {
                        "type": "string",
                        "enum": ["Normal", "Reduced", "Minimum Viable", "Recovery Only"]
                    }
                },
                "required": ["task_id", "completion_time", "mh_mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task in the system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task":               {"type": "string"},
                    "type":               {"type": "string", "enum": ["Daily", "Weekly", "Recurring", "Mandatory", "Optional", "Bonus"]},
                    "date":               {"type": "string", "description": "YYYY-MM-DD"},
                    "priority":           {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                    "category":           {"type": "string", "enum": ["Health", "Study", "Work", "Social", "Maintenance", "Hobby"]},
                    "energy_cost":        {"type": "string", "enum": ["Low", "Medium", "High", "Very High"]},
                    "time_block":         {"type": "string", "enum": ["Morning", "Afternoon", "Evening", "Night", "Flexible"]},
                    "xp":                 {"type": "integer"},
                    "gold":               {"type": "integer"},
                    "mandatory":          {"type": "boolean"},
                    "late_rule":          {"type": "string", "enum": ["None", "Soft", "Medium", "Hard"]},
                    "late_rule_behavior": {"type": "string", "enum": ["Penalty", "Incentive", "Neutral"]},
                    "mh_impact":          {"type": "integer"},
                    "recurring_rule":     {"type": "string"},
                    "impact_notes":       {"type": "string"}
                },
                "required": ["task", "type", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_event",
            "description": "Log a real-world event that affects MH or player state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "enum": ["steps", "substance", "leisure", "day_off", "cheat_day", "mh_manual"]
                    },
                    "date":     {"type": "string", "description": "YYYY-MM-DD"},
                    "quantity": {"type": "number"},
                    "notes":    {"type": "string"}
                },
                "required": ["event_type", "date"]
            }
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
    },
    # ── Writes (new) ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_skill",
            "description": "Create a new skill and link it to a primary stat. Use when the user wants to add a skill to their tree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill":             {"type": "string"},
                    "primary_stat_id":   {"type": "string", "description": "UUID of the primary stat"},
                    "xp_to_next_level":  {"type": "integer"},
                    "secondary_stat_id": {"type": "string"},
                    "decay_rate":        {"type": "string", "enum": ["Slow", "Medium", "Fast"]},
                    "current_level":     {"type": "integer"},
                    "xp_accumulated":    {"type": "integer"}
                },
                "required": ["skill", "primary_stat_id", "xp_to_next_level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_skill",
            "description": "Update mutable fields on an existing skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "updates":  {"type": "object", "description": "Fields to update — skill, current_level, xp_accumulated, xp_to_next_level, decay_rate, last_active, in_decay, secondary_stat_id"}
                },
                "required": ["skill_id", "updates"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_arc",
            "description": "Create a new arc — a goal window that applies modifiers while active. Use when the user wants to set up a new goal or focus area.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arc":        {"type": "string"},
                    "weight":     {"type": "string", "enum": ["Background", "Normal", "Focused", "Critical"]},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date":   {"type": "string", "description": "YYYY-MM-DD"},
                    "status":     {"type": "string", "enum": ["Active", "Paused", "Done"]}
                },
                "required": ["arc"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_arc",
            "description": "Update an existing arc — rename it, change its weight, adjust dates, or change status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arc_id":  {"type": "string"},
                    "updates": {"type": "object", "description": "Fields to update — arc, status, weight, start_date, end_date"}
                },
                "required": ["arc_id", "updates"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "link_arc_task",
            "description": "Link a task to an arc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arc_id":  {"type": "string"},
                    "task_id": {"type": "string"}
                },
                "required": ["arc_id", "task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "link_arc_skill",
            "description": "Link a skill to an arc so it receives the arc's XP modifier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arc_id":   {"type": "string"},
                    "skill_id": {"type": "string"}
                },
                "required": ["arc_id", "skill_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_effect",
            "description": "Create a new buff or debuff effect. Use when the user wants to log something that's affecting their performance — illness, a good streak, a hard week.",
            "parameters": {
                "type": "object",
                "properties": {
                    "effect":                    {"type": "string"},
                    "effect_type":               {"type": "string", "enum": ["Buff", "Debuff"]},
                    "intensity":                 {"type": "integer", "description": "1–10"},
                    "stat_offset":               {"type": "integer", "description": "Flat MH adjustment applied daily"},
                    "suppresses_arc_pressure":   {"type": "boolean"},
                    "expires_on":                {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["effect", "effect_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_effect",
            "description": "Update an existing effect — extend it, deactivate it, or change its intensity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "effect_id": {"type": "string"},
                    "updates":   {"type": "object", "description": "Fields to update — effect, active, intensity, stat_offset, suppresses_arc_pressure, expires_on"}
                },
                "required": ["effect_id", "updates"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Update an existing task — reschedule it, change priority, adjust rewards, or edit any mutable field.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "updates": {"type": "object", "description": "Fields to update — task, type, status, priority, category, date, energy_cost, late_rule, late_rule_behavior, mandatory, blocked, deferred, xp, gold, mh_impact, time_block, recurring_rule, impact_notes"}
                },
                "required": ["task_id", "updates"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Soft-delete a task — marks it deferred. Cannot delete completed tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_recurring_tasks",
            "description": "Generate today's instances of all recurring tasks. Normally called by the morning flow — only use manually if the user reports missing recurring tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_anchor",
            "description": "Log a scheduled real-world event — an appointment, class, or commitment — for a given date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "anchor":            {"type": "string"},
                    "date":              {"type": "string", "description": "YYYY-MM-DD"},
                    "type":              {"type": "string", "enum": ["Class", "Appointment", "Commitment", "Other"]},
                    "time":              {"type": "string", "description": "HH:MM"},
                    "priority_pressure": {"type": "string", "enum": ["None", "Elevates Tasks", "Locks Day"]}
                },
                "required": ["anchor", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_stat",
            "description": "Directly adjust a stat value by a delta. Use for manual corrections only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stat_id": {"type": "string"},
                    "delta":   {"type": "integer", "description": "Amount to add (can be negative)"}
                },
                "required": ["stat_id", "delta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_skill_link",
            "description": "Link a skill to a task so it receives XP when the task is completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id":         {"type": "string"},
                    "skill_id":        {"type": "string"},
                    "crossover_level": {"type": "string", "enum": ["Indirect", "Partial", "Direct"]}
                },
                "required": ["task_id", "skill_id", "crossover_level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_skill_link",
            "description": "Remove a skill link from a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id":  {"type": "string"},
                    "skill_id": {"type": "string"}
                },
                "required": ["task_id", "skill_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manual_mh_adjust",
            "description": "Manually adjust MH score with a reason. Logs the change as an mh_manual event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "delta":  {"type": "integer", "description": "MH change — positive or negative"},
                    "reason": {"type": "string"}
                },
                "required": ["delta", "reason"]
            }
        }
    },
]

# ---------------------------------------------------------------------------
# Tool groups — sent selectively by message intent to cut token overhead
# ---------------------------------------------------------------------------

_TOOL_MAP = {t["function"]["name"]: t for t in TOOLS}

# READ: pure data-fetch — no side effects.
_TOOLS_READ = [_TOOL_MAP[n] for n in [
    "get_tasks", "get_player_state", "get_active_arcs", "get_active_effects",
    "get_task", "get_skill_links", "get_skills", "get_skill",
    "get_arcs", "get_arc", "get_arc_tasks",
    "get_effects", "get_effect",
    "get_anchors", "get_snapshot", "get_streak_log",
    "get_stats", "get_stat",
]]

# WRITE: daily-use mutations — always paired with READ so the model can
# resolve IDs before writing.
_TOOLS_WRITE = [_TOOL_MAP[n] for n in [
    "complete_task", "create_task", "log_event", "end_day",
    "create_effect", "update_effect",
    "update_task", "delete_task",
    "create_anchor", "manual_mh_adjust",
    "create_arc", "update_arc",
]]

# ADMIN: structural / low-frequency — only sent on explicit admin intent.
_TOOLS_ADMIN = [_TOOL_MAP[n] for n in [
    "create_skill", "update_skill",
    "link_arc_task", "link_arc_skill",
    "generate_recurring_tasks",
    "update_stat",
    "create_skill_link", "delete_skill_link",
]]


def _select_tools(message: str) -> list:
    """
    Route to the minimal tool set for this message.

    ADMIN  -> READ + WRITE + ADMIN  (38 tools — full set)
    WRITE  -> READ + WRITE          (30 tools — saves ~20% schema tokens)
    READ   -> READ only             (18 tools — saves ~55% schema tokens)

    Ambiguous messages default to READ+WRITE (safe: read tools have no
    side effects and the model needs them to resolve IDs before writing).
    """
    msg = message.lower()

    _admin_signals = (
        "recurring", "generate", "skill link", "link skill", "link arc",
        "arc link", "unlink", "delete skill", "remove skill",
        "update stat", "adjust stat",
    )
    if any(s in msg for s in _admin_signals):
        return _TOOLS_READ + _TOOLS_WRITE + _TOOLS_ADMIN

    _write_signals = (
        "done", "complete", "finish", "add task", "create task",
        "log ", "mark ", "reschedule", "move to", "delete task", "remove task",
        "close day", "end day", "update", "change", "edit", "create arc",
        "create effect", "new task", "add effect", "anchor",
        "walked", "steps", "smoked", "drank", "day off", "cheat day",
        "add ", "create ", "delete ", "remove ",
    )
    if any(s in msg for s in _write_signals):
        return _TOOLS_READ + _TOOLS_WRITE

    # Read-only heuristic: explicit question with a read keyword
    _read_signals = (
        "what", "show", "how ", "check", "list", "tell me", "see",
        "streak", "stat", "skill", "arc", "effect", "buff", "debuff",
        "goal", "snapshot", "history", "schedule", "player state",
        "how am i", "how's my", "any tasks", "what's left",
    )
    if any(s in msg for s in _read_signals):
        return _TOOLS_READ

    # Default: READ+WRITE (handles casual completions, pronouns, ambiguous input)
    return _TOOLS_READ + _TOOLS_WRITE


# ---------------------------------------------------------------------------
# System prompt — conversational tool-use mode
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Life Map assistant. You manage the user's personal productivity system through natural conversation. You have no memory between sessions — everything you know comes from the context block and your tools.

Use tools silently. Never mention UUIDs, field names, table names, or enum values. Never describe what you're about to do — just do it.

## Replies

One or two sentences. Warm, brief.
After a write with rewards: "✓ [what happened] | +{xp} XP, +{gold} G"
After a write without rewards: one plain confirmation sentence.
After a read: answer the question naturally.
Bad: "Task created successfully with priority P0, mandatory: true."
Bad: "I have logged the event with event_type: steps."

## Tool sequencing

completing a task — always 2 steps:
  1. get_tasks(date, mh_mode) → find the matching task by name
  2. complete_task(task_id, ...)
Never call complete_task with a guessed ID.

update_task / delete_task — always 2 steps:
  1. get_tasks(date, mh_mode) → find the task ID
  2. update_task(task_id, ...) or delete_task(task_id)

reading a specific item by name — find ID via list tool first, then detail tool if needed.

## Read tool routing

"tasks today" / "what's left"   → get_tasks(today, mh_mode)
"tasks tomorrow" / "and tomorrow?" → get_tasks(tomorrow, mh_mode)
"skill tree" / "my skills"       → get_skills()
"stat check" / "my stats"        → get_stats()
"how am I doing"                 → get_player_state()
"my goals" / "arcs"              → get_arcs()
"active buffs"                   → get_active_effects()
"streak"                         → get_streak_log()
"what's scheduled"               → get_anchors(date)

## Inference defaults

Priority → P1 | Energy → Medium | Time block → Flexible | XP → 30 | Gold → 5
Late rule → Soft, Penalty | Mandatory → false
"must do" / "without fail" / "no matter what" → mandatory: true, P0, Hard
"tomorrow" → tomorrow's date | "tonight" → Evening, today | "this week" → end of week
Category → infer (gym=Health, reading=Hobby, email=Work, cooking=Maintenance, etc.)
Type → Optional for one-off, Daily if habitual, Recurring if pattern described

Completion timing:
"half" / "rough session" / "only part" → partial_credit: 0.5
"late" / "just got to it" → soft timing
"missed it" / "didn't do it" → don't complete — offer defer or delete

Task name matching:
Strip filler words (task, the, my, thing, complete, it). "gym" → "Morning gym session". "ssn thing" → "SSN support letter".
If multiple match, pick closest. If genuinely ambiguous, ask.

Pronoun resolution:
"it" / "that task" / "the one I just added" → resolve from [Last action] in context. Do NOT call get_tasks to resolve a pronoun if last_action is present.

## Closing the day

end_day is irreversible. Always confirm first: "Close the day? This can't be undone."
Call end_day only after explicit yes. After it completes, call get_player_state and include the streak in your reply.

## Errors

Task not found: call get_tasks again and look harder. Tell the user only if still not found.
Other errors: one plain sentence. No invented workarounds.

## Never

- Guess or invent IDs
- Ask for clarification on low-stakes inputs — infer and proceed
- Repeat the user's words back
- Offer options lists unless the user is stuck
- End with "Let me know if you need anything!"
"""

# ---------------------------------------------------------------------------
# Allowed columns for create_task — prevents unknown-column crashes (CORE-002)
# ---------------------------------------------------------------------------

_TASK_COLUMNS = {
    "task", "type", "status", "priority", "category", "date", "energy_cost",
    "late_rule", "late_rule_behavior", "late_rule_behavior", "mandatory", "blocked",
    "deferred", "xp", "gold", "mh_impact", "time_block", "recurring_rule",
    "impact_notes", "anchor_id", "reminder_needed", "reminder_lead",
}

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def _execute_tool(name: str, args: dict) -> dict:
    """
    Map tool names to script functions. All imports are lazy so startup is fast.
    Each executor wraps its call and normalises errors into a dict.
    """
    from scripts.reads import (
        get_player_state, get_tasks, get_active_arcs, get_active_effects,
        get_task, get_skill_links, get_skills, get_skill, get_arcs, get_arc,
        get_arc_tasks, get_effects, get_effect, get_anchors, get_snapshot,
        get_streak_log, get_stats, get_stat,
    )
    from scripts.writes import (
        complete_task, create_task, log_event, end_day,
        create_skill, update_skill, create_arc, update_arc,
        link_arc_task, link_arc_skill, create_effect, update_effect,
        update_task, delete_task, generate_recurring_tasks, create_anchor,
        update_stat, create_skill_link, delete_skill_link, manual_mh_adjust,
    )

    executors = {
        # reads — existing
        "get_tasks":          lambda a: get_tasks(a["date"], a["mh_mode"]),
        "get_player_state":   lambda a: get_player_state(),
        "get_active_arcs":    lambda a: get_active_arcs(),
        "get_active_effects": lambda a: get_active_effects(),
        # reads — new
        "get_task":           lambda a: get_task(a["task_id"]),
        "get_skill_links":    lambda a: get_skill_links(a["task_id"]),
        "get_skills":         lambda a: get_skills(),
        "get_skill":          lambda a: get_skill(a["skill_id"]),
        "get_arcs":           lambda a: get_arcs(),
        "get_arc":            lambda a: get_arc(a["arc_id"]),
        "get_arc_tasks":      lambda a: get_arc_tasks(a["arc_id"]),
        "get_effects":        lambda a: get_effects(),
        "get_effect":         lambda a: get_effect(a["effect_id"]),
        "get_anchors":        lambda a: get_anchors(a["date"]),
        "get_snapshot":       lambda a: get_snapshot(a["date"]),
        "get_streak_log":     lambda a: get_streak_log(a.get("limit", 7)),
        "get_stats":          lambda a: get_stats(),
        "get_stat":           lambda a: get_stat(a["stat_id"]),
        # writes — existing
        # CORE-002: sanitise create_task args against allowed column list
        "create_task":        lambda a: create_task({k: v for k, v in a.items() if k in _TASK_COLUMNS}),
        # CORE-003: pass event_type as first positional arg, not the whole dict
        "log_event":          lambda a: log_event(a["event_type"], a),
        "complete_task":      lambda a: _resolve_and_complete(a),
        "end_day":            lambda a: _end_day_safe(a["date"]),
        # writes — new
        "create_skill":       lambda a: create_skill(a),
        "update_skill":       lambda a: update_skill(a["skill_id"], a["updates"]),
        "create_arc":         lambda a: create_arc(a),
        "update_arc":         lambda a: update_arc(a["arc_id"], a["updates"]),
        "link_arc_task":             lambda a: link_arc_task(a["arc_id"], a["task_id"]),
        "link_arc_skill":            lambda a: link_arc_skill(a["arc_id"], a["skill_id"]),
        # CORE-005: don't mutate args dict with .pop(); handle both key names safely
        "create_effect":             lambda a: create_effect({
            **{k: v for k, v in a.items() if k not in ("effect_type",)},
            "type": a.get("effect_type", a.get("type")),
        }),
        "update_effect":             lambda a: update_effect(a["effect_id"], a["updates"]),
        "update_task":               lambda a: _exec_with_resolved_id(update_task, a["task_id"], a["updates"]),
        "delete_task":               lambda a: _exec_with_resolved_id(delete_task, a["task_id"]),
        "generate_recurring_tasks":  lambda a: generate_recurring_tasks(a["date"]),
        "create_anchor":             lambda a: create_anchor(a),
        "update_stat":        lambda a: update_stat(a["stat_id"], a["delta"]),
        "create_skill_link":  lambda a: create_skill_link(a["task_id"], a["skill_id"], a["crossover_level"]),
        "delete_skill_link":  lambda a: delete_skill_link(a["task_id"], a["skill_id"]),
        "manual_mh_adjust":   lambda a: manual_mh_adjust(a["delta"], a["reason"]),
    }

    fn = executors.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}

    result = fn(args)

    # Surface script errors directly — don't let the model rephrase them
    if isinstance(result, dict) and result.get("success") is False:
        error_msg = result.get("error") or result.get("reason") or "Something went wrong."
        return {"_script_error": True, "message": error_msg}

    return result


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _resolve_task_id — shared ID validation for any task mutation
# ---------------------------------------------------------------------------

def _resolve_task_id(task_id: str) -> tuple:
    """
    Validate task_id against today's live task list (MH mode bypassed — CORE-001).
    Returns (validated_id, None) on success.
    Returns (None, error_dict) on failure — error_dict contains the task list so
    the model can find the correct ID and retry in the same tool-call loop.
    """
    from scripts.reads import get_tasks
    from datetime import date as _date

    today = _date.today().isoformat()
    tasks = get_tasks(today, "Normal")
    valid_ids = {t["id"] for t in tasks}

    if task_id in valid_ids:
        return task_id, None

    return None, {
        "error":           "task_id_not_found",
        "message":         "No task with that ID in today's list. Here are today's tasks:",
        "available_tasks": [{"id": t["id"], "task": t["task"]} for t in tasks],
    }


def _exec_with_resolved_id(fn, task_id: str, *extra_args):
    """Call fn(task_id, *extra_args) only after validating task_id via _resolve_task_id."""
    resolved_id, err = _resolve_task_id(task_id)
    if err:
        return err
    return fn(resolved_id, *extra_args)


# _resolve_and_complete — bypass MH filter for task completion (CORE-001)
# ---------------------------------------------------------------------------

def _resolve_and_complete(args: dict) -> dict:
    """
    Intercepts every complete_task call and validates the task_id against
    the live task list before executing. Always fetches with mh_mode='Normal'
    so MH energy filtering cannot hide a task the user wants to complete.
    (CORE-001: task completion is an explicit user action — MH gating must not block it.)
    """
    from scripts.reads import get_player_state
    from scripts.writes import complete_task

    task_id         = args.get("task_id", "")
    completion_time = args.get("completion_time", "on_time")
    partial_credit  = float(args.get("partial_credit", 1.0))

    resolved_id, err = _resolve_task_id(task_id)
    if err:
        return err

    ps      = get_player_state()
    mh_mode = ps.get("mh_mode", "Normal")

    return complete_task(resolved_id, {
        "completion_time": completion_time,
        "partial_credit":  partial_credit,
        "mh_mode":         mh_mode,
    })


# ---------------------------------------------------------------------------
# _end_day_safe wrapper
# ---------------------------------------------------------------------------

def _end_day_safe(today: str) -> dict:
    """
    Wraps end_day to handle the duplicate-close case gracefully.
    Returns a friendly message instead of propagating the Postgres constraint error.
    """
    from scripts.writes import end_day as end_day_fn
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

    # CORE-010: derive mh_mode from live player state at request time,
    # not from the client's potentially stale currentContext.
    try:
        from scripts.reads import get_player_state as _get_ps
        _ps_live = _get_ps()
        _live_mh_mode = _ps_live.get("mh_mode", ctx.mh_mode)
    except Exception:
        _live_mh_mode = ctx.mh_mode

    # Fetch today's task counts for richer context
    try:
        from scripts.reads import get_tasks as _get_tasks
        _tasks_today    = _get_tasks(today, _live_mh_mode)
        _task_total     = len(_tasks_today)
        _task_mandatory = sum(1 for t in _tasks_today if t.get("mandatory"))
    except Exception:
        _task_total     = 0
        _task_mandatory = 0

    # CORE-008: track last_action per request so the model can resolve
    # pronouns ("it", "that task") without calling get_tasks unnecessarily.
    # last_action is injected into the context block below.
    _last_action: dict = {}

    context_block = (
        f"[Date: {today}, Tomorrow: {tomorrow} | "
        f"MH: {ctx.mh_score} ({_live_mh_mode}) | "
        f"Gold: {ctx.gold_balance} | Streak: {ctx.streak_count} | "
        f"Tasks today: {_task_total} ({_task_mandatory} mandatory)]"
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
                tools=_select_tools(req.message),
                tool_choice="auto",
                temperature=0.15,
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

                    # CORE-008: update last_action after every write that creates/modifies an entity
                    if name == "create_task" and isinstance(result, dict) and "task_id" in result:
                        _last_action = {
                            "tool": "create_task",
                            "id":   result.get("task_id"),
                            "name": args.get("task"),
                        }
                    elif name in ("update_task", "complete_task") and isinstance(result, dict):
                        _last_action = {
                            "tool": name,
                            "id":   args.get("task_id"),
                            "name": args.get("task", _last_action.get("name")),
                        }
                    elif name == "create_arc" and isinstance(result, dict) and "arc_id" in result:
                        _last_action = {
                            "tool": "create_arc",
                            "id":   result.get("arc_id"),
                            "name": args.get("arc"),
                        }
                    elif name == "create_effect" and isinstance(result, dict) and "effect_id" in result:
                        _last_action = {
                            "tool": "create_effect",
                            "id":   result.get("effect_id"),
                            "name": args.get("effect"),
                        }

                    # Inject last_action into context for subsequent rounds so the model
                    # can resolve pronouns without an extra tool call (CORE-008)
                    if _last_action:
                        # Update the system context message in-place for the next round
                        last_action_note = (
                            f"\n[Last action: {_last_action.get('tool')} → "
                            f"'{_last_action.get('name')}' (id: {_last_action.get('id')})]"
                        )
                        # Patch the first user message's context block
                        if messages and messages[1]["role"] == "user":
                            base = messages[1]["content"]
                            # Only add the note once; subsequent rounds will update it
                            if "[Last action:" not in base:
                                messages[1]["content"] = base + last_action_note
                            else:
                                # Replace existing last_action note
                                import re
                                messages[1]["content"] = re.sub(
                                    r"\[Last action:.*?\]", last_action_note.strip(), base
                                )

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
                    elif name == "manual_mh_adjust" and isinstance(result, dict):
                        state_delta.update({
                            "new_mh_score": result.get("new_mh_score"),
                            "new_mh_mode":  result.get("new_mh_mode"),
                        })
                    elif name == "end_day" and isinstance(result, dict):
                        state_delta.update({
                            "streak_count":  result.get("streak_count"),
                            "mandatory_met": result.get("mandatory_met"),
                        })

                except Exception as e:
                    result = {"error": str(e)}

                # Short-circuit on clean script errors — but NOT for complete_task
                # task_id_not_found: let the model see the task list and retry
                if isinstance(result, dict) and result.get("_script_error"):
                    if name != "complete_task":
                        return ChatResponse(
                            reply=result["message"],
                            state_delta=state_delta if state_delta else None,
                            action_taken=action_taken,
                            declined=False,
                        )

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      json.dumps(result, default=str),
                })

        # Exceeded tool rounds
        logger.warning(f"MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}) hit for message: {req.message[:80]!r}")
        return ChatResponse(
            reply="I got a bit turned around there. Can you try again?",
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
