# Feature Checklist — vs. `summarizer_bot_prd_v1.md`

Status as of 2026-09-06, after Combine Mode + live-testing bug fixes
(commit `95a2d8c`). Legend: ✅ done · ⚠️ partial/deviation · ❌ not built.

## 5.1 Input Handling
- ✅ Listens to authorized user's messages
- ✅ URL vs plain-text detection (`looks_like_url`)
- ✅ URL extraction failure → fallback message asking to paste text
- ✅ Plain text used directly

## 5.2 Content Extraction (Web Articles)
- ✅ Fetch via `httpx`
- ✅ Extract via `trafilatura`
- ⚠️ No `readability-lxml` fallback (PRD listed it as optional fallback; trafilatura alone has been sufficient so far)
- ✅ Graceful failure on paywalled/JS-rendered/404/timeout (returns `None` → fallback message)

## 5.3 Normalization
- ✅ Every input becomes `{title, author, source, url, text}`

## 5.4 AI Summarization
- ✅ `summarize(content) -> Summary`
- ✅ Fixed TL;DR / KEY POINTS / TAKEAWAY format
- ✅ Gemini API (`gemini-3.6-flash`, corrected from the retired `gemini-2.5-flash`)
- ✅ Fixed error message on API failure
- ✅ 30s timeout so a hung call can't block forever

## 5.5 Combine Mode
- ✅ Pulls last ~10 saved items (title + summary) before summarizing
- ✅ Related-item check happens in the *same* Gemini call as the summary
- ✅ Bot suggests merge via inline Yes/No buttons (`This looks related to #<id>...`)
- ✅ Confirm → Gemini merges both original texts into one summary, replaces old row's `summary`, bumps `created_at`, records `merged_from`
- ✅ Decline/ignore → new entry already saved separately, nothing forced
- ✅ Relatedness threshold tuned to "same general subject" (not just identical story) based on real usage

## 5.6 Bot Commands
- ✅ `/start`
- ✅ `/help`
- ❌ `/summarize <url>` as an explicit command — **not built**. Auto-detection in the plain message handler covers both URL and pasted text without a command, which the PRD flagged as an acceptable stretch-goal substitute
- ❌ No command to browse/search past saves (`/search`, `/notes` etc. were explicitly out of scope for V1 — see below)

## 5.7 Storage
- ✅ SQLite, raw `sqlite3`, single `summaries` table matching the PRD schema
- ✅ `save_summary`, `get_recent`, `get_by_id`, `update_merged_summary`
- ❌ No retrieval command from Telegram itself — data is only reachable by querying the `.db` file directly (see V2 discussion below)

## 5.8 Access Control
- ✅ Single hardcoded `AUTHORIZED_USER_ID` via `.env`
- ✅ Unauthorized users get a generic rejection

## 5.9 Error Handling
- ✅ Invalid/empty input
- ✅ URL fetch/extraction failure
- ✅ AI API failure
- ✅ Unauthorized user
- ✅ Global error handler added (logs unhandled exceptions from any handler — not in original PRD, added after the callback bug)

## Technical Stack (Section 6)
- ✅ `python-telegram-bot`, Python, Gemini API, `trafilatura`, `httpx`, raw `sqlite3`, `.env`/`python-dotenv`, `pytest`
- ✅ Git + GitHub (repo created, pushed, `main` up to date)

## Build Order (Section 8)
- ✅ 1. Telegram skeleton
- ✅ 2. AI summarizer on pasted text
- ✅ 3. Web extractor wired in
- ✅ 4. SQLite persistence
- ✅ 5. Error handling pass
- ✅ 6. README + basic tests (27 tests, all passing)

## Explicitly Out of Scope for V1 (Section 9) — still true today
- ❌ Threads / TikTok extraction
- ❌ `/search`, `/notes`, `/eli5`, `/technical`, `/action` modes
- ❌ Real embeddings/vector search (Combine Mode still uses the lightweight recent-history prompt)
- ❌ Tags, categories
- ❌ Web dashboard
- ❌ Multi-user support

## Testing
- ✅ 27 unit tests: URL detection/normalization, database (incl. Combine Mode helpers), prompt building, `RELATED_ID` parsing
- ⚠️ No automated tests for `handlers.py` itself (Telegram wiring) or for live network calls (webpage fetch, Gemini) — these were verified via manual live smoke tests instead, per the "test in a real browser/environment" principle for things that are hard to mock meaningfully
- ✅ 5 real bugs found via live testing are documented in `memory.md` with root cause + fix

## Known gap vs. actual usage
The PRD's examples (Appendix A/B) frame this as a "save news articles" tool,
but live usage so far has been personal tips/notes (e.g. interview prep) —
short, informal, mixed-language snippets, not long-form articles. The bot
works for both, but nothing in the product is optimized for the notes case
specifically (e.g. there's no way to read saved notes back from Telegram —
see the "Storage" section above).

---

## V2 Progress (vs. `summarizer_bot_prd_v2.md`)

### Phase 2.1 — Platform-aware fallback for Threads / TikTok
- ✅ `detect_unsupported_platform()` recognizes `threads.net`/`.com` and
  `tiktok.com` (incl. `vt.`/`vm.`/`www.` subdomains), case-insensitively,
  without false-matching lookalike domains
- ✅ Wired into `handle_message` *before* the generic fetch attempt — no
  wasted request, immediate platform-specific reply
- ✅ Deliberately does **not** attempt extraction (see PRD 2.1 rationale —
  Meta's oEmbed terms don't permit it, no official TikTok API exists)
- ✅ 5 new tests (domain matching, case-insensitivity, lookalike-domain
  rejection); verified live with a mocked Telegram update that
  `fetch_and_extract` is never called for these domains

### Phase 2.2 — Retrieval (`/list`, `/search`, `/view`)
- ✅ `/list [n]` — last n saved items (default 10, max 50, clamped; invalid input falls back to default)
- ✅ `/search <keyword>` — case-insensitive substring match across title, summary, and original_text; reports total match count even when results are capped
- ✅ `/view <id>` — full summary for one item, with metadata (date, source, url if present, merged-from ids if it's a merged entry) — closes the loop so `/list`/`/search` results are actually actionable, not just a dead-end preview
- ✅ `/list` and `/search` output ends with a "Use /view <id>..." hint for discoverability
- ✅ Display falls back to a first-line preview of the note when there's no title (most saved items are untitled pasted text)
- ✅ Output truncates safely under Telegram's 4096-char limit
- ✅ 27 new tests (DB layer + formatting helpers) across this phase; verified live against the real database and via mocked command-handler argument parsing (valid/invalid/oversized `/list` counts, empty `/search`, multi-word `/search`, no-match case, `/view` on a merged entry, missing id, invalid id)

### Phase 2.3 — Manage entries (`/delete`, `/undo`)
- ✅ Schema migration: nullable `previous_summary` column added via a guarded `ALTER TABLE` (checks `PRAGMA table_info` first) so existing databases upgrade in place on next `init_db()`, without touching a fresh install's `CREATE TABLE`
- ✅ `/delete <id>` — inline Yes/No confirmation (same stateless `callback_data` pattern as merge, see `memory.md` #5) before removing the row; handles cancel, confirm, and double-delete (already-gone id) cleanly
- ✅ `update_merged_summary()` now snapshots the pre-merge `summary` into `previous_summary` at merge time
- ✅ `/undo <id>` — reverts a merged entry to its pre-merge summary and clears `merged_from`; single-level (repeatable, doesn't step further back); correctly reports "no merge to undo" for an item with no snapshot
- ⚠️ Known limitation (expected, not a bug): merges made *before* this change have no `previous_summary` to restore — `/undo` only works going forward from here
- ✅ 12 new tests (migration idempotency + correctness, delete, undo); verified live end-to-end (migration against a throwaway copy of the real database, full delete confirm/cancel/double-delete flow, and undo against a freshly created merge) — real `summarizer.db` was never touched during testing

### Phase 2.4 — Note-style output for short content
- ✅ Content under 80 words gets a compact `SUMMARY: <1-3 sentences>` format instead of the full `TL;DR/KEY POINTS/TAKEAWAY` structure; 80+ words keeps the full structure unchanged
- ✅ Merges apply the same rule — if both sources being merged are short, the merged result stays compact too
- ✅ `RELATED_ID` parsing needed no changes — it already worked on any line containing the tag regardless of surrounding format
- ✅ 10 new/updated tests (short vs. long branching for both summarize and merge prompts); verified live against realistic short-note and long-article content — outputs matched exactly as designed

### Bonus — clickable commands (in response to a usability question, not a planned phase)
- ✅ `set_my_commands()` registered via `post_init` — Telegram clients now show a tappable "/" command menu with descriptions for all 7 commands instead of requiring them to be typed from memory
- ✅ `/start` and `/help` now include inline "📋 Show recent items" / "❓ Help" buttons that run `/list` and `/help` directly on tap — the only two commands with no required argument, so the only two a button can fully replace
- ✅ Commands needing an argument (`/search`, `/view`, `/delete`, `/undo`) can't be reduced to a bare button tap (Telegram has no way to prefill a value into the input box from a callback) — the command menu still helps by autocompleting the command name itself
- ✅ Verified live: `post_init` hook present on the built `Application`, all handler patterns registered correctly, `/start` includes the buttons, and both quick actions produce correct output against the real database

### Bonus — view a related note before deciding to merge (user-requested, not a planned phase)
- ✅ Merge suggestions now have a third, optional "👀 View #id first" button alongside Yes/No — useful when the related item is old enough that you don't remember what it said
- ✅ Viewing sends a *new* message rather than editing the suggestion, so the original Yes/No/View buttons stay live afterward — viewing never consumes or resets the decision, matching the "not compulsory, just an added option" requirement
- ✅ Extracted `format_full_item()` (previously private to `/view`) into a shared `app/bot/formatting.py` so both `/view` and this button use identical formatting instead of duplicating it
- ✅ Verified live: the view button sends a new message with the full related item and does *not* call `edit_message_text` on the original suggestion
