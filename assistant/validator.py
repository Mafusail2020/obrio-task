"""Deterministic checks on generated drafts.

errors   -> the generator is retried once with the problems fed back
warnings -> shown to the agent next to the draft
"""

import re

from assistant.schema import DraftSet, Gate, Issue, Level, Source, Tone
from classifier import language

INTERNAL_DOMAIN = "kb.nebula.internal"
MAX_WORDS = {Tone.SHORT: 60, Tone.FORMAL: 180, Tone.EMPATHETIC: 180}
MAX_SHORT_SENTENCES = 3
SIMILARITY_LIMIT = 0.7  # word-set Jaccard between two tones' English versions
OVERLAP_NGRAM = 8       # verbatim words copied from an internal article
URL_RE = re.compile(r"(?:https?://|www\.)[^\s)\]>\"']+", re.IGNORECASE)
# Promises that apply a policy: money, credits, cancellations, account changes.
POLICY_PROMISE_RE = re.compile(r"refund|money back|reimburs|compensat|credit|cancel|delet|erase", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\b(link|url|article|insert|name)\b[^\]]*\]", re.IGNORECASE)


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def _jaccard(a: str, b: str) -> float:
    wa, wb = set(_words(a)), set(_words(b))
    return len(wa & wb) / len(wa | wb) if wa | wb else 1.0


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def policy_promises(commitments: list[str]) -> list[str]:
    return [c for c in commitments if POLICY_PROMISE_RE.search(c)]


def validate(drafts: DraftSet, sources: list[Source], ticket_language: str, channel: str, gate: Gate,
             all_article_ids: frozenset[str] = frozenset()) -> list[Issue]:
    """`all_article_ids`: every KB id, to catch article ids pasted into the reply text."""
    issues: list[Issue] = []
    by_id = {s.id: s for s in sources}
    known_ids = set(all_article_ids) | set(by_id)

    tones = [d.tone for d in drafts.drafts]
    if sorted(t.value for t in tones) != sorted(t.value for t in Tone):
        issues.append(Issue(severity="error", message=f"need exactly one draft per tone (formal, empathetic, short); got {[t.value for t in tones]}"))

    internal_ngrams, customer_ngrams = set(), set()
    for s in sources:
        target = internal_ngrams if s.audience == "internal" else customer_ngrams
        target |= _ngrams(_words(s.body), OVERLAP_NGRAM)
    internal_ngrams -= customer_ngrams  # wording that is also public is fine to reuse
    allowed_urls = {s.url.rstrip("/").lower() for s in sources if s.audience == "customer"}

    for d in drafts.drafts:
        unknown = [i for i in d.source_ids if i not in by_id]
        if unknown:
            issues.append(Issue(severity="error", tone=d.tone, message=f"cites articles that were not provided: {unknown}"))

        cited = [by_id[i] for i in d.source_ids if i in by_id]
        if channel != "unknown":
            wrong = [s.id for s in cited if "any" not in s.channels and channel not in s.channels]
            if wrong:
                issues.append(Issue(severity="error", tone=d.tone, message=f"cites articles for another billing channel than {channel}: {wrong}"))
        elif policy_promises(d.commitments) and any(s.condition for s in cited):
            issues.append(Issue(severity="error", tone=d.tone, message=(
                "applies a channel-specific policy as fact although the billing channel is unknown "
                f"(promises: {policy_promises(d.commitments)}); ask where the customer paid instead")))

        for field, text in (("english", d.english), ("local", d.local)):
            if INTERNAL_DOMAIN in text:
                issues.append(Issue(severity="error", tone=d.tone, message=f"{field} text links an internal KB page"))
            bad_urls = [u for u in URL_RE.findall(text) if u.rstrip("/.,;:").lower() not in allowed_urls]
            if bad_urls:
                issues.append(Issue(severity="error", tone=d.tone, message=(
                    f"{field} text contains links that are not retrieved customer articles: {bad_urls}")))
            if PLACEHOLDER_RE.search(text) or any(re.search(rf"(?<![/\w-]){re.escape(i)}(?![\w-])", text) for i in known_ids):
                issues.append(Issue(severity="error", tone=d.tone, message=(
                    f"{field} text contains a placeholder or an article id instead of a real link or wording")))

        detected = language.detect(d.local)
        if detected and detected != ticket_language:
            issues.append(Issue(severity="error", tone=d.tone, message=(
                f"`local` is written in '{detected}', expected '{ticket_language}'")))
        if ticket_language != "en":
            detected_en = language.detect(d.english)
            if detected_en and detected_en != "en":
                issues.append(Issue(severity="error", tone=d.tone, message=f"`english` is written in '{detected_en}'"))

        n_words = len(_words(d.english))
        if n_words > MAX_WORDS[d.tone]:
            issues.append(Issue(severity="warning", tone=d.tone, message=f"{n_words} words; {d.tone.value} limit is {MAX_WORDS[d.tone]}"))
        if d.tone == Tone.SHORT and _sentences(d.english) > MAX_SHORT_SENTENCES:
            issues.append(Issue(severity="warning", tone=d.tone, message=f"short draft has {_sentences(d.english)} sentences (max {MAX_SHORT_SENTENCES})"))

        if internal_ngrams & _ngrams(_words(d.english), OVERLAP_NGRAM):
            issues.append(Issue(severity="warning", tone=d.tone, message="copies internal procedure wording verbatim; rephrase for the customer"))
        if policy_promises(d.commitments) and gate.level == Level.RED:
            issues.append(Issue(severity="warning", tone=d.tone, message=(
                f"makes policy promises on a decision-required ticket: {policy_promises(d.commitments)}")))

    ds = drafts.drafts
    for i in range(len(ds)):
        for j in range(i + 1, len(ds)):
            sim = _jaccard(ds[i].english, ds[j].english)
            if sim > SIMILARITY_LIMIT:
                issues.append(Issue(severity="warning", message=(
                    f"{ds[i].tone.value} and {ds[j].tone.value} drafts are too similar ({sim:.0%} shared words)")))
    return issues
