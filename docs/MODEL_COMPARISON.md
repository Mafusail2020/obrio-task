# Model comparison (Task 1 classifier)

All models ran the same final prompt (v5), the same pipeline and the same 41 tickets. A ticket **passes** when category, priority, needs_human and all required risk flags are right and there is no false risk flag. Regenerate the table with `python -m evaluation.report compare --prompt v5`; raw results are in [`evaluation/results/`](../evaluation/results/).

## Results

| Model | Overall pass | Category | Sub-intent | Priority | needs_human | Req. flags | False flags | LLM failures | Latency avg / p95 | Tokens in / out |
|---|---|---|---|---|---|---|---|---|---|---|
| **gemma3:12b** | **39/41** | 100% | 100% | 98% | 98% | 5/5 | 1 | 0 | 22.8s / 28.2s | 2108 / 206 |
| **llama3.1 8B** | 38/41 | 100% | 97% | 93% | **100%** | 5/5 | **0** | 0 | **10.5s / 12.1s** | 1944 / 170 |
| qwen3-vl:4b (thinking) | 34/41 | 87% | 87% | 93% | 95% | 4/5 | 0 | **6** | 42.9s / 76.3s | 1982 / **1147** |
| llama3.2:3b | 27/41 | 95% | 92% | 78% | 90% | 5/5 | **7** | 0 | 5.6s / 6.8s | 1954 / 182 |

Hardware: MacBook, Ollama, one request at a time. Latency is the LLM call only.

| Claude (not measured yet: no API key in the dev environment) | Estimated $ / ticket | $ / 10k tickets (with prompt cache) |
|---|---|---|
| Claude Haiku 5.5 | $0.00028 | ~$1.3 |
| Claude Sonnet 5.5 | $0.0056 | ~$26 |
| Claude Opus 5.5 | $0.0112 | ~$49 |

These are estimated from the measured token counts above; see [COST_AND_CACHING.md](COST_AND_CACHING.md).

## What each model got wrong

**gemma3:12b** (2 misses)
- T37, all-caps "THIEVES… SCAM" ticket: false `legal_or_chargeback_threat` → **P1** instead of P2. Over-escalation, the safe direction.
- T33 "hi it doesnt work": the label expects a human because the ticket is vague and low-confidence. gemma was *confident* it's `spam_or_unclear`, so it got automated. This is a borderline label rather than a real error.

**llama3.1 8B** (3 misses): all three are invented secondary intents that raise priority (P2 instead of P3/P4), see [EDGE_CASES.md](EDGE_CASES.md). It's the only model with **zero** false risk flags and **100%** needs_human.

**qwen3-vl:4b with thinking** (7 misses)
- **6 extraction failures:** after 2 attempts the output still didn't match the schema. The pipeline handled them safely (→ P2 manual review). Thinking-mode output and Ollama's JSON-schema constraint don't mix reliably.
- It's also the slowest model by far: ~1,150 output tokens per ticket, of which ~1,000 are hidden reasoning, taking 43 s on average and 76 s at p95.
- One missed required flag: no `aggressive_tone` on the "I want my money back NOW… THREE times!!!" ticket.

**llama3.2:3b** (14 misses): unsafe for this task.
- **Prompt injection worked again** (T39 → `product_question`, P4, automated) and **sarcasm** was read as `feedback` (T40). Both had been fixed for the 8B model in v2.
- **7 false risk flags**, including `self_harm_or_crisis` on a calm Russian account-deletion request (T28 → P1 crisis queue) and `legal_or_chargeback_threat` on two ordinary billing tickets.

## Conclusions

1. **Size matters up to ~8B, then flattens.** 3B → 8B: from 27 to 38 passes and from 7 to 0 false flags. 8B → 12B: +1 pass at 2.2× latency.
2. **Thinking doesn't pay off for extraction.** The 4B thinking model is 4× slower than the 8B, produces 6× the output tokens and fails schema validation on 15% of tickets. Our task is narrow labelling with definitions in the prompt, not multi-step reasoning. This matches the decision to run Claude at `effort: low`.
3. **The safety layers did their job on weaker models.** No model under-prioritised a real crisis (all had the crisis ticket at P1). qwen's schema failures all went to human review, and the deterministic router turned model mistakes into *over*-escalation rather than silent automation, except where the model was tricked into wrong facts (llama3.2 + injection).
4. **Prompts transfer imperfectly down, well up.** The v5 prompt was tuned on llama3.1. gemma3:12b did as well without any tuning, while llama3.2:3b relapsed on failures v2 had fixed. Tuning on a mid-size model and expecting bigger models to hold up is a reasonable development strategy.

## Final choice

| Use | Choice | Why |
|---|---|---|
| **Development and evals** | **llama3.1 8B** (Ollama) | Best quality per second: 38/41, the only model with 0 false flags and 100% needs_human, 10.5 s per ticket. Free unlimited reruns, data stays local. |
| **Production (recommended)** | **Claude Haiku 5.5** | At 10k tickets/month a self-hosted GPU costs far more than ~$1–3 of Haiku API usage. Structured outputs guarantee schema-valid JSON, which removes the failure class qwen showed. Strong multilingual handling for uk/ru/es/de tickets. **To do before go-live:** run this same eval on Haiku (one command: `--provider claude`). If it falls below llama3.1's 38/41, step up to Sonnet 5.5 (still only ~$26/10k with caching). |
| **Fallback provider** | llama3.1 8B | Keeps triage running during an API outage (`LLM_FALLBACK_PROVIDER=ollama`). |
| Not recommended | llama3.2:3b, qwen3-vl:4b | 3B: injection and false crisis flags. 4B thinking: slow, schema failures. |

gemma3:12b is a valid alternative to llama3.1 if accuracy matters more than speed locally. Its single real miss (false P1) is in the safe direction.
