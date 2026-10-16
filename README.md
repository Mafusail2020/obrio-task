# Nebula Ticket Triage: AI classifier prototype

Takes a support ticket and returns its **category**, **priority** and **recommended next step**, and flags tickets that need a human.

```
ticket → preprocess (PII mask) → guardrails (keywords) → LLM extraction (facts) → deterministic router (policy) → result
```

- **LLM extracts facts only**: intents (multi-label), customer goal, sentiment, risk flags, language, entities, confidence, summary.
- **Python rules decide policy**: priority, queue, next-step action, `needs_human`. See [classifier/router.py](classifier/router.py).
- **Guardrails**: multilingual keyword net for crisis and legal/chargeback threats. A match sets `redirect_to_human`, which forces P1 and a human whatever the LLM says.
- **Swappable LLM**: local Ollama for development, Claude API for production. See [classifier/llm/](classifier/llm/).

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # set LLM_PROVIDER, and ANTHROPIC_API_KEY for Claude
ollama pull llama3.1          # for local runs
```

## Run

```bash
.venv/bin/streamlit run app.py                                            # UI: classify, evaluate, review queue
.venv/bin/python -m evaluation.run_eval --provider ollama --prompt v5     # eval on 41 test tickets
.venv/bin/python -m evaluation.run_eval --provider claude --ids T36,T39   # subset on Claude
.venv/bin/python -m pytest -q                                             # unit tests (no LLM needed)
```

## Layout

| Path | What |
|---|---|
| `classifier/taxonomy.py` | Categories, sub-intents, flags, priorities, actions |
| `classifier/schema.py` | Pydantic contracts (LLM output, routing decision) |
| `classifier/llm/` | `LLMClient` interface + Ollama / Claude / mock clients |
| `classifier/guardrails.py` | Keyword safety net, `redirect_to_human` |
| `classifier/router.py` | Routing policy table |
| `classifier/review_queue.py` | Human-in-the-loop queue |
| `prompts/vN.md` | Immutable prompt versions; see [prompts/CHANGELOG.md](prompts/CHANGELOG.md) |
| `data/test_tickets.json` | 41 synthetic tickets with reviewed expected labels |
| `evaluation/` | Eval runner, scoring, saved results per prompt/model |
| `docs/decisions.md` | Which decisions were mine and which were AI-proposed |

## Documentation

| Doc | Covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Model choice, prompt structure, categories, failure modes and mitigations |
| [docs/AUTOMATION_LIMITS.md](docs/AUTOMATION_LIMITS.md) | Which tickets must not be automated, human-in-the-loop review queue |
| [docs/PROMPT_EVOLUTION.md](docs/PROMPT_EVOLUTION.md) | v1 → v5 with eval numbers |
| [docs/EDGE_CASES.md](docs/EDGE_CASES.md) | Unexpected AI results and what was done |
| [docs/decisions.md](docs/decisions.md) | My decisions vs AI proposals |

Final eval (prompt v5, llama3.1 8B, 41 tickets): category 100%, sub-intent 97%, needs_human 100%, priority 93% (all misses over-prioritised), all risk flags caught, no false flags.
