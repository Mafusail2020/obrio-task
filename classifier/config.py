import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "evaluation" / "results"

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
    claude_effort: str = os.getenv("CLAUDE_EFFORT", "low")
    prompt_version: str = os.getenv("PROMPT_VERSION", "latest")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "120"))
    max_ticket_chars: int = int(os.getenv("MAX_TICKET_CHARS", "4000"))

    def default_model(self, provider: str) -> str:
        return {"ollama": self.ollama_model, "claude": self.claude_model}.get(provider, "mock")


settings = Settings()
