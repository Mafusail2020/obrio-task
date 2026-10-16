from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Provider failed: connection, refusal, truncated or unparseable output."""


@dataclass
class LLMResponse(Generic[T]):
    parsed: T
    raw_text: str
    model: str
    latency_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


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
