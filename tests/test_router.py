from classifier import router
from classifier.schema import GuardrailResult
from classifier.taxonomy import Action, Priority, Queue, RiskFlag
from tests.helpers import make_extraction

NO_GUARD = GuardrailResult()


def route(ext, guard=NO_GUARD, flags=None):
    flags = flags if flags is not None else list(ext.risk_flags) if ext else []
    return router.route(ext, guard, flags)


def test_every_sub_intent_has_a_base_route():
    from classifier.taxonomy import SubIntent
    assert set(router.BASE_ROUTES) == set(SubIntent)


def test_every_action_has_a_hint():
    assert set(router.ACTION_HINTS) == set(Action)


def test_crisis_overrides_everything():
    ext = make_extraction("product_question", flags=("self_harm_or_crisis",))
    d = route(ext)
    assert (d.priority, d.queue, d.action, d.needs_human) == (Priority.P1, Queue.CRISIS_RESPONSE, Action.ESCALATE_URGENT, True)
    assert d.rule_id == "hard:crisis"


def test_guardrail_redirect_forces_human_even_if_llm_missed_flag():
    ext = make_extraction("unexpected_charge")
    guard = GuardrailResult(flags=[RiskFlag.LEGAL_OR_CHARGEBACK_THREAT], redirect_to_human=True, reason="keyword match")
    d = route(ext, guard, flags=[RiskFlag.LEGAL_OR_CHARGEBACK_THREAT])
    assert d.priority == Priority.P1 and d.queue == Queue.BILLING_SENIOR and d.needs_human


def test_extraction_failure_goes_to_manual_review():
    d = route(None)
    assert d.action == Action.REVIEW_MANUALLY and d.needs_human and d.priority == Priority.P2


def test_extraction_failure_with_crisis_keyword_still_p1():
    guard = GuardrailResult(flags=[RiskFlag.SELF_HARM_OR_CRISIS], redirect_to_human=True, reason="kw")
    d = route(None, guard, flags=[RiskFlag.SELF_HARM_OR_CRISIS])
    assert d.priority == Priority.P1 and d.queue == Queue.CRISIS_RESPONSE


def test_store_cancellation_is_automatable():
    d = route(make_extraction("cancellation", goal="cancel", channel="app_store"))
    assert d.action == Action.SEND_STORE_CANCEL_INSTRUCTIONS and not d.needs_human and d.priority == Priority.P3


def test_web_cancellation_needs_agent():
    d = route(make_extraction("cancellation", goal="cancel", channel="web"))
    assert d.action == Action.PROCESS_CANCELLATION and d.needs_human and d.priority == Priority.P2


def test_secondary_intent_raises_priority_and_requires_human():
    d = route(make_extraction("notifications", "login_access"))
    assert d.priority == Priority.P2 and d.needs_human
    assert d.queue == Queue.TECH_SUPPORT  # routed by primary


def test_same_category_secondary_does_not_raise_priority():
    d = route(make_extraction("slow_replies", "suspected_bot", goal="refund"))
    assert d.priority == Priority.P3 and d.needs_human


def test_low_confidence_requires_human():
    d = route(make_extraction("product_question", confidence="low"))
    assert d.needs_human and "low classification confidence" in d.human_reasons


def test_angry_customer_bumped_but_not_above_p2():
    d = route(make_extraction("product_question", flags=("aggressive_tone",)))
    assert d.priority == Priority.P3 and d.needs_human
    d = route(make_extraction("refund_request", flags=("aggressive_tone", "scam_accusation"), channel="web"))
    assert d.priority == Priority.P2


def test_agent_note_asks_for_channel_when_unknown():
    d = route(make_extraction("refund_request", goal="refund"))
    assert "Billing channel unknown" in d.agent_note


def test_priority_bump():
    assert Priority.P4.bump(Priority.P2) == Priority.P3
    assert Priority.P3.bump(Priority.P2) == Priority.P2
    assert Priority.P2.bump(Priority.P2) == Priority.P2
    assert Priority.P1.bump(Priority.P2) == Priority.P1
