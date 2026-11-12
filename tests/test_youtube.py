import asyncio

from app.extractors import youtube


def test_fetch_watches_canonical_url_at_low_resolution_and_adds_oembed_title(monkeypatch):
    seen = {}

    def fake_generate_text(api_key, contents, timeout, deadline, config):
        seen["uri"] = contents[0].file_data.file_uri
        seen["resolution"] = config.media_resolution
        return "A talk about building live AI agents."

    async def fake_oembed(video_id):
        return {"title": "Building with Gemini 2.0", "author": "Google for Developers"}

    monkeypatch.setattr(youtube, "generate_text", fake_generate_text)
    monkeypatch.setattr(youtube, "_oembed", fake_oembed)

    result = asyncio.run(youtube.fetch_and_extract("9hE5-98ZeCg", "key"))

    assert seen["uri"] == "https://www.youtube.com/watch?v=9hE5-98ZeCg"
    assert seen["resolution"] == youtube.types.MediaResolution.MEDIA_RESOLUTION_LOW
    assert result == {
        "title": "Building with Gemini 2.0",
        "author": "Google for Developers",
        "text": "A talk about building live AI agents.",
    }


def test_fetch_still_works_without_oembed(monkeypatch):
    async def no_oembed(video_id):
        return {}

    monkeypatch.setattr(youtube, "generate_text", lambda *args: "text")
    monkeypatch.setattr(youtube, "_oembed", no_oembed)
    assert asyncio.run(youtube.fetch_and_extract("9hE5-98ZeCg", "key")) == {"title": None, "author": None, "text": "text"}
