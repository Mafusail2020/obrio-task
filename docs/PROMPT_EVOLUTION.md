# Prompt evolution

Every prompt version is a separate, immutable file in [`prompts/`](../prompts/). Every version was evaluated on the full test set (41 synthetic tickets, labels reviewed by me) with the same model, Ollama `llama3.1` 8B. Raw results for every run are in [`evaluation/results/`](../evaluation/results/). The detailed log of each failure and fix is in [`prompts/CHANGELOG.md`](../prompts/CHANGELOG.md).

## Results

| | v1 | v2 | v3 | v4 | v5 (final) |
|---|---|---|---|---|---|
| category | 90% | 97% | 97% | 100% | **100%** |
| sub-intent | 79% | 97% | 97% | 95% | **97%** |
| goal | 76% | 97% | 97% | 97% | **97%** |
| billing channel | 88% | 81% | 100% | 100% | **100%** |
| priority | 82% | 88% | 98% | 98% | **93%** |
| needs_human | 88% | 95% | 98% | 93% | **100%** |
| required risk flags | 3/5 | 5/5 | 5/5 | 5/5 | **5/5** |
| false risk flags | 1 | 1 | 1 | 0 | **0** |
| input tokens / ticket | 342 | 1194 | 1686 | 1820 | 1944 |

v1 and v2 ran on 40 tickets under the original pipeline. v3 is shown re-run under the later pipeline (category derived in code, language detector, T41 added), so v3–v5 compare like for like. v5 is shown after the final router change.

## How it changed

**v1: minimal baseline.** Role, taxonomy as bare lists, one line per field. Written deliberately thin, to see where the model fails without guidance. It failed on safety (missed a Ukrainian crisis message), security (followed a prompt injection), and tone (sarcasm and rage → `feedback`).

**v2: definitions and rules.** A definition for every sub-intent, goal, sentiment level and flag; "classify the problem, not the tone"; a recall-biased crisis definition for any language; the ticket treated as data inside tags; product context. The biggest single jump: sub-intent 79% → 97%, all risk flags caught.

**v3: few-shot examples + tighter rules.** Billing channel only when explicit; "a refund demand is the goal, not a second intent"; sentiment describes the customer's own words; six new examples. Priority accuracy reached 98%, but the examples introduced side effects (a false legal flag, language drift).

**v4: fix the examples.** Removed the lawyer threat from the "rip-off" example and added a separate calm chargeback example; added a notifications example. False flags went to zero, but a new example pulled an accidental purchase toward `unexpected_charge`.

**v5: boundary test as a question.** "Did the customer choose to make this purchase?" separates `refund_request` from `unexpected_charge`; advertising is spam with high confidence. needs_human reached 100%.

## Before and after

v1, the whole classification instruction for refunds:
```
- billing_subscription: unexpected_charge, cancellation, refund_request, ...
```

v5:
```
- unexpected_charge: a charge the customer did not expect or authorise: trial turned into a paid
  subscription, charged after cancelling, duplicate charges, unknown charge. Use this even when they
  also ask for the money back.
- refund_request: wants money back for a purchase they knowingly made (accidental purchase, wrong
  plan, changed mind, waiting for a promised refund).
...
unexpected_charge vs refund_request: ask "did the customer choose to make this purchase?" ...
```

## What I learned

- **Definitions beat examples** for the first big gain (v1 → v2). Examples were useful for specific boundaries, but on an 8B model **every example shifts neighbouring decisions**. Each one needed a full rerun.
- **Some problems were better fixed in code than in the prompt:** a category inconsistent with its sub-intent, language detection, and cross-intent priority rules. Prompt changes kept trading one borderline ticket for another; code fixes were stable.
- **Prompt length cost:** input tokens grew from 342 to 1,944 per ticket. On Claude Haiku 5.5 that's still about $0.0002 per ticket.
- **Plateau:** from v3 on, priority and needs_human stay within 93–100%. The remaining misses are borderline tickets that flip between runs, so further prompt work on this model has diminishing returns. The next step would be measuring the same prompt on Claude.
