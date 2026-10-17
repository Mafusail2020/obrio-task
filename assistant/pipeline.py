"""assist(ticket): Task 1 triage -> retrieval -> gate -> drafts -> validation."""

from typing import Optional

from assistant import gate as gate_rules
from assistant.embeddings import VectorIndex
from assistant.generator import generate
from assistant.retrieval import RetrievalConfig, retrieve
from assistant.schema import AssistMeta, AssistResult, DraftSet
from assistant.validator import validate
from classifier.llm.base import LLMClient, LLMError
from classifier.pipeline import classify
from classifier.schema import TriageResult

MAX_ATTEMPTS = 2
NON_COMMITMENTS = {"", "none", "n/a", "na", "-", "no", "nothing"}


def normalize(drafts: DraftSet, ticket_language: str, english_summary: Optional[str] = None) -> DraftSet:
    """Deterministic clean-up of model output.

    - English tickets: `local` is the English text. Models asked for a "local"
      version of an English reply translated it into Spanish (prompt v1), so
      the field is filled in code instead of trusting the model. The same
      happened to `summary_local` (v2), so it gets the Task 1 English summary.
    - "none"-style placeholders are removed from `commitments`.
    """
    if ticket_language == "en" and english_summary:
        drafts.summary_local = english_summary
    for d in drafts.drafts:
        if ticket_language == "en":
            d.local = d.english
        d.commitments = [c for c in d.commitments if c.strip().lower().rstrip(".") not in NON_COMMITMENTS]
    return drafts


def assist(text: str, client: LLMClient, index: VectorIndex, prompt_version: str = "latest",
           classifier_prompt: str = "latest", channel_override: Optional[str] = None,
           triage: Optional[TriageResult] = None, retrieval_cfg: RetrievalConfig = RetrievalConfig()) -> AssistResult:
    """`triage` can be passed in to skip re-classifying (e.g. when the agent only changes the channel)."""
    triage = triage or classify(text, client, prompt_version=classifier_prompt)
    ext = triage.extraction
    channel = channel_override or (ext.entities.billing_channel.value if ext else "unknown")
    meta = AssistMeta(provider=client.provider, model=client.model, embedder=index.embedder.model,
                      channel=channel, channel_overridden=channel_override is not None)

    sources, meta.retrieval_query = retrieve(triage.ticket_text, triage, index, channel, retrieval_cfg)
    gate = gate_rules.decide(triage, sources, channel)
    result = AssistResult(triage=triage, gate=gate, sources=sources, meta=meta)
    if not gate.generate_drafts:
        return result

    ticket_language = ext.language if ext else "en"
    feedback, latency, tok_in, tok_out = "", 0.0, 0, 0
    drafts: Optional[DraftSet] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        meta.attempts = attempt
        try:
            response, meta.prompt_version = generate(client, triage.ticket_text, triage, sources, channel,
                                                     prompt_version, feedback)
        except LLMError as e:
            result.error = f"Draft generation failed: {e}"
            if e.kind == "fatal":
                break
            feedback = str(e) if e.kind == "invalid_output" else ""
            continue
        latency += response.latency_ms
        tok_in += response.input_tokens or 0
        tok_out += response.output_tokens or 0
        drafts = normalize(response.parsed, ticket_language, ext.summary if ext else None)
        result.error = None
        issues = validate(drafts, sources, ticket_language, channel, gate,
                          frozenset(a.id for a in index.articles))
        result.drafts, result.issues = drafts, issues
        errors = [i for i in issues if i.severity == "error"]
        if not errors:
            break
        feedback = "\n".join(f"- {(i.tone.value + ': ') if i.tone else ''}{i.message}" for i in errors)

    meta.latency_ms = round(latency) if latency else None
    meta.input_tokens, meta.output_tokens = tok_in or None, tok_out or None
    return result
