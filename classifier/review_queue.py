"""Human-in-the-loop queue: tickets with needs_human=True wait here for an agent.

The agent either approves the AI triage or corrects it. Corrections are kept,
so they can be promoted into the test set (feedback loop for prompt changes).
Stored as JSONL for the prototype; a real deployment would use the helpdesk.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from classifier.config import DATA_DIR
from classifier.schema import TriageResult

QUEUE_FILE = DATA_DIR / "review_queue.jsonl"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(items: list[dict], path: Path) -> None:
    path.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")


def add(result: TriageResult, original_text: str, path: Path = QUEUE_FILE) -> str:
    item = {
        "id": uuid.uuid4().hex[:8],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "pending",
        "original_text": original_text,
        "result": result.model_dump(mode="json"),
        "review": None,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item["id"]


def list_items(status: Optional[str] = None, path: Path = QUEUE_FILE) -> list[dict]:
    items = _read(path)
    return [i for i in items if status is None or i["status"] == status]


def resolve(item_id: str, approved: bool, corrections: dict, note: str = "", path: Path = QUEUE_FILE) -> None:
    items = _read(path)
    for item in items:
        if item["id"] == item_id:
            item["status"] = "approved" if approved else "corrected"
            item["review"] = {
                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
                "corrections": corrections,
                "note": note,
            }
            break
    else:
        raise KeyError(item_id)
    _write(items, path)
