"""Streamlit tab: reply assistant for support agents."""

import json
import uuid
from datetime import datetime

import streamlit as st

from assistant.embeddings import OllamaEmbedder, VectorIndex
from assistant.generator import language_name
from assistant.kb import load_kb
from assistant.pipeline import assist
from assistant.schema import AssistResult, Level, Tone
from classifier.config import DATA_DIR, settings
from classifier.llm.base import LLMClient

FEEDBACK_FILE = DATA_DIR / "assistant_feedback.jsonl"
CHANNELS = {"unknown": "Unknown", "web": "Website", "app_store": "App Store", "google_play": "Google Play"}
TYPE_ICONS = {"policy": "📕", "procedure": "📗", "troubleshooting": "🛠", "help_article": "🌐", "macro": "💬"}
LEVEL_STYLE = {Level.RED: st.error, Level.YELLOW: st.warning, Level.GREEN: st.success}
LEVEL_TITLE = {Level.RED: "🔴 DECISION REQUIRED: you decide, not the AI",
               Level.YELLOW: "🟡 Verify before sending", Level.GREEN: "🟢 Standard ticket"}


@st.cache_resource(show_spinner="Embedding knowledge base…")
def cached_index(embed_model: str) -> VectorIndex:
    return VectorIndex(load_kb(), OllamaEmbedder(embed_model, host=settings.ollama_host))


def log_feedback(result_id: str, tone: str, verdict: str, r: AssistResult) -> None:
    with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "result_id": result_id,
                            "tone": tone, "verdict": verdict, "gate": r.gate.level.value,
                            "model": r.meta.model, "prompt": r.meta.prompt_version}) + "\n")


def render(client: LLMClient, prompt_version: str, classifier_prompt: str, embed_model: str, samples: list[dict]) -> None:
    try:
        index = cached_index(embed_model)
    except Exception as e:  # embedding model missing or Ollama down
        st.error(f"Could not build the KB index with `{embed_model}`: {e}")
        return

    options = ["Custom text"] + [f"{t['id']} · {t['text'][:70]}…" for t in samples]
    choice = st.selectbox("Start from an example", options, key="as_sample")
    default = "" if choice == options[0] else samples[options.index(choice) - 1]["text"]
    text = st.text_area("Ticket text", value=default, height=120, key=f"as_text_{choice}")

    if st.button("Get drafts", type="primary", disabled=not text.strip()):
        with st.spinner("Classifying, searching the KB and drafting replies…"):
            st.session_state["as_result"] = assist(text, client, index, prompt_version, classifier_prompt)
            st.session_state["as_id"] = uuid.uuid4().hex[:8]

    r: AssistResult | None = st.session_state.get("as_result")
    if r is None:
        return
    rid = st.session_state["as_id"]
    ext = r.triage.extraction
    st.divider()

    # --- summary + channel override ---
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Summary**")
        lang = ext.language if ext else "en"
        if r.drafts and lang != "en":
            st.markdown(f"🗣 *{language_name(lang)}:* {r.drafts.summary_local}")
        st.markdown(f"🇬🇧 *English:* {ext.summary if ext else 'classification failed'}")
        if ext:
            intents = ", ".join(f"`{i.sub_intent.value}`" for i in ext.intents)
            st.caption(f"{intents} · goal `{ext.customer_goal.value}` · language `{lang}`"
                       + (f" · amount {ext.entities.amount}" if ext.entities.amount else ""))
    with right:
        keys = list(CHANNELS)
        new_channel = st.selectbox("Billing channel", keys, index=keys.index(r.meta.channel),
                                   format_func=CHANNELS.get, key=f"as_channel_{rid}",
                                   help="Set it if you know it from the admin panel; drafts are regenerated.")
        st.caption("set by agent" if r.meta.channel_overridden else "detected from the ticket")
        if new_channel != r.meta.channel and st.button("Re-run with this channel"):
            with st.spinner("Regenerating…"):
                st.session_state["as_result"] = assist(r.triage.ticket_text, client, index, prompt_version,
                                                       classifier_prompt, channel_override=new_channel, triage=r.triage)
                st.session_state["as_id"] = uuid.uuid4().hex[:8]
            st.rerun()

    # --- gate banner ---
    g = r.gate
    LEVEL_STYLE[g.level](LEVEL_TITLE[g.level] + "".join(f"\n- {reason}" for reason in g.reasons))
    unlocked = g.level != Level.RED or st.checkbox(
        "I checked the policy and the customer's history; I take the decision.", key=f"as_ack_{rid}")

    # --- KB sources ---
    st.markdown("**Knowledge base**")
    for s in r.sources:
        tags = [s.audience, s.reason + (f" ({s.score})" if s.score is not None else "")]
        title = f"{TYPE_ICONS.get(s.type, '•')} {s.title}" + (f"  ⚠ {s.condition}" if s.condition else "")
        with st.expander(f"{title}  ·  {' · '.join(tags)}", expanded=not g.generate_drafts):
            st.markdown(s.body)
            if s.audience == "customer":
                st.caption(f"Customer link: {s.url}")
    if not r.sources:
        st.caption("No matching articles.")

    if not g.generate_drafts:
        st.info("No AI drafts for this ticket. Write the reply personally, following the protocol above.")
        return
    if r.drafts is None:
        st.error(r.error or "No drafts were generated.")
        return

    # --- drafts ---
    st.markdown("**Drafts**")
    show_en = lang != "en" and st.toggle("Show English version", key=f"as_en_{rid}")
    by_tone = {d.tone: d for d in r.drafts.drafts}
    tabs = st.tabs([t.value.capitalize() for t in Tone])
    for tab, tone in zip(tabs, Tone):
        with tab:
            d = by_tone.get(tone)
            if d is None:
                st.warning("This tone is missing.")
                continue
            body = d.english if show_en else d.local
            if unlocked:
                edited = st.text_area("Edit before sending", value=body, height=180, key=f"as_edit_{rid}_{tone.value}_{show_en}")
                st.code(edited, language=None, wrap_lines=True)  # has a copy button
            else:
                st.text_area("Locked until you confirm the decision above", value=body, height=180,
                             disabled=True, key=f"as_lock_{rid}_{tone.value}_{show_en}")
            st.caption("Sources: " + (", ".join(d.source_ids) or "none"))
            st.caption("Promises: " + ("; ".join(d.commitments) or "none"))
            for issue in r.issues:
                if issue.tone in (tone, None):
                    (st.error if issue.severity == "error" else st.warning)(f"{issue.severity}: {issue.message}")
            c1, c2, c3 = st.columns(3)
            for col, verdict, label in ((c1, "used", "👍 Used as-is"), (c2, "edited", "✎ Edited"), (c3, "rejected", "👎 Rejected")):
                if col.button(label, key=f"as_fb_{rid}_{tone.value}_{verdict}"):
                    log_feedback(rid, tone.value, verdict, r)
                    st.toast("Feedback saved")

    if r.drafts.missing_info:
        st.markdown("**Check before sending**")
        for m in r.drafts.missing_info:
            st.markdown(f"- {m}")

    m = r.meta
    st.caption(f"{m.provider}/{m.model} · drafts prompt {m.prompt_version} · embeddings {m.embedder} · "
               f"{m.latency_ms or 0} ms · tokens {m.input_tokens}/{m.output_tokens} · attempts {m.attempts}")
    with st.expander("Retrieval query & raw result"):
        st.code(m.retrieval_query or "(no semantic search)", language=None)
        st.json(r.model_dump(mode="json"))
