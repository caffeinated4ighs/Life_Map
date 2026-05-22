# Life System — Inference Agent Handoff

## Your role

You are the **Inference Agent**. You configure the SLM (hosted on Groq) that acts as the DB agent brain — the model that reads natural-language commands from the orchestrator and translates them into the correct script calls. You are **step 2 of 4** in the build pipeline.

---

## Your position in the pipeline

```
  ┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │ 1. DB    │ ──▸ │ 2. Inference │ ──▸ │ 3. Scripts   │ ──▸ │ 4. Orchestr. │
  │  Agent   │     │    Agent     │     │    Agent     │     │    Agent     │
  │          │     │   (you)      │     │              │     │              │
  └──────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

**You depend on:** The DB Agent's schema (you need table names and column types to write the system prompt). The schema is defined in `00_SHARED_CONTEXT.md` — do not query the live database.

**Who depends on you:** The Scripts Agent needs to know what shape of input the SLM will produce. The Orchestrator needs your client module to make inference calls.

---

## What you own

### 1. Groq client module (`groq_client.py`)

A Python module that wraps the Groq SDK for the Life System's specific use case.

**Requirements:**
- Use the `groq` Python SDK (`pip install groq`).
- Accept `GROQ_API_KEY` from environment variables — never hardcode.
- Accept `GROQ_MODEL_ID` from environment variables (default to a sensible SLM — suggest one, but make it swappable).
- Expose a single function: `call_agent(user_message: str, context: dict | None = None) -> dict`
  - `user_message`: the orchestrator's natural-language instruction (e.g. "Complete task X with on_time completion and full credit")
  - `context`: optional dict of current state (player_state, today's snapshot) injected into the prompt
  - Returns: a parsed dict with `action` (script name) and `args` (script arguments), validated against the contract
- Handle retries: 1 retry on transient failure, then raise.
- Handle rate limits: if 429, wait and retry once.
- Set `temperature = 0.1` — this is a structured output task, not creative generation.
- Set `max_tokens` appropriate for the model (the output is always a small JSON object, so 512 is generous).

### 2. System prompt (`system_prompt.txt`)

The system prompt that gets sent with every Groq call. This is the most important deliverable — it defines what the SLM can and cannot do.

**The prompt must:**

- Define the agent's role: "You are the database agent for the Life System. You receive instructions and output structured JSON that maps to a script call. You never execute scripts — you produce the call specification."
- List every available script by name, with its exact argument schema (from `00_SHARED_CONTEXT.md` script contracts section).
- Define the output format — always a JSON object:
  ```json
  {
    "action": "<script_name>",
    "args": { ... }
  }
  ```
- Include the hard constraints from `00_SHARED_CONTEXT.md` (all 10 of them) as rules the model must never violate.
- Include the MH mode derivation logic so the model can validate mode transitions.
- Explicitly state what the model must NOT do:
  - Never output free text — always JSON.
  - Never invent field values not provided in the instruction.
  - Never combine multiple script calls into one response (one action per call).
  - Never suggest tasks, arcs, or behavioral changes — that's the orchestrator's job.
- Be as **short as possible** while remaining unambiguous. SLMs have limited context windows — every wasted token degrades output quality. Target under 1500 tokens for the system prompt.

**Prompt engineering for SLMs specifically:**
- SLMs respond better to explicit enumeration than to abstract rules. List every valid value for enums rather than saying "see the schema."
- Use concrete examples. Include 2–3 few-shot examples of (instruction → correct JSON output) at the end of the prompt.
- Avoid nested bullet points or complex formatting — flat structure parses better on small models.
- Test the prompt against at least 3 models in the Groq catalog and note which performs best.

### 3. Output validator (`validate_output.py`)

A Python module that validates the SLM's JSON output before it reaches the Scripts Agent.

**Requirements:**
- Validate that `action` is one of the known script names.
- Validate that `args` contains all required fields for that script (and no unknown fields).
- Validate enum values against the allowed lists (e.g. priority must be P0–P3).
- Validate types (numbers are numbers, booleans are booleans, UUIDs look like UUIDs).
- On validation failure: return a structured error dict `{valid: false, errors: [...]}` — never raise an exception. The orchestrator decides whether to retry or abort.
- On success: return `{valid: true, action: str, args: dict}`.

### 4. Model recommendation (`model_notes.md`)

A short document (under 300 words) with:
- Which Groq-hosted model you recommend and why.
- Token budget analysis: system prompt tokens + typical input + typical output.
- Any model-specific quirks (e.g. "this model tends to wrap JSON in markdown fences — the validator strips them").
- Fallback model if the primary choice is unavailable.

---

## What you do NOT own

- The database schema or migrations (DB Agent).
- The actual script implementations (Scripts Agent).
- Cron scheduling, health checks, or secret management (Orchestrator Agent).
- Any decision logic — you produce a call spec, the orchestrator acts on it.

---

## Deliverables checklist

| File | Format | Purpose |
|------|--------|---------|
| `groq_client.py` | Python | Groq SDK wrapper with `call_agent()` |
| `system_prompt.txt` | Text | System prompt for the SLM |
| `validate_output.py` | Python | Output validation before script execution |
| `model_notes.md` | Markdown | Model choice + token analysis |

---

## Validation criteria

Before handing off, verify:
- [ ] `call_agent("Get player state")` returns `{"action": "get_player_state", "args": {}}`.
- [ ] `call_agent("Complete task abc-123 on time with full credit")` returns a valid `complete_task` call spec with all required fields.
- [ ] `call_agent("What should I do today?")` returns an error or refusal — the model does not make decisions.
- [ ] The validator catches: missing required fields, invalid enum values, wrong types.
- [ ] The validator passes: all valid script call shapes from the contracts table.
- [ ] The system prompt fits within the chosen model's context window with room for input + output.

---

*Read `00_SHARED_CONTEXT.md` before starting. The script contracts table is your source of truth for action names and argument shapes.*
