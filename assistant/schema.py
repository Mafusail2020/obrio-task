from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from classifier.schema import TriageResult


class Tone(str, Enum):
    FORMAL = "formal"
    EMPATHETIC = "empathetic"
    SHORT = "short"


# ---------- LLM output ----------

class Draft(BaseModel):
    tone: Tone
    english: str = Field(description="The reply in English.")
    local: str = Field(description="The same reply in the customer's language (identical to english for English tickets).")
    source_ids: list[str] = Field(description="Ids of the KB articles this reply relies on.")
    commitments: list[str] = Field(
        description="In English: every promise the reply makes (refund, credits, timeline, action). Empty if none.")


class DraftSet(BaseModel):
    reasoning: str = Field(description="Briefly: what the customer needs and which KB facts apply.")
    summary_local: str = Field(description="One-sentence summary of the ticket in the customer's language.")
    drafts: list[Draft] = Field(description="Exactly three drafts: formal, empathetic, short.")
    missing_info: list[str] = Field(description="Facts the agent must still check or ask for, in English.")


# ---------- deterministic layers ----------

class Source(BaseModel):
    id: str
    title: str
    type: str
    audience: str
    url: str
    channels: list[str]
    condition: Optional[str] = None  # set when a channel-specific article is shown while the channel is unknown
    reason: str                      # why it was retrieved
    score: Optional[float] = None
    body: str


class Level(str, Enum):
    RED = "red"        # agent must decide; copy disabled until acknowledged
    YELLOW = "yellow"  # verify before sending
    GREEN = "green"    # standard


class Gate(BaseModel):
    level: Level
    reasons: list[str] = Field(default_factory=list)
    generate_drafts: bool = True  # False for crisis tickets


class Issue(BaseModel):
    severity: str  # "error" (triggers a retry) | "warning" (shown to the agent)
    tone: Optional[Tone] = None
    message: str


class AssistMeta(BaseModel):
    provider: str
    model: str
    prompt_version: Optional[str] = None
    embedder: str
    channel: str = "unknown"            # billing channel used for retrieval
    channel_overridden: bool = False    # set by the agent in the UI
    retrieval_query: Optional[str] = None
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    attempts: int = 0


class AssistResult(BaseModel):
    triage: TriageResult
    gate: Gate
    sources: list[Source]
    drafts: Optional[DraftSet] = None
    issues: list[Issue] = Field(default_factory=list)
    error: Optional[str] = None
    meta: AssistMeta
