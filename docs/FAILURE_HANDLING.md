# Failure handling

**Rule: an LLM failure never loses a ticket or lowers its safety level.** Guardrails run before the LLM and independently of it, so crisis and chargeback tickets still become P1 when every provider is down.

## Error kinds ([`base.py`](../classifier/llm/base.py) → policy in [`extractor.py`](../classifier/extractor.py))

| Kind | Causes | Policy |
|---|---|---|
| `invalid_output` | Schema mismatch, truncated (`max_tokens`), empty parse | Retry **with the validation error fed back** |
| `transient` | Timeout, 429, 5xx, connection, Ollama unreachable | Retry after a backoff, then the fallback provider |
| `fatal` | Bad key, model missing, 400, refusal | No retry on the same provider; fallback if configured |

## Scenarios

| Scenario | Outcome |
|---|---|
| Invalid JSON | Rare thanks to structured outputs (Claude `messages.parse`, Ollama JSON-schema `format`); one retry with feedback, then `extraction_failed` |
| Sub-intent from the wrong category | Category derived in code; warning logged |
| Timeout (`LLM_TIMEOUT_S`, 120 s) | Claude SDK retries itself (`max_retries=2`), then one more retry here → fallback → `extraction_failed` |
| Rate limit / 5xx | SDK backoff honours `retry-after` → same path. At volume: a request queue, not more retries |
| Auth error, refusal | Not retried; fallback or `extraction_failed`; the UI warns about a missing key |
| Primary down, fallback configured | `FallbackClient` (e.g. Claude → local Ollama); `invalid_output` never switches provider; the fallback is recorded in `meta.warnings` |
| **`extraction_failed`** | Hard rule: **P2, manual review, human**; guardrail flags still apply |
| Ticket too long | Cut at 4,000 characters, flagged in the UI |

Fallback levels: second provider → degraded mode (guardrails + manual-review rule, no LLM) → human review queue.

**Tested** ([`tests/test_failures.py`](../tests/test_failures.py), no real LLM):
- transient retried without feedback; invalid retried with feedback
- fatal not retried
- invalid JSON ×2 → P2 review
- outage + crisis keyword → P1
- fallback used and recorded, but doesn't hide invalid output
- Ollama timeout → transient
- Claude 429/500/timeout → transient, 401 → fatal

**Gaps:**
- No circuit breaker, so every ticket waits for the primary's timeout during an outage.
- No request queue or concurrency limit.
- No automatic re-run of failed tickets once the provider recovers.
