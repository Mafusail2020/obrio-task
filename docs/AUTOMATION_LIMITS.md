# Limits of automation (Task 1)

"Automated" means acted on without a person: an auto-reply, an article, or store instructions. Every ticket is still classified.

## Do not automate

| Ticket type | Why | Router |
|---|---|---|
| Self-harm / crisis, any language | A robotic reply can cause harm; psychic-app users are often in distress | P1 crisis queue (keywords *or* LLM) |
| Chargeback, bank, lawyer, regulator | Money loss, merchant standing, legal exposure | P1 senior billing |
| Refunds and charge disputes, **website purchases** | Money decision depending on history and possible abuse; a wrong "yes" costs money, a wrong "no" causes chargebacks | Human (store purchases: automated instructions, since the store decides) |
| Advisor misconduct, bots, off-platform payment requests | Trust & Safety investigation; affects advisor income | P2 T&S |
| Account access, email change, GDPR deletion | Identity verification (account takeover risk); legal deadline | Human |
| Scam accusations, angry customers | Reputation risk; auto-replies escalate (Klarna brought humans back for this) | +1 priority (cap P2), human |
| Customer asks for a human | They must always reach one | `redirect_to_human`, priority unchanged |
| Low confidence or failed extraction | Acting on a guess is worse than waiting | Human; failure → P2 manual review |

Safe to automate: store cancellation/refund instructions, payment help, notification settings, product questions, feedback, clarification on vague tickets.

## Human-in-the-loop: a review queue gated by risk and confidence

[`classifier/review_queue.py`](../classifier/review_queue.py) + the **Review queue** tab.

1. **Gate:** any rule saying `needs_human` sends the ticket to the queue, sorted by priority, with explicit reasons ("refund is a money decision").
2. **Context:** the agent sees the AI triage, summary, facts and suggested step, so they don't start from scratch (Klarna's lesson).
3. **Approve or correct** sub-intent, priority and next step; every correction is stored as `{ai, human}`.
4. **Feedback loop:** corrections become new test cases. The approval rate per sub-intent decides where to widen or narrow automation: e.g. enable the `payment_failed` auto-reply after a month of ~98% approvals, and roll back if corrections spike.
