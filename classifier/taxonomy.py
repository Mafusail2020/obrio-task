"""Closed vocabularies shared by the LLM schema, the router and the UI.

The LLM may only answer with values from these enums. Everything that is
business policy (priority, queue, action) is decided in router.py, not here.
"""

from enum import Enum


class Category(str, Enum):
    BILLING_SUBSCRIPTION = "billing_subscription"
    ADVISOR_COMPLAINT = "advisor_complaint"
    TECHNICAL_ISSUE = "technical_issue"
    ACCOUNT_PRIVACY = "account_privacy"
    GENERAL_OTHER = "general_other"


class SubIntent(str, Enum):
    # billing_subscription
    UNEXPECTED_CHARGE = "unexpected_charge"
    CANCELLATION = "cancellation"
    REFUND_REQUEST = "refund_request"
    MISSING_CREDITS = "missing_credits"
    PAID_CONTENT_NOT_DELIVERED = "paid_content_not_delivered"
    PAYMENT_FAILED = "payment_failed"
    # advisor_complaint
    READING_QUALITY = "reading_quality"
    SLOW_REPLIES = "slow_replies"
    SUSPECTED_BOT = "suspected_bot"
    RUDE_OR_MISCONDUCT = "rude_or_misconduct"
    # technical_issue
    CRASH_OR_BUG = "crash_or_bug"
    FEATURE_NOT_LOADING = "feature_not_loading"
    NOTIFICATIONS = "notifications"
    # account_privacy
    LOGIN_ACCESS = "login_access"
    CHANGE_EMAIL = "change_email"
    DELETE_ACCOUNT_OR_DATA = "delete_account_or_data"
    # general_other
    PRODUCT_QUESTION = "product_question"
    FEEDBACK = "feedback"
    SPAM_OR_UNCLEAR = "spam_or_unclear"


CATEGORY_SUBINTENTS: dict[Category, tuple[SubIntent, ...]] = {
    Category.BILLING_SUBSCRIPTION: (
        SubIntent.UNEXPECTED_CHARGE,
        SubIntent.CANCELLATION,
        SubIntent.REFUND_REQUEST,
        SubIntent.MISSING_CREDITS,
        SubIntent.PAID_CONTENT_NOT_DELIVERED,
        SubIntent.PAYMENT_FAILED,
    ),
    Category.ADVISOR_COMPLAINT: (
        SubIntent.READING_QUALITY,
        SubIntent.SLOW_REPLIES,
        SubIntent.SUSPECTED_BOT,
        SubIntent.RUDE_OR_MISCONDUCT,
    ),
    Category.TECHNICAL_ISSUE: (
        SubIntent.CRASH_OR_BUG,
        SubIntent.FEATURE_NOT_LOADING,
        SubIntent.NOTIFICATIONS,
    ),
    Category.ACCOUNT_PRIVACY: (
        SubIntent.LOGIN_ACCESS,
        SubIntent.CHANGE_EMAIL,
        SubIntent.DELETE_ACCOUNT_OR_DATA,
    ),
    Category.GENERAL_OTHER: (
        SubIntent.PRODUCT_QUESTION,
        SubIntent.FEEDBACK,
        SubIntent.SPAM_OR_UNCLEAR,
    ),
}

SUBINTENT_CATEGORY: dict[SubIntent, Category] = {
    sub: cat for cat, subs in CATEGORY_SUBINTENTS.items() for sub in subs
}


class CustomerGoal(str, Enum):
    REFUND = "refund"
    CANCEL = "cancel"
    FIX_ISSUE = "fix_issue"
    GET_INFO = "get_info"
    COMPLAIN_ONLY = "complain_only"
    ACCOUNT_CHANGE = "account_change"


class Sentiment(str, Enum):
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


class RiskFlag(str, Enum):
    SELF_HARM_OR_CRISIS = "self_harm_or_crisis"
    LEGAL_OR_CHARGEBACK_THREAT = "legal_or_chargeback_threat"
    SCAM_ACCUSATION = "scam_accusation"
    AGGRESSIVE_TONE = "aggressive_tone"


class BillingChannel(str, Enum):
    APP_STORE = "app_store"
    GOOGLE_PLAY = "google_play"
    WEB = "web"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Priority(str, Enum):
    P1 = "P1"  # urgent: safety, legal, chargeback
    P2 = "P2"  # high: money or access at stake, angry customer
    P3 = "P3"  # normal
    P4 = "P4"  # low: questions, feedback

    @property
    def rank(self) -> int:
        return int(self.value[1])

    def bump(self, ceiling: "Priority") -> "Priority":
        """Raise priority by one level, but never above `ceiling`."""
        target = max(self.rank - 1, ceiling.rank)
        return Priority(f"P{min(target, self.rank)}")


def highest(*priorities: Priority) -> Priority:
    return min(priorities, key=lambda p: p.rank)


class Queue(str, Enum):
    CRISIS_RESPONSE = "crisis_response"
    BILLING_SENIOR = "billing_senior"
    BILLING = "billing"
    TRUST_SAFETY = "trust_safety"
    ADVISOR_QUALITY = "advisor_quality"
    TECH_SUPPORT = "tech_support"
    ACCOUNT_PRIVACY = "account_privacy"
    GENERAL = "general"


class Action(str, Enum):
    ESCALATE_URGENT = "escalate_urgent"
    HANDLE_DISPUTE = "handle_dispute"
    INVESTIGATE_CHARGE = "investigate_charge"
    PROCESS_CANCELLATION = "process_cancellation"
    SEND_STORE_CANCEL_INSTRUCTIONS = "send_store_cancel_instructions"
    REVIEW_REFUND = "review_refund"
    SEND_STORE_REFUND_INSTRUCTIONS = "send_store_refund_instructions"
    RESTORE_CREDITS = "restore_credits"
    RESEND_CONTENT = "resend_content"
    SEND_PAYMENT_HELP = "send_payment_help"
    REVIEW_ADVISOR_SESSION = "review_advisor_session"
    INVESTIGATE_ADVISOR = "investigate_advisor"
    INVESTIGATE_BUG = "investigate_bug"
    SEND_SELF_SERVICE_ARTICLE = "send_self_service_article"
    RESTORE_ACCESS = "restore_access"
    PROCESS_ACCOUNT_CHANGE = "process_account_change"
    PROCESS_DATA_DELETION = "process_data_deletion"
    LOG_FEEDBACK = "log_feedback"
    REQUEST_MORE_INFO = "request_more_info"
    REVIEW_MANUALLY = "review_manually"
