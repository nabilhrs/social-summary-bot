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

## 7. `/help` crashed with `Can't parse entities: can't find end of the entity`

**Symptom:** Every `/help` call (and the "❓ Help" quick-action button) threw
`telegram.error.BadRequest: Can't parse entities: can't find end of the
entity starting at byte offset 970`, first seen live on the VM deployment.

**Cause:** `HELP_TEXT` (`app/bot/commands.py`) is sent with
`parse_mode="Markdown"`. Telegram's legacy Markdown parser treats any bare
`_` as an italic marker with no word-boundary awareness. The placeholder
names `<keep_id>`, `<absorb_id>`, and `<api_key>` contributed three
underscores total — an odd number, so the last one had no closing partner
and the whole message failed to parse.

**Fix:** Wrapped every command usage line in backticks (e.g.
`` `/merge <keep_id> <absorb_id>` ``) — text inside a code span isn't
scanned for further entities, so the underscores inside are inert. Also
renders as monospace, which reads better for command syntax anyway.

**Lesson:** Any static string sent with `parse_mode="Markdown"` needs its
literal-vs-entity character count checked before trusting it — legacy
Markdown counts `_`/`*`/`` ` `` globally across the whole message, not
per-clause, so unrelated placeholder names elsewhere in the same string can
break parsing. A quick guard: `text.count("_") % 2 == 0` (and likewise for
`*`) catches this before it ships. This one only surfaced on the real VM
deployment, not in local dev — worth a live `/help` check after any
`HELP_TEXT`/`WELCOME_TEXT` edit, since no test was exercising the actual
Telegram parse call.

---

## 8. "Something went wrong while generating the summary" on a Threads link

**Symptom:** On the VM, a Threads link replied with the generic summary
failure message. The same link summarized fine when replayed locally.

**Cause:** Every Gemini call was a single attempt on a single model, and
every error collapsed into one generic message. When reproducing it, Gemini
returned `503 UNAVAILABLE — "This model is currently experiencing high
demand"` on `gemini-3.6-flash` twice in a row (and on `3.7`/`3.8-flash`
during the model survey). The free tier's per-model daily quota (429) is the
other common cause. Both are temporary or model-specific, so failing outright
and saying only "try again" was wrong on both counts.

**Fix:** All Gemini text generation now goes through
`app/ai/gemini.py:generate_text()`. It retries 5xx and network
timeouts once, moves to the next model on 429 or 404 (so a retired model
falls through too, unlike bug #1), and stops immediately on a rejected key.
If every model fails, it raises `GeminiError(kind)` and the handler shows a
message for that kind. Fallbacks are `gemini-3.5-flash-lite`, then
`gemini-3.1-flash-lite`. The fallback chain was verified live against real
503s. `/setkey` validation also no longer rejects a valid key that's merely
out of quota.

**Lesson:** For an external API with free-tier limits and demand spikes,
"one attempt, generic error" isn't enough. Classify the failure (quota,
auth, overload, other), retry only what's retryable, and tell the user
which one happened. Before picking fallback models, test them live for every
input type the bot sends (text, both summary formats, video). A model
showing up in `models.list()` doesn't mean it works: `gemini-2.5-flash` is
still listed but retired.

---

## 9. An empty `DB_PATH=` would have silently thrown away every save

**Symptom:** None seen in practice; found while adding a `TIMEZONE`
setting. Reproduced: with `DB_PATH=` empty, a table created on one
connection isn't visible from the next.

**Cause:** `.env.example` ships `DB_PATH=` with no value, and
`deploy/setup.sh` copies it to `.env`. python-dotenv sets the variable to
`""`, so `os.getenv("DB_PATH", "summarizer.db")` returned `""` (the default
only applies when the variable is *missing*). `sqlite3.connect("")` opens a
private temporary database that disappears when the connection closes.
Every save would have been lost.

**Fix:** `os.getenv("DB_PATH") or "summarizer.db"` (same pattern for
`TIMEZONE`), plus a startup log line showing the resolved database path.

**Lesson:** `os.getenv(name, default)` doesn't cover empty values, and
`.env` templates create exactly those. For optional settings, use
`os.getenv(name) or default`, and log any path the app writes data to at
startup, so a wrong location shows up in the logs.

---

## Environment notes (not bugs, but easy to re-trip)

- This machine's default Python (`Python312-32`) is **32-bit**. The
  `cryptography` package (a transitive dependency of `google-genai`) has no
  prebuilt wheel for 32-bit Windows and fails to build from source (needs
  Rust). Always use the 64-bit interpreter for this project's venv:
  `py -3.14 -m venv venv`.
