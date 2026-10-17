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
.venv/bin/python -m evaluation.report tickets --prompt v5                 # regenerate docs/EVAL_REPORT.md
.venv/bin/python -m evaluation.report compare --prompt v5                 # model comparison table
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
| [docs/EVAL_REPORT.md](docs/EVAL_REPORT.md) | Per-ticket input → expected → actual → pass/fail table, accuracy, failures (generated) |
| [docs/FAILURE_HANDLING.md](docs/FAILURE_HANDLING.md) | Invalid JSON, timeouts, rate limits, fallback provider, degraded mode |
| [docs/MODEL_COMPARISON.md](docs/MODEL_COMPARISON.md) | 4 local models compared on quality, speed and cost; final choice |
| [docs/COST_AND_CACHING.md](docs/COST_AND_CACHING.md) | Cost per ticket, 10k/month forecast, optimisations, what to cache and why |
| [docs/decisions.md](docs/decisions.md) | My decisions vs AI proposals |

Final eval (prompt v5, llama3.1 8B, 41 tickets): category 100%, sub-intent 97%, needs_human 100%, priority 93% (all misses over-prioritised), all risk flags caught, no false flags.

---

# Task 2: Reply assistant for support agents

The agent pastes a ticket and gets a summary (ticket language + English), three drafts (formal / empathetic / short) in the customer's language with an English toggle, and the KB articles behind them. High-risk tickets are marked 🔴 and the drafts stay locked until the agent confirms the decision; crisis tickets get no AI drafts at all.

```
ticket → Task 1 classifier → retrieval (sub-intent policies + embeddings on the English summary, channel-aware)
       → human-judgment gate 🔴/🟡/🟢 → 1 LLM call: 3 drafts × {english, local} → validator (1 retry) → UI
```

```bash
.venv/bin/streamlit run app.py                                                      # "Reply assistant" tab
.venv/bin/python -m evaluation.run_assistant_eval --model gemma3:12b --prompt v3 --report   # 20-ticket eval
```

Needs the Ollama embedding model: `ollama pull qwen3-embedding`.

| Path | What |
|---|---|
| `assistant/` | KB loader, embeddings + cache, retrieval, gate, generator, validator, pipeline, Streamlit tab |
| `data/kb/` | 29 synthetic KB articles (policies, procedures, troubleshooting, help articles, macros) |
| `data/assistant_test.json` | 20 test tickets with expected KB articles, gate level, language |
| `prompts/assistant/vN.md` | Immutable prompt versions; see [prompts/assistant/CHANGELOG.md](prompts/assistant/CHANGELOG.md) |

| Doc | Covers |
|---|---|
| [docs/ASSISTANT_ARCHITECTURE.md](docs/ASSISTANT_ARCHITECTURE.md) | Retrieval choice, prompt structure for tones, trade-offs, model comparison, failures, cost, caching |
| [docs/ASSISTANT_HUMAN_JUDGMENT.md](docs/ASSISTANT_HUMAN_JUDGMENT.md) | Scenarios where the agent must decide, and how the UI marks them |
| [docs/ASSISTANT_PROMPTS.md](docs/ASSISTANT_PROMPTS.md) | Prompt evolution, how tones were achieved, what failed, one bad output and its fix |
| [docs/ASSISTANT_EVAL_REPORT.md](docs/ASSISTANT_EVAL_REPORT.md) | Per-ticket results table (generated) |

Final eval (prompt v3, 20 tickets): llama3.1 20/20 and gemma3:12b 19/20 automatic checks; retrieval 20/20 on both. gemma3:12b chosen for drafting because of clearly better Ukrainian/Russian.
