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
