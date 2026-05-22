# Model Notes — Life System Inference Agent

## Recommended model

**`meta-llama/llama-4-scout-17b-16e-instruct`** (Groq-hosted)

Llama 4 Scout is the best fit for this task. It reliably follows strict JSON-only output instructions with near-zero hallucination on structured schemas, handles few-shot examples well, and at 17B parameters it stays fast enough for synchronous orchestrator calls. Its 10M token context window means the system prompt + state context will never be an issue.

## Token budget

| Component | Estimated tokens |
|-----------|-----------------|
| System prompt | ~620 |
| Context injection (player_state + snapshot) | ~150–300 |
| User instruction | ~20–60 |
| Model output (JSON call spec) | ~50–120 |
| **Total per call** | **~840–1100** |

Well within budget. `max_tokens = 512` is a safe ceiling for the output; the model never needs more than ~120 for a valid response.

## Known quirks

- **Llama 4 Scout** behaves cleanly with JSON-only instructions and rarely wraps output in markdown fences. The `_extract_json` function in `groq_client.py` strips them defensively anyway.
- At `temperature = 0.1` the model is highly deterministic. Identical inputs will produce identical outputs in >95% of test runs.

## Fallback model

**`meta-llama/llama-4-maverick-17b-128e-instruct`** — same generation, slightly larger context handling, equally reliable on structured output tasks. Use if Scout is unavailable or rate-limited.

Set via environment variable:
```
GROQ_MODEL_ID=meta-llama/llama-4-maverick-17b-128e-instruct
```
