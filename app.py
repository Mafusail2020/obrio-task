"""Streamlit UI: classify tickets, run/compare evals, work the human review queue.

Run: streamlit run app.py
"""

import json
import os

import pandas as pd
import streamlit as st

from classifier import review_queue
from classifier.config import RESULTS_DIR, settings
from classifier.llm import PROVIDERS, LLMClient, get_client_with_fallback
from classifier.pipeline import classify
from classifier.prompts import list_versions
from classifier.schema import TriageResult
from classifier.taxonomy import SUBINTENT_CATEGORY, Action, Priority, SubIntent
from evaluation import run_eval
from evaluation.scoring import FIELDS, load_test_set

st.set_page_config(page_title="Nebula Ticket Triage", page_icon="✶", layout="wide")

PRIORITY_COLORS = {"P1": "red", "P2": "orange", "P3": "blue", "P4": "gray"}


@st.cache_resource(show_spinner=False)
def cached_client(provider: str, model: str, fallback: str) -> LLMClient:
    return get_client_with_fallback(provider, model, fallback_provider=fallback)


# ---------- sidebar ----------

with st.sidebar:
    st.header("Model")
    provider = st.selectbox("Provider", PROVIDERS, index=PROVIDERS.index(settings.llm_provider)
                            if settings.llm_provider in PROVIDERS else 0)
    model = st.text_input("Model", value=settings.default_model(provider), key=f"model_{provider}")
    versions = list_versions()
    prompt_version = st.selectbox("Prompt version", versions, index=len(versions) - 1)
    fallback_options = ["none"] + [p for p in PROVIDERS if p != provider]
    default_fb = settings.llm_fallback_provider if settings.llm_fallback_provider in fallback_options else "none"
    fallback = st.selectbox("Fallback provider (if primary is down)", fallback_options,
                            index=fallback_options.index(default_fb))
    if provider == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        st.warning("ANTHROPIC_API_KEY is not set. Add it to .env (or use `ant auth login`).")
    st.caption("The LLM only extracts facts. Priority, queue and escalation come from "
               "deterministic rules in `classifier/router.py`.")

client = cached_client(provider, model, fallback)
tab_classify, tab_eval, tab_review = st.tabs(["Classify", "Evaluation", "Review queue"])


# ---------- classify ----------

def render_result(r: TriageResult) -> None:
    d = r.routing
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Priority**  \n:{PRIORITY_COLORS[d.priority.value]}-background[{d.priority.value}]")
    c2.markdown(f"**Queue**  \n`{d.queue.value}`")
    c3.markdown(f"**Next step**  \n`{d.action.value}`")
    c4.markdown(f"**Human needed**  \n{'🧑 yes' if d.needs_human else '🤖 no'}")

    if r.error:
        st.error(f"LLM extraction failed: {r.error}")
    if d.needs_human and d.human_reasons:
        st.warning("Why a human: " + "; ".join(d.human_reasons))

    st.markdown("**Agent note**")
    st.code(d.agent_note, language=None)

    left, right = st.columns(2)
    with left:
        st.markdown("**Classification (LLM)**")
        if r.extraction:
            e = r.extraction
            for n, i in enumerate(e.intents):
                st.markdown(f"{'Primary' if n == 0 else 'Also'}: `{i.category.value}` › `{i.sub_intent.value}`")
            st.markdown(f"Goal `{e.customer_goal.value}` · Sentiment `{e.sentiment.value}` · "
                        f"Language `{e.language}` · Confidence `{e.confidence.value}`")
            ent = {k: v for k, v in e.entities.model_dump(mode="json").items() if v and v != "unknown"}
            if ent:
                st.markdown("Entities: " + ", ".join(f"{k}=`{v}`" for k, v in ent.items()))
            st.caption(f"Model reasoning: {e.reasoning}")
    with right:
        st.markdown("**Risk flags**")
        llm_flags = {f.value for f in (r.extraction.risk_flags if r.extraction else [])}
        guard_flags = {f.value for f in r.guardrails.flags}
        if not r.risk_flags:
            st.markdown("none")
        for f in r.risk_flags:
            src = " + ".join(s for s, ok in (("keywords", f.value in guard_flags), ("LLM", f.value in llm_flags)) if ok)
            st.markdown(f"- `{f.value}` ({src})")
        if r.guardrails.human_requested:
            st.markdown("🙋 Customer asked for a human")
        if r.guardrails.redirect_to_human:
            st.markdown(f":red[**redirect_to_human**] · {r.guardrails.reason}")
        st.markdown("**Routing trace**")
        st.markdown(f"Rule `{d.rule_id}`" + (f" · modifiers: {', '.join(f'`{m}`' for m in d.modifiers)}" if d.modifiers else ""))

    m = r.meta
    st.caption(f"{m.provider}/{m.model} · prompt {m.prompt_version} · {m.latency_ms or 0:.0f} ms · "
               f"tokens {m.input_tokens}/{m.output_tokens} · attempts {m.attempts}"
               + (f" · PII masked: {', '.join(r.pii_masked)}" if r.pii_masked else "")
               + (" · TRUNCATED" if r.truncated else "")
               + (f" · language from {m.language_source}" if m.language_source else ""))
    for w in m.warnings:
        st.caption(f"⚠️ {w}")
    with st.expander("Raw JSON"):
        st.json(r.model_dump(mode="json"))


with tab_classify:
    tickets = load_test_set()
    options = ["Custom text"] + [f"{t['id']} · {t['text'][:70]}…" for t in tickets]
    choice = st.selectbox("Start from a test ticket", options)
    default = "" if choice == options[0] else tickets[options.index(choice) - 1]["text"]
    text = st.text_area("Ticket text", value=default, height=140, key=f"text_{choice}")
    queue_it = st.checkbox("Send to review queue when a human is needed", value=True)

    if st.button("Classify", type="primary", disabled=not text.strip()):
        with st.spinner(f"Classifying with {provider}/{model}…"):
            result = classify(text, client, prompt_version=prompt_version)
        st.session_state["last_result"] = result
        if queue_it and result.routing.needs_human:
            qid = review_queue.add(result, text)
            st.toast(f"Added to review queue ({qid})")

    if "last_result" in st.session_state:
        st.divider()
        render_result(st.session_state["last_result"])


# ---------- evaluation ----------

def result_files() -> list:
    return sorted(RESULTS_DIR.glob("*.json"), reverse=True) if RESULTS_DIR.exists() else []


with tab_eval:
    st.subheader("Run evaluation")
    ids = st.multiselect("Tickets (empty = all)", [t["id"] for t in tickets])
    if st.button(f"Run on {provider}/{model} with prompt {prompt_version}"):
        bar = st.progress(0.0, text="Starting…")
        report = run_eval.run(client, prompt_version, ids or None,
                              lambda n, total, row: bar.progress(n / total, text=f"{row['id']} ({n}/{total})"))
        path = run_eval.save(report)
        st.success(f"Saved {path}")

    files = result_files()
    if not files:
        st.info("No results yet.")
    else:
        st.subheader("Compare runs")
        reports = {f.name: json.loads(f.read_text(encoding="utf-8")) for f in files}
        comp = []
        for name, rep in reports.items():
            row = {"run": name, "n": rep["run"]["n_tickets"]}
            row.update({f: rep["summary"]["fields"][f]["accuracy"] for f in FIELDS})
            row["false_flags"] = sum(rep["summary"]["false_flags"].values())
            row["failures"] = rep["summary"]["extraction_failures"]
            row["latency_ms"] = rep["summary"]["avg_latency_ms"]
            comp.append(row)
        st.dataframe(pd.DataFrame(comp), hide_index=True, width="stretch",
                     column_config={f: st.column_config.NumberColumn(format="percent") for f in FIELDS})

        st.subheader("Per-ticket results")
        selected = st.selectbox("Run", list(reports))
        rep = reports[selected]
        only_bad = st.checkbox("Only mismatches", value=True)
        rows = []
        for r in rep["rows"]:
            ext = r["result"]["extraction"]
            misses = [f for f, v in r["scores"].items() if v is False]
            if only_bad and not misses and not r["false_flags"]:
                continue
            rows.append({
                "id": r["id"],
                "tags": ", ".join(r["tags"]),
                "expected": " | ".join(r["expected"]["primary_sub_intent"]) or "(any)",
                "got": " + ".join(i["sub_intent"] for i in ext["intents"]) if ext else "FAILED",
                "prio exp/got": f"{r['expected']['priority']} / {r['result']['routing']['priority']}",
                "human exp/got": f"{r['expected']['needs_human']} / {r['result']['routing']['needs_human']}",
                "flags": ", ".join(r["result"]["risk_flags"]),
                "misses": ", ".join(misses + [f"false:{f}" for f in r["false_flags"]]),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        detail = st.selectbox("Inspect ticket", [r["id"] for r in rep["rows"]])
        row = next(r for r in rep["rows"] if r["id"] == detail)
        st.markdown(f"> {row['text']}")
        c1, c2 = st.columns(2)
        c1.markdown("**Expected**")
        c1.json(row["expected"])
        c2.markdown("**Got**")
        c2.json(row["result"]["extraction"] or {"error": row["error"]})


# ---------- review queue ----------

with tab_review:
    pending = review_queue.list_items("pending")
    done = [i for i in review_queue.list_items() if i["status"] != "pending"]
    st.subheader(f"Pending review: {len(pending)}")
    st.caption("Tickets the policy marked as needs_human. An agent approves the AI triage or corrects it; "
               "corrections are stored and can be promoted into the test set.")

    sub_options = [s.value for s in SubIntent]
    for item in pending:
        res = TriageResult.model_validate(item["result"])
        d = res.routing
        title = f"{d.priority.value} · {d.queue.value} · {item['original_text'][:60]}…"
        with st.expander(title):
            st.markdown(f"> {item['original_text']}")
            st.markdown("**Why human:** " + "; ".join(d.human_reasons))
            st.code(d.agent_note, language=None)
            ai_sub = res.extraction.primary.sub_intent.value if res.extraction else sub_options[-1]
            with st.form(f"review_{item['id']}"):
                c1, c2, c3 = st.columns(3)
                sub = c1.selectbox("Primary sub-intent", sub_options, index=sub_options.index(ai_sub))
                prio = c2.selectbox("Priority", [p.value for p in Priority], index=[p.value for p in Priority].index(d.priority.value))
                actions = [a.value for a in Action]
                act = c3.selectbox("Next step", actions, index=actions.index(d.action.value))
                note = st.text_input("Note (optional)")
                if st.form_submit_button("Save review"):
                    corrections = {}
                    if sub != ai_sub:
                        corrections["sub_intent"] = {"ai": ai_sub, "human": sub,
                                                     "category": SUBINTENT_CATEGORY[SubIntent(sub)].value}
                    if prio != d.priority.value:
                        corrections["priority"] = {"ai": d.priority.value, "human": prio}
                    if act != d.action.value:
                        corrections["action"] = {"ai": d.action.value, "human": act}
                    review_queue.resolve(item["id"], approved=not corrections, corrections=corrections, note=note)
                    st.rerun()

    if done:
        st.subheader(f"Reviewed: {len(done)}")
        corrected = sum(1 for i in done if i["status"] == "corrected")
        st.caption(f"AI triage approved as-is: {len(done) - corrected}/{len(done)}")
        st.dataframe(pd.DataFrame([{
            "id": i["id"], "status": i["status"], "text": i["original_text"][:80],
            "corrections": json.dumps(i["review"]["corrections"]) if i["review"]["corrections"] else "",
            "note": i["review"]["note"],
        } for i in done]), hide_index=True, width="stretch")
