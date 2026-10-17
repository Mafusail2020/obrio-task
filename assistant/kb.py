"""Simulated knowledge base: Markdown articles with front-matter in data/kb/.

Each article has an `audience`: `customer` articles may be linked in a reply,
`internal` ones (policies, procedures, macros) are shown to the agent only.
`sub_intents` ties articles to the Task 1 taxonomy for deterministic retrieval.
`channels` says which billing channel an article applies to (web, app_store,
google_play or any), so a website-only policy is never presented as fact to
an App Store customer.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from classifier.config import DATA_DIR

KB_DIR = DATA_DIR / "kb"
TYPES = ("policy", "procedure", "troubleshooting", "help_article", "macro")
CHANNELS = ("web", "app_store", "google_play", "any")
CHANNEL_NAMES = {"web": "the Nebula website", "app_store": "the App Store", "google_play": "Google Play"}


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    type: str
    audience: str
    sub_intents: tuple[str, ...]
    channels: tuple[str, ...]
    url: str
    last_reviewed: str
    body: str

    @property
    def is_customer_facing(self) -> bool:
        return self.audience == "customer"

    @property
    def channel_specific(self) -> bool:
        return "any" not in self.channels

    def applies_to(self, channel: str) -> bool:
        return "any" in self.channels or channel in self.channels

    @property
    def condition(self) -> str:
        """Human-readable condition for channel-specific articles."""
        return "applies only if paid via " + " or ".join(CHANNEL_NAMES[c] for c in self.channels)

    @property
    def text_for_embedding(self) -> str:
        return f"{self.title}\n{self.body}"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text_for_embedding.encode()).hexdigest()[:16]


def _parse_value(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return tuple(_unquote(v) for v in raw[1:-1].split(",") if v.strip())
    return _unquote(raw)


def _unquote(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'" else v


def parse_article(text: str) -> Article:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError("missing front-matter")
    meta = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = _parse_value(value)
    channels = tuple(meta.get("channels", ("any",)))
    if meta.get("type") not in TYPES or meta.get("audience") not in ("internal", "customer") \
            or not set(channels) <= set(CHANNELS):
        raise ValueError(f"bad type/audience/channels in {meta.get('id')}")
    return Article(
        id=meta["id"], title=meta["title"], type=meta["type"], audience=meta["audience"],
        sub_intents=tuple(meta.get("sub_intents", ())), channels=channels, url=meta["url"],
        last_reviewed=meta["last_reviewed"], body=m.group(2).strip(),
    )


def load_kb(directory: Path = KB_DIR) -> list[Article]:
    articles = [parse_article(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.md"))]
    ids = [a.id for a in articles]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate article ids in KB")
    return articles
