import time

import anthropic
from pydantic import ValidationError

from classifier.llm.base import LLMClient, LLMError, LLMResponse, T


class ClaudeClient(LLMClient):
    """Claude via the official Anthropic SDK, using structured outputs (`messages.parse`).

    The SDK already retries 408/409/429/5xx and connection errors with backoff
    (`max_retries`), so errors that reach us are what is left after that.
    """

    provider = "claude"

    def __init__(self, model: str, effort: str = "low", timeout_s: float = 120.0, max_retries: int = 2):
        super().__init__(model, timeout_s)
        self.effort = effort
        # Credentials resolve from ANTHROPIC_API_KEY (or an `ant auth login` profile).
        self._client = anthropic.Anthropic(timeout=timeout_s, max_retries=max_retries)

    def generate_structured(self, system_prompt: str, user_message: str, schema: type[T]) -> LLMResponse[T]:
        start = time.perf_counter()
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=4096,
                # The system prompt is identical for every ticket (~1.9k tokens, above the
                # 512-token minimum), so it is cached; only the ticket is new input.
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_message}],
                output_format=schema,
                output_config={"effort": self.effort},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise LLMError("Claude authentication failed: set ANTHROPIC_API_KEY", kind="fatal") from e
        except (anthropic.BadRequestError, anthropic.NotFoundError) as e:
            raise LLMError(f"Claude rejected the request: {e.message}", kind="fatal") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Claude rate limited (after SDK retries)", kind="transient") from e
        except anthropic.APITimeoutError as e:
            raise LLMError(f"Claude timed out after {self.timeout_s:.0f}s", kind="transient") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Claude connection failed: {e}", kind="transient") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}", kind="transient") from e
        except ValidationError as e:
            raise LLMError(f"Claude output does not match schema: {e}", kind="invalid_output") from e
        latency_ms = (time.perf_counter() - start) * 1000

        if response.stop_reason == "refusal":
            raise LLMError("Claude declined to process this ticket (refusal)", kind="fatal")
        if response.stop_reason == "max_tokens":
            raise LLMError("Claude output was truncated (max_tokens)", kind="invalid_output")
        if response.parsed_output is None:
            raise LLMError("Claude returned no parsed output", kind="invalid_output")

        raw = next((b.text for b in response.content if b.type == "text"), "")
        usage = response.usage
        return LLMResponse(
            parsed=response.parsed_output,
            raw_text=raw,
            model=self.model,
            latency_ms=latency_ms,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens,
            cache_write_tokens=usage.cache_creation_input_tokens,
        )
