"""Read-only access to versioned prompts in prompts/vN.md (classifier) and
prompts/assistant/vN.md (reply assistant).

Prompt files are immutable: every change is a new version file, so the
evolution can be compared and every eval result points to the exact prompt.
"""

import re
from pathlib import Path

from classifier.config import PROMPTS_DIR

_VERSION_RE = re.compile(r"^v(\d+)\.md$")


def list_versions(directory: Path = PROMPTS_DIR) -> list[str]:
    versions = [m.group(1) for p in directory.iterdir() if (m := _VERSION_RE.match(p.name))]
    return [f"v{n}" for n in sorted(versions, key=int)]


def resolve_version(version: str, directory: Path = PROMPTS_DIR) -> str:
    if version == "latest":
        versions = list_versions(directory)
        if not versions:
            raise FileNotFoundError(f"No prompt versions found in {directory}")
        return versions[-1]
    return version


def load_prompt(version: str = "latest", directory: Path = PROMPTS_DIR) -> tuple[str, str]:
    """Returns (resolved_version, system_prompt)."""
    version = resolve_version(version, directory)
    path = directory / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt {version} not found at {path}")
    return version, path.read_text(encoding="utf-8")


def build_user_message(ticket_text: str) -> str:
    return f"<ticket>\n{ticket_text}\n</ticket>"
