"""
Handler for plain (non-command) messages.

Full pipeline (PRD 5.1-5.4, 5.7, 5.9): detect URL vs plain text -> extract if
URL -> normalize -> summarize -> reply -> save.
"""
import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.config import config
from app.extractors.base import looks_like_url, normalize_pasted_text, normalize_web_article
from app.extractors.webpage import fetch_and_extract
from app.ai.summarizer import summarize
from app.database.database import save_summary

logger = logging.getLogger(__name__)

# PRD 5.9 — fixed error responses for each failure path.
UNAUTHORIZED_TEXT = "Sorry, this bot is private."
INVALID_INPUT_TEXT = "That doesn't look like a link or usable text."
EXTRACTION_FAILED_TEXT = (
    "I couldn't extract this article automatically. Please paste the text here and I'll summarize it."
)
SUMMARY_FAILED_TEXT = "Something went wrong while generating the summary. Please try again."


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message

    if message is None or message.text is None:
        return

    if user is None or not config.is_authorized(user.id):
        await message.reply_text(UNAUTHORIZED_TEXT)
        return

    raw_text = message.text.strip()
    if not raw_text:
        await message.reply_text(INVALID_INPUT_TEXT)
        return

    if looks_like_url(raw_text):
        extracted = await fetch_and_extract(raw_text)
        if extracted is None:
            await message.reply_text(EXTRACTION_FAILED_TEXT)
            return
        content = normalize_web_article(raw_text, extracted)
    else:
        content = normalize_pasted_text(raw_text)

    summary = await summarize(content)
    if summary is None:
        await message.reply_text(SUMMARY_FAILED_TEXT)
        return

    await message.reply_text(summary.text)

    try:
        await asyncio.to_thread(save_summary, content, summary.text)
    except Exception:
        logger.exception("Failed to save summary to database")
