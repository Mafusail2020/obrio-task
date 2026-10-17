# Reply assistant prompt changelog

Same rule as the classifier: prompt files are immutable, every change is a new `vN.md`. Results come from `python -m evaluation.run_assistant_eval` on `data/assistant_test.json` (20 tickets) and are saved in `evaluation/results/assistant/`.

## Retrieval calibration (before v1)

`qwen3-embedding`, query = Task 1 English summary + intents + goal + channel (+ the original text only for English tickets), on the 20 test tickets classified by llama3.1:
- The expected article was the **#1** semantic hit for 19/20 tickets. The remaining one, the crisis ticket, gets its protocol through the risk-flag rule, not semantic search.
- Top relevant hits scored 0.63–0.86. Weak tail matches (e.g. "ask for more info" macro on a crash ticket) scored ~0.45–0.55.
- **Threshold set to 0.60**: keeps every relevant top hit, drops the weak tail.

## v1: baseline

Role (agent sends, not the model), "use only KB facts", no promises without KB support, conditional (channel-specific) policies only when the channel is known, no internal procedures in the reply, bilingual output. Tones described with one adjective each ("polite and professional", "warm and understanding", "brief and to the point"). Deliberately thin on tone definitions, to see whether the tones stay distinct without guidance.

**Result (llama3.1 8B, 20 tickets): passed 4/20.** Retrieval 20/20, gate 19/20, tones present 19/19, but language 4/19, valid 3/19, tones distinct 13/19. Generation: ~64 s and ~960 output tokens per ticket (three replies × two languages).

Failures that drove v2:
- **English tickets answered in Spanish.** For every English ticket the model filled `local` with a Spanish translation (44 validator errors). "The same reply in the customer's language" was read as "translate it". The retry with feedback ("`local` is written in 'es', expected 'en'") **did not fix it**, so it repeated on attempt 2.
- **Tones collapsed:** formal and short shared 74–84% of their words on 6/19 tickets. One adjective per tone wasn't enough.
- **`commitments` misused:** "We will look into the charge", "Please let us know", even the literal string `"none"` were listed as promises. This spammed "promise on a decision-required ticket" warnings and failed the no-promise check on A01 (channel unknown).
- **Upstream error cascade (A07):** the classifier added a spurious `refund_request` to a Spanish slow-advisor ticket (the known llama3.1 secondary-intent issue). Retrieval therefore linked both refund policies as conditional, the gate went red, and all drafts asked "where did you buy your credits?", which is irrelevant for a credit restore.
- **A03:** billing channel known (App Store), yet the drafts still told the customer to check their bank statement to see where they paid.
- `summary_local` came back with a "Summary:" label.

## v2: tone contracts, explicit language rule, narrow commitments

Code changes (deterministic, so the model can't get them wrong):
- English tickets: `local` is filled with the English text in code, never trusted from the model.
- Placeholder commitments ("none", "n/a"…) are stripped.
- KB: `policy-credits` now states that credit restores don't depend on the billing channel.

Prompt changes:
- Tones defined by **structure and length**, not adjectives: formal = greeting + restatement + steps + closing, no contractions, 60–150 words. Empathetic = opens by acknowledging the feeling in the customer's words, 50–120 words. Short = 1–3 sentences, ≤ 40 words, no greeting.
- Language rule: `local` only in the ticket language given in the tag; empty for English tickets.
- `commitments` defined narrowly (refund, credits, cancellation, account change, timeline); "we'll look into it" and questions excluded.
- "Ask where the customer paid only when the answer depends on it; never ask if the channel is known." "Only use KB excerpts about the actual problem."

**Result (llama3.1 8B): passed 18/20** (v1: 4/20). Language 19/19, valid 19/19, tones distinct 19/19, no-promise check 1/1. Remaining automatic failures: one short draft with 6 sentences (A03), and A07's gate (still red from the upstream classifier error). Generation ~59 s, ~830 output tokens.

**Reading the drafts showed problems the automatic checks miss:**
- **A01: placeholder link** in the formal draft: `[link to help-refund-app-store or help-refund-google-play]`. The store help articles weren't retrieved, so the model invented a reference to them. The same draft says "we will provide a refund according to our refund policy", yet `commitments` was empty, so self-reported promises are still unreliable.
- **A03 (English): `summary_local` in Spanish.** The same failure as v1, in a field the code fix hadn't covered. The empathetic draft **invented a feeling** ("I understand you're feeling frustrated", though the customer was neutral), used "Unfortunately" despite the rule, and brought up refunds nobody asked about.
- **A10 (Ukrainian): meaning drift.** The customer *reinstalled* the app twice (feminine verb form); the summary says *restarted* (masculine form). Non-words or wrong words in the reply ("заворушливо", "терпимість" instead of "терпіння").
- **A14 (Russian): English left inside the Russian text** ("permanently удалены"); "move on" translated as "хотите продолжить" ("want to continue").
- `missing_info` asked for the billing channel even when it was known or irrelevant (a crash ticket); `commitments` listed customer steps ("update app").

## v3: grounding and translation fidelity (+ run on gemma3:12b)

Code:
- `summary_local` for English tickets = the Task 1 English summary (no model involvement).
- Validator: placeholder links (`[link…]`) or KB article ids in the reply text → error → retry.
- Gate: "refund decision" 🔴 only when the refund/charge intent is the **primary** intent; a secondary one gives 🟡 "check whether the customer actually asks for money back" (fixes the A07 cascade). Decision made by the user.

Prompt:
- Answer only what was asked; links only as the exact customer-article URL, never placeholders or ids.
- Empathetic: name a feeling only if the customer expressed it; never "unfortunately".
- Translation: keep the customer's facts exactly, match grammatical gender (uk/ru), no English words in `local` except product names, menu paths and URLs.
- `commitments` = what *support* promises, explicitly including conditional refunds ("if eligible", "according to policy"); customer steps excluded. `missing_info` never asks for a known or irrelevant channel.

Run on llama3.1 8B and gemma3:12b (better multilingual), which also gives the Task 2 model comparison.

**Result (prompt v3):** llama3.1 8B 18/20, gemma3:12b 17/20 on automatic checks. Gate 20/20 on llama after the primary-intent rule (A07 fixed). Generation: llama ~69 s / ~910 output tokens, gemma ~108 s / ~680 output tokens.

Manual reading, llama3.1 vs gemma3:12b:
- **Ukrainian (A10):** llama now keeps the facts ("reinstalled twice") but still produces non-words ("заворушенням"). gemma's text is natural ("як це може бути неприємно").
- **Russian (A14):** llama uses calques ("проверить вашу идентичность", a literal "identity"; it should be "личность") and **invented a URL**, `https://help.nebula.com/article/policy-data-deletion`: a made-up domain plus an internal article id. gemma's Russian is natural ("подтвердить вашу личность").
- **Implicit promises (A01, channel unknown):** llama writes "we're here to help you get a refund"; gemma stays neutral ("help me determine the appropriate refund process").
- Invented feelings are gone on both models.

Validator problems found (my checks, not the prompt):
- The hallucinated URL passed, because the article-id check skips ids inside URLs. **Fix: URL allowlist.** Every link in a reply must exactly match a retrieved customer article's URL, otherwise it's an error and the draft is retried.
- "Applies a conditional policy as fact" fired on "we will investigate the charge" (2 false errors on gemma). Both models still list "we'll look into it" as a commitment despite the prompt. **Fix:** only *policy* promises (refund, credits, cancellation, deletion) count, for the validator error, the red-gate warning and the eval's no-promise check.
- "Copies internal wording" warned on facts that are also in public help articles. **Fix:** n-grams also present in customer-facing articles are ignored.

The prompt stays at v3; both models were re-run with the corrected validator.

**Final result (prompt v3, corrected validator):** llama3.1 8B **20/20**, gemma3:12b **19/20** (A20: the gate depends on gemma's own classification of a vague ticket). Retrieval 20/20 and language 19/19 on both; llama's A14 needed a retry (URL allowlist), and no invented links appear in either model's final drafts. Generation: llama ~78 s / 875 output tokens, gemma ~84 s / 652. **gemma3:12b chosen for drafting** because of clearly better Ukrainian/Russian at similar latency; see docs/ASSISTANT_ARCHITECTURE.md.

## LLM judge on the final v3 drafts (offline)

gemma3:12b judged 57 drafts per model with the appropriate / too general / inappropriate rubric:
- llama3.1: 39 / 14 / 4.
- gemma3:12b: 48 / 9 / 0 (gemma judging its own drafts).

Spot-checking the flags against the drafts: correct catches were A18, A05, A01 and A14's leftover English word; wrong flags were A14 grounding, A15's URL and A17's conditional explanation.

Two real problems the judge found are **left as known issues** (decision: document, don't iterate further):
- A18: internal procedure steps ("check the admin panel, click Resend") turned into customer instructions.
- A05: refund eligibility asserted although it depends on unverified usage.

Both are covered at runtime by the agent review and the 🔴 gate, and are most likely model-capability limits: gemma3:12b already avoided A18, and a stronger model (Claude Sonnet 5.5 recommended for drafting) is expected to remove them (not yet verified). Details in docs/ASSISTANT_ARCHITECTURE.md → Known issues.
