# Model comparison (Task 1)

Same prompt (v5), pipeline and 41 tickets. **Pass** = category, priority, needs_human and required flags all right, and no false flag. Regenerate: `python -m evaluation.report compare --prompt v5`.

| Model | Pass | Category | Sub-intent | Priority | needs_human | Req. flags | False flags | LLM failures | Latency avg / p95 | Tokens in / out |
|---|---|---|---|---|---|---|---|---|---|---|
| **gemma3:12b** | **39/41** | 100% | 100% | 98% | 98% | 5/5 | 1 | 0 | 22.8 / 28.2 s | 2108 / 206 |
| **llama3.1 8B** | 38/41 | 100% | 97% | 93% | **100%** | 5/5 | **0** | 0 | **10.5 / 12.1 s** | 1944 / 170 |
| qwen3-vl:4b (thinking) | 34/41 | 87% | 87% | 93% | 95% | 4/5 | 0 | **6** | 42.9 / 76.3 s | 1982 / 1147 |
| llama3.2:3b | 27/41 | 95% | 92% | 78% | 90% | 5/5 | **7** | 0 | 5.6 / 6.8 s | 1954 / 182 |

Hardware: MacBook, Ollama, one request at a time. Claude estimates (not measured, no API key), per 10k tickets with prompt cache: Haiku 5.5 ~$1.3, Sonnet 5.5 ~$26, Opus 5.5 ~$49 ([COST_AND_CACHING.md](COST_AND_CACHING.md)).

**Misses:**
- **gemma3:12b:** a false legal flag on all-caps "THIEVES" → P1 (safe direction); T33 is a borderline label.
- **llama3.1:** 3 invented secondary intents → P2 instead of P3/P4. The only model with 0 false flags and 100% needs_human.
- **qwen3-vl:4b:** 6 schema failures (thinking output + JSON-schema constraint), all safely routed to manual review; ~1,000 hidden reasoning tokens per ticket; one missed `aggressive_tone`.
- **llama3.2:3b:** unsafe. Injection worked again (T39 → P4 automated), sarcasm → `feedback`, 7 false flags including **crisis on a calm Russian deletion request**.

**Conclusions:**
1. Quality rises sharply from 3B to 8B (27 → 38 passes, 7 → 0 false flags), then flattens: 12B gives +1 pass at 2.2× latency.
2. Thinking doesn't pay for narrow extraction: 4× slower, 6× output tokens, 15% schema failures. This supports `effort: low` on Claude.
3. The safety layers held: no model under-prioritised a crisis, and model errors became over-escalation rather than silent automation, except for injected facts on 3B.
4. A prompt tuned on 8B transferred up (gemma did as well untuned) but not down (3B relapsed on failures fixed in v2).

| Use | Choice | Why |
|---|---|---|
| Dev / evals | **llama3.1 8B** | Best quality per second; 0 false flags; 100% needs_human |
| Production | **Claude Haiku 5.5** (verify with `--provider claude`; step up to Sonnet if below 38/41) | Cheaper than a self-hosted GPU at 10k/month; guaranteed JSON; multilingual |
| Fallback | llama3.1 8B | `LLM_FALLBACK_PROVIDER=ollama` |
| Avoid | llama3.2:3b, qwen3-vl:4b | Injection and false crisis flags; slow with schema failures |
