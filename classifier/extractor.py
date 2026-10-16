"""LLM step: ticket text -> validated Extraction (facts only, no policy)."""

from dataclasses import dataclass

from classifier.llm.base import LLMClient, LLMError, LLMResponse
from classifier.prompts import build_user_message
from classifier.schema import Extraction


class ExtractionError(Exception):
    def __init__(self, message: str, attempts: int):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class ExtractionRun:
    extraction: Extraction
    response: LLMResponse
    attempts: int
    warnings: list[str]


def extract(client: LLMClient, system_prompt: str, ticket_text: str, max_attempts: int = 2) -> ExtractionRun:
    """Calls the LLM; on schema or consistency errors retries with the error fed back."""
    user_message = build_user_message(ticket_text)
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        message = user_message
        if last_error:
            message += (
                "\n\nYour previous answer was invalid:\n"
                f"{last_error}\nReturn a corrected answer."
            )
        try:
            response = client.generate_structured(system_prompt, message, Extraction)
        except LLMError as e:
            last_error = str(e)
            continue

        errors = response.parsed.consistency_errors()
        if not errors:
            warnings = response.parsed.repair_categories()
            return ExtractionRun(extraction=response.parsed, response=response, attempts=attempt, warnings=warnings)
        last_error = "; ".join(errors)

    raise ExtractionError(f"Extraction failed after {max_attempts} attempts: {last_error}", max_attempts)
