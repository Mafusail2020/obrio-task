import pytest

from assistant import gate as gate_rules
from assistant.embeddings import HashEmbedder, VectorIndex
from assistant.kb import load_kb
from assistant.pipeline import assist
from assistant.retrieval import RetrievalConfig, build_query, retrieve
from assistant.schema import DraftSet, Gate, Level
from assistant.validator import validate
from classifier.llm.mock_client import MockClient
from classifier.pipeline import classify
from classifier.taxonomy import SubIntent
from tests.helpers import make_extraction

KB = load_kb()
INDEX = VectorIndex(KB, HashEmbedder(), cache_file=None)
CFG = RetrievalConfig(threshold=0.2)


def triage_for(text, *subs, **kw):
    return classify(text, MockClient([make_extraction(*subs, **kw).model_dump(mode="json")]), prompt_version="v5")


def draft(tone, english, local=None, sources=("help-notifications",), commitments=()):
    return {"tone": tone, "english": english, "local": local or english,
            "source_ids": list(sources), "commitments": list(commitments)}


GOOD_DRAFTS = {
    "reasoning": "wants fewer notifications", "summary_local": "Customer gets too many notifications.",
    "drafts": [
        draft("formal", "Thank you for contacting us. You can adjust notifications in Profile, Settings, Notifications."),
        draft("empathetic", "Five a day is a lot, I completely understand! Just open Profile and switch off the ones you don't want."),
        draft("short", "Go to Profile → Settings → Notifications to turn them off."),
    ],
    "missing_info": [],
}


# ---------- KB ----------

def test_kb_metadata_is_consistent():
    valid_subs = {s.value for s in SubIntent}
    for a in KB:
        assert set(a.sub_intents) <= valid_subs, a.id
        assert ("help.nebula.example" in a.url) == (a.audience == "customer"), a.id


# ---------- retrieval ----------

def test_unknown_channel_returns_both_refund_policies_as_conditional():
    t = triage_for("I want a refund", "refund_request", goal="refund")
    sources, _ = retrieve(t.ticket_text, t, INDEX, "unknown", CFG)
    by_id = {s.id: s for s in sources}
    assert {"policy-refund-web", "policy-refund-store"} <= set(by_id)
    assert by_id["policy-refund-web"].condition and by_id["policy-refund-store"].condition


def test_known_channel_drops_other_channel_articles():
    t = triage_for("I want a refund", "refund_request", goal="refund", channel="web")
    sources, _ = retrieve(t.ticket_text, t, INDEX, "web", CFG)
    ids = {s.id for s in sources}
    assert "policy-refund-web" in ids and "policy-refund-store" not in ids
    assert all(s.condition is None for s in sources)


def test_non_english_ticket_text_is_not_embedded():
    t = triage_for("Поверніть гроші, будь ласка, мене списали двічі", "unexpected_charge", language="uk")
    query = build_query(t.ticket_text, t)
    assert "Поверніть" not in query and "test summary" in query


def test_crisis_flag_pulls_crisis_protocol():
    t = triage_for("I don't want to live anymore", "reading_quality")
    sources, _ = retrieve(t.ticket_text, t, INDEX, "unknown", CFG)
    assert sources[0].id == "sop-crisis-protocol"


# ---------- gate ----------

def test_crisis_gate_blocks_drafts():
    t = triage_for("I don't want to live anymore", "reading_quality")
    g = gate_rules.decide(t, [], "unknown")
    assert g.level == Level.RED and not g.generate_drafts


def test_refund_unknown_channel_is_red_with_channel_warning():
    t = triage_for("refund please", "refund_request", goal="refund")
    sources, _ = retrieve(t.ticket_text, t, INDEX, "unknown", CFG)
    g = gate_rules.decide(t, sources, "unknown")
    assert g.level == Level.RED and any("channel unknown" in r for r in g.reasons)


def test_store_refund_is_not_red():
    t = triage_for("refund please", "refund_request", goal="refund", channel="app_store")
    sources, _ = retrieve(t.ticket_text, t, INDEX, "app_store", CFG)
    assert gate_rules.decide(t, sources, "app_store").level != Level.RED


# ---------- validator ----------

def _sources(*ids):
    t = triage_for("x", "refund_request")
    all_sources, _ = retrieve("refund", t, INDEX, "unknown", RetrievalConfig(threshold=-1, k=len(KB), max_linked=10))
    return [s for s in all_sources if s.id in ids]


GREEN = Gate(level=Level.GREEN)


def test_valid_drafts_have_no_errors():
    issues = validate(DraftSet(**GOOD_DRAFTS), _sources("help-notifications"), "en", "unknown", GREEN)
    assert not [i for i in issues if i.severity == "error"]


def test_missing_tone_and_unknown_source_are_errors():
    bad = dict(GOOD_DRAFTS, drafts=GOOD_DRAFTS["drafts"][:2] + [draft("short", "Ok.", sources=("made-up",))])
    bad["drafts"][2]["tone"] = "formal"
    msgs = [i.message for i in validate(DraftSet(**bad), _sources("help-notifications"), "en", "unknown", GREEN)]
    assert any("one draft per tone" in m for m in msgs) and any("not provided" in m for m in msgs)


def test_conditional_policy_applied_as_fact_is_an_error():
    d = dict(GOOD_DRAFTS, drafts=[draft(t, "We will refund you in full within 5-10 business days.",
                                        sources=("policy-refund-web",), commitments=("full refund",))
                                  for t in ("formal", "empathetic", "short")])
    msgs = [i.message for i in validate(DraftSet(**d), _sources("policy-refund-web"), "en", "unknown", GREEN)
            if i.severity == "error"]
    assert any("channel is unknown" in m for m in msgs)


def test_wrong_language_and_internal_link_are_errors():
    d = dict(GOOD_DRAFTS, drafts=[draft(t, "Please see https://kb.nebula.internal/policy/refund-web for the rules.",
                                        local="Please see our policy page for the full refund rules today.")
                                  for t in ("formal", "empathetic", "short")])
    msgs = [i.message for i in validate(DraftSet(**d), _sources("help-notifications"), "uk", "unknown", GREEN)]
    assert any("internal KB page" in m for m in msgs) and any("expected 'uk'" in m for m in msgs)


def test_collapsed_tones_are_flagged():
    same = "Thank you for your message, you can switch notifications off in Profile, Settings, Notifications."
    d = dict(GOOD_DRAFTS, drafts=[draft(t, same) for t in ("formal", "empathetic", "short")])
    msgs = [i.message for i in validate(DraftSet(**d), _sources("help-notifications"), "en", "unknown", GREEN)]
    assert any("too similar" in m for m in msgs)


# ---------- pipeline ----------

def _client(drafts_responses):
    classification = make_extraction("notifications", goal="fix_issue").model_dump(mode="json")
    drafts_iter = iter(drafts_responses)

    def respond(system, user):
        return next(drafts_iter) if user.startswith("<ticket language=") else classification
    return MockClient(respond)


def test_pipeline_happy_path():
    r = assist("How do I turn off notifications?", _client([GOOD_DRAFTS]), INDEX, retrieval_cfg=CFG)
    assert r.drafts and r.gate.level == Level.GREEN and r.meta.attempts == 1


def test_pipeline_retries_on_validation_error():
    bad = dict(GOOD_DRAFTS, drafts=GOOD_DRAFTS["drafts"][:2])
    client = _client([bad, GOOD_DRAFTS])
    r = assist("How do I turn off notifications?", client, INDEX, retrieval_cfg=CFG)
    assert r.meta.attempts == 2 and len(r.drafts.drafts) == 3
    assert "previous answer had problems" in client.calls[-1][1]


def test_pipeline_crisis_makes_no_generation_call():
    client = _client([])
    r = assist("I don't want to live anymore", client, INDEX, retrieval_cfg=CFG)
    assert r.drafts is None and not r.gate.generate_drafts
    assert not any(u.startswith("<ticket language=") for _, u in client.calls)


def test_channel_override_is_used():
    r = assist("How do I turn off notifications?", _client([GOOD_DRAFTS]), INDEX,
               channel_override="google_play", retrieval_cfg=CFG)
    assert r.meta.channel == "google_play" and r.meta.channel_overridden


def test_secondary_refund_intent_is_yellow_not_red():
    t = triage_for("advisor was slow, give credits back", "slow_replies", "refund_request", goal="refund")
    sources, _ = retrieve(t.ticket_text, t, INDEX, "unknown", CFG)
    g = gate_rules.decide(t, sources, "unknown")
    assert not any(r.startswith("refund decision") for r in g.reasons)
    assert any("secondary refund" in r for r in g.reasons)


def test_placeholder_link_and_article_id_are_errors():
    for text in ("See [link to the refund article] for details.", "Please read help-refund-app-store first."):
        d = dict(GOOD_DRAFTS, drafts=[draft(t, text) for t in ("formal", "empathetic", "short")])
        msgs = [i.message for i in validate(DraftSet(**d), _sources("help-notifications"), "en", "unknown", GREEN,
                                            frozenset(a.id for a in KB))]
        assert any("placeholder" in m for m in msgs), text


def test_customer_url_is_not_mistaken_for_article_id():
    d = dict(GOOD_DRAFTS, drafts=[draft(t, "Guide: https://help.nebula.example/app/notifications") for t in ("formal", "empathetic", "short")])
    msgs = [i.message for i in validate(DraftSet(**d), _sources("help-notifications"), "en", "unknown", GREEN,
                                        frozenset(a.id for a in KB))]
    assert not any("placeholder" in m for m in msgs)


def test_hallucinated_url_is_an_error_but_retrieved_customer_url_is_fine():
    srcs = _sources("help-notifications")
    bad = dict(GOOD_DRAFTS, drafts=[draft(t, "Details: https://help.nebula.com/article/policy-data-deletion") for t in ("formal", "empathetic", "short")])
    good = dict(GOOD_DRAFTS, drafts=[draft(t, "Details: https://help.nebula.example/app/notifications.") for t in ("formal", "empathetic", "short")])
    assert any("not retrieved customer articles" in i.message for i in validate(DraftSet(**bad), srcs, "en", "unknown", GREEN))
    assert not any("not retrieved" in i.message for i in validate(DraftSet(**good), srcs, "en", "unknown", GREEN))


def test_investigate_is_not_a_policy_promise():
    d = dict(GOOD_DRAFTS, drafts=[draft(t, "Where did you pay? We will investigate.", sources=("policy-refund-web",),
                                        commitments=("investigate the charge",)) for t in ("formal", "empathetic", "short")])
    msgs = [i.message for i in validate(DraftSet(**d), _sources("policy-refund-web"), "en", "unknown", GREEN)]
    assert not any("channel is unknown" in m for m in msgs)


def test_embedding_outage_degrades_to_linked_policies():
    class Down(HashEmbedder):
        def embed_query(self, text):
            raise ConnectionError("ollama down")
    idx = VectorIndex(KB, HashEmbedder(), cache_file=None)
    idx.embedder = Down()
    t = triage_for("refund please", "refund_request", goal="refund", channel="web")
    sources, query = retrieve(t.ticket_text, t, idx, "web", CFG)
    assert query is None and [s.id for s in sources] == ["policy-refund-web"]
