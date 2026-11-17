import httpx
import pytest
from google.genai import errors

from app.ai import gemini
from app.ai.gemini import (
    FAILED,
    INVALID_KEY,
    MODELS,
    QUOTA_DAILY,
    QUOTA_RATE,
    UNAVAILABLE,
    GeminiError,
    generate_text,
)


def _api_error(code: int, message: str) -> errors.APIError:
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": {"code": code, "message": message, "status": "X"}})


DAILY_429 = _api_error(429, "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier")
RATE_429 = _api_error(429, "quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
OVERLOADED_503 = _api_error(503, "This model is currently experiencing high demand.")
BAD_KEY_400 = _api_error(400, "API key not valid. Please pass a valid API key.")
NOT_FOUND_404 = _api_error(404, "models/x is not found")


class _Response:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Plays back a scripted outcome per model, in call order."""

    def __init__(self, script: dict):
        self.script = {model: list(outcomes) for model, outcomes in script.items()}
        self.calls: list[str] = []
        self.models = self

    def generate_content(self, model, contents, config=None):
        self.calls.append(model)
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda _seconds: None)

    def install(script):
        client = _FakeClient(script)
        monkeypatch.setattr(gemini.genai, "Client", lambda **_kwargs: client)
        return client

    return install


PRIMARY, FALLBACK_1, FALLBACK_2 = MODELS


def test_returns_primary_model_text(fake_client):
    client = fake_client({PRIMARY: ["hello"]})
    assert generate_text("key", "prompt") == "hello"
    assert client.calls == [PRIMARY]


def test_retries_transient_error_on_same_model(fake_client):
    client = fake_client({PRIMARY: [OVERLOADED_503, "recovered"]})
    assert generate_text("key", "prompt") == "recovered"
    assert client.calls == [PRIMARY, PRIMARY]


def test_retries_network_timeout(fake_client):
    client = fake_client({PRIMARY: [httpx.ReadTimeout("slow"), "ok"]})
    assert generate_text("key", "prompt") == "ok"
    assert client.calls == [PRIMARY, PRIMARY]


def test_falls_back_after_persistent_overload(fake_client):
    client = fake_client({PRIMARY: [OVERLOADED_503, OVERLOADED_503], FALLBACK_1: ["from lite"]})
    assert generate_text("key", "prompt") == "from lite"
    assert client.calls == [PRIMARY, PRIMARY, FALLBACK_1]


def test_quota_skips_straight_to_next_model(fake_client):
    client = fake_client({PRIMARY: [DAILY_429], FALLBACK_1: ["from lite"]})
    assert generate_text("key", "prompt") == "from lite"
    assert client.calls == [PRIMARY, FALLBACK_1]


def test_retired_model_falls_through(fake_client):
    client = fake_client({PRIMARY: [NOT_FOUND_404], FALLBACK_1: ["ok"]})
    assert generate_text("key", "prompt") == "ok"
    assert client.calls == [PRIMARY, FALLBACK_1]


def test_daily_quota_on_every_model(fake_client):
    fake_client({PRIMARY: [DAILY_429], FALLBACK_1: [DAILY_429], FALLBACK_2: [RATE_429]})
    with pytest.raises(GeminiError) as exc_info:
        generate_text("key", "prompt")
    assert exc_info.value.kind == QUOTA_DAILY


def test_rate_limit_on_every_model(fake_client):
    fake_client({PRIMARY: [RATE_429], FALLBACK_1: [RATE_429], FALLBACK_2: [RATE_429]})
    with pytest.raises(GeminiError) as exc_info:
        generate_text("key", "prompt")
    assert exc_info.value.kind == QUOTA_RATE


def test_mixed_quota_and_overload_reports_unavailable(fake_client):
    fake_client(
        {
            PRIMARY: [DAILY_429],
            FALLBACK_1: [OVERLOADED_503, OVERLOADED_503],
            FALLBACK_2: [OVERLOADED_503, OVERLOADED_503],
        }
    )
    with pytest.raises(GeminiError) as exc_info:
        generate_text("key", "prompt")
    assert exc_info.value.kind == UNAVAILABLE


def test_invalid_key_stops_immediately(fake_client):
    client = fake_client({PRIMARY: [BAD_KEY_400]})
    with pytest.raises(GeminiError) as exc_info:
        generate_text("key", "prompt")
    assert exc_info.value.kind == INVALID_KEY
    assert client.calls == [PRIMARY]


def test_empty_responses_everywhere_is_failed(fake_client):
    fake_client({PRIMARY: [""], FALLBACK_1: [None], FALLBACK_2: ["  "]})
    with pytest.raises(GeminiError) as exc_info:
        generate_text("key", "prompt")
    assert exc_info.value.kind == FAILED


class _FakeFiles:
    def __init__(self):
        self.uploaded, self.deleted = [], []

    def upload(self, file, config):
        name = f"files/{len(self.uploaded)}"
        self.uploaded.append((name, config.mime_type))
        return _File(name, "ACTIVE")

    def get(self, name):
        return _File(name, "ACTIVE")

    def delete(self, name):
        self.deleted.append(name)


class _File:
    def __init__(self, name, state):
        self.name = name
        self.state = type("S", (), {"name": state})()

    def __eq__(self, other):
        return isinstance(other, _File) and other.name == self.name


class _RecordingClient:
    def __init__(self, result="described"):
        self.files = _FakeFiles()
        self.models = self
        self.contents = None
        self.result = result

    def generate_content(self, model, contents, config=None):
        self.contents = contents
        if isinstance(self.result, Exception):
            raise self.result
        return _Response(self.result)


def _install(monkeypatch, client):
    monkeypatch.setattr(gemini.genai, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(gemini.time, "sleep", lambda _s: None)


def test_describe_many_inlines_small_images_uploads_video_and_keeps_order(monkeypatch):
    from app.ai.gemini import TEXT_ITEM, describe_many

    client = _RecordingClient()
    _install(monkeypatch, client)

    result = describe_many("key", [(b"img", "image/jpeg"), ("clip.mp4", "video/mp4"), ("a note", TEXT_ITEM)], "describe")

    assert result == "described"
    assert client.files.uploaded == [("files/0", "video/mp4")]
    kinds = [type(c).__name__ for c in client.contents]
    assert kinds == ["Part", "_File", "str", "str"]
    assert client.contents[2:] == ["a note", "describe"]
    assert client.files.deleted == ["files/0"]


def test_describe_many_uploads_large_images(monkeypatch):
    from app.ai.gemini import describe_many

    client = _RecordingClient()
    _install(monkeypatch, client)
    describe_many("key", [(b"x" * (5 * 1024 * 1024), "image/png")], "describe")
    assert client.files.uploaded == [("files/0", "image/png")]


def test_describe_many_deletes_uploads_even_when_gemini_fails(monkeypatch):
    from app.ai.gemini import describe_many

    client = _RecordingClient(result=_api_error(400, "bad request"))
    _install(monkeypatch, client)
    with pytest.raises(GeminiError):
        describe_many("key", [("a.mp4", "video/mp4"), ("b.mp4", "video/mp4")], "describe")
    assert client.files.deleted == ["files/0", "files/1"]
