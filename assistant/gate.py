"""Human-judgment gate: decides how much the agent may rely on AI drafts.

Rules, not the LLM, decide. Inputs are the Task 1 facts and what retrieval found.
  RED    — the agent must make the decision; drafts are shown but cannot be copied
           until the agent acknowledges. Crisis: no drafts at all.
  YELLOW — drafts are usable but specific facts must be verified.
  GREEN  — standard.
"""

from assistant.schema import Gate, Level, Source
from classifier.schema import TriageResult
from classifier.taxonomy import BillingChannel, Confidence, RiskFlag, Sentiment, SubIntent

RED_SUB_INTENTS = {
    SubIntent.RUDE_OR_MISCONDUCT: "advisor misconduct report: Trust & Safety decides, never promise an outcome",
    SubIntent.SUSPECTED_BOT: "bot accusation against an advisor: do not confirm or deny",
    SubIntent.DELETE_ACCOUNT_OR_DATA: "GDPR deletion: verify identity first, legal deadline",
    SubIntent.LOGIN_ACCESS: "account access: verify identity before revealing anything",
    SubIntent.CHANGE_EMAIL: "account change: verify identity first",
}
MONEY_DECISIONS = {SubIntent.REFUND_REQUEST, SubIntent.UNEXPECTED_CHARGE}
STORE = {BillingChannel.APP_STORE.value, BillingChannel.GOOGLE_PLAY.value}


def decide(triage: TriageResult, sources: list[Source], channel: str = "unknown") -> Gate:
    """`channel` is the billing channel used for retrieval (Task 1's, or the agent's override)."""
    red, yellow = [], []
    flags = set(triage.risk_flags)
    ext = triage.extraction

    if RiskFlag.SELF_HARM_OR_CRISIS in flags:
        return Gate(level=Level.RED, generate_drafts=False, reasons=[
            "possible self-harm or crisis: write personally, follow the crisis protocol (no AI drafts)"])
    if RiskFlag.LEGAL_OR_CHARGEBACK_THREAT in flags:
        red.append("chargeback / legal threat: senior billing decides, see chargeback procedure")

    if ext is None:
        yellow.append("automatic classification failed: drafts are based on the raw text only")
    else:
        subs = {i.sub_intent for i in ext.intents}
        red += [msg for s, msg in RED_SUB_INTENTS.items() if s in subs]
        # Only the primary intent can make this a refund decision: the classifier sometimes
        # invents a secondary refund_request (e.g. on a slow-advisor ticket, A07).
        if ext.primary.sub_intent in MONEY_DECISIONS and channel not in STORE:
            red.append("refund decision: eligibility depends on purchase history the AI cannot see; check the refund policy")
        elif subs & MONEY_DECISIONS and ext.primary.sub_intent not in MONEY_DECISIONS:
            yellow.append("secondary refund/charge intent detected: check whether the customer actually asks for money back")
        if SubIntent.MISSING_CREDITS in subs or (subs & {SubIntent.SLOW_REPLIES, SubIntent.READING_QUALITY}
                                                 and ext.customer_goal.value == "refund"):
            yellow.append("credit restore: check the amount (over 50 credits needs team lead approval)")
        if ext.confidence == Confidence.LOW:
            yellow.append("low classification confidence: make sure the drafts answer the right question")
        if ext.entities.amount:
            yellow.append(f"amount mentioned ({ext.entities.amount}): verify it against billing records")
        if RiskFlag.SCAM_ACCUSATION in flags or RiskFlag.AGGRESSIVE_TONE in flags or ext.sentiment == Sentiment.VERY_NEGATIVE:
            yellow.append("angry customer or scam accusation: check the tone before sending")

    if channel == "unknown" and any(s.condition for s in sources):
        yellow.append("billing channel unknown: channel-specific policies are conditional; confirm where the customer paid")
    if not any(s.reason == "semantic match" or s.reason.startswith("policy") for s in sources):
        yellow.append("no matching KB article: drafts can only ask clarifying questions")

    if red:
        return Gate(level=Level.RED, reasons=red + yellow)
    return Gate(level=Level.YELLOW if yellow else Level.GREEN, reasons=yellow)
