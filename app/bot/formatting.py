"""
Shared display formatting for a single saved item — used by /view
(app/bot/commands.py) and the merge suggestion's "view first" button
(app/bot/handlers.py).
"""


def format_full_item(item: dict) -> str:
    lines = [f"#{item['id']} — {item['title'] or 'Untitled'}"]
    lines.append(f"Saved: {item['created_at'][:10]} · Source: {item['source']}")
    if item.get("url"):
        lines.append(f"URL: {item['url']}")
    if item.get("merged_from"):
        merged_ids = "#" + item["merged_from"].replace(",", ", #")
        lines.append(f"Merged from: {merged_ids}")
    lines.append("")
    lines.append(item["summary"])
    return "\n".join(lines)
