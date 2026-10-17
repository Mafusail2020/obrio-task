"""Failure handling: invalid JSON, timeouts, rate limits, fatal errors, provider fallback."""

import anthropic
import httpx
import pytest

from classifier import extractor
from classifier.llm.base import LLMError
from classifier.llm.claude_client import ClaudeClient
from classifier.llm.fallback_client import FallbackClient
from classifier.llm.mock_client import MockClient
from classifier.llm.ollama_client import OllamaClient
from classifier.pipeline import classify
from classifier.schema import Extraction
from classifier.taxonomy import Action, Priority
from tests.helpers import make_extraction

GOOD = make_extraction("cancellation", goal="cancel").model_dump(mode="json")
REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(extractor, "TRANSIENT_BACKOFF_S", 0)


def test_transient_error_is_retried_without_feedback():
    client = MockClient([LLMError("timeout", kind="transient"), GOOD])
    r = classify("cancel please", client, prompt_version="v5")
    assert r.error is None and r.meta.attempts == 2
    assert "previous answer was invalid" not in client.calls[1][1]


def test_fatal_error_is_not_retried():
    client = MockClient([LLMError("bad key", kind="fatal"), GOOD])
    r = classify("cancel please", client, prompt_version="v5")
    assert r.extraction is None and len(client.calls) == 1 and r.meta.error_kind == "fatal"
    assert r.routing.action == Action.REVIEW_MANUALLY


def test_invalid_json_twice_goes_to_manual_review():
    r = classify("cancel please", MockClient(["{oops", "not json either"]), prompt_version="v5")
    assert r.extraction is None and r.meta.error_kind == "invalid_output"
    assert r.routing.needs_human and r.routing.priority == Priority.P2


def test_outage_keeps_guardrails_active():
    client = MockClient([LLMError("down", kind="transient")])
    r = classify("I don't want to live anymore", client, prompt_version="v5")
    assert r.extraction is None and r.routing.priority == Priority.P1


def test_fallback_answers_when_primary_is_down():
    primary = MockClient([LLMError("rate limited", kind="transient")], model="primary")
    secondary = MockClient([GOOD], model="secondary")
    r = classify("cancel please", FallbackClient([primary, secondary]), prompt_version="v5")
    assert r.error is None and r.meta.model == "secondary"
    assert any("fallback" in w for w in r.meta.warnings)


def test_fallback_does_not_hide_invalid_output():
    primary = MockClient(["{oops"], model="primary")
    secondary = MockClient([GOOD], model="secondary")
    with pytest.raises(LLMError) as e:
        FallbackClient([primary, secondary]).generate_structured("s", "u", Extraction)
    assert e.value.kind == "invalid_output" and not secondary.calls


def test_ollama_timeout_maps_to_transient(monkeypatch):
    client = OllamaClient("llama3.1", timeout_s=1)
    monkeypatch.setattr(client._client, "chat", lambda **kw: (_ for _ in ()).throw(httpx.ReadTimeout("slow")))
    with pytest.raises(LLMError) as e:
        client.generate_structured("s", "u", Extraction)
    assert e.value.kind == "transient" and "timed out" in str(e.value)


@pytest.mark.parametrize("exc, kind", [
    (anthropic.RateLimitError("429", response=httpx.Response(429, request=REQ), body=None), "transient"),
    (anthropic.InternalServerError("500", response=httpx.Response(500, request=REQ), body=None), "transient"),
    (anthropic.AuthenticationError("401", response=httpx.Response(401, request=REQ), body=None), "fatal"),
    (anthropic.APITimeoutError(request=REQ), "transient"),
])
def test_claude_errors_map_to_kinds(monkeypatch, exc, kind):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    client = ClaudeClient("claude-haiku-5-5", max_retries=0)
    monkeypatch.setattr(client._client.messages, "parse", lambda **kw: (_ for _ in ()).throw(exc))
    with pytest.raises(LLMError) as e:
        client.generate_structured("s", "u", Extraction)
    assert e.value.kind == kind
