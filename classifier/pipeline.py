"""classify(text): preprocess -> guardrails -> LLM extraction -> deterministic routing."""

from typing import Optional

from classifier import guardrails, language, router
from classifier.config import settings
from classifier.extractor import ExtractionError, extract
from classifier.llm.base import LLMClient
from classifier.preprocess import preprocess
from classifier.prompts import load_prompt
from classifier.schema import RunMeta, TriageResult


def classify(text: str, client: LLMClient, prompt_version: str = "latest",
             max_chars: Optional[int] = None) -> TriageResult:
    pre = preprocess(text, max_chars=max_chars or settings.max_ticket_chars)
    guard = guardrails.check(pre.text)
    version, system_prompt = load_prompt(prompt_version)
    meta = RunMeta(provider=client.provider, model=client.model, prompt_version=version)

    extraction, error = None, None
    try:
        run = extract(client, system_prompt, pre.text)
        extraction = run.extraction
        meta.attempts = run.attempts
        meta.latency_ms = run.response.latency_ms
        meta.input_tokens = run.response.input_tokens
        meta.output_tokens = run.response.output_tokens
        meta.cache_read_tokens = run.response.cache_read_tokens
        meta.cache_write_tokens = run.response.cache_write_tokens
        meta.warnings += run.warnings
        used = getattr(client, "last_used", None)  # FallbackClient: record who actually answered
        if used is not None:
            meta.provider, meta.model = used.provider, used.model
            if used is not client.clients[0]:
                meta.warnings.append(f"primary provider failed; answered by fallback {used.provider}/{used.model}")
    except ExtractionError as e:
        error = str(e)
        meta.attempts = e.attempts
        meta.error_kind = e.kind

    if extraction is not None:
        detected = language.detect(pre.text)
        if detected:
            if detected != extraction.language.lower():
                meta.warnings.append(f"language: LLM said {extraction.language}, detector {detected}")
            extraction.language = detected
            meta.language_source = "detector"
        else:
            meta.language_source = "llm"

    # Union: a flag raised by either the keyword net or the LLM counts.
    flags = list(guard.flags)
    if extraction is not None:
        flags += [f for f in extraction.risk_flags if f not in flags]

    return TriageResult(
        ticket_text=pre.text,
        truncated=pre.truncated,
        pii_masked=pre.pii_masked,
        guardrails=guard,
        extraction=extraction,
        risk_flags=flags,
        routing=router.route(extraction, guard, flags),
        error=error,
        meta=meta,
    )
