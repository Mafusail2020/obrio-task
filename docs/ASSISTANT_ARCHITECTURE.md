# Reply assistant (Task 2): architecture

An internal copilot for support agents. The agent pastes a ticket and gets: a summary (in the ticket's language and in English), three reply drafts (formal / empathetic / short) in the customer's language with an English version on a toggle, and the knowledge-base articles behind them. **The AI never sends anything.** The agent reads, edits and sends; on high-risk tickets the drafts are locked until the agent confirms they've made the decision.

Run it: `streamlit run app.py` → **Reply assistant** tab.

## Pipeline

```
ticket (any language)
  │
  ▼
1. Task 1 classifier (reused)   English summary · intents · goal · billing channel · language · risk flags
  │                             agent can override the channel in the UI → steps 2–5 re-run (no re-classification)
  ▼
2. Retrieval                    a) policy articles linked to the sub-intents (metadata), filtered by channel
  │                             b) risk-flag protocols (crisis, chargeback)
  │                             c) semantic top-3 (qwen3-embedding), threshold 0.60, query = ENGLISH summary
  ▼
3. Human-judgment gate          🔴 decision required · 🟡 verify · 🟢 standard   (rules, not the LLM)
  │                             crisis → stop: protocol only, no drafts
  ▼
4. Generator (1 LLM call)       local summary + 3 drafts × {english, local} + source ids + commitments + missing info
  ▼
5. Normalise + validate         deterministic fixes, then checks → 1 retry with the problems fed back
  ▼
6. UI                           summary (2 languages) · channel dropdown · gate banner · KB quotes · 3 tabs · feedback
```

Code: [`assistant/`](../assistant/). KB: [`data/kb/`](../data/kb/) (29 articles). Prompts: [`prompts/assistant/`](../prompts/assistant/).

## Knowledge base

A real support KB holds **facts and procedures**, not ready replies (see the research notes in the conversation log; sources: Qiscus, Knowmax, BoldDesk). The simulated Nebula KB has 29 Markdown articles in five types: 6 policies, 7 procedures, 5 troubleshooting guides, 9 customer help articles, 2 macros. Each has front-matter:

```yaml
id: policy-refund-web
type: policy                    # policy | procedure | troubleshooting | help_article | macro
audience: internal              # internal → agent only; customer → may be linked in a reply
sub_intents: [refund_request, unexpected_charge, cancellation]   # Task 1 taxonomy
channels: [web]                 # web | app_store | google_play | any
url: https://kb.nebula.internal/policy/refund-web
last_reviewed: 2026-09-15
```

Policy values are invented but explicit (e.g. "accidental purchase: full refund within 14 days if ≤ 3 paid readings used; refunds above $50 need team lead approval"), so a draft that promises too much can be detected. The tone-of-voice rules live in the prompt, not in the KB, because they apply to every reply and shouldn't depend on retrieval.

## Why this retrieval approach

Four options were compared before building: whole KB in the prompt, embeddings only, hybrid BM25 + embeddings, category filter + embeddings. The choice was **metadata links + multilingual embeddings**:

| Decision | Reason |
|---|---|
| **Policies linked by sub-intent are always included** | What a reply may promise must not depend on embedding luck. The Task 1 sub-intent already says which policy applies. |
| **Semantic search for everything else** | Paraphrases ("charged after the trial" ≈ "auto-renewal") and articles not tagged with the sub-intent (troubleshooting, help articles). |
| **Query = Task 1 English summary (+ intents, goal, channel); non-English ticket text is never embedded** | The KB is English. The summary is already an English restatement of the problem, so a German or Ukrainian ticket is searched in the KB's language, even though the embedding model is multilingual. English tickets also add the original text. |
| **Channel filter + conditional tags** | With a known channel, articles for other channels are dropped. With an unknown channel, both variants are kept but tagged "applies only if paid via the Nebula website", and the drafts must ask where the customer paid instead of applying either. Without this, an App Store customer could be promised a website-only refund. |
| **Threshold 0.60** | Calibrated on the 20 test tickets: the expected article was the #1 hit for 19/20; relevant hits scored 0.63–0.86, weak tail matches ~0.45–0.55. |
| **No reranker, no BM25, no vector DB** | 29 short articles: brute-force cosine is instant and there's no measurable gain at this size. These are the scale-up steps for a real KB with hundreds of articles. |

**Result:** retrieval hit 20/20, wrong-channel articles 0/3, on both models.

## How the prompt produces three different tones

Final prompt: [`prompts/assistant/v3.md`](../prompts/assistant/v3.md). Its history and what failed are in [ASSISTANT_PROMPTS.md](ASSISTANT_PROMPTS.md).

1. **Role:** "An agent will read, edit and send the reply; you never talk to the customer."
2. **Fact rules:** only KB facts; no promises unless a KB excerpt allows it; conditional policies are not facts when the channel is unknown; internal articles are never copied or linked; only exact customer-article URLs.
3. **Tone contracts defined by structure and length, not adjectives.** v1 used adjectives and the tones collapsed (formal ≈ short, 74–84% shared words):
   - **formal:** greeting, restate the issue, steps, closing line; no contractions, no exclamation marks; 60–150 words.
   - **empathetic:** opens by acknowledging the situation in the customer's words; names a feeling only if the customer expressed it; never "unfortunately"; 50–120 words.
   - **short:** 1–3 sentences, ≤ 40 words, no greeting, only the action and the link.
4. **Language rules:** `english` is always English; `local` only in the ticket's language; keep the customer's facts and grammatical gender; no English words left in `local`.
5. **Structured output** (JSON schema) with `commitments` (support's promises, in English, for the agent and the validator) and `missing_info`.

All three tones come from **one call** (the user's choice: cheaper and faster than three calls). The model sees all three at once, which also helps it make them different. The validator measures distinctness (word overlap ≤ 70%): 19/19 on both models with v3.

## Conscious trade-offs (time and tools)

| Trade-off | Why | What production would do |
|---|---|---|
| **Local models (llama3.1, gemma3:12b) instead of Claude** | No API key in the dev environment; free unlimited reruns for prompt iteration | Run the same eval on Claude (Haiku for classification, Sonnet for drafting) and switch via config |
| **Synthetic KB of 29 articles** | Nebula's internal KB isn't public | Index the real KB; keep the same front-matter (type, audience, sub_intents, channels) |
| **Brute-force cosine search, no vector DB, no reranker, no BM25** | 29 short articles: instant, and no measurable gain at this size | Vector store + reranker + hybrid search for hundreds of articles |
| **One LLM call for all three tones** | 3× cheaper and faster than three calls; the model sees all tones at once | Keep, unless the tones collapse on a new model (measured by the validator) |
| **Deterministic validator instead of an LLM critic at runtime** | A critic call would double latency and cost; the agent reviews every draft anyway | Keep; maybe add a critic only for 🔴 tickets |
| **LLM judge runs on the same small local model class** | Only local models available; judge reliability measured by spot-checks, not a labelled sample | Stronger judge (Claude Sonnet) + a human-labelled sample to measure agreement |
| **20-ticket test set, labels drafted by AI and reviewed by me** | Time | Real historical tickets with agent replies as references |
| **Single message, no conversation history or customer account data** | Out of scope for the prototype | Pass thread history and account data (plan, billing channel, purchases) from the helpdesk. That would also make the channel override and many 🔴 checks automatic |
| **Streamlit page instead of a helpdesk integration** | Fastest way to a working UI | Zendesk/Intercom sidebar app calling the same `assist()` function |
| **Known issues left open** (A18 internal steps in a reply, A05 asserted eligibility) | Decision to document rather than iterate; covered by the 🔴 gate and agent review | Re-evaluate on a stronger model first; add prompt rules only if they persist |

## Deterministic layers around the LLM

Several failures were fixed in code instead of in the prompt, because a rule that can be enforced shouldn't depend on the model following an instruction:

| Layer | What it does |
|---|---|
| **Normalise** | English tickets: `local` and `summary_local` are filled in code (the model translated English replies into Spanish in v1/v2). "none"-style placeholders are removed from `commitments`. |
| **Validator: errors → 1 retry with feedback** | Exactly one draft per tone · cited articles must have been retrieved · no article for another known channel · no policy promise based on a conditional article when the channel is unknown · `local` in the ticket language (same `langdetect` detector as Task 1) · no internal URL · **every link must be a retrieved customer-article URL** · no placeholders like `[link]` or article ids |
| **Validator: warnings → shown on the draft** | Length per tone · tones too similar · internal wording copied verbatim (unless it's also public) · policy promises on a 🔴 ticket |
| **Gate** | Rules over Task 1 facts decide 🔴/🟡/🟢; see [ASSISTANT_HUMAN_JUDGMENT.md](ASSISTANT_HUMAN_JUDGMENT.md) |

## Model comparison

Same prompt (v3), pipeline, embeddings and 20 tickets. The model does both steps (classification and drafting).

| | llama3.1 8B | gemma3:12b |
|---|---|---|
| Automatic checks passed | **20/20** | 19/20 (A20: gate 🟢 instead of 🟡 because gemma's classifier was confident on a vague ticket) |
| Generation latency (avg) | 78 s | 84 s |
| Output tokens per ticket | 875 | **652** |
| Ukrainian / Russian quality (manual) | Understandable but with non-words and calques ("заворушенням", "проверить вашу идентичность") | **Natural, correct terms** |
| Hallucinations (manual) | Invented a URL (`help.nebula.com/article/policy-data-deletion`); now caught by the URL allowlist and retried | None found |
| Implicit promises when the channel is unknown | "we're here to help you get a refund" | Neutral |
| **LLM judge** (gemma3:12b, 57 drafts each) | 39 appropriate · 14 too general · **4 inappropriate** | **48 appropriate** · 9 too general · **0 inappropriate** (self-judged: possible bias) |

**Choice:**
- **Local / development: gemma3:12b for drafting.** The automatic checks are close, but the drafts are customer-facing text in the customer's language, and gemma's translations are clearly better at similar latency.
- **Production (recommended): Claude.** Haiku 5.5 for classification (Task 1); **Sonnet 5.5 for drafting**, since drafting needs more language quality than extraction. Not measured yet: no API key in the dev environment. Next step: run `--provider claude` on the same test set.
- A split setup (small model classifies, stronger model drafts) is supported by the architecture (two independent calls), but not yet wired into the UI.

## Quality evaluation: automatic checks + LLM judge + manual reading

Three layers, because each misses things the others catch:

| Layer | What it measures | Where |
|---|---|---|
| Automatic checks (eval runner) | Retrieval hit, wrong-channel articles, gate level, three tones present, language, validator errors, no policy promises when the channel is unknown, tone distinctness, length | [ASSISTANT_EVAL_REPORT.md](ASSISTANT_EVAL_REPORT.md) |
| **LLM judge** (offline only, [`evaluation/judge.py`](../evaluation/judge.py), prompt [`prompts/judge/v1.md`](../prompts/judge/v1.md)) | Per draft: appropriate / too general / inappropriate (the rubric from the agentic-RAG copilot paper), grounded in KB, tone fit, translation faithful | [ASSISTANT_JUDGE_REPORT.md](ASSISTANT_JUDGE_REPORT.md) |
| Manual reading | Translation quality, invented facts, tone | [ASSISTANT_PROMPTS.md](ASSISTANT_PROMPTS.md) |

**How reliable is the judge?** I checked its flagged verdicts against the actual drafts (llama3.1 run):
- **Correct catches:**
  - A18: internal procedure turned into customer instructions (see known issues below), missed by both the validator and my manual reading.
  - A05: drafts assert refund eligibility.
  - A01: implied refund promise.
  - A14: an English word left in the Russian text.
- **Wrong:**
  - A14: "data permanently erased" marked unsupported; the KB says exactly that.
  - A15: a correct retrieved URL marked as "not in KB".
  - A17: a correct conditional explanation of both payment paths marked inappropriate.
- Several "too general" verdicts on short drafts are debatable: short drafts are brief by design.

So the judge is **a good pointer to where to look and a fair relative comparison between models, not an absolute score.** It runs on the same small local model class as the generator. A stronger judge (e.g. Claude Sonnet) and a human-labelled sample to measure judge agreement would be the next steps.

## Known issues (found by the judge, not fixed)

Both are most likely model-capability limits that a stronger drafting model (the recommended Claude Sonnet 5.5 for production) would largely remove. There's already a hint: the stronger local model (gemma3:12b) didn't make the A18 mistake at all, and had fewer unsupported claims overall (52/57 grounded vs 44/57). This isn't verified on Claude yet; re-running the eval and the judge with `--provider claude` would confirm it.

1. **Internal procedures leaking into customer instructions (A18, llama3.1).** The short draft told the customer to "check your order in the admin panel… click Resend": steps from the internal `sop-missing-content` procedure that only agents can perform. The validator's verbatim-overlap check didn't fire because the wording was paraphrased. Mitigation in place: the agent reviews every draft. Possible fix: a prompt rule "procedures describe what the *agent* does; never instruct the customer to perform agent steps", plus a validator term list (admin panel, team lead, Trust & Safety…).
2. **Refund eligibility asserted instead of conditional (A05, both models).** For an accidental website purchase, drafts said "you're eligible for a full refund", but eligibility depends on usage (≤ 3 paid readings) that nobody has checked. Mitigation in place: the ticket is 🔴 *refund decision*, copy is locked until the agent confirms, and the promise is flagged on the draft. Possible fix: "when eligibility depends on facts the agent must verify, phrase it conditionally and list the facts in `missing_info`".

## Failure handling

Reuses Task 1's `LLMClient`, error kinds, retry policy and optional fallback provider (see [FAILURE_HANDLING.md](FAILURE_HANDLING.md)).

| Failure | Behaviour |
|---|---|
| Classification fails | Retrieval runs on the raw text only if it's English, otherwise without semantic search; gate 🟡 "classification failed" |
| **Embedding model down** | Retrieval degrades to metadata-linked policies + risk-flag protocols (tested); KB index build failure shows an error in the tab instead of crashing |
| Generation: invalid JSON, timeout, rate limit | Same retry policy as Task 1; if it still fails, the summary, gate and KB sources are shown and the agent writes the reply manually |
| Validator errors remain after the retry | Drafts are shown with the errors next to them; the agent decides |
| Crisis ticket | No generation call at all |

## Cost and caching

Per ticket there are two LLM calls: classification (~1.9k in / ~170 out) and drafting (~1.5k in / ~650–875 out; bilingual output roughly doubles output tokens for non-English tickets).

| Setup | $ / ticket | $ / 10k tickets |
|---|---|---|
| Haiku 5.5 for both | ~$0.0009 | ~$9 |
| Haiku 5.5 classify + **Sonnet 5.5 draft** (recommended) | ~$0.012 | ~$120 |
| Sonnet 5.5 for both | ~$0.017 | ~$175 |

These are estimates from measured token counts × list prices, before caching and thinking tokens. Even the most expensive setup is small compared with agent time: drafts that save 2 minutes on 10k tickets save ~330 agent-hours.

**Optimisations, in order:**
1. **Reuse the Task 1 result.** In production the ticket was already classified at routing time, so the assistant shouldn't classify again. The pipeline accepts an existing triage (already used by the channel-override re-run).
2. **Generate on demand:** only when the agent opens the ticket and clicks, not for every incoming ticket.
3. **English tickets don't need a `local` version:** already filled in code; the prompt asks for an empty string, saving output tokens.
4. **Prompt caching** for the static system prompt (~850 tokens, above the 512-token minimum).
5. Cheaper model for 🟢 tickets, stronger model for the rest.

**Caching:**

| What | Cached? | Invalidation |
|---|---|---|
| KB article embeddings | **Yes, implemented**: on disk, keyed by (embedding model, content hash); only new or edited articles are re-embedded (editing `policy-credits` re-embedded 1 article) | Automatic: content hash or model change |
| System prompt (provider prompt cache) | Yes, on Claude | Automatic on any prompt byte change |
| KB excerpts in the prompt | No: they differ per ticket and come after the static part | n/a |
| Classification for the same ticket | **Yes, implemented** for the channel re-run (triage is reused) | New ticket text |
| Generated drafts | Only per ticket in the UI session. Caching drafts across tickets ("similar ticket → reuse reply") is rejected: replies must reflect the specific customer, channel and KB version | Prompt version, KB content, channel |
