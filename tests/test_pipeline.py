from classifier.llm.base import LLMError
from classifier.llm.mock_client import MockClient
from classifier.pipeline import classify
from classifier.taxonomy import Action, Priority, RiskFlag
from tests.helpers import make_extraction


def good(*subs, **kw):
    return make_extraction(*subs, **kw).model_dump(mode="json")


def test_happy_path():
    client = MockClient([good("cancellation", goal="cancel", channel="app_store")])
    r = classify("How do I cancel? I bought via App Store.", client, prompt_version="v1")
    assert r.error is None and r.routing.action == Action.SEND_STORE_CANCEL_INSTRUCTIONS
    assert r.meta.attempts == 1 and r.meta.prompt_version == "v1"


def test_wrong_category_is_derived_from_sub_intent():
    bad = good("cancellation")
    bad["intents"][0]["category"] = "technical_issue"
    r = classify("cancel please", MockClient([bad]), prompt_version="v1")
    assert r.error is None and r.meta.attempts == 1
    assert r.extraction.primary.category.value == "billing_subscription"
    assert any("derived from sub_intent" in w for w in r.meta.warnings)


def test_retries_on_invalid_output_then_succeeds():
    client = MockClient(["{not json", good("cancellation")])
    r = classify("cancel please", client, prompt_version="v1")
    assert r.error is None and r.meta.attempts == 2
    assert "previous answer was invalid" in client.calls[1][1]


def test_language_from_detector_overrides_llm():
    client = MockClient([good("cancellation", language="uk")])
    r = classify("Please cancel my subscription, I no longer use the app.", client, prompt_version="v1")
    assert r.extraction.language == "en" and r.meta.language_source == "detector"


def test_short_text_keeps_llm_language():
    r = classify("hi it doesnt work", MockClient([good("spam_or_unclear", language="en")]), prompt_version="v1")
    assert r.extraction.language == "en" and r.meta.language_source == "llm"


def test_human_request_forces_human_without_changing_priority():
    client = MockClient([good("product_question", goal="get_info")])
    r = classify("How do crystals work? I want to talk to a real person please", client, prompt_version="v1")
    assert r.guardrails.human_requested and r.routing.needs_human
    assert r.routing.priority == Priority.P4


def test_llm_down_falls_back_to_manual_review_but_keeps_guardrails():
    client = MockClient([LLMError("connection refused")])
    r = classify("I'm filing a chargeback", client, prompt_version="v1")
    assert r.extraction is None and r.error
    assert r.routing.priority == Priority.P1 and r.routing.needs_human


def test_flags_union_of_guardrail_and_llm():
    client = MockClient([good("unexpected_charge", flags=("aggressive_tone",))])
    r = classify("SCAM! give my money back", client, prompt_version="v1")
    assert set(r.risk_flags) == {RiskFlag.SCAM_ACCUSATION, RiskFlag.AGGRESSIVE_TONE}


def test_pii_is_masked_before_llm():
    client = MockClient([good("product_question")])
    classify("my email is a@b.com", client, prompt_version="v1")
    assert "a@b.com" not in client.calls[0][1]
