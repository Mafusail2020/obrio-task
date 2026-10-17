# Reply assistant (Task 2): architecture

The agent pastes a ticket and gets:
- a summary in the ticket's language and in English
- 3 drafts (formal / empathetic / short) in the customer's language, with English on a toggle
- the KB articles behind them

**The AI never sends anything.** On 🔴 tickets the drafts stay locked until the agent confirms the decision. Run: `streamlit run app.py` → **Reply assistant**.

```
ticket → 1. Task 1 classifier   English summary · intents · goal · channel · language · flags
                                (agent can override the channel → steps 2–5 re-run, no re-classification)
       → 2. retrieval           a) policies linked by sub-intent, channel-filtered  b) risk-flag protocols
                                c) semantic top-3, qwen3-embedding, threshold 0.60, query = ENGLISH summary
       → 3. gate                🔴 / 🟡 / 🟢 by rules; crisis → protocol only, no drafts
       → 4. 1 LLM call          local summary + 3 × {english, local} + source ids + commitments + missing info
       → 5. normalise + validate → 1 retry with problems fed back
       → 6. UI
```

Code [`assistant/`](../assistant/) · KB [`data/kb/`](../data/kb/) · prompts [`prompts/assistant/`](../prompts/assistant/).

## Knowledge base

Support KBs hold facts and procedures, not ready replies (Qiscus, Knowmax, BoldDesk). Our 29 synthetic articles: 6 policies, 7 procedures, 5 troubleshooting, 9 help articles, 2 macros.

```yaml
type: policy        # policy | procedure | troubleshooting | help_article | macro
audience: internal  # internal → agent only; customer → linkable
sub_intents: [refund_request, unexpected_charge]   # Task 1 taxonomy
channels: [web]     # web | app_store | google_play | any
```

Policy values are explicit (e.g. "accidental purchase: full refund within 14 days if ≤ 3 readings used; > $50 needs team lead"), so an over-promise is detectable. Tone rules live in the prompt, because they apply to every reply.

## Retrieval: why

Compared before building: whole KB in the prompt · embeddings only · BM25 + embeddings · category filter + embeddings. **Chosen: metadata links + multilingual embeddings.**

| Decision | Reason |
|---|---|
| Policies linked by sub-intent always included | What a reply may promise must not depend on embedding luck |
| Semantic search for the rest | Paraphrases; troubleshooting and help articles |
| **Query = English summary; non-English ticket text never embedded** | The KB is English; the summary is already an English restatement (English tickets add the original text) |
| Channel filter + conditional tags | Known channel: other channels dropped. Unknown: both kept, tagged "applies only if…", and drafts must ask where they paid, otherwise an App Store customer could be promised a website refund |
| Threshold 0.60 | Expected article was the #1 hit on 19/20 tickets; relevant 0.63–0.86, weak tail 0.45–0.55 |
| No reranker, BM25 or vector DB | 29 articles: brute-force is instant, no gain at this size |

Result: retrieval hit 20/20, wrong-channel articles 0/3, on both models.

## Prompt for three tones ([`v3.md`](../prompts/assistant/v3.md), history in [ASSISTANT_PROMPTS.md](ASSISTANT_PROMPTS.md))

1. Role: the agent sends; you never talk to the customer.
2. Facts: KB only; no promise without KB support; conditional ≠ fact when the channel is unknown; never copy or link internal articles; exact customer URLs only.
3. **Tone contracts by structure and length** (adjectives collapsed in v1): formal = greeting, steps, closing, no contractions, 60–150 words; empathetic = acknowledge in the customer's words, no invented feelings, 50–120 words; short = ≤ 3 sentences, ≤ 40 words.
4. Language: `local` only in the ticket's language; keep facts and grammatical gender; no English words.
5. JSON schema with `commitments` (in English) and `missing_info`.

All 3 tones come from **one call**, which is cheaper and lets the model contrast them; distinctness was 19/19.

## Deterministic layers

| Layer | Does |
|---|---|
| Normalise | English tickets: `local`/`summary_local` filled in code (the model translated them into Spanish); "none" commitments stripped |
| Validator errors → retry | one draft per tone · cited articles retrieved · no wrong-channel article · no policy promise from a conditional article with unknown channel · `local` language (Task 1 `langdetect`) · **links must be retrieved customer URLs** · no placeholders or article ids |
| Validator warnings | length · tones too similar · internal wording copied (unless public) · policy promise on 🔴 |
| Gate | [ASSISTANT_HUMAN_JUDGMENT.md](ASSISTANT_HUMAN_JUDGMENT.md) |

## Trade-offs (time and tools)

| Trade-off | Production would |
|---|---|
| Local models (no API key) | Run the eval on Claude: Haiku classifies, Sonnet drafts |
| 29 synthetic articles | Index the real KB with the same front-matter |
| Brute-force search, no reranker / BM25 | Vector store + reranker + hybrid search |
| One call for 3 tones | Keep unless tones collapse on a new model |
| Deterministic validator, no runtime critic | Keep; maybe a critic for 🔴 only |
| Judge on the same small model class | Claude judge + a human-labelled sample |
| 20 tickets, AI-drafted labels reviewed by me | Historical tickets with agent replies |
| Single message, no account data | Thread history + account data from the helpdesk (automates the channel and many 🔴 checks) |
| Streamlit page | Zendesk/Intercom sidebar calling `assist()` |
| Known issues left open | Re-check on a stronger model first |

## Model comparison (v3, 20 tickets, one model for both steps)

| | llama3.1 8B | gemma3:12b |
|---|---|---|
| Automatic checks | **20/20** | 19/20 (A20: gate 🟢 instead of 🟡, gemma's own classification) |
| Generation latency / output tokens | 78 s / 875 | 84 s / **652** |
| uk / ru (manual) | Non-words, calques | **Natural** |
| Hallucinations (manual) | Invented URL (now caught) | None |
| LLM judge (57 drafts) | 39 appropriate · 14 too general · 4 inappropriate | **48 · 9 · 0** (self-judged) |

**Choice:** gemma3:12b drafts locally (customer-facing text in the customer's language). For production: Haiku 5.5 classifies, **Sonnet 5.5 drafts**; not measured yet. Two independent calls make the split easy; it isn't wired into the UI.

## Quality evaluation

| Layer | Measures | Report |
|---|---|---|
| Automatic checks | Retrieval, channel, gate, tones, language, validity, promises, distinctness, length | [ASSISTANT_EVAL_REPORT.md](ASSISTANT_EVAL_REPORT.md) |
| **LLM judge** (offline, [`judge.py`](../evaluation/judge.py)) | Appropriate / too general / inappropriate (agentic-RAG paper rubric), grounding, tone, translation | [ASSISTANT_JUDGE_REPORT.md](ASSISTANT_JUDGE_REPORT.md) |
| Manual reading | Translation, invented facts, tone | [ASSISTANT_PROMPTS.md](ASSISTANT_PROMPTS.md) |

**Judge reliability** (spot-checked on the llama run):
- **Correct:** A18 (missed by the validator and by me), A05, A01, A14's English word.
- **Wrong:** A14 grounding (the KB supports it), A15 (correct URL), A17 (correct conditional answer).
- **Verdict:** a good pointer and relative comparison, not an absolute score.

## Known issues (found by the judge, not fixed)

These are likely model limits. gemma already avoids A18 and grounds more claims (52/57 vs 44/57); unverified on Claude.

1. **A18, llama:** told the customer to "check the admin panel… click Resend", agent-only steps paraphrased past the overlap check. Possible fix: "never instruct the customer to do agent steps" + a term list.
2. **A05, both models:** "you're eligible for a full refund" when usage is unverified. Covered by 🔴 + locked copy + flagged promise. Possible fix: conditional phrasing + `missing_info`.

## Failure handling

Reuses Task 1's client, error kinds, retries and fallback ([FAILURE_HANDLING.md](FAILURE_HANDLING.md)).

| Failure | Behaviour |
|---|---|
| Classification fails | Semantic search only if the text is English; 🟡 |
| **Embedding model down** | Metadata-linked policies + protocols only (tested); index-build error shown in the tab |
| Generation fails | Summary, gate and sources still shown; the agent writes manually |
| Validator errors after retry | Shown next to the drafts |
| Crisis | No generation call |

## Cost and caching

Two calls per ticket: classify (~1.9k in / 170 out) + draft (~1.5k in / 650–875 out; bilingual roughly doubles output).

| Setup | $ / ticket | $ / 10k |
|---|---|---|
| Haiku for both | ~$0.0009 | ~$9 |
| **Haiku classify + Sonnet draft** | ~$0.012 | ~$120 |
| Sonnet for both | ~$0.017 | ~$175 |

These are estimates before caching and thinking. 2 min saved on each of 10k tickets ≈ 330 agent-hours.

**Optimise:**
1. Reuse the Task 1 triage from routing (supported).
2. Generate on demand.
3. No `local` for English tickets.
4. Prompt cache (~850-token system prompt).
5. Cheaper model for 🟢.

| Cache | Status | Invalidation |
|---|---|---|
| KB embeddings | **Implemented**, on disk by (model, content hash); editing one article re-embeds one | Automatic |
| System prompt | Claude prompt cache | Any prompt change |
| KB excerpts | No: they differ per ticket | – |
| Triage for the channel re-run | **Implemented** | New ticket |
| Drafts across tickets | **Rejected**: must reflect the customer, channel and KB version | – |
