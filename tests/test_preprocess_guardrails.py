from classifier import guardrails
from classifier.preprocess import preprocess
from classifier.taxonomy import RiskFlag


def test_masks_email_card_phone():
    p = preprocess("mail me at jane.doe@gmail.com, card 4111 1111 1111 1111, call +380 67 123 45 67")
    assert "[EMAIL]" in p.text and "[CARD]" in p.text and "[PHONE]" in p.text
    assert p.pii_masked == ["card", "email", "phone"]


def test_keeps_order_ids_amounts_and_non_luhn_numbers():
    text = "order #NB-58213, charged $41.99, ref 1234567890123"
    assert preprocess(text).text == text


def test_keeps_tone_signals():
    text = "YOU ARE THIEVES!!! f***ing crooks"
    assert preprocess(text).text == text


def test_truncates_and_reports():
    p = preprocess("a" * 50, max_chars=10)
    assert p.truncated and len(p.text) == 10


def test_crisis_keywords_trigger_redirect():
    g = guardrails.check("I don't want to live like this")
    assert RiskFlag.SELF_HARM_OR_CRISIS in g.flags and g.redirect_to_human


def test_ukrainian_crisis_keyword():
    assert guardrails.check("я не хочу жити").redirect_to_human


def test_chargeback_triggers_redirect():
    g = guardrails.check("I'm filing a chargeback with my bank")
    assert RiskFlag.LEGAL_OR_CHARGEBACK_THREAT in g.flags and g.redirect_to_human


def test_scam_flags_but_does_not_redirect():
    g = guardrails.check("SCAM APP, you are thieves")
    assert g.flags == [RiskFlag.SCAM_ACCUSATION] and not g.redirect_to_human


def test_human_request_redirects_but_is_not_a_risk_flag():
    for text in ["Can I speak to a human?", "I want a live agent", "Хочу поговорити з живою людиною"]:
        g = guardrails.check(text)
        assert g.human_requested and g.redirect_to_human and g.flags == [], text


def test_chatgpt_question_is_not_a_human_request():
    assert not guardrails.check("Am I paying to talk to ChatGPT?").human_requested


def test_no_false_positive_on_issue():
    assert guardrails.check("I have an issue with my subscription").flags == []
