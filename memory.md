# Project Memory — Bugs & Lessons

A running log of bugs found in this project, why they happened, and how they
were fixed — so the same mistake doesn't get repeated in a later change.

---

## 1. `gemini-2.5-flash` model retired

**Symptom:** `google.genai.errors.ClientError: 404 NOT_FOUND` — "This model
models/gemini-2.5-flash is no longer available to new users."

**Cause:** Used a model name that sounded current at time of writing without
checking against a live API call first.

**Fix:** Switched to `gemini-3.6-flash` ([app/ai/summarizer.py](app/ai/summarizer.py)).

**Lesson:** Gemini model names go stale. When adding/changing a model name,
verify it with one live API call before assuming it's correct — the error
message itself usually names the current replacement.

---

## 2. `RELATED_ID` parsed as `None` when Gemini wrote `#1` instead of `1`

**Symptom:** Combine Mode never offered a merge, even for content that was
obviously related.

**Cause:** The regex extracting `RELATED_ID` from the model's raw response
only matched a bare number (`\d+`). Gemini sometimes formatted it as
`RELATED_ID: #1`, which silently failed to match — falling through to "no
match" instead of erroring loudly.

**Fix:** Regex now tolerates an optional `#` (`app/ai/summarizer.py`,
`_RELATED_ID_RE`). Prompt wording also now explicitly says "bare number id
(no # symbol)".

**Lesson:** When parsing free-text LLM output with a regex, silent
fallback-to-None on a non-match hides format drift. Test against the *actual*
raw model output, not just hand-written fixtures, before trusting a parser.

---

## 3. Combine Mode never matched genuinely related notes

**Symptom:** Three personal notes all about job-interview tips (STAR method,
using AI, MNC questions) never triggered a merge suggestion, despite looking
clearly related to a human.

**Cause:** Not a bug — the prompt instructed Gemini to only flag items
covering "the same specific topic or story," which is the right bar for
distinct news articles but too strict for accumulating notes/tips on one
subject. Gemini followed the instruction correctly and said no match.

**Fix:** Loosened the instruction to "same general subject" with a concrete
example pair (`app/ai/prompts.py`).

**Lesson:** When an LLM's decision seems wrong, reproduce the exact call and
read the *raw* output before assuming a parsing bug — often the model did
exactly what the prompt asked, and the fix is the prompt's wording, not the
code. Also: match strictness should reflect actual usage patterns, not just
the example scenario in the original spec.

---

## 4. Merge button did nothing — `allowed_updates=["message"]`

**Symptom:** Clicking "Yes, merge" showed a loading spinner, then reverted
with no visible change — no error, no message edit, buttons still there.

**Cause:** `main.py` called `app.run_polling(allowed_updates=["message"])`.
This was correct when only plain messages were handled, but a
`CallbackQueryHandler` was added later without updating this list —
Telegram was told to never deliver `callback_query` updates at all, so the
handler never even ran.

**Fix:** `allowed_updates=["message", "callback_query"]`.

**Lesson:** `allowed_updates` is an allowlist, not a hint. Any time a new
update type's handler is added (callback queries, inline queries, etc.),
`allowed_updates` must be updated in the same change — grep for it whenever
adding a new handler type.

---

## 5. Merge button said "suggestion has expired" even on a fresh click

**Symptom:** Clicking merge shortly after receiving the suggestion still
failed with "This merge suggestion has expired."

**Contributing cause found:** Two instances of `main.py` were running
simultaneously against the same bot token (one left over from an earlier
background test session). With two pollers, Telegram updates can be handled
by either process — the suggestion may have been created by one process's
in-memory state while the button click was handled by the other, which had
no record of it.

**Underlying design issue:** Pending-merge state was kept in
`context.user_data` (in-process memory only). That state doesn't survive a
bot restart, and isn't shared across multiple instances if more than one is
ever accidentally running.

**Fix:** Removed the in-memory pending state entirely. The merge decision is
now encoded directly in the button's own `callback_data`
(`merge:<yes|no>:<existing_id>:<new_id>`), so there's nothing to expire and
no reliance on a specific process instance handling the click.

**Lesson:**
- Prefer stateless design for anything spanning a Telegram round-trip
  (button click, follow-up message) over in-memory dicts — bot processes
  get restarted often during development.
- Before debugging a "sometimes works" symptom, check for duplicate running
  processes (`tasklist` / `Get-CimInstance Win32_Process`) — two pollers on
  one bot token is an easy, easy-to-miss way to get inconsistent behavior.
- Kill background test processes explicitly and verify they're actually
  gone (`TaskStop` on an agent-tracked task does not guarantee the
  underlying OS process died) rather than assuming a stop call worked.

---

## 6. Threads multi-part detection missed the actual real-world case

**Symptom:** A user showed a real Threads post with a native "1/9" pill
badge next to the caption — the bot's multi-part-thread heads-up never
fired for it.

**Cause:** The detector (`looks_like_partial_thread` in
`app/extractors/threads.py`) only regex-matched numbering typed into the
caption text itself (`(1/4)`, `part 2 of 5`). Threads' own native
multi-part badge is UI chrome computed client-side from the reply
relationship graph — it was never part of the caption, so no regex on the
caption could ever see it. The detector "worked" only for the rare case of
someone manually typing a fraction into their own post text.

**Investigated before fixing:** checked whether any per-post threading
signal (reply count, thread position, etc.) survives an unauthenticated
fetch anywhere in the raw HTML. It doesn't — a promising `reply_count`
string match turned out to be generic app config (a feature-gating flag),
not real per-post data, once the surrounding JSON was inspected.

**Fix:** Removed detection entirely rather than patch the regex further —
there's no reliable signal to detect on on. The bot now unconditionally
appends the "I can only read the linked post, not replies" disclosure to
every Threads extraction, regardless of whether numbering is visible.

**Lesson:** A detector that only catches the rare manually-typed case
while silently missing the platform's own native version of the same
feature is worse than no detector — it creates false confidence that the
problem is handled. When the reliable signal doesn't exist, disclose the
limitation unconditionally instead of guessing when it applies. Also:
before trusting a "found it" grep hit in a large raw HTML blob, check the
surrounding context — a substring match on a field name doesn't mean it's
real per-record data rather than generic config that happens to share a
name.

---

## Environment notes (not bugs, but easy to re-trip)

- This machine's default Python (`Python312-32`) is **32-bit**. The
  `cryptography` package (a transitive dependency of `google-genai`) has no
  prebuilt wheel for 32-bit Windows and fails to build from source (needs
  Rust). Always use the 64-bit interpreter for this project's venv:
  `py -3.14 -m venv venv`.
