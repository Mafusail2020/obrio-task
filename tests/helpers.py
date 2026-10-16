from classifier.schema import Entities, Extraction, Intent
from classifier.taxonomy import (
    SUBINTENT_CATEGORY,
    BillingChannel,
    Confidence,
    CustomerGoal,
    RiskFlag,
    Sentiment,
    SubIntent,
)


def make_extraction(*subs: str, goal: str = "fix_issue", sentiment: str = "neutral",
                    flags: tuple[str, ...] = (), channel: str = "unknown",
                    confidence: str = "high", language: str = "en") -> Extraction:
    return Extraction(
        reasoning="test",
        intents=[Intent(category=SUBINTENT_CATEGORY[SubIntent(s)], sub_intent=SubIntent(s)) for s in subs],
        customer_goal=CustomerGoal(goal),
        sentiment=Sentiment(sentiment),
        risk_flags=[RiskFlag(f) for f in flags],
        language=language,
        entities=Entities(billing_channel=BillingChannel(channel), amount=None, advisor_name=None,
                          transaction_id=None, date_mentioned=None),
        confidence=Confidence(confidence),
        summary="test summary",
    )
