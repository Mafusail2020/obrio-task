# Reply assistant: prompts, tones, what went wrong

Immutable versions in [`prompts/assistant/`](../prompts/assistant/); full log in [`CHANGELOG.md`](../prompts/assistant/CHANGELOG.md); 20-ticket test set [`data/assistant_test.json`](../data/assistant_test.json).

| | v1 | v2 | v3 (final) |
|---|---|---|---|
| Model | llama3.1 | llama3.1 | llama3.1 · gemma3:12b |
| Passed all checks | 4/20 | 18/20 | **20/20 · 19/20** |
| Right language | 4/19 | 19/19 | 19/19 · 19/19 |
| Tones distinct | 13/19 | 19/19 | 19/19 · 19/19 |
| Valid after retry | 3/19 | 19/19 | 19/19 · 19/19 |
| Retrieval hit | 20/20 | 20/20 | 20/20 · 20/20 |

v2 and v3 also include code fixes (normalisation, validator, gate).

## How the tones were achieved

**v1, adjectives: failed.** "formal: polite and professional / empathetic: warm and understanding / short: brief and to the point". Formal and short shared 74–84% of their words on 6/19 tickets.

**v2/v3, contracts by structure and length: 19/19 distinct.**
```
formal:     greeting, restate the issue, numbered steps, closing; no contractions or "!"; 60–150 words
empathetic: open by acknowledging the situation in the customer's words; name a feeling only if
            they expressed it; never "unfortunately"; 50–120 words
short:      1–3 sentences, ≤ 40 words, no greeting or apology; only the action and the link
```
What works:
- a different *structure* per tone
- length ranges that barely overlap
- banned phrases named explicitly (following BoldDesk / SupportBench guidance)
- validator checks: word overlap ≤ 70% and length limits

v3 also stopped invented feelings ("I understand you're frustrated" on a neutral question).

## What didn't work the first time

| Problem | Seen | Fix |
|---|---|---|
| English tickets answered in **Spanish** (`local` read as "translate") | v1, every English ticket; **a retry with the error didn't help** | Code fills `local` (v2) and `summary_local` (v3) for English tickets |
| Tones collapsed | v1 | Tone contracts |
| `commitments` = "we'll look into it", "none" | v1–v3 | Narrow definition; placeholders stripped; validator counts only policy promises |
| "Where did you pay?" asked when the channel was known or irrelevant | v1–v2 | Prompt rules for drafts and `missing_info` |
| Classifier's extra refund intent → 🔴 on a slow-advisor ticket | A07 | Gate: refund decision only for the primary intent |
| Placeholder `[link to help-refund-app-store …]` | v2 | Exact URLs only; validator: placeholders and article ids → error |
| Meaning drift ("reinstalled" → "restarted"), wrong gender, English words in Russian | v2 | Keep facts and gender, no English words in `local` (v3); gemma3:12b chosen for drafting |
| My validator's false errors ("investigate the charge" treated as a policy) | v3 | Only policy promises count |

## One bad AI output and the fix

**A14** (ru): *"Удалите, пожалуйста, мой аккаунт и все мои данные…"* ("please delete my account and all my data"). llama3.1, v3, short draft:

> …нам нужно будет проверить вашу **идентичность**. … подробнее по адресу **https://help.nebula.com/article/policy-data-deletion**.

1. **Invented link:** the wrong domain (ours is `help.nebula.example`) plus the id of an **internal** article that has no public page, so the customer gets a 404 or someone else's site. The prompt already said "exact customer URLs only"; my article-id check skipped text inside URLs.
2. "идентичность" is a calque of "identity"; Russian uses "личность".

**Fix:**
- **URL allowlist in the validator:** every link must exactly match a retrieved customer article's URL, otherwise it's an error and the draft is retried with the problem fed back. In the final run this ticket took 2 attempts and has no invented link.
- A unit test pins the case (`test_hallucinated_url_is_an_error_but_retrieved_customer_url_is_fine`).
- gemma3:12b drafts this ticket in natural Russian ("подтвердить вашу личность") with no invented links.

**Lesson:** "use exact URLs" in a prompt is a request; an allowlist is a guarantee. Anything checkable is checked in code.
