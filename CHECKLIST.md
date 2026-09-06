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
- ✅ `detect_unsupported_platform()` recognizes `tiktok.com` (incl.
  `vt.`/`vm.`/`www.` subdomains), case-insensitively, without
  false-matching lookalike domains — wired into `handle_message` *before*
  the generic fetch attempt, immediate platform-specific reply, no wasted
  request
- ✅ TikTok deliberately does **not** attempt extraction (no official API
  for third-party content retrieval, and live testing during the Threads
  investigation below showed TikTok pushes back on automated access more
  aggressively than Threads does) — explicitly deferred, not built, per
  the user's own choice when asked
- ⚠️ **Revised for Threads** — see below, no longer in the unsupported list
- ✅ Tests + live verification for the remaining TikTok-only fallback

### Revision — real Threads extraction via Open Graph tags (supersedes the original Phase 2.1 Threads fallback)
- **Why revisited:** the original "unsupported" verdict was about the
  oEmbed *API* specifically, whose terms restrict use to rendering an
  embed. Open Graph meta tags are a different, universal web standard
  every site uses for link previews (the same mechanism Slack/iMessage/
  Discord use) — reading them via a normal HTTP fetch isn't the same
  restricted mechanism, and isn't scraping in the ToS-violating sense.
- ✅ Verified live (via the in-app browser, on real public posts) before
  writing any code: a Threads post permalink's raw, un-rendered HTML
  contains the full caption in `og:description` — confirmed on both a
  short post and a ~270-character multi-paragraph post with an emoji,
  with no truncation
- ✅ Also verified live: the reply chain is **not** reachable this way — a
  root post's raw HTML contains zero trace of its own replies' text or
  post ids. Threads hydrates those entirely via client-side JS after load,
  so getting them would require a full headless browser or reverse-
  engineering a private API — both rejected as disproportionate/ToS-risky
- ✅ New `app/extractors/threads.py`: parses `og:description` (the
  caption) and `og:title` (used to derive the author name) via regex,
  HTML-entity-unescaped
- ✅ New `source: "threads"` value (`normalize_threads_post()`) distinct
  from `"web"`/`"pasted_text"`, so `/view` shows where content actually
  came from
- ⚠️ **Correction after real-world testing:** the first version tried to
  *detect* a multi-part post by regex-matching numbering typed into the
  caption (`(1/4)`, `part 2 of 5`). The user hit a real Threads post using
  Threads' own **native** "1/9"-style thread badge — UI chrome, not text
  in the caption — which the regex structurally cannot see. Investigated
  live: no per-post threading signal (reply count, thread position, etc.)
  survives an unauthenticated fetch anywhere in the raw HTML; a promising
  `reply_count` hit turned out to be generic app config, not real per-post
  data. Conclusion: detection is not reliably achievable at all, native or
  manual. **Fix:** removed the regex/detection entirely; the bot now
  unconditionally discloses the "I can only read the linked post, not
  replies" limitation on every Threads extraction, rather than gambling on
  detecting when it applies
- ✅ 12 tests (OG-tag parsing incl. entity-unescaping and missing/empty
  cases, author extraction, domain routing, normalization); verified live
  end-to-end twice: once against a post with no numbering (confirmed the
  note now always appears) and once via the original real-network fetch
  matching the earlier browser investigation exactly

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

### Bonus — automatic paragraph vs. bullets for compact summaries (user-requested, not a planned phase)
- ✅ The compact-format instruction (Phase 2.4) now lets Gemini pick a single tight paragraph for a single-point note, or a short bullet list when the note clearly lists several distinct points — no new setting or command, the model judges per note
- ✅ Verified live: a one-line reminder stayed a plain sentence; a 7-item tips list came back bulleted

### Bonus — /merge <keep_id> <absorb_id> for manually merging any two items (user-requested, not a planned phase)
- ✅ Lets you merge any two saved items on demand, not just ones Combine Mode happened to flag together at save time — closes the gap where two related notes saved far apart, or before Combine Mode existed, had no way to be joined after the fact
- ✅ First id is the survivor (keeps its row, absorbs the second's content into one summary via the existing `update_merged_summary`); rejects merging an id with itself; reports clearly which id is missing if either doesn't exist
- ✅ Reuses the exact same confirm/decline/view-first flow as an automatic suggestion (`build_merge_keyboard()`, extracted into `app/bot/formatting.py`, and the existing `handle_merge_callback` — zero new callback-handling code needed since a manual merge and an auto-suggested one are identical once both ids are known)
- ✅ 9 new tests (two-id parsing, keyboard construction/callback_data correctness); verified live end-to-end against a throwaway copy of the real database — confirm prompt, self-merge rejection, missing-id handling, no-args usage message, view-before-deciding (leaves the prompt untouched), and the actual merge (survivor absorbed the other's content, the absorbed row stayed intact) all behaved correctly

### Bonus — delete directly from /list or /search results (user-requested, not a planned phase)
- ✅ Telegram can't attach a button to one line inside a text message, but it can attach a row of buttons below the whole message — `/list` and `/search` (and the `/start`/`/help` quick "📋 Show recent items" button) now show a small "🗑 #id" button per displayed item, alongside the existing text list
- ✅ Tapping one opens the exact same Yes/No confirmation `/delete <id>` already uses (`build_delete_keyboard()`, extracted into `app/bot/formatting.py` alongside `build_merge_keyboard()`) — one tap to request, one more to confirm, nothing deletes on the first tap
- ✅ Capped at 20 items (`_MAX_ITEMS_FOR_DELETE_BUTTONS`) — beyond that a wall of buttons would be worse than useful; `/list 50` still works, it just falls back to typing `/delete <id>`
- ✅ 9 new tests (keyboard construction, row-chunking at 5 per row, empty-list and over-threshold edge cases); verified live end-to-end against a throwaway copy of the real database — `/list` correctly attached one button per shown item, tapping a button produced the right confirmation prompt, and confirming actually deleted the row

### Revision — real TikTok video summarization (supersedes the earlier "skip TikTok for now" decision)
- **Why revisited:** the user explicitly asked for actual video content
  summarization rather than a caption-only shortcut, reasoning that typing
  or pasting anything defeats the point of pasting a link. Restated the
  ToS tradeoff plainly one more time before proceeding, since — unlike
  Threads' Open Graph approach — this genuinely does cross TikTok's terms
  (downloading video content isn't permitted), same category of tool as
  `youtube-dl`.
- ✅ Verified live before building: a plain fetch (and yt-dlp *without* its
  `curl-cffi` "impersonation" extra) gets blocked by TikTok's JS
  bot-challenge — confirms TikTok resists automated access harder than any
  other platform this bot touches. Installing `yt-dlp[default,curl-cffi]`
  gets past it (solves the challenge natively).
- ✅ Verified live end-to-end on a real public video: downloaded via
  yt-dlp (2.2MB, 28s video), uploaded to Gemini's Files API, and asked to
  describe the actual content — the response correctly described visuals
  (candles, outfit, a specific necklace) and lip-synced lyrics that were
  **not** in the caption at all, confirming this genuinely summarizes the
  video, not just whatever text the poster typed
  ✅ Verified again through the real `handle_message` pipeline end-to-end
  (processing message → download → Gemini video description → normal
  summarize() → full TL;DR/KEY POINTS/TAKEAWAY, since the description was
  long enough to earn the full format) — saved correctly with
  `source: "tiktok"` and the real author extracted from yt-dlp's metadata
- ✅ New `app/extractors/tiktok.py`: downloads video via yt-dlp to a temp
  dir, uploads to Gemini, asks for a description, cleans up both the temp
  file and the uploaded Gemini copy in a `finally` block regardless of
  outcome; wrapped in an overall 120s timeout (video processing is much
  slower than text) and a 200MB download size cap
  ✅ Sends a "🎥 Downloading and analyzing..." heads-up before starting,
  since this can take much longer than any other input type and silence
  during a 30-120s wait would look like the bot hung
  ✅ Feeds into the *existing* summarize() pipeline unchanged (Combine
  Mode's `RELATED_ID`, the short-content compact format, everything) by
  producing plain text like every other extractor — no changes needed to
  `app/ai/summarizer.py` or `app/ai/prompts.py`
- ✅ `detect_unsupported_platform()`'s domain dict is now empty (kept as an
  extensibility point, see `app/extractors/base.py`) — both Threads and
  TikTok have real extraction now
- ✅ 3 new tests for the pure caption-combination helper; the
  download/upload/describe pipeline itself is network- and
  filesystem-dependent like the other extractors, so it was verified live
  rather than mocked, consistent with the rest of this project's testing
  approach

### Major revision — multi-user support with per-user data isolation (user-requested, not a planned phase)
- **Why:** the user asked to make the bot "publicly available to be used
  by anyone." Given the risks discussed and confirmed with the user first
  (no per-user data isolation existed at all; the owner's Gemini key
  would foot the bill for every user with no cap; TikTok downloading at
  true public scale is a different risk category than one person's
  personal use; the bot only runs while the owner's own machine does),
  this landed as **a private allowlist of multiple people, each with
  fully isolated data, no usage caps for now** — not literally open to
  anyone on Telegram.
- ✅ `AUTHORIZED_USER_IDS` (comma-separated, ordered) replaces the old
  singular `AUTHORIZED_USER_ID` — `config.is_authorized()` now checks
  list membership; `.env`, `.env.example`, and the real local `.env` all
  updated
- ✅ New `user_id` column on `summaries`, backfilled via a guarded
  migration (same pattern as `previous_summary`) — pre-existing rows are
  assigned to whichever id is *first* in `AUTHORIZED_USER_IDS`, i.e. the
  original solo owner
- ✅ Every database function now takes an explicit `user_id` and scopes
  its query to it: `save_summary`, `get_recent`, `get_by_id`, `list_items`,
  `search_items`, `update_merged_summary`, `delete_item`, `undo_merge`.
  `get_by_id` in particular checks `id AND user_id` together, not just
  `id` — the specific thing that stops one user from viewing, merging,
  undoing, or deleting another user's row even by guessing its numeric id
- ✅ Every call site in `app/bot/commands.py` and `app/bot/handlers.py`
  updated to pass `update.effective_user.id` through — Combine Mode's
  related-item check, the plain-message save, and all six management
  commands (`/list`, `/search`, `/view`, `/merge`, `/delete`, `/undo`)
  plus their button-triggered callback equivalents
- ✅ 8 new isolation-specific tests at the database layer (cross-user
  `get_recent`/`list_items`/`search_items` exclusion; `get_by_id` and
  `delete_item` returning "not found" for another user's real row;
  `update_merged_summary`/`undo_merge` refusing to touch another user's
  row) plus a migration test confirming legacy rows backfill to the
  first configured id
- ✅ Verified live end-to-end with two distinct simulated Telegram user
  ids sharing one bot process and one database: `/list` for each user
  showed only their own item; User B's `/view`, `/delete`, and `/merge`
  attempts against User A's real, existing item were all correctly
  refused with "not found" rather than silently succeeding or leaking
  data — the critical security property this whole change exists for
- ⚠️ **Known, accepted gaps at the time** (explicitly signed off on by
  the user rather than silently decided): no per-user usage caps on
  Gemini API calls; no dedicated hosting. Both addressed next, below.

### Follow-up — per-user Gemini API keys, replacing the "no usage caps" gap
- **Why:** the accepted gap above meant one invited user (especially via
  the TikTok video path — the most expensive call) could consume the
  owner's entire Gemini quota/budget with nothing stopping them. Rather
  than build rate limiting, the user chose the cleaner fix: make everyone
  pay for their own usage.
- ✅ New `user_settings` table (`user_id` → `gemini_api_key`), explicitly
  documented as plaintext with no encryption at rest — same trust model
  as the rest of this SQLite-based project, worth knowing if the
  allowlist ever grows past a small trusted group
- ✅ `resolve_gemini_api_key(user_id)`: a personal key (set via `/setkey`)
  always wins; otherwise only the *first* id in `AUTHORIZED_USER_IDS`
  (the original owner) falls back to the shared `.env` key — every other
  invited user gets `None` and must set their own. This is the one
  function every Gemini-calling code path goes through, so there's a
  single place the policy lives
- ✅ `app/ai/summarizer.py` and `app/extractors/tiktok.py` no longer build
  one fixed module-level `genai.Client` at import time — every call now
  takes the caller's resolved key and constructs a client per-request
- ✅ New `/setkey <api_key>` command: makes one small live Gemini call to
  validate the key *before* saving it (so a typo fails immediately with a
  clear message, not on the user's next real summary attempt), then
  best-effort deletes the message containing the raw key from chat
  history
- ✅ The "no key" check happens in `handle_message` *before* any
  extraction work starts (right after the empty-input check) — so a user
  without a key never triggers a TikTok download or web fetch only to
  fail at the summarize step; `handle_merge_callback` checks it right
  before the actual merge call, but *after* the free "view"/"decline"
  branches, which need no Gemini call at all
- ✅ 9 new tests for the API-key DB functions (get/set/overwrite/per-user
  scoping, and all three `resolve_gemini_api_key` branches); verified
  live end-to-end: a non-owner sending anything was correctly blocked
  with a `/setkey` prompt *before* any Gemini call fired, `/setkey` with
  a garbage key was correctly rejected without being stored, and
  `/setkey` with a (mocked-valid) key correctly deleted the message,
  stored the key, and made `resolve_gemini_api_key` return it immediately

### Follow-up — hosting, replacing the "runs only on the owner's machine" gap
See `DEPLOY.md` for the full setup. Summary: a free-tier always-on cloud
VM running the bot as a `systemd` service (auto-restart on crash, starts
on boot), so it no longer depends on the owner's own laptop being open.
