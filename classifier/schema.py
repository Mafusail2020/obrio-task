"""Data contracts.

`Extraction` is the only thing the LLM produces: facts about the ticket.
`RoutingDecision` is produced by deterministic code (router.py).
"""

from typing import Optional

from pydantic import BaseModel, Field

from classifier.taxonomy import (
    SUBINTENT_CATEGORY,
    Action,
    BillingChannel,
    Category,
    Confidence,
    CustomerGoal,
    Priority,
    Queue,
    RiskFlag,
    Sentiment,
    SubIntent,
)


# ---------- LLM output ----------

class Intent(BaseModel):
    category: Category
    sub_intent: SubIntent


class Entities(BaseModel):
    billing_channel: BillingChannel = Field(
        description="Where the user paid: app_store, google_play, web, or unknown if not stated."
    )
    amount: Optional[str] = Field(description="Money amount mentioned, with currency, e.g. '$42'. null if none.")
    advisor_name: Optional[str] = Field(description="Name of the advisor/psychic mentioned. null if none.")
    transaction_id: Optional[str] = Field(description="Order or transaction id mentioned. null if none.")
    date_mentioned: Optional[str] = Field(description="Date or time reference for the issue, as written. null if none.")


class Extraction(BaseModel):
    reasoning: str = Field(description="One or two short sentences: what the customer wants and why these labels.")
    intents: list[Intent] = Field(description="All intents in the ticket, most important first. At least one.")
    customer_goal: CustomerGoal
    sentiment: Sentiment
    risk_flags: list[RiskFlag] = Field(description="Every risk flag that applies. Empty list if none.")
    language: str = Field(description="ISO 639-1 code of the ticket language, e.g. 'en', 'uk', 'es'.")
    entities: Entities
    confidence: Confidence = Field(description="How sure you are about the primary intent.")
    summary: str = Field(description="One-sentence summary in English for the support agent.")

    @property
    def primary(self) -> Intent:
        return self.intents[0]

    def consistency_errors(self) -> list[str]:
        """Checks that the JSON schema cannot express and code cannot repair."""
        return [] if self.intents else ["intents must contain at least one item"]

    def repair_categories(self) -> list[str]:
        """Category is fully determined by sub-intent, so a mismatch is fixed in code
        (the sub-intent is the more specific label) instead of failing the ticket."""
        warnings = []
        for i, intent in enumerate(self.intents):
            expected = SUBINTENT_CATEGORY[intent.sub_intent]
            if intent.category != expected:
                warnings.append(f"intents[{i}]: category {intent.category.value} -> {expected.value} "
                                f"(derived from sub_intent {intent.sub_intent.value})")
                intent.category = expected
        return warnings


# ---------- deterministic layers ----------

class GuardrailResult(BaseModel):
    flags: list[RiskFlag] = Field(default_factory=list)
    matches: dict[str, list[str]] = Field(default_factory=dict)  # flag -> matched phrases
    human_requested: bool = False
    redirect_to_human: bool = False
    reason: Optional[str] = None


class RoutingDecision(BaseModel):
    priority: Priority
    queue: Queue
    action: Action
    needs_human: bool
    human_reasons: list[str] = Field(default_factory=list)
    rule_id: str
    modifiers: list[str] = Field(default_factory=list)
    agent_note: str


class RunMeta(BaseModel):
    provider: str
    model: str
    prompt_version: str
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    attempts: int = 0
    language_source: Optional[str] = None  # "detector" or "llm"
    warnings: list[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    ticket_text: str  # after preprocessing (PII masked)
    truncated: bool = False
    pii_masked: list[str] = Field(default_factory=list)
    guardrails: GuardrailResult
    extraction: Optional[Extraction] = None
    risk_flags: list[RiskFlag] = Field(default_factory=list)  # union of guardrail + LLM flags
    routing: RoutingDecision
    error: Optional[str] = None
    meta: RunMeta
