"""
Background jobs started with the bot: filling in titles/categories for
items saved before those existed.
"""
import asyncio
import logging

from app.ai.gemini import GeminiError
from app.ai.summarizer import organize_items
from app.config import config
from app.database.database import (
    get_categories,
    get_items_missing_category,
    resolve_gemini_api_key,
    update_fields,
)

logger = logging.getLogger(__name__)

_BACKFILL_RETRY_SECONDS = 6 * 60 * 60


async def backfill_user(user_id: int) -> int:
    """Gives every uncategorized item a category, and a title if it has none.
    Returns how many items were updated."""
    items = await asyncio.to_thread(get_items_missing_category, user_id)
    if not items:
        return 0
    api_key = await asyncio.to_thread(resolve_gemini_api_key, user_id)
    if api_key is None:
        return 0

    existing = [name for name, _count in await asyncio.to_thread(get_categories, user_id)]
    results = await organize_items(items, existing, api_key)

    updated = 0
    for item in items:
        title, category = results.get(item["id"], (None, None))
        fields = {}
        if category:
            fields["category"] = category
        if title and not item.get("title"):
            fields["title"] = title
        if fields:
            await asyncio.to_thread(update_fields, item["id"], user_id, **fields)
            updated += 1
    return updated


async def backfill_loop() -> None:
    while True:
        for user_id in config.authorized_user_ids:
            try:
                updated = await backfill_user(user_id)
                if updated:
                    logger.info("Backfilled titles/categories for %d item(s) of user %s", updated, user_id)
            except GeminiError as exc:
                logger.warning("Backfill for user %s failed (%s); will retry later", user_id, exc.kind)
            except Exception:
                logger.exception("Backfill for user %s crashed", user_id)
        await asyncio.sleep(_BACKFILL_RETRY_SECONDS)
