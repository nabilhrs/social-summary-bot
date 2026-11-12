# Social Summary Bot: User Guide

The Social Summary Bot keeps a summary of the things you want to remember. Send it a link, some text, a screenshot or a voice note, and it sends back a short summary with a title and a category, and saves it. Later you can browse by category, search, or just ask it a question.

---

## 1. Getting started

Open your bot in Telegram and tap **Start** (or send `/start`). That's it: there's nothing to set up inside the bot. Tap the **/** button next to the message box any time to see every command.

---

## 2. What you can send

| Send | What happens |
|---|---|
| **Text** | Summarized as-is. Forwarded messages work too. |
| **A web article link** | The article text is pulled from the page and summarized. |
| **A Threads post link** | The post's own text is summarized. Replies in the thread aren't visible to the bot, so it reminds you to paste the rest if you want it included. |
| **A TikTok link** | The video is downloaded and watched: you get a summary of what's shown and said, plus the caption. Takes 30 seconds or more. |
| **An Instagram reel or video post link** | Same as TikTok. For a post with several videos, the first one is used. |
| **An Instagram photo post link** | The photos (up to 10 in a carousel) are read: any text in them is transcribed and the rest described, then summarized together with the caption. |
| **A photo or screenshot** | Any text in it is transcribed, and the rest of the image is described. |
| **A voice note or audio file** | Written down word for word, in the language you spoke, then summarized. |
| **A video file** | Watched and described, then summarized. |
| **A PDF or text file** | Its text is extracted, then summarized. |

Add a caption to a file ("recipe to try", "for the Friday meeting") and the bot keeps it as context. Files can be up to 20 MB, which is Telegram's limit for bots.

---

## 3. What you get back

Every reply has:

- A **title** in bold. Web articles keep their own headline; everything else gets a short one written for it.
- A **📂 category**, like Career or Food & Drink.
- The **summary**. Short notes (under about 80 words) get one or two sentences. Longer content gets:
  - **TL;DR:** the gist in one or two sentences
  - **KEY POINTS:** 3 to 6 bullets
  - **TAKEAWAY:** one sentence
- **Saved as #13**: the note's number, which commands like `/view 13` use.
- Four buttons: **✏️ Rename**, **📂 Category**, **📝 Note**, **🗑 Delete**.

---

## 4. Fixing a save

Use the buttons under the summary (or under `/view <id>`):

- **✏️ Rename:** the bot asks for a new title. Reply to that message with it.
- **📂 Category:** pick one of your categories, or tap **➕ New category** and reply with a name.
- **📝 Note:** reply with your own thoughts ("tried this, works", "ask Sarah about it"). Notes add up, so you can add more later.
- **🗑 Delete:** asks you to confirm first. This can't be undone.

The same things work as commands: `/rename 13 Better title`, `/move 13 Travel`, `/note 13 your note` (`/note 13 clear` removes it), `/delete 13`.

**About categories:** the bot picks one for every save and reuses your existing categories whenever they fit, so the list stays short. If it guessed wrong, move the note and future guesses take your categories into account.

---

## 5. Related notes and merging

When something new looks related to an older save, the bot asks:

> This looks related to #4 — STAR Method Interview Tips. Want me to merge these into one summary?

- **Yes, merge:** both are combined into one summary under the older number (#4).
- **No, keep separate:** nothing changes; the new note is already saved.
- **👀 View #4 first:** shows the older note, and the Yes/No buttons stay so you can decide after.

You can also merge any two notes yourself: `/merge 4 13` keeps #4 and folds #13 into it. Changed your mind? `/undo 4` puts back #4's summary from before the last merge.

---

## 6. Finding things later

**Browse:** `/list` shows your categories with how many notes each has. Tap one to see its notes 10 at a time, with **◀ Prev** and **Next ▶**. `/list career` jumps straight to a category. Tap **📚 Categories** to go back.

**Search:** `/search interview` finds notes with that word in the title, summary, original text, your notes or the category.

**Read one in full:** `/view 13`.

**Ask a question:** `/ask` answers from your saved notes only, and shows which notes it used. For example:

> `/ask what were the tips for introducing myself in an interview?`
>
> Use a three-part opener: what you studied, what you've done, and why you're applying (#8, #11). Keep it to 2-3 minutes (#1).

Ask in English or Malay and it answers in the same language. If your notes don't cover the question, it says so instead of guessing.

---

## 7. Weekly digest

Every Sunday at 9am the bot sends a digest:

- what you saved that week, grouped by category
- one older note from your archive, to remind you it's there

If you saved nothing and there's nothing older to show, it doesn't send anything. Send `/digest` to see it any time.

---

## 8. Backing up

Send `/export` and the bot sends two files:

- `notes-<date>.md`: every note with its title, category, summary, your notes and the original text. Easy to read on any device.
- `notes-backup-<date>.json`: everything, field by field. Keep this one as your backup.

---

## 9. Limits to know about

| What | Limit |
|---|---|
| **Gemini free tier** | Each model has its own daily allowance. When one runs out, the bot moves to the next; the message says when all of them have. Allowances reset at midnight Pacific time (3 or 4pm in Malaysia). |
| **Files and videos** | Count twice: once to read the file, once to summarize it |
| **File size** | 20 MB (Telegram's limit for bots) |
| **Instagram** | Public posts only. Private accounts and stories need a login, and Instagram sometimes blocks the bot's server. |
| **Threads** | Only the post you linked, not the replies under it |
| **Photo albums** | Each photo in an album is summarized and saved separately |

---

## 10. Quick reference

| Command | What it does |
|---|---|
| *(any text, link or file)* | Summarizes and saves it |
| `/list` · `/list <category>` | Browse by category |
| `/search <word>` | Search everything you've saved |
| `/ask <question>` | Answer from your notes, with note numbers |
| `/view <id>` | Show one note in full, with its buttons |
| `/rename <id> <title>` | Change a title |
| `/move <id> <category>` | Change a category (new names create a new one) |
| `/note <id> <text>` · `/note <id> clear` | Add your own note, or remove it |
| `/merge <keep_id> <absorb_id>` | Merge two notes into the first |
| `/undo <id>` | Undo the last merge into a note |
| `/delete <id>` | Delete a note (asks first) |
| `/digest` | Show the weekly digest now |
| `/export` | Download all your notes |
| `/setkey <key>` | Use a different Gemini API key |
| `/help` | Short version of this guide |

---

## 11. FAQ

**It says Gemini is overloaded or out of quota.**
The bot already retried and tried two backup models. For "overloaded", wait a few minutes. For "today's free quota", it resets at midnight Pacific time. Nothing you sent is lost; send it again later.

**An Instagram link didn't work.**
If the bot says it needs a login, the post is private, a story, or Instagram is limiting the server. Send a screenshot or the video file itself and the bot reads that instead.

**The category is wrong.**
Tap **📂 Category** under the summary, or send `/move <id> <category>`.

**I sent the same thing twice.**
The bot usually notices and offers a merge. Otherwise, delete one with `/delete <id>`.

**Can I use it in Malay?**
Yes. Notes, voice notes, questions and searches all work in Malay, English or a mix of both.

**Who can see my notes?**
Only you: the bot answers only your Telegram account. Notes are stored on the machine running the bot and sent to Google Gemini to be summarized, and Google may use free-tier requests to improve its products, so don't send anything confidential.
