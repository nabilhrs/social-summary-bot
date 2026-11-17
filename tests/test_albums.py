import asyncio
from types import SimpleNamespace

from app.bot import handlers
from app.extractors.media import IMAGE, TEXT, VIDEO, MediaInfo


def _msg(message_id, group="g1", caption=None):
    return SimpleNamespace(message_id=message_id, media_group_id=group, caption=caption, replies=[])


def test_album_items_are_collected_and_processed_once_in_order(monkeypatch):
    calls = []

    async def fake_process(parts, user_id):
        calls.append(([p[0].message_id for p in parts], user_id))

    monkeypatch.setattr(handlers, "process_album", fake_process)
    monkeypatch.setattr(handlers, "_ALBUM_WAIT_SECONDS", 0.05)

    async def scenario():
        for message_id in (12, 10, 11):
            handlers.queue_album_item(_msg(message_id), 7, None, None)
            await asyncio.sleep(0.01)
        handlers.queue_album_item(_msg(30, group="g2"), 7, None, None)
        await asyncio.sleep(0.2)

    asyncio.run(scenario())
    assert sorted(calls) == [([10, 11, 12], 7), ([30], 7)]
    assert handlers._albums == {} and handlers._album_timers == {}


_FILES = {}


class _File:
    def __init__(self, data):
        self.data = data
        self.file_id = f"id-{len(_FILES)}"
        _FILES[self.file_id] = self

    async def download_as_bytearray(self):
        return bytearray(self.data)


class _Bot:
    async def get_file(self, file_id):
        return _FILES[file_id]


class _ReplyMessage(SimpleNamespace):
    async def reply_text(self, text, **kwargs):
        self.replies.append(text)

    def get_bot(self):
        return _Bot()


def test_process_album_reads_files_together_and_saves_one_note(monkeypatch):
    seen = {}

    def fake_describe_many(api_key, items, prompt, timeout, deadline):
        seen["items"] = items
        return "Slide 1 says hello. Slide 2 shows a chart."

    async def fake_save(message, user_id, api_key, content):
        seen["content"] = content

    monkeypatch.setattr(handlers, "describe_many", fake_describe_many)
    monkeypatch.setattr(handlers, "_summarize_and_save", fake_save)
    monkeypatch.setattr(handlers, "resolve_gemini_api_key", lambda user_id: "key")

    first = _ReplyMessage(message_id=1, media_group_id="g", caption=None, replies=[])
    second = _ReplyMessage(message_id=2, media_group_id="g", caption="deck from Friday", replies=[])
    parts = [
        (first, _File(b"jpg"), MediaInfo(IMAGE, "photo", "image/jpeg", 3)),
        (second, _File(b"notes"), MediaInfo(TEXT, "document", "text/plain", 5)),
        (second, _File(b"x"), None),  # unsupported file type
        (second, _File(b"big"), MediaInfo(VIDEO, "video", "video/mp4", 999 * 1024 * 1024)),
    ]
    asyncio.run(handlers.process_album(parts, 7))

    assert seen["items"] == [(b"jpg", "image/jpeg"), ("notes", handlers.TEXT_ITEM)]
    assert seen["content"]["source"] == "album"
    assert seen["content"]["text"].startswith("Note from the sender: deck from Friday\n\nSlide 1 says hello.")
    assert first.replies == ["📎 Reading your 2 files together (skipping 2 I can't read) — this may take a moment..."]


def test_process_album_with_nothing_readable_says_so(monkeypatch):
    message = _ReplyMessage(message_id=1, media_group_id="g", caption=None, replies=[])
    asyncio.run(handlers.process_album([(message, _File(b"x"), None)], 7))
    assert message.replies == [handlers.UNSUPPORTED_FILE_TEXT]
