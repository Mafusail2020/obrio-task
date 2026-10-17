# Reply assistant: where the agent must decide

The assistant never sends replies; every draft is reviewed by a person. In some situations, though, the agent must **not rely on the AI drafts at all** and has to make the decision themselves. Those situations are detected by deterministic rules ([`assistant/gate.py`](../assistant/gate.py)) over the Task 1 facts, not by the LLM, so a confused or manipulated model can't switch the warning off.

## How it is marked in the interface

| Level | When | What the UI does |
|---|---|---|
| 🔴 **Decision required** | The reply depends on a decision or check the AI cannot make | Red banner listing the reasons. **Drafts are shown read-only and the copy/edit controls are locked** until the agent ticks *"I checked the policy and the customer's history; I take the decision."* Policy promises in a draft are flagged on that draft. |
| 🔴 **Crisis** | Possible self-harm or crisis | Red banner; **no AI drafts are generated at all**. The crisis protocol is shown expanded. |
| 🟡 **Verify before sending** | The drafts are usable, but a specific fact must be checked | Yellow banner listing what to check; drafts are editable and copyable. |
| 🟢 **Standard** | None of the above | Green banner; drafts ready to edit and copy. |

On every draft, the agent also sees:
- **Sources:** which KB articles it relies on.
- **Promises:** what support commits to, in English, even for a Ukrainian reply.
- Validator warnings (too long, internal wording copied, promises on a 🔴 ticket).
- A **"Check before sending"** list (`missing_info`).

Conditional articles carry a ⚠ tag, e.g. "applies only if paid via the Nebula website".

## Scenarios where human judgment is mandatory

| # | Scenario | Level | Why the agent must decide |
|---|---|---|---|
| 1 | **Self-harm or crisis signals**, any language, direct or indirect | 🔴 no drafts | A templated or machine-written reply to someone in crisis can do real harm. The protocol requires a personal reply within 1 hour, care first, crisis resources, team lead notified. The AI is excluded completely, not just checked. |
| 2 | **Chargeback, bank dispute, lawyer or regulator** mentioned | 🔴 | Money and legal exposure. Senior billing decides; a careless sentence ("we can't refund you") can trigger the dispute. If a chargeback was already filed, a separate refund would be a double refund, which the AI can't know. |
| 3 | **Refund or unexpected charge as the main request** (website or unknown channel) | 🔴 | Eligibility depends on purchase history, usage and earlier cancellations in the admin panel, which the AI cannot see. Refunds above $50 need team lead approval. Store purchases are 🟢, because Apple/Google decide and the reply only gives instructions. |
| 4 | **Billing channel unknown** on a billing ticket | 🟡 (+ 🔴 if a refund) | Website and store policies differ completely. The drafts ask where the customer paid; the agent can set the channel from the admin panel with the dropdown, which regenerates the drafts with the right policy. |
| 5 | **Advisor misconduct or suspected bot** | 🔴 | Trust & Safety investigates; the agent must not promise an outcome, confirm or deny that an advisor is a bot, or share anything about the advisor. Restoring the session's credits is allowed but must be checked. |
| 6 | **Account access, email change, data deletion (GDPR)** | 🔴 | Identity must be verified first: account takeover risk. Never confirm that an account exists before verification. GDPR deletion has a 30-day legal deadline and is irreversible. |
| 7 | **Credit restore** (missing credits, bad or slow session + credits back) | 🟡 | The agent can restore up to 50 credits; more needs team lead approval. The amount must be checked in the account. |
| 8 | **Angry customer or scam accusation** | 🟡 | Reputation risk: these become public reviews. The tone of the chosen draft must fit the situation; an over-cheerful reply escalates. |
| 9 | **A money amount is mentioned** | 🟡 | The amount in the ticket may be wrong or in another currency; verify it against billing records before repeating it in a reply. |
| 10 | **Low classification confidence, or classification failed** | 🟡 | The drafts may answer the wrong question. |
| 11 | **No matching KB article** | 🟡 | Without a source, drafts can only ask clarifying questions; any factual claim would be unsupported. |
| 12 | **Secondary refund intent** (the classifier found money as a side topic) | 🟡 | Upstream classifiers sometimes invent a secondary refund intent (seen on a slow-advisor ticket). The agent checks whether the customer actually asks for money back. |

In every scenario the drafts are still offered (except crisis): they save typing even when the decision is the agent's. The gate changes **how much the agent may rely on them**, not whether the agent sees them.

## Design logic

- **Rules over model judgment:** the gate uses Task 1's facts and the retrieved sources. A prompt injection or a model mistake in the drafts can't lower the level.
- **Friction proportional to risk:** 🟢 costs nothing, 🟡 is a banner, 🔴 needs one deliberate click, crisis removes the AI entirely.
- **The decision is recorded:** the 🔴 acknowledgment and the per-draft feedback (used as-is / edited / rejected) are logged, which makes it possible to measure later where agents trust or reject the drafts.
