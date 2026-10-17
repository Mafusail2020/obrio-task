import json

from classifier.llm.mock_client import MockClient
from evaluation import judge

VERDICT = {"verdicts": [
    {"tone": t, "rating": r, "grounded": g, "unsupported_claims": c, "tone_ok": True, "translation_ok": True, "issue": i}
    for t, r, g, c, i in (("formal", "appropriate", True, [], ""),
                          ("empathetic", "too_general", True, [], "vague"),
                          ("short", "inappropriate", False, ["refund in 2 days"], "promises a refund"))]}


def _results(tmp_path):
    row = {"id": "A99", "text": "refund please", "result": {
        "triage": {"extraction": {"language": "en"}}, "meta": {"channel": "web"},
        "sources": [{"id": "policy-refund-web", "audience": "internal", "title": "Refunds", "body": "14 days", "condition": None}],
        "drafts": {"drafts": [{"tone": t, "english": "text", "local": "text"} for t in ("formal", "empathetic", "short")]}}}
    crisis = {"id": "A98", "text": "crisis", "result": dict(row["result"], drafts=None)}
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"run": {"provider": "ollama", "model": "m", "prompt_version": "v3"}, "rows": [row, crisis]}))
    return p


def test_judge_summarises_ratings_and_skips_tickets_without_drafts(tmp_path):
    client = MockClient([VERDICT])
    j = judge.judge_run(_results(tmp_path), client)
    s = j["summary"]
    assert len(client.calls) == 1  # crisis ticket (no drafts) not judged
    assert s["ratings"] == {"appropriate": 1, "too_general": 1, "inappropriate": 1}
    assert s["grounded"] == 2 and s["ratings_by_tone"]["short"] == {"inappropriate": 1}
    assert "refund in 2 days" in judge.markdown(j)


def test_judge_message_contains_kb_and_drafts(tmp_path):
    row = json.loads(_results(tmp_path).read_text())["rows"][0]
    msg = judge.build_message(row)
    assert 'id="policy-refund-web"' in msg and msg.count("<draft tone=") == 3 and "Billing channel known to the system: web" in msg
