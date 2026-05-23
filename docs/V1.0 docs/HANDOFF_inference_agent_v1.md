# Life Map — Inference Agent Handoff (v1)
> **Session date:** 2026-05-23
> **Issued by:** Supervisor
> **Repo:** https://github.com/caffeinated4ighs/Life_Map

---

## Supervisor context

Core system is operational. Script library is now complete — 14 reads, 16 writes, all audited and patched. The web chat currently exposes only 8 of those 30 functions as tools. Your job is to wire the remaining 22, fix the known system prompt issues, and rewrite the prompt tone entirely.

**Do not touch:** `scripts/`, `orchestrator/`, `inference/groq_client.py`, `inference/validate_output.py`, `inference/system_prompt.txt`. Those are the CLI path — separate from the web chat path and not your concern.

**Your entire deliverable is one file: `web_ui/api.py`.**

---

## Files to read before starting

From the repo in this order:
1. `docs/00_SHARED_CONTEXT.md` — schema, enums, all valid field values
2. `web_ui/api.py` — your working file, understand every section before touching anything
3. `scripts/reads.py` — all 14 function signatures and return shapes
4. `scripts/writes.py` — all 16 function signatures and return shapes

---

## What currently exists in `api.py`

### TOOLS list — 8 tools wired
`get_tasks`, `get_player_state`, `complete_task`, `create_task`, `log_event`, `get_active_arcs`, `get_active_effects`, `end_day`

### `_execute_tool` — 8 executors
Matches the 8 tools above.

### `SYSTEM_PROMPT`
Functional but rigid. Needs a full tone rewrite and new rules added. See Part 2.

### Endpoints
`/health`, `/morning`, `/state`, `/chat`, `/eod` — do not touch these.

### `_end_day_safe` wrapper
Already exists. Keep it.

---

## Part 1 — Expand TOOLS and `_execute_tool`

### Tools to add

Add the following to the `TOOLS` list. Match the exact style and structure of the existing entries. Every tool needs a clear, natural-language `description` — these descriptions are what the model reads to decide which tool to call, so write them as you'd explain the tool to a person, not as a technical spec.

---

#### Reads to add

**`get_task`**
```python
parameters: {
    "task_id": {"type": "string", "description": "UUID of the task"}
}
required: ["task_id"]
```
Description: *"Get full details for a specific task including its arc modifier and suppression status."*

---

**`get_skill_links`**
```python
parameters: {
    "task_id": {"type": "string", "description": "UUID of the task"}
}
required: ["task_id"]
```
Description: *"Get the skills linked to a task and their crossover levels."*

---

**`get_skills`**
```python
parameters: {} required: []
```
Description: *"Get all skills — levels, XP, decay status. Use when the user asks about their skill tree or a specific skill."*

---

**`get_skill`**
```python
parameters: {
    "skill_id": {"type": "string", "description": "UUID of the skill"}
}
required: ["skill_id"]
```
Description: *"Get details for a single skill by ID."*

---

**`get_arcs`**
```python
parameters: {} required: []
```
Description: *"Get all arcs regardless of status. Use when the user asks to see their goals or arcs."*

---

**`get_arc`**
```python
parameters: {
    "arc_id": {"type": "string", "description": "UUID of the arc"}
}
required: ["arc_id"]
```
Description: *"Get full details for a specific arc including linked tasks and skills."*

---

**`get_arc_tasks`**
```python
parameters: {
    "arc_id": {"type": "string", "description": "UUID of the arc"}
}
required: ["arc_id"]
```
Description: *"Get all tasks linked to a specific arc."*

---

**`get_effects`**
```python
parameters: {} required: []
```
Description: *"Get all effects — both active and expired. Use when the user asks about buffs, debuffs, or effect history."*

---

**`get_effect`**
```python
parameters: {
    "effect_id": {"type": "string", "description": "UUID of the effect"}
}
required: ["effect_id"]
```
Description: *"Get full details for a single effect including linked stats and arcs."*

---

**`get_anchors`**
```python
parameters: {
    "date": {"type": "string", "description": "YYYY-MM-DD"}
}
required: ["date"]
```
Description: *"Get scheduled anchors (appointments, commitments) for a given date."*

---

**`get_snapshot`**
```python
parameters: {
    "date": {"type": "string", "description": "YYYY-MM-DD"}
}
required: ["date"]
```
Description: *"Get the day snapshot for a given date — open/close MH, gold, XP earned, steps."*

---

**`get_streak_log`**
```python
parameters: {
    "limit": {"type": "integer", "description": "Number of recent days to return (default 7)"}
}
required: []
```
Description: *"Get the recent streak history. Use when the user asks about their streak, consistency, or recent performance."*

---

**`get_stats`**
```python
parameters: {} required: []
```
Description: *"Get all stats and their current values. Use when the user asks for a stat sheet or stat check."*

---

**`get_stat`**
```python
parameters: {
    "stat_id": {"type": "string", "description": "UUID of the stat"}
}
required: ["stat_id"]
```
Description: *"Get a single stat by ID."*

---

#### Writes to add

**`create_skill`**
```python
parameters: {
    "skill":            {"type": "string"},
    "primary_stat_id":  {"type": "string", "description": "UUID of the primary stat"},
    "xp_to_next_level": {"type": "integer"},
    "secondary_stat_id":{"type": "string"},
    "decay_rate":       {"type": "string", "enum": ["Slow", "Medium", "Fast"]},
    "current_level":    {"type": "integer"},
    "xp_accumulated":   {"type": "integer"}
}
required: ["skill", "primary_stat_id", "xp_to_next_level"]
```
Description: *"Create a new skill and link it to a primary stat. Use when the user wants to add a skill to their tree."*

---

**`update_skill`**
```python
parameters: {
    "skill_id": {"type": "string"},
    "updates":  {"type": "object", "description": "Fields to update — skill, current_level, xp_accumulated, xp_to_next_level, decay_rate, last_active, in_decay, secondary_stat_id"}
}
required: ["skill_id", "updates"]
```
Description: *"Update mutable fields on an existing skill."*

---

**`create_arc`**
```python
parameters: {
    "arc":        {"type": "string"},
    "weight":     {"type": "string", "enum": ["Background", "Normal", "Focused", "Critical"]},
    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
    "end_date":   {"type": "string", "description": "YYYY-MM-DD"},
    "status":     {"type": "string", "enum": ["Active", "Paused", "Done"]}
}
required: ["arc"]
```
Description: *"Create a new arc — a goal window that applies modifiers while active. Use when the user wants to set up a new goal or focus area."*

---

**`update_arc`**
```python
parameters: {
    "arc_id":  {"type": "string"},
    "updates": {"type": "object", "description": "Fields to update — arc, status, weight, start_date, end_date"}
}
required: ["arc_id", "updates"]
```
Description: *"Update an existing arc — rename it, change its weight, adjust dates, or change status."*

---

**`link_arc_task`**
```python
parameters: {
    "arc_id":  {"type": "string"},
    "task_id": {"type": "string"}
}
required: ["arc_id", "task_id"]
```
Description: *"Link a task to an arc."*

---

**`link_arc_skill`**
```python
parameters: {
    "arc_id":   {"type": "string"},
    "skill_id": {"type": "string"}
}
required: ["arc_id", "skill_id"]
```
Description: *"Link a skill to an arc so it receives the arc's XP modifier."*

---

**`update_effect`**
```python
parameters: {
    "effect_id": {"type": "string"},
    "updates":   {"type": "object", "description": "Fields to update — effect, active, intensity, stat_offset, suppresses_arc_pressure, expires_on"}
}
required: ["effect_id", "updates"]
```
Description: *"Update an existing effect — extend it, deactivate it, or change its intensity."*

---

**`update_task`**
```python
parameters: {
    "task_id": {"type": "string"},
    "updates": {"type": "object", "description": "Fields to update — task, type, status, priority, category, date, energy_cost, late_rule, late_rule_behavior, mandatory, blocked, deferred, xp, gold, mh_impact, time_block, recurring_rule, impact_notes"}
}
required: ["task_id", "updates"]
```
Description: *"Update an existing task — reschedule it, change priority, adjust rewards, or edit any mutable field."*

---

**`delete_task`**
```python
parameters: {
    "task_id": {"type": "string"}
}
required: ["task_id"]
```
Description: *"Soft-delete a task — marks it deferred. Cannot delete completed tasks."*

---

**`create_anchor`**
```python
parameters: {
    "anchor":           {"type": "string"},
    "date":             {"type": "string", "description": "YYYY-MM-DD"},
    "type":             {"type": "string", "enum": ["Class", "Appointment", "Commitment", "Other"]},
    "time":             {"type": "string", "description": "HH:MM"},
    "priority_pressure":{"type": "string", "enum": ["None", "Elevates Tasks", "Locks Day"]}
}
required: ["anchor", "date"]
```
Description: *"Log a scheduled real-world event — an appointment, class, or commitment — for a given date."*

---

**`update_stat`**
```python
parameters: {
    "stat_id": {"type": "string"},
    "delta":   {"type": "integer", "description": "Amount to add (can be negative)"}
}
required: ["stat_id", "delta"]
```
Description: *"Directly adjust a stat value by a delta. Use for manual corrections only."*

---

**`create_skill_link`**
```python
parameters: {
    "task_id":        {"type": "string"},
    "skill_id":       {"type": "string"},
    "crossover_level":{"type": "string", "enum": ["Indirect", "Partial", "Direct"]}
}
required: ["task_id", "skill_id", "crossover_level"]
```
Description: *"Link a skill to a task so it receives XP when the task is completed."*

---

**`delete_skill_link`**
```python
parameters: {
    "task_id":  {"type": "string"},
    "skill_id": {"type": "string"}
}
required: ["task_id", "skill_id"]
```
Description: *"Remove a skill link from a task."*

---

**`manual_mh_adjust`**
```python
parameters: {
    "delta":  {"type": "integer", "description": "MH change — positive or negative"},
    "reason": {"type": "string"}
}
required: ["delta", "reason"]
```
Description: *"Manually adjust MH score with a reason. Logs the change as an mh_manual event."*

---

### `_execute_tool` — executors to add

Add the following entries to the `executors` dict. Import the new functions at the top of `_execute_tool` alongside the existing imports, keeping all imports lazy.

```python
from scripts.reads import (
    get_player_state, get_tasks, get_active_arcs, get_active_effects,
    get_task, get_skill_links, get_skills, get_skill, get_arcs, get_arc,
    get_arc_tasks, get_effects, get_effect, get_anchors, get_snapshot,
    get_streak_log, get_stats, get_stat,
)
from scripts.writes import (
    complete_task, create_task, log_event, end_day,
    create_skill, update_skill, create_arc, update_arc,
    link_arc_task, link_arc_skill, update_effect, update_task,
    delete_task, create_anchor, update_stat, create_skill_link,
    delete_skill_link, manual_mh_adjust,
)
```

Executor entries to add:

```python
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
"create_skill":       lambda a: create_skill(a),
"update_skill":       lambda a: update_skill(a["skill_id"], a["updates"]),
"create_arc":         lambda a: create_arc(a),
"update_arc":         lambda a: update_arc(a["arc_id"], a["updates"]),
"link_arc_task":      lambda a: link_arc_task(a["arc_id"], a["task_id"]),
"link_arc_skill":     lambda a: link_arc_skill(a["arc_id"], a["skill_id"]),
"update_effect":      lambda a: update_effect(a["effect_id"], a["updates"]),
"update_task":        lambda a: update_task(a["task_id"], a["updates"]),
"delete_task":        lambda a: delete_task(a["task_id"]),
"create_anchor":      lambda a: create_anchor(a),
"update_stat":        lambda a: update_stat(a["stat_id"], a["delta"]),
"create_skill_link":  lambda a: create_skill_link(a["task_id"], a["skill_id"], a["crossover_level"]),
"delete_skill_link":  lambda a: delete_skill_link(a["task_id"], a["skill_id"]),
"manual_mh_adjust":   lambda a: manual_mh_adjust(a["delta"], a["reason"]),
```

---

### `state_delta` capture — extend for new write tools

The existing `state_delta` capture block only handles `complete_task` and `log_event`. Add capture for the new write tools that mutate player state:

```python
elif name == "manual_mh_adjust" and isinstance(result, dict):
    state_delta.update({
        "new_mh_score": result.get("new_mh_score"),
        "new_mh_mode":  result.get("new_mh_mode"),
    })
elif name == "end_day" and isinstance(result, dict):
    state_delta.update({
        "streak_count": result.get("streak_count"),
        "mandatory_met": result.get("mandatory_met"),
    })
```

---

### `success: false` error handling in `_execute_tool`

After `result = fn(args)`, add this check before returning:

```python
result = fn(args)

# Surface script errors directly — don't let the model rephrase them
if isinstance(result, dict) and result.get("success") is False:
    error_msg = result.get("error") or result.get("reason") or "Something went wrong."
    return {"_script_error": True, "message": error_msg}

return result
```

Then in the chat loop, after appending the tool result to messages, check for `_script_error` and short-circuit with a direct reply rather than continuing the loop:

```python
if isinstance(result, dict) and result.get("_script_error"):
    return ChatResponse(
        reply=result["message"],
        state_delta=state_delta if state_delta else None,
        action_taken=action_taken,
        declined=False,
    )
```

---

### `MAX_TOOL_ROUNDS` — add warning log

Replace the silent fallback at the end of the loop:

```python
# Exceeded tool rounds — shouldn't normally happen
return ChatResponse(reply="Done.", ...)
```

With:

```python
import logging
logger = logging.getLogger("api")
logger.warning(f"MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}) hit for message: {req.message[:80]!r}")
return ChatResponse(
    reply="I got a bit turned around there. Can you try again?",
    state_delta=state_delta if state_delta else None,
    action_taken=action_taken,
    declined=False,
)
```

---

### Context block — add task counts

Extend the context block injected into each message. After fetching player state, also fetch today's task counts:

```python
from scripts.reads import get_tasks as _get_tasks

_tasks_today = _get_tasks(today, ctx.mh_mode)
_task_total    = len(_tasks_today)
_task_mandatory = sum(1 for t in _tasks_today if t.get("mandatory"))

context_block = (
    f"[Date: {today}, Tomorrow: {tomorrow} | "
    f"MH: {ctx.mh_score} ({ctx.mh_mode}) | "
    f"Gold: {ctx.gold_balance} | Streak: {ctx.streak_count} | "
    f"Tasks today: {_task_total} ({_task_mandatory} mandatory)]"
)
```

---

## Part 2 — Rewrite `SYSTEM_PROMPT`

This is the most important part of this handoff. Replace the existing `SYSTEM_PROMPT` entirely with the following. Read the design intent carefully before writing a word.

### Design intent

The user wants the system to feel like home — like texting someone who knows their life and just handles things. Not a command interface. Not a chatbot asking clarifying questions. A capable, low-friction presence that listens, infers, acts, and confirms briefly.

The current prompt is functional but reads like a specification. It produces replies that feel transactional. The rewrite prioritises:

- **Natural inference over interrogation** — if something is ambiguous but low-stakes, pick the most reasonable interpretation and proceed. Don't ask, just do and confirm.
- **Zero schema leakage** — the user never sees UUIDs, field names, enum values, or database language. Ever.
- **Warm brevity** — confirmations are short and human. Not "Task created successfully with the following parameters." More like "Got it, added for tomorrow."
- **Fluid task resolution** — when completing tasks, always resolve by name. Never surface IDs.

### New `SYSTEM_PROMPT`

```python
SYSTEM_PROMPT = """You are the Life Map assistant — a personal productivity companion who knows the user's life system and helps them manage it through natural conversation.

You have tools to read and write to the database. Use them silently — the user should never know a tool was called unless you're telling them what just happened.

## How to respond

Be brief. Be warm. One or two sentences after a tool call is enough.
After completing something: say what happened and the reward if there is one.
After logging something: confirm it in plain language.
After a read: just answer the question naturally.

Good: "Added it for tomorrow — that's a P0 so I flagged it mandatory."
Good: "Done. +45 XP, +8 G. MH ticked up a little."
Good: "You've got 4 things today. The heavy ones are the gym and the SSN letter."
Bad: "Task created successfully with priority P0, mandatory: true, late_rule: Hard."
Bad: "I have logged the event with event_type: steps, quantity: 8000."

Never mention UUIDs, field names, table names, or enum values in replies.
Never ask for an ID — resolve tasks by name yourself using get_tasks first.

## Inference rules

When something is missing or ambiguous, infer and proceed — don't ask unless it's genuinely unclear or high-stakes (like deleting something).

Task defaults when not stated:
- Priority → P1
- Energy → Medium
- Time block → Flexible
- XP → 30, Gold → 5
- Late rule → Soft, Penalty
- Mandatory → false
- "without fail" / "must do" / "no matter what" → mandatory: true, P0, Hard late rule
- "tomorrow" → tomorrow's date
- "tonight" → Evening block, today's date
- "this week" → end of current week
- Category → infer from context (gym = Health, reading = Hobby, email = Work, etc.)

Completion defaults when not stated:
- Timing → on_time
- Credit → 1.0 (full)
- "half", "only did part", "tired", "rough session" → partial_credit: 0.5
- "late", "just got to it" → soft timing
- "missed it", "didn't do it" → don't complete, offer to defer or delete

Task matching:
- Match on key terms only. Ignore filler words like "task", "the", "my", "thing".
- "ssn thing" matches "SSN support letter". "gym" matches "Morning gym session".
- Always call get_tasks first to find the ID. Never guess a UUID.

Fuzzy queries:
- "and tomorrow?" → call get_tasks with tomorrow's date
- "how am I doing?" → call get_player_state
- "what's left?" → call get_tasks for today
- "skill tree?" → call get_skills
- "stat check" → call get_stats
- "streak?" → call get_streak_log

## After end_day

Always call get_player_state after end_day closes. Include the streak result in your reply.
Example: "Day closed. Streak's now at 4 — mandatory done. Sleep well."

## If something fails

If a tool returns an error, say so plainly in one sentence. Don't invent a workaround.
"Couldn't find that task — want to try a different name?"
"Looks like the day's already closed."

## What you don't do

- Don't ask clarifying questions for low-stakes inputs — just infer
- Don't describe what you're about to do — just do it
- Don't repeat the user's words back to them
- Don't offer a list of options unless the user is genuinely stuck
- Don't end every message with "Let me know if you need anything!"
"""
```

---

## Part 3 — Checklist before pushing

- [ ] All 22 new tools added to `TOOLS` list
- [ ] All 22 new executors added to `_execute_tool`
- [ ] Lazy imports updated to include all new functions
- [ ] `state_delta` capture extended for `manual_mh_adjust` and `end_day`
- [ ] `success: false` short-circuit added to `_execute_tool` and chat loop
- [ ] `MAX_TOOL_ROUNDS` warning log added
- [ ] Context block extended with task counts
- [ ] `SYSTEM_PROMPT` replaced in full
- [ ] No endpoints touched
- [ ] No files touched except `web_ui/api.py`
- [ ] `_end_day_safe` wrapper kept intact

---

## What this unlocks

After this handoff:
- The model can see and interact with the full data model — skills, arcs, effects, anchors, stats, snapshots, streak history
- The chat interface feels like a natural, low-friction companion rather than a command router
- Script errors surface cleanly without model hallucination
- The system is ready for the backend structure fixes (next session) and eventually the non-LLM direct-query interface

---

*The goal is for the user to be able to say "got the gym done, was rough" and have the system handle everything — find the task, complete it with partial credit, update state, and reply warmly in one sentence. That's the bar.*
