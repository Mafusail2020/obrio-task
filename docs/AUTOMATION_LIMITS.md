# Limits of automation

"Automation" here means acting on a ticket without a person: sending an automated reply, a self-service article, or store instructions. The classifier itself runs on every ticket; what changes is whether a human must take it.

## Tickets that should NOT be handled automatically

| Ticket type | Why not | In the router |
|---|---|---|
| **Self-harm or crisis signals**, in any language, direct or indirect | A wrong or robotic reply can cause real harm. Psychic-app users are disproportionately people in distress or emotional dependence. | Hard rule → P1, `crisis_response`, `escalate_urgent`. Triggered by keywords *or* the LLM. |
| **Chargeback, bank dispute, lawyer or regulator threats** | Direct money loss, chargeback ratios affect merchant standing, legal exposure. Needs a senior person who can resolve it before it escalates. | Hard rule → P1, `billing_senior`, `handle_dispute`. |
| **Refunds and charge disputes for web purchases** | A money decision that depends on policy, history and possible abuse. An automated "yes" costs money; an automated "no" creates chargebacks. | `review_refund` / `investigate_charge`, human. (App Store / Google Play refunds *can* be automated: the store decides, we only send instructions.) |
| **Advisor misconduct, suspected bots, off-platform payment requests** | Trust & Safety investigation; possible fraud against users; the decision affects an advisor's income. | P2, `trust_safety`, `investigate_advisor`. |
| **Account access, email change, data deletion (GDPR)** | Identity must be verified, otherwise it's an account takeover vector; GDPR has a legal deadline. | `restore_access` / `process_account_change` / `process_data_deletion`, human. |
| **Scam accusations and angry customers** | Reputation risk (these become public reviews); an automated reply to an angry customer escalates. Klarna had to bring back humans for exactly this. | Modifier: +1 priority (cap P2), human. |
| **Explicit request for a human** | Customers must always be able to reach a person (Klarna's lesson). | Guardrail `redirect_to_human`, priority unchanged. |
| **Low confidence or failed extraction** | The system doesn't know what the ticket is; acting on a guess is worse than waiting. | `needs_human`; failed extraction → P2 `review_manually`. |

What *can* be automated today: store cancellation/refund instructions, payment troubleshooting, notification settings, product questions, logging feedback, and asking for clarification on clearly vague tickets.

## Human-in-the-loop mechanism: a review queue gated by risk and confidence

Implemented in [`classifier/review_queue.py`](../classifier/review_queue.py) and the **Review queue** tab of the Streamlit app.

```
TriageResult ─► needs_human? ──no──► automated flow
                    │
                   yes
                    ▼
        review queue (sorted by priority)
        shows: ticket, AI triage, WHY a human is needed, agent note
                    │
        agent: approve ──or── correct (sub-intent / priority / next step) + note
                    │
                    ▼
        decision stored with AI-vs-human diff
                    │
                    ├─► corrected tickets become new eval cases
                    └─► approval rate per sub-intent ─► evidence to widen or narrow automation
```

How it works:
1. **Gate:** a ticket enters the queue when any hard rule, guardrail, modifier or base policy says `needs_human`. The reasons are listed explicitly ("refund is a money decision", "low classification confidence", "customer asked for a human").
2. **Context, not a blank ticket:** the agent sees the AI's classification, the English summary, extracted facts and a suggested next step. Klarna found escalations went badly when customers had to repeat themselves; the same applies to agents.
3. **One click to approve, a few clicks to correct.** Every correction is stored as `{ai, human}` per field.
4. **Feedback loop:** corrections are the best source of new test cases for the next prompt version. The share of tickets approved unchanged, per sub-intent, is the metric for graduated automation. For example, if `payment_failed` triage is approved 98% of the time over a month, that sub-intent's auto-reply can be enabled. If corrections spike, a sub-intent moves back to human review.

This keeps the AI in the role it handles well (reading, summarising, routing) and keeps humans on the decisions that cost money, touch safety, or need judgement.
