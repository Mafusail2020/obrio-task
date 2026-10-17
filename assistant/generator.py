"""One LLM call: ticket facts + KB excerpts -> local summary + 3 drafts (English and local)."""

from pathlib import Path

from assistant.schema import DraftSet, Source
from classifier.config import PROMPTS_DIR
from classifier.llm.base import LLMClient, LLMResponse
from classifier.prompts import load_prompt
from classifier.schema import TriageResult

ASSISTANT_PROMPTS_DIR: Path = PROMPTS_DIR / "assistant"

LANGUAGE_NAMES = {
    "en": "English", "uk": "Ukrainian", "ru": "Russian", "es": "Spanish", "de": "German", "fr": "French",
    "it": "Italian", "pt": "Portuguese", "pl": "Polish", "nl": "Dutch", "tr": "Turkish",
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def build_user_message(ticket_text: str, triage: TriageResult, sources: list[Source], channel: str) -> str:
    ext = triage.extraction
    lang = ext.language if ext else "en"
    facts = ["Classification failed; rely on the ticket text."] if ext is None else [
        f"Summary: {ext.summary}",
        "Intents: " + ", ".join(f"{i.category.value}/{i.sub_intent.value}" for i in ext.intents),
        f"Customer goal: {ext.customer_goal.value}",
        f"Billing channel: {channel}",
        f"Sentiment: {ext.sentiment.value}",
    ] + [f"{k}: {v}" for k, v in ext.entities.model_dump(mode='json').items()
         if v and k != "billing_channel" and v != "unknown"]

    articles = []
    for s in sources:
        attrs = f'id="{s.id}" type="{s.type}" audience="{s.audience}"'
        if s.audience == "customer":
            attrs += f' url="{s.url}"'
        if s.condition:
            attrs += f' condition="{s.condition}"'
        articles.append(f"<article {attrs}>\n{s.title}\n{s.body}\n</article>")

    return (
        f'<ticket language="{lang} ({language_name(lang)})">\n{ticket_text}\n</ticket>\n\n'
        f"<facts>\n" + "\n".join(facts) + "\n</facts>\n\n"
        f"<kb>\n" + ("\n".join(articles) if articles else "(no matching articles)") + "\n</kb>\n\n"
        f"Write the `local` version of every reply and `summary_local` in {language_name(lang)}."
    )


def generate(client: LLMClient, ticket_text: str, triage: TriageResult, sources: list[Source], channel: str,
             prompt_version: str = "latest", feedback: str = "") -> tuple[LLMResponse[DraftSet], str]:
    version, system_prompt = load_prompt(prompt_version, ASSISTANT_PROMPTS_DIR)
    message = build_user_message(ticket_text, triage, sources, channel)
    if feedback:
        message += f"\n\nYour previous answer had problems:\n{feedback}\nReturn a corrected answer."
    return client.generate_structured(system_prompt, message, DraftSet), version
