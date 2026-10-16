from typing import Optional

from classifier.config import Settings, settings as default_settings
from classifier.llm.base import LLMClient

PROVIDERS = ("ollama", "claude")


def get_client(provider: Optional[str] = None, model: Optional[str] = None,
               cfg: Settings = default_settings) -> LLMClient:
    provider = provider or cfg.llm_provider
    model = model or cfg.default_model(provider)

    if provider == "ollama":
        from classifier.llm.ollama_client import OllamaClient
        return OllamaClient(model=model, host=cfg.ollama_host, timeout_s=cfg.llm_timeout_s)
    if provider == "claude":
        from classifier.llm.claude_client import ClaudeClient
        return ClaudeClient(model=model, effort=cfg.claude_effort, timeout_s=cfg.llm_timeout_s)
    raise ValueError(f"Unknown LLM provider {provider!r}; expected one of {PROVIDERS}")
