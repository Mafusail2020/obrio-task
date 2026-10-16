"""Run the test set through the full pipeline and save scored results.

Usage:
    python -m evaluation.run_eval --provider ollama --model llama3.1 --prompt v1
    python -m evaluation.run_eval --provider claude --ids T04,T36
"""

import argparse
import json
import time
from datetime import datetime
from typing import Callable, Optional

from classifier.config import RESULTS_DIR
from classifier.llm import LLMClient, get_client
from classifier.pipeline import classify
from classifier.prompts import resolve_version
from evaluation.scoring import FIELDS, load_test_set, score_ticket, summarize


def run(client: LLMClient, prompt_version: str = "latest", ids: Optional[list[str]] = None,
        on_progress: Optional[Callable[[int, int, dict], None]] = None) -> dict:
    version = resolve_version(prompt_version)
    tickets = [t for t in load_test_set() if not ids or t["id"] in ids]
    rows = []
    started = time.perf_counter()

    for n, ticket in enumerate(tickets, 1):
        result = classify(ticket["text"], client, prompt_version=version)
        scored = score_ticket(ticket, result)
        row = {
            "id": ticket["id"],
            "tags": ticket["tags"],
            "text": ticket["text"],
            "expected": ticket["expected"],
            "result": result.model_dump(mode="json"),
            "error": result.error,
            "latency_ms": result.meta.latency_ms,
            "input_tokens": result.meta.input_tokens,
            "output_tokens": result.meta.output_tokens,
            **scored,
        }
        rows.append(row)
        if on_progress:
            on_progress(n, len(tickets), row)

    return {
        "run": {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "provider": client.provider,
            "model": client.model,
            "prompt_version": version,
            "n_tickets": len(rows),
            "wall_time_s": round(time.perf_counter() - started, 1),
        },
        "summary": summarize(rows),
        "rows": rows,
    }


def save(report: dict) -> str:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    r = report["run"]
    stamp = r["timestamp"].replace(":", "").replace("-", "")
    model = r["model"].replace(":", "_").replace("/", "_")
    path = RESULTS_DIR / f"{r['prompt_version']}_{r['provider']}_{model}_{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _print_progress(n: int, total: int, row: dict) -> None:
    bad = [f for f, v in row["scores"].items() if v is False]
    status = "OK " if not bad else "ERR" if row["error"] else "MIS"
    print(f"[{n:>2}/{total}] {row['id']} {status} {' '.join(bad)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--prompt", default="latest")
    parser.add_argument("--ids", default=None, help="comma-separated ticket ids")
    args = parser.parse_args()

    client = get_client(args.provider, args.model)
    report = run(client, args.prompt, args.ids.split(",") if args.ids else None, _print_progress)
    path = save(report)

    s = report["summary"]
    print(f"\n{report['run']['provider']}/{report['run']['model']} prompt={report['run']['prompt_version']}")
    for f in FIELDS:
        t = s["fields"][f]
        if t["total"]:
            print(f"  {f:<15} {t['correct']:>2}/{t['total']:<2} {t['accuracy']:.0%}")
    print(f"  false flags: {s['false_flags'] or 'none'}   failures: {s['extraction_failures']}"
          f"   avg latency: {s['avg_latency_ms']} ms   avg tokens in/out: {s['avg_input_tokens']}/{s['avg_output_tokens']}")
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
