# Prompt evolution (Task 1)

Immutable versions in [`prompts/`](../prompts/); every failure and fix in [`prompts/CHANGELOG.md`](../prompts/CHANGELOG.md). Each version was run on the full test set (41 tickets, labels reviewed by me) with llama3.1 8B.

| | v1 | v2 | v3 | v4 | v5 (final) |
|---|---|---|---|---|---|
| category | 90% | 97% | 97% | 100% | **100%** |
| sub-intent | 79% | 97% | 97% | 95% | **97%** |
| goal | 76% | 97% | 97% | 97% | **97%** |
| billing channel | 88% | 81% | 100% | 100% | **100%** |
| priority | 82% | 88% | 98% | 98% | **93%** |
| needs_human | 88% | 95% | 98% | 93% | **100%** |
| required flags | 3/5 | 5/5 | 5/5 | 5/5 | **5/5** |
| false flags | 1 | 1 | 1 | 0 | **0** |
| input tokens | 342 | 1194 | 1686 | 1820 | 1944 |

v3 is shown re-run on the later pipeline (category in code, language detector), so v3–v5 compare like for like.

- **v1, minimal baseline:** taxonomy as bare lists. It missed a Ukrainian crisis message, followed a prompt injection, and read sarcasm and rage as `feedback`.
- **v2, definitions:** a definition for every label; "classify the problem, not the tone"; a recall-biased crisis rule; ticket-as-data. The biggest jump (sub-intent 79% → 97%).
- **v3, few-shot + tighter rules:** channel only when explicit; "a refund is the goal, not a second intent". Priority reached 98%, but the examples caused a false legal flag and language drift.
- **v4, fixed the examples:** false flags went to 0, but a new example pulled an accidental purchase toward `unexpected_charge`.
- **v5, boundary as a question:** "did the customer choose this purchase?" needs_human reached 100%.

Before → after, for refunds:
```
v1: - billing_subscription: unexpected_charge, cancellation, refund_request, ...
v5: - unexpected_charge: a charge the customer did not expect or authorise (trial converted, charged
      after cancelling, duplicate) ... even when they also ask for the money back.
    - refund_request: money back for a purchase they knowingly made (accidental, wrong plan ...)
    unexpected_charge vs refund_request: ask "did the customer choose to make this purchase?"
```

**Lessons:**
- Definitions beat examples for the first big gain.
- On 8B, every example shifts neighbouring decisions.
- Consistency, language and priority rules were more stable fixed in code than in the prompt.
- From v3 on, results plateau at 93–100%, with borderline tickets flipping between runs.
