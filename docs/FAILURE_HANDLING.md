# Failure handling

Design rule: **an LLM failure must never lose a ticket or lower its safety level.** If the model fails, the ticket still gets a priority, a queue and a human. The keyword guardrails run before and independently of the LLM, so a crisis or chargeback ticket still becomes P1 even when every provider is down.

## Error classification

Every provider error is mapped to one of three kinds ([`classifier/llm/base.py`](../classifier/llm/base.py)), and the kind decides what happens next ([`classifier/extractor.py`](../classifier/extractor.py)):

| Kind | Causes | Policy |
|---|---|---|
| `invalid_output` | JSON doesn't match the schema; truncated output (`max_tokens`); empty parse | Retry **with the validation error fed back** to the model ("Your previous answer was invalid: … Return a corrected answer.") |
| `transient` | Timeout, rate limit (429), 5xx / overloaded, connection error, Ollama unreachable | Retry the same request after a short backoff; then the fallback provider if one is configured |
| `fatal` | Bad or missing API key, model not found / not pulled, request rejected (400), model refusal | **No retry** on the same provider (retrying can't fix it); fallback provider if configured |

## Scenario table

| Scenario | What happens | Ticket outcome |
|---|---|---|
| **Invalid JSON / schema mismatch** | Structured outputs make it rare (Claude `messages.parse` with the Pydantic schema; Ollama JSON-schema `format`). If it happens: one retry with the error fed back. | Usually a normal result on attempt 2. If it fails again → `extraction_failed`. |
| **Valid JSON, inconsistent labels** (sub-intent from another category) | Category derived from the sub-intent in code, warning logged. No retry needed. | Normal result + warning in `meta.warnings`. |
| **Timeout** | `LLM_TIMEOUT_S` (default 120 s). Claude: the SDK retries timeouts itself (`max_retries=2`, exponential backoff), then we retry once more. Ollama: mapped from `httpx.TimeoutException`. | Retry → fallback → `extraction_failed`. |
| **Rate limit (429)** | Claude SDK retries with backoff and honours `retry-after`; what reaches us is after those retries → `transient`. | Retry → fallback → `extraction_failed`. At volume, the right fix is a request queue with concurrency limits, not more retries. |
| **5xx / overloaded** | Same as rate limit. | Same. |
| **Auth / config error** | `fatal`: not retried. UI shows a missing-key warning in the sidebar. | Fallback if configured, otherwise `extraction_failed`. |
| **Model refusal** (`stop_reason: refusal`) | `fatal` for this provider. | Fallback, otherwise `extraction_failed`. |
| **Output truncated** (`max_tokens`) | `invalid_output` → retry with feedback. | Normal result or `extraction_failed`. |
| **Primary provider down, fallback configured** | `FallbackClient` tries the next provider (e.g. Claude → local Ollama). `invalid_output` is **not** a reason to switch providers. | Normal result; `meta.warnings` records "answered by fallback". |
| **Everything failed** (`extraction_failed`) | Router hard rule → **P2, `review_manually`, needs_human**. Guardrail flags still apply. | A human triages it manually. Crisis/legal keywords → still **P1**. |
| **Ticket too long** | Cut at `MAX_TICKET_CHARS` (4,000); `truncated=true` shown in the UI. | Normal result, flagged. |

## Fallback scenarios

1. **Provider fallback** (`LLM_FALLBACK_PROVIDER`, or the sidebar selector): Claude primary + local Ollama fallback keeps triage running through an API outage. The fallback is lower quality but far better than an empty queue. The reverse also works for development: local primary, Claude as backup.
2. **Degraded mode, no LLM at all:** guardrails + `extraction_failed` rule. Every ticket still gets a queue and a human. Crisis and legal keywords still escalate to P1.
3. **Human fallback:** every failed ticket lands in the review queue with the error reason visible.

## What is tested

[`tests/test_failures.py`](../tests/test_failures.py), all without a real LLM:
- Transient errors are retried **without** feedback; invalid output is retried **with** feedback.
- Fatal errors are not retried.
- Invalid JSON twice → manual review at P2.
- LLM down + crisis keyword → still P1.
- Fallback answers when the primary is down and is recorded in metadata.
- Fallback does **not** hide invalid output.
- Ollama `httpx.ReadTimeout` → transient.
- Claude 429 / 500 / timeout → transient; 401 → fatal.

## Known gaps (out of scope for the prototype)

- No circuit breaker: during a long outage, every ticket still waits for the primary's timeout before falling back. A breaker that skips the primary for N minutes after repeated failures would fix that.
- No request queue or concurrency limit; needed before production volume (rate limits).
- `extraction_failed` tickets are not retried automatically later; a background re-run when the provider recovers would cut manual work.
