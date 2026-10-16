import time

import ollama
from pydantic import ValidationError

from classifier.llm.base import LLMClient, LLMError, LLMResponse, T


class OllamaClient(LLMClient):
    """Local models via Ollama. Uses Ollama's JSON-schema `format` for structured output."""

    provider = "ollama"

    def __init__(self, model: str, host: str = "http://localhost:11434", timeout_s: float = 120.0):
        super().__init__(model, timeout_s)
        self._client = ollama.Client(host=host, timeout=timeout_s)

    def generate_structured(self, system_prompt: str, user_message: str, schema: type[T]) -> LLMResponse[T]:
        start = time.perf_counter()
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                format=schema.model_json_schema(),
                options={"temperature": 0},
            )
        except (ollama.ResponseError, ConnectionError, OSError) as e:
            raise LLMError(f"Ollama request failed: {e}") from e
        latency_ms = (time.perf_counter() - start) * 1000

        raw = response.message.content or ""
        try:
            parsed = schema.model_validate_json(raw)
        except ValidationError as e:
            raise LLMError(f"Ollama output does not match schema: {e}") from e

        return LLMResponse(
            parsed=parsed,
            raw_text=raw,
            model=self.model,
            latency_ms=latency_ms,
            input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
        )
