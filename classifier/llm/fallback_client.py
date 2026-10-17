from classifier.llm.base import LLMClient, LLMError, LLMResponse, T


class FallbackClient(LLMClient):
    """Tries providers in order. If the primary is down (transient) or misconfigured
    (fatal), the next one answers. Invalid output is not a provider outage, so it is
    raised to the extractor, which retries with the error fed back."""

    provider = "fallback"

    def __init__(self, clients: list[LLMClient]):
        super().__init__(model=" -> ".join(f"{c.provider}/{c.model}" for c in clients))
        self.clients = clients
        self.last_used: LLMClient = clients[0]

    def generate_structured(self, system_prompt: str, user_message: str, schema: type[T]) -> LLMResponse[T]:
        errors = []
        for client in self.clients:
            try:
                response = client.generate_structured(system_prompt, user_message, schema)
                self.last_used = client
                return response
            except LLMError as e:
                if e.kind == "invalid_output":
                    raise
                errors.append(f"{client.provider}: {e}")
        raise LLMError("All providers failed: " + " | ".join(errors), kind="transient")
