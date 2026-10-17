from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Provider failed. `kind` drives the retry policy in extractor.py:

    - invalid_output: response didn't match the schema → retry with the error fed back
    - transient: timeout, rate limit, 5xx, connection → retry as-is (or fall back to another provider)
    - fatal: auth/config error, refusal → don't retry the same provider
    """

    def __init__(self, message: str, kind: str = "transient"):
        super().__init__(message)
        self.kind = kind


@dataclass
class LLMResponse(Generic[T]):
    parsed: T
    raw_text: str
    model: str
    latency_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None


class LLMClient(ABC):
    """One interface for every provider.

    Callers pass a Pydantic model as the output schema; each provider turns it
    into its own structured-output mechanism and returns a validated instance.
    """

    provider: str = "base"

    def __init__(self, model: str, timeout_s: float = 120.0):
        self.model = model
        self.timeout_s = timeout_s

    @abstractmethod
    def generate_structured(self, system_prompt: str, user_message: str, schema: type[T]) -> LLMResponse[T]:
        ...

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r})"
