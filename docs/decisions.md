# Decisions Log

Which main parts of this project came from me, and which came from Claude and were then accepted or rejected by me

---

## Stack & tooling

| # | Decision | Type | Why |
|---|---|---|---|
| 1 | Python for everything, frontend in Streamlit | Mine | Faster and cheaper prototyping |
| 2 | Separate LLM client class, easy switch between local Ollama (for testing) and Claude API | Mine | Mostly because of free cost, but if needed claude can be used for better quality |
| 3 | Documentation in English | Mine | Quality standart |

## Process

| # | Decision | Type | Why |
|---|---|---|---|
| 4 | Research Nebula and similar apps (what users actually write) before designing anything | Mine | To understand how taxonomy must look |
| 5 | Research how other companies solve ticket triage before designing | Mine | Reuse proven patterns instead of inventing from scratch |
| 6 | Bring in an external article on intent detection and extract key ideas from it | Mine | Found great article, and decided to use it |

## Design

| # | Decision | Type | Why |
|---|---|---|---|
| 7 | Limit taxonomy to 4–5 main categories | Mine | Few, clear, mutually exclusive categories are easier to classify and to route |
| 8 | Deterministic routing: LLM extracts facts, Python rules decide priority, queue and escalation | Chosen by me | Consistent, auditable, policy changes don't require prompt changes |
| 9 | `redirect_to_human` in guardrails | Mine | More safe fallback options |
| 10 | On `redirect_to_human`, the LLM still runs (labels + summary for the agent), but routing is forced to a human | Chosen by me | Agent gets context; if the LLM fails, the ticket is escalated anyway |
| 11 | Category is derived in code from the sub-intent when the LLM returns a mismatching pair | Chosen by me | Sub-intent is more specific; a mismatch shouldn't send a ticket to manual review (T20 in v3) |
| 12 | Language detected by a deterministic library (`langdetect`), with LLM fallback for short/uncertain texts | Chosen by me | Few-shot examples in another language made the LLM mislabel English tickets (v3) |

## Ideas from the intent-detection article (my notes)

| # | Idea | How it is used |
|---|---|---|
| A1 | Compound intents need multi-label classification | `intents[]` list, primary first |
| A2 | What the customer *meant* and what they need next, not just what they said | `customer_goal` field |
| A3 | Intent taxonomy spans several dimensions | Separate fields: topic, goal, sentiment, risk flags, language, entities |
| A4 | Pipeline with confidence thresholding → human review below threshold | `confidence` + `needs_human` rule |
| A5 | Design the taxonomy from the data, not the org chart | Categories derived from real user complaints |
