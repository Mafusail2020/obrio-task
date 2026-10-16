"""The test set's expected priority / needs_human must agree with the routing
policy, given the expected labels. Catches labelling mistakes and silent
policy changes."""

import pytest

from classifier import guardrails, router
from evaluation.scoring import load_test_set
from tests.helpers import make_extraction

TICKETS = load_test_set()


def test_size_and_unique_ids():
    ids = [t["id"] for t in TICKETS]
    assert len(ids) >= 40 and len(set(ids)) == len(ids)


@pytest.mark.parametrize("ticket", TICKETS, ids=[t["id"] for t in TICKETS])
def test_expected_routing_matches_policy(ticket):
    exp = ticket["expected"]
    primary = exp["primary_sub_intent"][0] if exp["primary_sub_intent"] else "spam_or_unclear"
    subs = [primary] + [s for s in (exp.get("required_sub_intents") or []) if s != primary]
    ext = make_extraction(*subs, flags=tuple(exp["risk_flags"]), channel=exp.get("billing_channel") or "unknown",
                          confidence=exp.get("policy_confidence", "high"))
    guard = guardrails.check(ticket["text"])
    flags = list(dict.fromkeys(guard.flags + ext.risk_flags))
    d = router.route(ext, guard, flags)
    assert d.priority.value == exp["priority"]
    assert d.needs_human == exp["needs_human"]
