import time

import httpx
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
        except httpx.TimeoutException as e:
            raise LLMError(f"Ollama timed out after {self.timeout_s:.0f}s", kind="transient") from e
        except ollama.ResponseError as e:
            # 404 = model not pulled: retrying won't help
            kind = "fatal" if e.status_code == 404 else "transient"
            raise LLMError(f"Ollama error {e.status_code}: {e.error}", kind=kind) from e
        except (ConnectionError, OSError, httpx.HTTPError) as e:
            raise LLMError(f"Ollama unreachable: {e}", kind="transient") from e
        latency_ms = (time.perf_counter() - start) * 1000

        raw = response.message.content or ""
        try:
            parsed = schema.model_validate_json(raw)
        except ValidationError as e:
            raise LLMError(f"Ollama output does not match schema: {e}", kind="invalid_output") from e

        return LLMResponse(
            parsed=parsed,
            raw_text=raw,
            model=self.model,
            latency_ms=latency_ms,
            input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
        )
