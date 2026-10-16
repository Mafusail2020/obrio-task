"""Deterministic language detection.

The LLM mislabelled the language of English tickets after a Ukrainian few-shot
example was added (prompt v3), so language comes from a statistical detector.
It is unreliable on very short texts, so for those (or low-probability
results) the LLM's answer is kept as a fallback.
"""

from typing import Optional

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0  # langdetect is random by default

MIN_CHARS = 20
MIN_PROB = 0.9


def detect(text: str) -> Optional[str]:
    """ISO 639-1 code, or None when the detector is not confident."""
    if len(text.strip()) < MIN_CHARS:
        return None
    try:
        best = detect_langs(text)[0]
    except LangDetectException:
        return None
    return best.lang.split("-")[0] if best.prob >= MIN_PROB else None
