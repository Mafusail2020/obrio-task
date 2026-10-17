# Cost and caching

## Token profile (measured)

From the final eval (prompt v5, 41 tickets, [`evaluation/results/`](../evaluation/results/)):

| | Tokens per ticket |
|---|---|
| Input: system prompt (taxonomy, rules, 9 examples) + JSON schema | ~1,890 (identical for every ticket) |
| Input: the ticket itself | ~50 on average (short tickets; long emails would be 200–800) |
| Output: structured JSON incl. `reasoning` and `summary` | ~170 |
| Retries | ~0% in the final run (0 failures); budget 2–5% for production |

The prompt grew from 342 input tokens (v1) to 1,944 (v5). **97% of the input is the static prompt.** That shapes both the cost and the caching story.

These counts come from the llama tokenizer. Claude's tokenizer differs by roughly ±20%, and Claude Haiku/Sonnet/Opus 5.5 also spend some adaptive-thinking tokens (we run `effort: low`). Treat the Claude figures below as estimates until a Claude eval run measures `usage` directly.

## Cost per ticket and forecast for 10,000 tickets/month

Prices per 1M tokens (input / output): Haiku 5.5 $0.10 / $0.50 · Sonnet 5.5 $2 / $10 · Opus 5.5 $4 / $20. Cache writes cost 1.25× input; cache reads 0.1× (Opus 5.5: 0.05×).

| Model | $ / ticket (no cache) | $ / 10k tickets (no cache) | $ / ticket (prompt cache, 90% hits) | $ / 10k (cached) |
|---|---|---|---|---|
| **Claude Haiku 5.5** | $0.00028 | **$2.8** | $0.00013 | **$1.3** |
| Claude Sonnet 5.5 | $0.0056 | $56 | $0.0026 | $26 |
| Claude Opus 5.5 | $0.0112 | $112 | $0.0049 | $49 |
| Local llama3.1 8B (Ollama) | $0 API | $0 API + hosting | n/a | n/a |

How the Haiku figure is built: `1,944 × $0.10/M + 170 × $0.50/M = $0.000194 + $0.000085`. With caching, a hit pays `1,890 × $0.01/M` for the prompt instead of `1,890 × $0.10/M`.

**Local is not free at production volume.** At ~10.5 s per ticket on this laptop, 10k tickets is ~29 hours of single-stream compute a month. Running that reliably means an always-on GPU server, which costs far more per month than $1–3 of Haiku API usage. Local models make sense here for **development and evals** (unlimited free reruns, no data leaves the machine) and as a **fallback provider**, not as the production default.

**Even the most expensive option is small next to agent time.** At Opus prices, 10k tickets cost ~$110/month. Saving a human agent 30 seconds of routing per ticket is ~83 hours/month. So the model choice should be driven by **quality and safety first**, then latency, with cost a distant third. See [MODEL_COMPARISON.md](MODEL_COMPARISON.md).

## Optimising cost without losing quality

Ordered from "free" to "trade-off":

1. **Prompt caching** (implemented): the static ~1.9k-token system prompt is marked with `cache_control`. About −53% on Haiku, −54% on Sonnet, −56% on Opus at 90% hit rate. No quality impact.
2. **`effort: low`** (implemented): classification gains nothing from deep reasoning; keeps thinking tokens minimal.
3. **Keep policy in code, not in the prompt** (already the architecture): routing, priority and SLA rules cost zero tokens and don't need the bigger model to apply them.
4. **Cheapest adequate model + cascade:** Haiku for every ticket; re-run only `confidence: low` tickets (2–5%) on Sonnet. Most of Sonnet's quality on hard tickets at roughly Haiku's price.
5. **Trim the prompt with evidence:** every example costs ~60–100 tokens on every ticket. Remove an example only if a full eval rerun shows no regression (v3/v4 showed that examples have side effects in both directions).
6. **Batch API (−50%)** only for non-urgent work: re-classifying a backlog, eval runs, analytics. **Not** for live triage, because batch results can take hours and crisis tickets can't wait.
7. **Drop the `reasoning` field?** It saves ~30–40 output tokens, but it helps the model and is what the agent and the reviewer read. Not worth it at these prices.

## Caching: is it needed, and what exactly?

There are three different kinds of cache. They get different answers.

### 1. Provider prompt caching: **yes, implemented**

- **What:** the static prefix, i.e. the system prompt (taxonomy, rules, examples) plus the output schema. It's byte-identical for every ticket, ~1.9k tokens, above Haiku 5.5's 512-token minimum.
- **Why it fits:** 97% of input tokens are this prefix. The ticket is the only variable part, and it comes last in the request.
- **TTL choice:** 10k tickets/month ≈ one ticket every ~4.3 minutes on average, and more often during business hours. That's under the default 5-minute TTL, so the cache stays warm through the working day. The 1-hour TTL costs 2× per write and only pays off for gaps of 5–60 minutes; not worth it here. Night-time gaps will cost one cache write in the morning, which is negligible.
- **Invalidation:** automatic. Any change to the prompt bytes, a new prompt version, or a new model creates a new cache entry; old ones expire after the TTL. No manual invalidation is needed. A schema change also changes the prefix.
- **How to verify:** `usage.cache_read_input_tokens` is recorded per ticket in `meta.cache_read_tokens`. If it stays 0 across consecutive tickets, something in the prefix is varying.

### 2. Result cache (ticket → classification): **only as a small dedupe cache**

- **What it would store:** the LLM's *facts* (`Extraction`), keyed by `sha256(normalised masked text) + prompt_version + model`. **Routing is never cached**: it's computed by code in microseconds, and caching it would freeze old policy after a router change.
- **Expected hit rate:** low for real traffic, since free-text tickets are almost never byte-identical. Hits come from customers re-sending the same message, the same message arriving via email and chat, spam waves, and re-clicking "Classify" in the UI.
- **Invalidation:** prompt version and model are part of the key, so a new prompt or model naturally misses. Short TTL (e.g. 24 h), so a cached answer can't outlive a taxonomy change by long.
- **Verdict:** a cheap nice-to-have for duplicates and spam bursts, not a cost lever. At $0.00013 per ticket, the savings don't justify the extra infrastructure in the prototype. Not implemented.

### 3. Semantic cache (similar ticket → reuse its answer): **no**

Reusing the classification of a "similar" ticket is dangerous here:
- Similar wording, different meaning: "I want to cancel" vs "I **can't** cancel", or "refund my credits" for a slow advisor vs for a bug.
- **Risk flags must be computed for every ticket individually.** A crisis sentence appended to an otherwise ordinary refund request must not inherit the cached "P2 billing" answer.
- The saving would be ~$0.0001 per hit.

The safety risk is far larger than the saving, so semantic caching is rejected.

### Local models (Ollama)

Ollama keeps the model loaded between requests (`keep_alive`), and llama.cpp reuses the KV cache for a repeated prompt prefix within a slot. That's the local equivalent of prompt caching, and it works without configuration. No application-level cache is needed.
