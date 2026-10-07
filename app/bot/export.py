"""
/export file builders: a readable Markdown file and a complete JSON backup
of one user's saved items.
"""
import json

_EXPORTED_FIELDS = (
    "id",
    "created_at",
    "source",
    "url",
    "title",
    "author",
    "summary",
    "original_text",
    "merged_from",
    "previous_summary",
)


def build_json(items: list[dict]) -> bytes:
    rows = [{field: item.get(field) for field in _EXPORTED_FIELDS} for item in items]
    return json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")


def build_markdown(items: list[dict], exported_on: str) -> bytes:
    lines = [f"# Saved notes — exported {exported_on}", "", f"{len(items)} item(s), newest first.", ""]
    for item in items:
        lines.append(f"## #{item['id']} — {item.get('title') or 'Untitled'}")
        meta = [item["created_at"][:10], item["source"]]
        if item.get("author"):
            meta.append(item["author"])
        lines.append(f"_{' · '.join(meta)}_")
        if item.get("url"):
            lines.append(f"<{item['url']}>")
        if item.get("merged_from"):
            lines.append(f"Merged from: #{item['merged_from'].replace(',', ', #')}")
        lines += ["", item["summary"].strip(), "", "<details><summary>Original text</summary>", ""]
        lines += [item["original_text"].strip(), "", "</details>", "", "---", ""]
    return "\n".join(lines).encode("utf-8")
