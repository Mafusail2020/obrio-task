# Cost and caching (Task 1)

## Tokens per ticket (measured, prompt v5)

~1,890 static prompt + ~50 ticket = **~1,944 input**; **~170 output**; ~0% retries (budget 2–5%). **97% of the input is the static prompt.** Counts come from the llama tokenizer: Claude's differs by ~±20%, and Claude adds some thinking tokens at `effort: low`, so Claude figures are estimates.

## Cost

Prices per 1M tokens (in / out): Haiku 5.5 $0.10/$0.50 · Sonnet 5.5 $2/$10 · Opus 5.5 $4/$20. Cache write 1.25×, cache read 0.1× (Opus 0.05×).

| Model | $ / ticket | $ / 10k | $ / ticket, cache 90% hits | $ / 10k, cached |
|---|---|---|---|---|
| **Haiku 5.5** | $0.00028 | **$2.8** | $0.00013 | **$1.3** |
| Sonnet 5.5 | $0.0056 | $56 | $0.0026 | $26 |
| Opus 5.5 | $0.0112 | $112 | $0.0049 | $49 |
| llama3.1 local | $0 API | hosting | – | – |

Haiku: `1,944 × $0.10/M + 170 × $0.50/M`.

- **Local isn't free in production:** 10k tickets × 10.5 s ≈ 29 h of compute a month, which needs an always-on GPU costing far more than $1–3 of Haiku. Local is for development, evals and fallback.
- **Even Opus (~$110/10k) is small next to agent time:** 30 s saved per ticket is ~83 h/month. Choose by quality and safety first.

**Optimisations, free → trade-off:**
1. Prompt caching (implemented): −53% Haiku, −54% Sonnet, −56% Opus.
2. `effort: low` (implemented).
3. Policy in code, not in the prompt (already the architecture).
4. Cascade: Haiku for everything, Sonnet only for `confidence: low` (2–5%).
5. Trim few-shot examples, only with a full rerun (examples have side effects).
6. Batch API (−50%) only for backfills and evals, never live triage.
7. Keep `reasoning`: ~35 tokens, useful to the model and the reviewer.

## Caching

| Cache | Verdict | Details |
|---|---|---|
| **Provider prompt cache** | **Yes, implemented** | Static system prompt + schema, ~1.9k tokens (> 512-token Haiku minimum), identical for every ticket. 10k/month ≈ one ticket every ~4.3 min, inside the 5-min TTL during the day; the 1-hour TTL (2× write) isn't worth it. Invalidation is automatic on any prompt or model change. Verify with `meta.cache_read_tokens` > 0. |
| Result cache (ticket → facts) | Small dedupe only, not built | Key `sha256(masked text) + prompt_version + model`; store facts, never routing (policy changes). Hit rate is low (duplicates, spam waves, UI re-clicks); 24 h TTL. Not worth the infrastructure at $0.00013/ticket. |
| Semantic cache (similar ticket → reuse) | **No** | "I want to cancel" ≠ "I *can't* cancel"; risk flags must be computed per ticket (a crisis line must not inherit a cached P2). The saving is ~$0.0001. |
| Local (Ollama) | Built in | `keep_alive` + llama.cpp KV-prefix reuse |
