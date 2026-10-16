import time

import anthropic
from pydantic import ValidationError

from classifier.llm.base import LLMClient, LLMError, LLMResponse, T


class ClaudeClient(LLMClient):
    """Claude via the official Anthropic SDK, using structured outputs (`messages.parse`)."""

    provider = "claude"

    def __init__(self, model: str, effort: str = "low", timeout_s: float = 120.0):
        super().__init__(model, timeout_s)
        self.effort = effort
        # Credentials resolve from ANTHROPIC_API_KEY (or an `ant auth login` profile).
        self._client = anthropic.Anthropic(timeout=timeout_s)

    def generate_structured(self, system_prompt: str, user_message: str, schema: type[T]) -> LLMResponse[T]:
        start = time.perf_counter()
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                output_format=schema,
                output_config={"effort": self.effort},
            )
        except anthropic.AuthenticationError as e:
            raise LLMError("Claude authentication failed: set ANTHROPIC_API_KEY") from e
        except anthropic.RateLimitError as e:
            raise LLMError(f"Claude rate limited: {e}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Claude connection failed: {e}") from e
        except ValidationError as e:
            raise LLMError(f"Claude output does not match schema: {e}") from e
        latency_ms = (time.perf_counter() - start) * 1000

        if response.stop_reason == "refusal":
            raise LLMError("Claude declined to process this ticket (refusal)")
        if response.stop_reason == "max_tokens":
            raise LLMError("Claude output was truncated (max_tokens)")
        if response.parsed_output is None:
            raise LLMError("Claude returned no parsed output")

        raw = next((b.text for b in response.content if b.type == "text"), "")
        return LLMResponse(
            parsed=response.parsed_output,
            raw_text=raw,
            model=self.model,
            latency_ms=latency_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
