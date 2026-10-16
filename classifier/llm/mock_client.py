import json
from typing import Callable, Union

from pydantic import ValidationError

from classifier.llm.base import LLMClient, LLMError, LLMResponse, T

Responder = Callable[[str, str], Union[str, dict, Exception]]


class MockClient(LLMClient):
    """Offline client for tests. `responder(system, user)` returns a dict, a JSON
    string, or an exception to raise. Pass a list to return responses in order."""

    provider = "mock"

    def __init__(self, responses: Union[Responder, list], model: str = "mock"):
        super().__init__(model)
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    def _next(self, system_prompt: str, user_message: str):
        if callable(self._responses):
            return self._responses(system_prompt, user_message)
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]

    def generate_structured(self, system_prompt: str, user_message: str, schema: type[T]) -> LLMResponse[T]:
        self.calls.append((system_prompt, user_message))
        out = self._next(system_prompt, user_message)
        if isinstance(out, Exception):
            raise out
        raw = out if isinstance(out, str) else json.dumps(out)
        try:
            parsed = schema.model_validate_json(raw)
        except ValidationError as e:
            raise LLMError(f"Mock output does not match schema: {e}") from e
        return LLMResponse(parsed=parsed, raw_text=raw, model=self.model, latency_ms=0.0)
