"""Two-stage retrieval: deterministic metadata links first, then semantic search.

1. Linked: policy articles tagged with the ticket's sub-intents, plus fixed
   protocols for risk flags (crisis, chargeback). Policy must never depend on
   embedding luck.
2. Semantic: embeddings over all articles. The query is built from the Task 1
   ENGLISH summary + intents + goal + channel. Non-English ticket text is never
   embedded: the KB is English, and the summary is already an English
   restatement of the problem.

Channel rules: with a known billing channel, articles for other channels are
dropped. With an unknown channel, channel-specific articles are kept but
tagged with a condition ("applies only if paid via the Nebula website"), so
neither the agent nor the generator treats them as fact.
"""

from dataclasses import dataclass
from typing import Optional

from assistant.embeddings import VectorIndex
from assistant.kb import Article
from assistant.schema import Source
from classifier.schema import TriageResult
from classifier.taxonomy import RiskFlag

FLAG_ARTICLES = {
    RiskFlag.SELF_HARM_OR_CRISIS: "sop-crisis-protocol",
    RiskFlag.LEGAL_OR_CHARGEBACK_THREAT: "sop-chargeback-handling",
}


@dataclass
class RetrievalConfig:
    k: int = 3
    threshold: float = 0.60  # min cosine similarity (qwen3-embedding); calibrated on data/assistant_test.json
    max_linked: int = 3


def build_query(ticket_text: str, triage: TriageResult) -> Optional[str]:
    """English-only retrieval query, or None if there is nothing English to search with."""
    ext = triage.extraction
    if ext is None:
        # Task 1 failed: only an English ticket can be searched directly.
        return ticket_text if _is_english(triage) else None
    intents = ", ".join(i.sub_intent.value.replace("_", " ") for i in ext.intents)
    query = (f"{ext.summary}\nTopics: {intents}. Customer wants: {ext.customer_goal.value.replace('_', ' ')}."
             f" Paid via: {ext.entities.billing_channel.value.replace('_', ' ')}.")
    if ext.language == "en":
        query += f"\nTicket: {ticket_text}"
    return query


def _is_english(triage: TriageResult) -> bool:
    from classifier import language
    return language.detect(triage.ticket_text) == "en"


def _source(a: Article, channel: str, reason: str, score: Optional[float] = None) -> Source:
    condition = a.condition if channel == "unknown" and a.channel_specific else None
    return Source(id=a.id, title=a.title, type=a.type, audience=a.audience, url=a.url,
                  channels=list(a.channels), condition=condition, reason=reason,
                  score=round(score, 3) if score is not None else None, body=a.body)


def retrieve(ticket_text: str, triage: TriageResult, index: VectorIndex, channel: str = "unknown",
             cfg: RetrievalConfig = RetrievalConfig()) -> tuple[list[Source], Optional[str]]:
    """Returns (sources, query used for semantic search)."""
    usable = [a for a in index.articles if channel == "unknown" or a.applies_to(channel)]
    by_id = {a.id: a for a in usable}
    sources: dict[str, Source] = {}

    for flag in triage.risk_flags:
        aid = FLAG_ARTICLES.get(flag)
        if aid and aid in by_id:
            sources[aid] = _source(by_id[aid], channel, f"required for risk flag {flag.value}")

    if triage.extraction is not None:
        subs = [i.sub_intent.value for i in triage.extraction.intents]
        linked = [a for a in usable if a.type == "policy" and set(a.sub_intents) & set(subs)]
        linked.sort(key=lambda a: min(subs.index(s) for s in a.sub_intents if s in subs))  # primary intent first
        for a in linked[: cfg.max_linked]:
            hit = next(s for s in subs if s in a.sub_intents)
            sources.setdefault(a.id, _source(a, channel, f"policy linked to sub-intent {hit}"))

    query = build_query(ticket_text, triage)
    if query:
        allowed = {a.id for a in usable}
        try:
            ranked = index.search(query, k=len(index.articles))
        except Exception:  # embedding model down: degrade to metadata-linked articles only
            return list(sources.values()), None
        hits = [(a, s) for a, s in ranked if a.id in allowed][: cfg.k]
        for a, score in hits:
            if score >= cfg.threshold and a.id not in sources:
                sources[a.id] = _source(a, channel, "semantic match", score)

    return list(sources.values()), query
