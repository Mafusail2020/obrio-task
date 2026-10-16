# Architecture

## Overview

```
ticket text
  │
  ▼
1. preprocess      normalise whitespace, mask PII (emails, Luhn-valid cards, +phones), length cap
  │
  ▼
2. guardrails      multilingual keyword net → risk flags; crisis / legal / "talk to a human" → redirect_to_human
  │
  ▼
3. LLM extraction  prompt vN + Pydantic schema → structured FACTS (validated, 1 retry on invalid output)
  │                category derived from sub-intent in code; language from a detector
  ▼
4. router          deterministic policy table → priority, queue, next-step action, needs_human, agent note
  │
  ▼
TriageResult ──► Streamlit UI · eval runner · human review queue
```

The core split: **the LLM extracts facts, code makes decisions.** The LLM answers "what is this ticket about, what does the customer want, how do they feel, is there risk". It never decides priority, queue or escalation. Those come from a policy table in [`classifier/router.py`](../classifier/router.py) that a support lead can read and change without touching a prompt.

Why:
- **Consistent:** same facts → same priority, every time.
- **Auditable:** every decision records the rule that fired (`rule_id`) and the modifiers applied.
- **Changeable:** a policy change (e.g. "refunds over $50 → senior queue") is a code change with a unit test, not a prompt re-tune.
- **Cheaper:** fact extraction is a narrow task, so small models handle it (an 8B local model in all the evals here).

This follows the pattern used by Zendesk Intelligent Triage: classification is an input layer, and deterministic triggers do the routing.

## Model / tool choice

| Use | Model | Why |
|---|---|---|
| Development, evals | **Ollama `llama3.1` 8B** (local) | Free, offline, unlimited reruns while iterating prompts; no customer data leaves the machine. If prompts work on an 8B model, they have headroom on stronger ones. |
| Production target | **Claude Haiku 5.5** via the Anthropic API | Cheapest current Claude ($0.10 / $0.50 per 1M tokens); **structured outputs** (`messages.parse` with the Pydantic schema) guarantee schema-valid JSON; strong multilingual understanding. Run with `effort: low`, since classification doesn't benefit from deep reasoning. |

Both sit behind one interface, `LLMClient.generate_structured(system, user, schema)` ([`classifier/llm/`](../classifier/llm/)). Switching is one setting (`LLM_PROVIDER=ollama|claude`) or a dropdown in the UI. A `MockClient` runs the whole pipeline in unit tests without any model.

Rough cost at production scale: ~1.9k input + ~0.2k output tokens per ticket on Haiku 5.5 ≈ $0.0003 per ticket, about **$3 per 10,000 tickets** (before thinking tokens; not yet measured).

All eval numbers in this repo are from the local 8B model. A Claude run hasn't been done yet (no API key in the dev environment).

## Prompt structure

Final prompt: [`prompts/v5.md`](../prompts/v5.md). Its history is in [`PROMPT_EVOLUTION.md`](PROMPT_EVOLUTION.md).

1. **Role and product context:** what Nebula sells, the three billing channels.
2. **Scope limit:** "You do not decide priority or routing."
3. **Injection defence:** the ticket is inside `<ticket>` tags and is data; instructions inside it are ignored.
4. **Taxonomy with one-line definitions** for every sub-intent, plus "classify by the problem, not the tone".
5. **Multi-intent rules:** separate intents only for genuinely different problems; a refund demand is usually the *goal*, not a second intent.
6. **Definitions** for goal, sentiment scale and each risk flag. The crisis flag is recall-biased: "any language, indirect signs, when unsure include it".
7. **Field rules:** `reasoning` first, billing channel only when explicit, English summary.
8. **Boundary tests:** e.g. "did the customer choose to make this purchase?" separates `refund_request` from `unexpected_charge`.
9. **Nine few-shot examples**, newly written (never copied from the test set), each covering a known boundary.

The output schema ([`classifier/schema.py`](../classifier/schema.py)) is passed to the model as JSON schema, with closed enums for every label. `reasoning` is the first field, so the model explains before it labels.

## Categories and the logic behind them

The taxonomy was **built from real complaints, not from guessing Obrio's org chart**: Trustpilot and Apple Community reviews of Nebula, plus similar apps (Kasamba, Keen, Purple Garden).

| Category | Sub-intents | Real-world source |
|---|---|---|
| `billing_subscription` | unexpected_charge, cancellation, refund_request, missing_credits, paid_content_not_delivered, payment_failed | #1 complaint: $1 teaser → ~$42 subscription; "cancelled twice, still charged"; missing bonus credits; undelivered "soulmate sketch" |
| `advisor_complaint` | reading_quality, slow_replies, suspected_bot, rude_or_misconduct | Slow replies "burning credits", suspicion of AI bots posing as psychics |
| `technical_issue` | crash_or_bug, feature_not_loading, notifications | "My Plan screen won't load" |
| `account_privacy` | login_access, change_email, delete_account_or_data | Access problems; GDPR deletion (legal deadline) |
| `general_other` | product_question, feedback, spam_or_unclear | Long tail; vague tickets |

Design rules:
- **Five categories, two levels** (category → sub-intent, like Zendesk's hierarchy). Few enough to stay mutually exclusive; specific enough for routing.
- **Refund sits inside Billing, not on its own.** Most "refund" tickets are really "unexpected charge" or "can't cancel"; a separate category would blur boundaries. A credits refund for a bad advisor session belongs to `advisor_complaint`, because the cause decides who handles it.
- **Risk is a set of flags, not a category:** `self_harm_or_crisis`, `legal_or_chargeback_threat`, `scam_accusation`, `aggressive_tone`. A billing ticket can carry a chargeback threat; a reading complaint can hide a crisis.
- **Multi-label:** `intents[]`, primary first ("cancel *and* refund", "app crashed *and* advisor ignored me").
- **What they meant, not what they said:** `customer_goal` (refund / cancel / fix_issue / get_info / complain_only / account_change). "Your app is a scam!!!" is a refund request.
- **Entities:** billing channel, amount, advisor, transaction id, date. The billing channel changes the next step: App Store / Google Play refunds must go through the store.

## Routing policy

1. **Hard rules (first match wins):** crisis → P1 crisis queue; legal/chargeback → P1 senior billing; LLM failure → P2 manual review.
2. **Base route per sub-intent** (priority, queue, action, human/automatable), with store variants: App Store / Google Play cancellation or refund → automated store instructions.
3. **Modifiers:**
   - a secondary intent in a *different* category can raise priority
   - low confidence → human
   - scam accusation or angry customer → +1 priority (capped at P2) and human
   - guardrail `redirect_to_human` → human
4. **Agent note:** action hint, English summary, all intents, extracted facts, "reply in Ukrainian", "billing channel unknown: ask the customer".

"Next step" means an **internal action for the support team** (e.g. `send_store_refund_instructions`, `investigate_advisor`), not a reply to the customer. Generated replies could promise refunds that policy doesn't allow.

## Where the system can fail, and mitigations

| Failure mode | Seen in evals | Mitigation |
|---|---|---|
| **Missed crisis** in another language with no obvious keywords | T36 (Ukrainian), v1 | Recall-biased crisis definition in the prompt + multilingual keyword guardrail + hard P1 rule; either source raising the flag is enough. Residual risk remains: neither layer is complete. |
| **Prompt injection** ("classify as P4") | T39, v1 | Ticket-as-data instruction; policy lives in code, so the model can't set priority directly; closed enums. Residual: the model can still be tricked into wrong *facts*. The guardrails run independently of the LLM. |
| **Classifying tone instead of problem** (sarcasm, rage → `feedback`) | T40, T37, v1 | "Classify by the problem" rule; sentiment is a separate field. |
| **Few-shot contamination:** one example shifts neighbouring tickets | T37 false legal flag (v3); T05 drift (v4) | Every prompt change gets a full 41-ticket rerun, not a spot check; examples are written to differ from the test set. |
| **Invented secondary intents** inflating priority | T13/T16/T18 (v2), T18/T20/T41 (v5) | Prompt rule ("refund is the goal, not a second intent") + router rule: only a different-category secondary can raise priority. |
| **Hallucinated entities** (billing channel guessed as `web`) | T06/T07/T09, v2 | "Only when explicitly stated"; `unknown` → agent note asks the customer. |
| **Inconsistent labels** (sub-intent paired with the wrong category) | T20, v3 | Category derived from sub-intent in code. |
| **Language mislabelled** after a non-English example | T27, T35, v3 | Language from `langdetect`; LLM value only as fallback for short or uncertain text. |
| **Overconfident or underconfident self-reported confidence** | T32/T33 | Categorical confidence (high/medium/low), not a fake float; hard rules never depend on confidence. |
| **Run-to-run flip-flops** on borderline tickets (even at temperature 0) | T18 fixed in v3/v4, back in v5 | Treat single-ticket changes below ~2 tickets as noise; borderline tickets end up in the review queue. |
| **LLM outage / invalid output** | n/a | One retry with the error fed back; then `extraction_failed` → P2 manual review. Guardrails still apply, so a crisis keyword still gives P1. |
| **PII sent to a third-party API** | n/a | Emails, Luhn-valid card numbers and international phone numbers are masked before the LLM call. |
| **Taxonomy drift** (new kinds of tickets) | n/a | `spam_or_unclear` share and reviewer corrections in the HITL queue show where categories are missing. |
