# Reply assistant: prompts, tones, and what went wrong

All prompt versions are kept unchanged in [`prompts/assistant/`](../prompts/assistant/). The detailed log with every failure is in [`prompts/assistant/CHANGELOG.md`](../prompts/assistant/CHANGELOG.md). Each version was evaluated on the same 20 tickets ([`data/assistant_test.json`](../data/assistant_test.json)); raw results are in [`evaluation/results/assistant/`](../evaluation/results/assistant/).

## Results by version

| | v1 | v2 | v3 (final) |
|---|---|---|---|
| Model | llama3.1 | llama3.1 | llama3.1 · gemma3:12b |
| Passed all automatic checks | 4/20 | 18/20 | **20/20 · 19/20** |
| Reply in the right language | 4/19 | 19/19 | 19/19 · 19/19 |
| Tones distinct | 13/19 | 19/19 | 19/19 · 19/19 |
| Valid after retry | 3/19 | 19/19 | 19/19 · 19/19 |
| Retrieval hit | 20/20 | 20/20 | 20/20 · 20/20 |

v2 and v3 also include code changes (normalisation, validator, gate), described in the changelog. The v3 numbers come from the final validator.

## How the different tones were achieved

**v1: adjectives (didn't work).**
```
- formal: polite and professional.
- empathetic: warm and understanding.
- short: brief and to the point.
```
llama3.1 produced three near-identical replies: formal and short shared 74–84% of their words on 6/19 tickets. "Polite" vs "brief" isn't a strong enough difference for an 8B model.

**v2/v3: tone contracts by structure and length (worked: 19/19 distinct).**
```
- formal: greeting, one sentence restating the issue, the solution as numbered steps or clear
  sentences, a polite closing line. No contractions, no exclamation marks. 60–150 words.
- empathetic: open with one sentence that acknowledges the customer's situation in their own
  words. Name a feeling only if the customer expressed it; if they were neutral, acknowledge the
  request instead of inventing frustration. ... Never use "unfortunately". 50–120 words.
- short: one to three sentences, at most 40 words. No greeting and no apology: only the action
  and, if available, the link.
```
What made the difference:
- **Each tone has a different structure** (steps vs acknowledgment-first vs action-only), not just a different mood.
- **Length ranges barely overlap**, so the replies can't collapse into one.
- **Things to avoid are named explicitly** ("unfortunately", contractions in formal, greetings in short), following the support-writing guidance in the research (BoldDesk, SupportBench).
- **The validator measures it:** word overlap above 70% between two tones is flagged, and length limits per tone are checked.

**What still needed fixing after the tones worked (v3):** the empathetic draft invented feelings ("I understand you're feeling frustrated" on a neutral "how do I cancel?"). Fixed by "name a feeling only if the customer expressed it".

## What didn't work the first time

| Problem | Seen in | Fix |
|---|---|---|
| English tickets answered in Spanish (`local` read as "translate") | v1, every English ticket; **a retry with the error message didn't help** | Code: `local` = English text for English tickets (v2); `summary_local` the same (v3) |
| Tones collapsed | v1 | Tone contracts (v2) |
| `commitments` filled with "we'll look into it", "Please let us know", the string "none" | v1–v3 | Narrow definition in the prompt; placeholders stripped in code; the validator counts only *policy* promises (refund, credits, cancellation, deletion) |
| Drafts asked "where did you pay?" when the channel was known, or for a crash | v1–v2 | "Ask only when the answer depends on it; never if known" (v2); `missing_info` rule (v3) |
| Upstream cascade: a classifier error (extra refund intent) turned a slow-advisor ticket into a 🔴 refund decision | v1–v2, A07 | Gate: refund decision only for the **primary** intent (v3) |
| Placeholder link `[link to help-refund-app-store …]` | v2, A01 | Prompt: exact URLs only; validator: placeholders and article ids → error |
| Translation errors: meaning drift ("reinstalled" → "restarted"), wrong grammatical gender, English words inside Russian text | v2, A10/A14 | Prompt: keep facts and gender, no English words in `local` (v3). Remaining non-words on llama → gemma3:12b chosen for drafting |
| My validator raised false errors ("we will investigate the charge" treated as applying a policy) | v3, gemma | Validator counts only policy promises |

## One concrete bad AI output and how it was solved

**Ticket A14** (Russian): *"Удалите, пожалуйста, мой аккаунт и все мои данные. Больше не хочу пользоваться приложением."* ("Please delete my account and all my data. I don't want to use the app anymore.")

llama3.1, prompt v3, short draft:

> Чтобы удалить аккаунт и данные, нам нужно будет проверить вашу **идентичность**. … Вы можете найти более подробную информацию о нашей политике удаления данных по адресу **https://help.nebula.com/article/policy-data-deletion**.

Two problems:
1. **The link is invented.** `help.nebula.com` isn't our help center (`help.nebula.example`), and `policy-data-deletion` is the id of an **internal** article that has no public page. A customer clicking it gets a 404 or, worse, someone else's domain. The prompt already said "only articles with audience customer may be linked, using their exact url". The model ignored it, and my validator missed it because its article-id check deliberately skipped text inside URLs.
2. "проверить вашу идентичность" is a calque of "verify your identity" (Russian uses "личность"). It's understandable but clearly machine-made.

**How it was solved:**
- **URL allowlist in the validator** (deterministic, model-independent): every link in `english` and `local` must exactly match the URL of a retrieved customer-facing article. Anything else is an error, and the generator is retried with the specific problem fed back: *"local text contains links that are not retrieved customer articles: [...]"*. In the final run this ticket needed 2 attempts, and the shown draft has no invented link.
- A unit test pins this case: [`tests/test_assistant.py`](../tests/test_assistant.py) `test_hallucinated_url_is_an_error_but_retrieved_customer_url_is_fine`.
- For the language quality, gemma3:12b is the drafting model locally: its Russian for the same ticket is natural ("подтвердить вашу личность"), and it produced no invented links in the run.

**Lesson:** "only use the exact URL" in a prompt is a request; an allowlist is a guarantee. Anything checkable (links, ids, language, which articles were cited) is checked in code.
