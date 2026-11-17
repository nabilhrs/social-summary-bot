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
| **A YouTube link** (videos, Shorts, live replays) | Gemini watches the video straight from YouTube and you get a summary of what it covers, under the video's real title. Longer videos take longer. Private and age-restricted videos can't be watched. |
| **A TikTok link** | The video is downloaded and watched: you get a summary of what's shown and said, plus the caption. Takes 30 seconds or more. |
| **An Instagram reel, photo post or carousel link** | Every photo and video in the post is read together, in order: text is transcribed, photos described, and videos watched (what's shown and said), then summarized with the caption. Up to 10 items and about 3 minutes of video per post. |
| **A photo or screenshot** | Any text in it is transcribed, and the rest of the image is described. |
| **A voice note or audio file** | Written down word for word, in the language you spoke, then summarized. |
| **A video file** | Watched and described, then summarized. |
| **A PDF or text file** | Its text is extracted, then summarized. |
| **Several files at once** (an album) | Read together, in order, and saved as **one** note, so a recipe or thread split across 4 screenshots stays in one piece. The reply comes a couple of seconds later while the bot waits for the whole album. |

Add a caption to a file ("recipe to try", "for the Friday meeting") and the bot keeps it as context. Files can be up to 20 MB, which is Telegram's limit for bots.

**Already saved?** If you send a link you saved before, the bot replies **📌 Already saved as #41** instead of summarizing it again, so no quota is spent. It recognises the same link even with a different share suffix (like `?igsh=...` or `?si=...`). Tap **👀 View #41** to see it, or **🔄 Save again** if you want a fresh copy anyway.

---

## 3. What you get back

Every reply has:

- A **title** in bold. Web articles and YouTube videos keep their own title; everything else gets a short one written for it.
- A **📂 category**, like Career or Food & Drink.
- The **summary**. Short notes (under about 80 words) get one or two sentences. Longer content gets:
  - **TL;DR:** the gist in one or two sentences
  - **KEY POINTS:** 3 to 6 bullets
  - **TAKEAWAY:** one sentence
- **Saved as #13**: the note's number, which commands like `/view 13` use.
- Buttons: **✏️ Rename**, **📂 Category**, **📝 Note**, **⭐ Star**, **⏰ Remind me**, **🗑 Delete** (plus **🎙 Edit transcript** for voice notes and audio).

---

## 4. Fixing a save

Use the buttons under the summary (or under `/view <id>`):

- **✏️ Rename:** the bot asks for a new title. Reply to that message with it.
- **📂 Category:** pick one of your categories, or tap **➕ New category** and reply with a name.
- **📝 Note:** reply with your own thoughts ("tried this, works", "ask Sarah about it"). Notes add up, so you can add more later.
- **⭐ Star:** marks the note as a favourite (tap again to unstar). See them all with `/starred`.
- **⏰ Remind me:** pick **Tonight 8pm**, **Tomorrow 9am**, **Saturday 9am**, **Monday 9am** or **In a month**, or **🕐 Other time…** and reply with any time in words ("fri 3pm", "esok pukul 8 pagi"). The bot sends the note back to you then, with its buttons. Handy for a recipe to try this weekend or a tip to use next week. `/reminders` lists what's coming up; tap one to cancel it.
- **🗑 Delete:** asks you to confirm first. This can't be undone.
- **🎙 Edit transcript** (voice notes and audio only): the bot sends what it heard as text you can tap to copy. Paste it into a reply, fix the misheard words, and send it. The bot saves the corrected transcript and rewrites the summary and title from it, keeping the same number and category. You can also check what it heard any time under **🎙 What I heard** in the summary (tap to expand).

The same things work as commands: `/rename 13 Better title`, `/move 13 Travel`, `/note 13 your note` (`/note 13 clear` removes it), `/delete 13`.

**About categories:** the bot picks one for every save and reuses your existing categories whenever they fit, so the list stays short. If it guessed wrong, move the note and future guesses take your categories into account.

**Tidying categories:** `/categories` shows them all. Tap one to:
- **✏️ Rename** it (reply with the new name). Renaming to a name you already have merges the two.
- **🔀 Merge into…** another category, e.g. "Pets" into "Pets & Animals". Its notes all move over.
- **📋 Show notes** in it.

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

**Favourites:** `/starred` lists the notes you've starred, and they also get their own **⭐ Starred** entry in the `/list` menu. Starred notes show a ⭐ in every list.

**Search:** `/search interview` finds notes with that word in the title, summary, original text, your notes or the category.

**Read one in full:** `/view 13`.

**Ask a question:** `/ask` answers from your saved notes only, and shows which notes it used. For example:

> `/ask what were the tips for introducing myself in an interview?`
>
> Use a three-part opener: what you studied, what you've done, and why you're applying (#8, #11). Keep it to 2-3 minutes (#1).

Ask in English or Malay and it answers in the same language. If your notes don't cover the question, it says so instead of guessing.

---

## 7. Reminders and the weekly digest

**Any reminder, not just notes:** `/remind <when> <what>` sets a plain reminder, in English or Malay. You can also just send a message starting with "remind me" or "ingatkan saya".

| You send | You're reminded |
|---|---|
| `/remind tomorrow 7am dentist appointment` | tomorrow at 7:00am |
| `/remind in 2 hours call mum` | in 2 hours |
| `/remind fri 3pm submit the report` | this Friday at 3:00pm |
| `/remind 25/11 9:30am renew road tax` | 25 November at 9:30am (dates are day/month) |
| `/remind tonight take out the trash` | tonight at 8:00pm |
| `remind me next week book the car service` | in a week, at 9:00am |
| `/remind esok pukul 8 pagi temujanji doktor` | tomorrow at 8:00am |
| `/remind 2 jam lagi angkat kain` | in 2 hours |
| `/remind jumaat 2 petang hantar laporan` | Friday at 2:00pm |
| `ingatkan saya malam ini telefon mak` | tonight at 8:00pm |

The time can go at the start or the end ("dentist appointment tomorrow 7am" works too). With a day but no time, it's 9am; "pagi"/"morning" means 9am, "petang"/"afternoon" 4pm/3pm, "malam"/"night" 8pm. The bot always replies with the exact date and time it understood, plus a **❌ Cancel** button, so check it at a glance. Times are read without the AI, so this works instantly, uses no quota, and still works when Gemini is busy.

**Weekly digest:** every Sunday at 9am the bot sends a digest:

- what you saved that week, grouped by category
- one older note from your archive, to remind you it's there

If you saved nothing and there's nothing older to show, it doesn't send anything. Send `/digest` to see it any time.

---

## 8. Backing up

**Automatic:** every Sunday, right after the digest, the bot sends `notes-backup-<date>.json`, a complete copy of all your notes. Keep it (Telegram keeps it in the chat too), and your notes never live only on the server.

**Any time:** send `/export` and the bot sends two files:

- `notes-<date>.md`: every note with its title, category, summary, your notes and the original text. Easy to read on any device.
- `notes-backup-<date>.json`: everything, field by field.

---

## 9. Limits to know about

| What | Limit |
|---|---|
| **Gemini free tier** | Each model has its own daily allowance. When one runs out, the bot moves to the next; the message says when all of them have. Allowances reset at midnight Pacific time (3 or 4pm in Malaysia). |
| **Files and videos** | Count twice: once to read the file, once to summarize it |
| **File size** | 20 MB (Telegram's limit for bots) |
| **Instagram** | Public posts only. Private accounts and stories need a login, and Instagram sometimes blocks the bot's server. |
| **Threads** | Only the post you linked, not the replies under it |
| **Albums and carousels** | Up to 10 items each; Instagram carousels also stop adding videos after about 3 minutes of video in total |

---

## 10. Quick reference

| Command | What it does |
|---|---|
| *(any text, link or file)* | Summarizes and saves it |
| `/list` · `/list <category>` | Browse by category |
| `/starred` | Your starred notes |
| `/search <word>` | Search everything you've saved |
| `/ask <question>` | Answer from your notes, with note numbers |
| `/view <id>` | Show one note in full, with its buttons |
| `/rename <id> <title>` | Change a title |
| `/move <id> <category>` | Change a category (new names create a new one) |
| `/categories` | Rename or merge categories |
| `/note <id> <text>` · `/note <id> clear` | Add your own note, or remove it |
| `/merge <keep_id> <absorb_id>` | Merge two notes into the first |
| `/undo <id>` | Undo the last merge into a note |
| `/delete <id>` | Delete a note (asks first) |
| `/digest` | Show the weekly digest now |
| `/remind <when> <what>` | A reminder in English or Malay, e.g. `/remind tomorrow 7am dentist` |
| `/reminders` | See or cancel upcoming reminders |
| `/export` | Download all your notes |
| `/usage` | Today's Gemini requests per model, and saves waiting to retry |
| `/setkey <key>` | Use a different Gemini API key |
| `/help` | Short version of this guide |

---

## 11. FAQ

**It says Gemini is busy, or the daily quota is used up.**
You don't need to do anything. The bot keeps what you sent and tries again by itself: after 2 minutes, then 5, 15, 30 and 60. If the daily quota ran out, it waits until the quota resets (midnight Pacific time, 3 or 4pm in Malaysia). When it works, the summary arrives as a reply to your original message. If Gemini is still unavailable after about two hours of trying, the bot tells you it stopped, and you can send it again later. This applies to things you send to be saved; `/ask`, merges and transcript edits just tell you to try again.

**How much Gemini quota have I used today?**
Send `/usage`. It shows today's requests per model and how many saves are waiting to retry. Gemini doesn't say how much quota is left, so the bot counts its own requests, and the first time a model runs out it remembers that number as the limit. After that, it sends you a heads-up when the main model is 3 requests away from running out.

**I got a "⚠️ Something broke" message.**
The bot hit an unexpected error and is telling you right away instead of failing silently. The message says roughly where it happened. If the same error keeps happening it's muted for an hour, so you won't get a flood. The full details are in the server log (`journalctl -u social-summary-bot -n 100`).

**An Instagram link didn't work.**
If the bot says it needs a login, the post is private, a story, or Instagram is limiting the server. Send a screenshot or the video file itself and the bot reads that instead.

**The category is wrong.**
Tap **📂 Category** under the summary, or send `/move <id> <category>`.

**I sent the same thing twice.**
For links, the bot catches it before doing any work and replies "Already saved". For text, files and photos it usually notices and offers a merge. Otherwise, delete one with `/delete <id>`.

**A YouTube video didn't work.**
Gemini can only watch public videos. Private, members-only and age-restricted videos fail, and very long ones (several hours) can be too much for one request.

**Can I use it in Malay?**
Yes. Notes, voice notes, questions and searches all work in Malay, English or a mix of both.

**Who can see my notes?**
Only you: the bot answers only your Telegram account. Notes are stored on the machine running the bot and sent to Google Gemini to be summarized, and Google may use free-tier requests to improve its products, so don't send anything confidential.
