"""LLM step: ticket text -> validated Extraction (facts only, no policy).

Retry policy by error kind (see LLMError):
  invalid_output -> retry with the validation error fed back to the model
  transient      -> retry the same request (timeouts, rate limits, 5xx, connection)
  fatal          -> stop at once (bad credentials, model missing, refusal)
When attempts run out, ExtractionError is raised and the pipeline routes the
ticket to manual review; the keyword guardrails still apply.
"""

import time
from dataclasses import dataclass

from classifier.llm.base import LLMClient, LLMError, LLMResponse
from classifier.prompts import build_user_message
from classifier.schema import Extraction

TRANSIENT_BACKOFF_S = 1.0


class ExtractionError(Exception):
    def __init__(self, message: str, attempts: int, kind: str = "invalid_output"):
        super().__init__(message)
        self.attempts = attempts
        self.kind = kind


@dataclass
class ExtractionRun:
    extraction: Extraction
    response: LLMResponse
    attempts: int
    warnings: list[str]


def extract(client: LLMClient, system_prompt: str, ticket_text: str, max_attempts: int = 2) -> ExtractionRun:
    user_message = build_user_message(ticket_text)
    feedback = ""
    last_error, last_kind = "", "invalid_output"

    for attempt in range(1, max_attempts + 1):
        message = user_message
        if feedback:
            message += f"\n\nYour previous answer was invalid:\n{feedback}\nReturn a corrected answer."
        try:
            response = client.generate_structured(system_prompt, message, Extraction)
        except LLMError as e:
            last_error, last_kind = str(e), e.kind
            if e.kind == "fatal":
                raise ExtractionError(f"Extraction failed (not retried): {e}", attempt, e.kind) from e
            if e.kind == "invalid_output":
                feedback = str(e)
            elif attempt < max_attempts:
                time.sleep(TRANSIENT_BACKOFF_S)
            continue

        errors = response.parsed.consistency_errors()
        if not errors:
            warnings = response.parsed.repair_categories()
            return ExtractionRun(extraction=response.parsed, response=response, attempts=attempt, warnings=warnings)
        feedback = last_error = "; ".join(errors)
        last_kind = "invalid_output"

    raise ExtractionError(f"Extraction failed after {max_attempts} attempts: {last_error}", max_attempts, last_kind)
