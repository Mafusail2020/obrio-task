"""Deterministic routing policy: facts in, decision out.

The LLM never decides priority, queue or escalation. This file is the policy
table a support lead can read and change without touching any prompt.

Order of evaluation:
  1. Hard rules (first match wins): crisis, legal/chargeback, extraction failure.
  2. Base route of the primary intent (with billing-channel variants).
  3. Modifiers: secondary intents, low confidence, scam accusation, aggressive tone.
"""

from dataclasses import dataclass
from typing import Optional

from classifier.schema import Extraction, GuardrailResult, Intent, RoutingDecision
from classifier.taxonomy import (
    Action,
    BillingChannel,
    Confidence,
    Priority,
    Queue,
    RiskFlag,
    Sentiment,
    SubIntent,
)

STORE_CHANNELS = (BillingChannel.APP_STORE, BillingChannel.GOOGLE_PLAY)


@dataclass(frozen=True)
class Route:
    priority: Priority
    queue: Queue
    action: Action
    needs_human: bool
    human_reason: Optional[str] = None


H = True   # human must handle
A = False  # safe to automate

# Base policy per sub-intent. `needs_human=False` means the ticket could be
# answered by an automated flow (self-service article, store instructions).
BASE_ROUTES: dict[SubIntent, Route] = {
    SubIntent.UNEXPECTED_CHARGE: Route(Priority.P2, Queue.BILLING, Action.INVESTIGATE_CHARGE, H, "charge must be checked in billing system"),
    SubIntent.CANCELLATION: Route(Priority.P2, Queue.BILLING, Action.PROCESS_CANCELLATION, H, "web/unknown subscription must be cancelled by an agent"),
    SubIntent.REFUND_REQUEST: Route(Priority.P2, Queue.BILLING, Action.REVIEW_REFUND, H, "refund is a money decision"),
    SubIntent.MISSING_CREDITS: Route(Priority.P3, Queue.BILLING, Action.RESTORE_CREDITS, H, "credit balance must be checked"),
    SubIntent.PAID_CONTENT_NOT_DELIVERED: Route(Priority.P3, Queue.BILLING, Action.RESEND_CONTENT, H, "order must be checked"),
    SubIntent.PAYMENT_FAILED: Route(Priority.P3, Queue.BILLING, Action.SEND_PAYMENT_HELP, A),
    SubIntent.READING_QUALITY: Route(Priority.P3, Queue.ADVISOR_QUALITY, Action.REVIEW_ADVISOR_SESSION, H, "session review and possible credit refund"),
    SubIntent.SLOW_REPLIES: Route(Priority.P3, Queue.ADVISOR_QUALITY, Action.REVIEW_ADVISOR_SESSION, H, "session review and possible credit refund"),
    SubIntent.SUSPECTED_BOT: Route(Priority.P2, Queue.TRUST_SAFETY, Action.INVESTIGATE_ADVISOR, H, "advisor integrity investigation"),
    SubIntent.RUDE_OR_MISCONDUCT: Route(Priority.P2, Queue.TRUST_SAFETY, Action.INVESTIGATE_ADVISOR, H, "advisor misconduct investigation"),
    SubIntent.CRASH_OR_BUG: Route(Priority.P3, Queue.TECH_SUPPORT, Action.INVESTIGATE_BUG, H, "bug needs reproduction"),
    SubIntent.FEATURE_NOT_LOADING: Route(Priority.P3, Queue.TECH_SUPPORT, Action.INVESTIGATE_BUG, H, "bug needs reproduction"),
    SubIntent.NOTIFICATIONS: Route(Priority.P4, Queue.TECH_SUPPORT, Action.SEND_SELF_SERVICE_ARTICLE, A),
    SubIntent.LOGIN_ACCESS: Route(Priority.P2, Queue.ACCOUNT_PRIVACY, Action.RESTORE_ACCESS, H, "identity must be verified"),
    SubIntent.CHANGE_EMAIL: Route(Priority.P4, Queue.ACCOUNT_PRIVACY, Action.PROCESS_ACCOUNT_CHANGE, H, "identity must be verified"),
    SubIntent.DELETE_ACCOUNT_OR_DATA: Route(Priority.P2, Queue.ACCOUNT_PRIVACY, Action.PROCESS_DATA_DELETION, H, "GDPR request with legal deadline"),
    SubIntent.PRODUCT_QUESTION: Route(Priority.P4, Queue.GENERAL, Action.SEND_SELF_SERVICE_ARTICLE, A),
    SubIntent.FEEDBACK: Route(Priority.P4, Queue.GENERAL, Action.LOG_FEEDBACK, A),
    SubIntent.SPAM_OR_UNCLEAR: Route(Priority.P4, Queue.GENERAL, Action.REQUEST_MORE_INFO, A),
}

# App Store / Google Play purchases are cancelled and refunded by the store,
# so the right next step is instructions, not an agent action.
STORE_VARIANTS: dict[SubIntent, Route] = {
    SubIntent.CANCELLATION: Route(Priority.P3, Queue.BILLING, Action.SEND_STORE_CANCEL_INSTRUCTIONS, A),
    SubIntent.REFUND_REQUEST: Route(Priority.P3, Queue.BILLING, Action.SEND_STORE_REFUND_INSTRUCTIONS, A),
}

ACTION_HINTS: dict[Action, str] = {
    Action.ESCALATE_URGENT: "Respond immediately with crisis resources; do not send automated replies.",
    Action.HANDLE_DISPUTE: "Senior billing agent: review charges and resolve before the chargeback/legal step.",
    Action.INVESTIGATE_CHARGE: "Check the charge history; explain or refund per policy.",
    Action.PROCESS_CANCELLATION: "Cancel the subscription in our billing system and confirm to the user.",
    Action.SEND_STORE_CANCEL_INSTRUCTIONS: "Send instructions to cancel via the app store subscription settings.",
    Action.REVIEW_REFUND: "Check eligibility and decide on the refund per policy.",
    Action.SEND_STORE_REFUND_INSTRUCTIONS: "Send instructions to request the refund from the app store.",
    Action.RESTORE_CREDITS: "Check credit balance and bonus history; restore missing credits.",
    Action.RESEND_CONTENT: "Check the order and deliver the purchased content.",
    Action.SEND_PAYMENT_HELP: "Send the payment troubleshooting article.",
    Action.REVIEW_ADVISOR_SESSION: "Review the chat session; decide on a credit refund.",
    Action.INVESTIGATE_ADVISOR: "Trust & Safety: review the advisor's sessions and account.",
    Action.INVESTIGATE_BUG: "Collect device/app version, reproduce, file a bug.",
    Action.SEND_SELF_SERVICE_ARTICLE: "Send the matching help-center article.",
    Action.RESTORE_ACCESS: "Verify identity and restore account access.",
    Action.PROCESS_ACCOUNT_CHANGE: "Verify identity and apply the account change.",
    Action.PROCESS_DATA_DELETION: "Verify identity and start the GDPR deletion flow (30-day deadline).",
    Action.LOG_FEEDBACK: "Thank the user and log the feedback for the product team.",
    Action.REQUEST_MORE_INFO: "Ask the user to clarify their request.",
    Action.REVIEW_MANUALLY: "Automatic classification failed; read and triage manually.",
}


def base_route(intent: Intent, channel: BillingChannel) -> tuple[Route, str]:
    if channel in STORE_CHANNELS and intent.sub_intent in STORE_VARIANTS:
        return STORE_VARIANTS[intent.sub_intent], f"base:{intent.sub_intent.value}:store"
    return BASE_ROUTES[intent.sub_intent], f"base:{intent.sub_intent.value}"


def route(extraction: Optional[Extraction], guardrails: GuardrailResult,
          risk_flags: list[RiskFlag]) -> RoutingDecision:
    flags = set(risk_flags)
    reasons: list[str] = []
    modifiers: list[str] = []

    # 1. Hard rules
    if RiskFlag.SELF_HARM_OR_CRISIS in flags:
        r = Route(Priority.P1, Queue.CRISIS_RESPONSE, Action.ESCALATE_URGENT, H)
        rule_id = "hard:crisis"
        reasons.append("possible self-harm or crisis")
    elif RiskFlag.LEGAL_OR_CHARGEBACK_THREAT in flags:
        r = Route(Priority.P1, Queue.BILLING_SENIOR, Action.HANDLE_DISPUTE, H)
        rule_id = "hard:legal_or_chargeback"
        reasons.append("legal or chargeback threat")
    elif extraction is None:
        r = Route(Priority.P2, Queue.GENERAL, Action.REVIEW_MANUALLY, H)
        rule_id = "hard:extraction_failed"
        reasons.append("LLM extraction failed")
    else:
        r, rule_id = base_route(extraction.primary, extraction.entities.billing_channel)
        if r.needs_human and r.human_reason:
            reasons.append(r.human_reason)

    if guardrails.redirect_to_human:
        reasons.append(f"guardrail redirect_to_human ({guardrails.reason})")

    priority, needs_human = r.priority, r.needs_human or guardrails.redirect_to_human

    # 3. Modifiers (only meaningful when we have an extraction)
    if extraction is not None:
        channel = extraction.entities.billing_channel
        primary_category = extraction.primary.category
        for intent in extraction.intents[1:]:
            sec, _ = base_route(intent, channel)
            # Only a genuinely different topic may raise priority. Same-category
            # secondaries are usually the goal restated as an intent (e.g. a bad
            # session + "refund my credits"), which small models over-produce.
            if intent.category != primary_category and sec.priority.rank < priority.rank:
                priority = sec.priority
                modifiers.append(f"secondary:{intent.sub_intent.value}:priority->{priority.value}")
            if sec.needs_human and not needs_human:
                needs_human = True
                reasons.append(f"secondary intent {intent.sub_intent.value}: {sec.human_reason}")

        if extraction.confidence == Confidence.LOW:
            needs_human = True
            reasons.append("low classification confidence")
            modifiers.append("low_confidence")

        if RiskFlag.SCAM_ACCUSATION in flags:
            priority = priority.bump(ceiling=Priority.P2)
            needs_human = True
            reasons.append("scam accusation (reputation risk)")
            modifiers.append(f"scam_accusation:priority->{priority.value}")

        if RiskFlag.AGGRESSIVE_TONE in flags or extraction.sentiment == Sentiment.VERY_NEGATIVE:
            priority = priority.bump(ceiling=Priority.P2)
            needs_human = True
            reasons.append("angry customer: automated reply may escalate")
            modifiers.append(f"angry:priority->{priority.value}")

    return RoutingDecision(
        priority=priority,
        queue=r.queue,
        action=r.action,
        needs_human=needs_human,
        human_reasons=list(dict.fromkeys(reasons)) if needs_human else [],
        rule_id=rule_id,
        modifiers=modifiers,
        agent_note=build_agent_note(r.action, extraction, guardrails),
    )


def build_agent_note(action: Action, extraction: Optional[Extraction], guardrails: GuardrailResult) -> str:
    lines = [ACTION_HINTS[action]]
    if extraction is not None:
        lines.append(f"Summary: {extraction.summary}")
        intents = [f"{i.category.value}/{i.sub_intent.value}" for i in extraction.intents]
        lines.append(f"Primary: {intents[0]}" + (f"; also: {', '.join(intents[1:])}" if len(intents) > 1 else ""))
        e = extraction.entities
        facts = [f"goal={extraction.customer_goal.value}", f"channel={e.billing_channel.value}"]
        facts += [f"{k}={v}" for k, v in (("amount", e.amount), ("advisor", e.advisor_name),
                                          ("txn", e.transaction_id), ("date", e.date_mentioned)) if v]
        lines.append("Facts: " + ", ".join(facts))
        if extraction.language != "en":
            lines.append(f"Language: {extraction.language}, reply in the customer's language.")
        billing_subs = (SubIntent.CANCELLATION, SubIntent.REFUND_REQUEST, SubIntent.UNEXPECTED_CHARGE)
        if e.billing_channel == BillingChannel.UNKNOWN and any(i.sub_intent in billing_subs for i in extraction.intents):
            lines.append("Billing channel unknown: ask whether they paid via App Store, Google Play or the website.")
    if guardrails.matches:
        lines.append("Keyword matches: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in guardrails.matches.items()))
    return "\n".join(lines)
