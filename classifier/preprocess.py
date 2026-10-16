"""Light cleanup before the ticket leaves our system.

Deliberately minimal: profanity, caps and punctuation are kept because they
carry tone. Only PII that the classifier does not need is masked.
"""

import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# 13-19 digits, optionally separated by spaces or dashes
CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
# international format only (leading +), so order ids and amounts are left alone
PHONE_RE = re.compile(r"\+\d[\d\s().-]{7,}\d")


@dataclass
class Preprocessed:
    text: str
    truncated: bool = False
    pii_masked: list[str] = field(default_factory=list)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _mask_cards(text: str, found: list[str]) -> str:
    def repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            found.append("card")
            return "[CARD]"
        return m.group()

    return CARD_RE.sub(repl, text)


def _mask(pattern: re.Pattern, label: str, text: str, found: list[str]) -> str:
    def repl(_: re.Match) -> str:
        found.append(label.lower())
        return f"[{label}]"

    return pattern.sub(repl, text)


def preprocess(text: str, max_chars: int = 4000) -> Preprocessed:
    text = text.replace("\r\n", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    found: list[str] = []
    text = _mask(EMAIL_RE, "EMAIL", text, found)
    text = _mask_cards(text, found)
    text = _mask(PHONE_RE, "PHONE", text, found)

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return Preprocessed(text=text, truncated=truncated, pii_masked=sorted(set(found)))
