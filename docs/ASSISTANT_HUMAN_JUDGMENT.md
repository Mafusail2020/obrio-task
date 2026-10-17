# Reply assistant: where the agent must decide

Every draft is reviewed by a person; in the cases below the agent must not rely on the drafts at all. These are detected by rules ([`assistant/gate.py`](../assistant/gate.py)) over Task 1 facts, so a confused or manipulated model can't switch the warning off.

## UI marking

| Level | UI |
|---|---|
| 🔴 **Decision required** | Red banner with the reasons; drafts **read-only, copy and edit locked** until the agent ticks *"I checked the policy and the customer's history; I take the decision"*; policy promises flagged on the draft |
| 🔴 **Crisis** | **No AI drafts at all**; crisis protocol shown expanded |
| 🟡 **Verify** | Yellow banner naming what to check; drafts usable |
| 🟢 **Standard** | Drafts ready |

Every draft also shows:
- its sources
- its promises (in English, even for a Ukrainian reply)
- validator warnings
- "Check before sending" (`missing_info`)
- ⚠ on conditional articles ("applies only if paid via the website")

## Scenarios

| # | Scenario | Level | Why |
|---|---|---|---|
| 1 | Self-harm / crisis, any language | 🔴 no drafts | A machine-written reply can harm; the protocol requires a personal reply within 1 h, crisis resources and the team lead |
| 2 | Chargeback, bank, lawyer, regulator | 🔴 | Senior billing decides; one careless sentence can trigger the dispute; refunding after a filed chargeback would double-refund |
| 3 | Refund / unexpected charge as the **primary** intent (website or unknown channel) | 🔴 | Eligibility depends on purchase history the AI can't see; > $50 needs team lead approval. Store purchases are 🟢 (the store decides) |
| 4 | Billing channel unknown on a billing ticket | 🟡 | Website and store policies differ; drafts ask where they paid; the agent can set the channel with the dropdown → drafts regenerate |
| 5 | Advisor misconduct, suspected bot | 🔴 | Trust & Safety decides; never promise an outcome or confirm/deny a bot |
| 6 | Access, email change, GDPR deletion | 🔴 | Identity first (account takeover); 30-day legal deadline; irreversible |
| 7 | Credit restore | 🟡 | Agent limit 50 credits; more needs team lead approval |
| 8 | Angry customer, scam accusation | 🟡 | Reputation risk; tone must fit |
| 9 | Money amount mentioned | 🟡 | Verify against billing before repeating it |
| 10 | Low confidence / classification failed | 🟡 | Drafts may answer the wrong question |
| 11 | No matching KB article | 🟡 | No source: drafts may only ask questions |
| 12 | Secondary refund intent | 🟡 | The classifier sometimes invents one; check whether money is actually asked for |

**Logic:**
- Drafts are still offered except for crisis, because they save typing; the gate sets **how much to rely on them**.
- Friction scales with risk: nothing → banner → one deliberate click → no AI.
- The 🔴 acknowledgment and per-draft feedback (used / edited / rejected) are logged, to measure where agents trust the drafts.
