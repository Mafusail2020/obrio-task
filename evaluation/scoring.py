"""Compare a TriageResult with the expected labels of one test ticket."""

import json
from collections import Counter
from pathlib import Path
from typing import Optional

from classifier.config import DATA_DIR
from classifier.schema import TriageResult
from classifier.taxonomy import SUBINTENT_CATEGORY, SubIntent

TEST_SET = DATA_DIR / "test_tickets.json"

FIELDS = ("category", "sub_intent", "mixed_intents", "goal", "channel", "language",
          "priority", "needs_human", "flags_required")


def load_test_set(path: Path = TEST_SET) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["tickets"]


def score_ticket(ticket: dict, result: TriageResult) -> dict:
    """Returns {field: True/False/None}; None means not scored for this ticket."""
    exp = ticket["expected"]
    ext = result.extraction
    s: dict[str, Optional[bool]] = {f: None for f in FIELDS}

    s["priority"] = result.routing.priority.value == exp["priority"]
    s["needs_human"] = result.routing.needs_human == exp["needs_human"]

    required = set(exp["risk_flags"])
    got = {f.value for f in result.risk_flags}
    s["flags_required"] = required <= got if required else None

    allowed = required | set(exp.get("optional_flags", []))
    false_flags = sorted(got - allowed)

    if ext is not None:
        accept = exp["primary_sub_intent"]
        if accept:
            s["sub_intent"] = ext.primary.sub_intent.value in accept
            accept_cats = {SUBINTENT_CATEGORY[SubIntent(a)].value for a in accept}
            s["category"] = ext.primary.category.value in accept_cats
        if exp.get("required_sub_intents"):
            got_subs = {i.sub_intent.value for i in ext.intents}
            s["mixed_intents"] = set(exp["required_sub_intents"]) <= got_subs
        if exp["customer_goal"]:
            s["goal"] = ext.customer_goal.value in exp["customer_goal"]
        if exp.get("billing_channel"):
            s["channel"] = ext.entities.billing_channel.value == exp["billing_channel"]
        s["language"] = ext.language.lower().startswith(exp["language"])
    else:  # extraction failed: every scorable LLM field counts as wrong
        if exp["primary_sub_intent"]:
            s["category"] = s["sub_intent"] = False
        if exp.get("required_sub_intents"):
            s["mixed_intents"] = False
        if exp["customer_goal"]:
            s["goal"] = False
        if exp.get("billing_channel"):
            s["channel"] = False
        s["language"] = False

    return {"scores": s, "false_flags": false_flags}


def summarize(rows: list[dict]) -> dict:
    totals: dict[str, dict] = {}
    for f in FIELDS:
        vals = [r["scores"][f] for r in rows if r["scores"][f] is not None]
        totals[f] = {"correct": sum(vals), "total": len(vals),
                     "accuracy": round(sum(vals) / len(vals), 3) if vals else None}

    false_flags = Counter(flag for r in rows for flag in r["false_flags"])
    failed = sum(1 for r in rows if r.get("error"))
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    tokens_in = [r["input_tokens"] for r in rows if r.get("input_tokens")]
    tokens_out = [r["output_tokens"] for r in rows if r.get("output_tokens")]
    return {
        "fields": totals,
        "false_flags": dict(false_flags),
        "extraction_failures": failed,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "avg_input_tokens": round(sum(tokens_in) / len(tokens_in)) if tokens_in else None,
        "avg_output_tokens": round(sum(tokens_out) / len(tokens_out)) if tokens_out else None,
    }
