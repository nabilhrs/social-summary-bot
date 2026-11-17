import asyncio
from types import SimpleNamespace

import main


def test_background_tasks_start_on_init_and_are_cancelled_on_stop(monkeypatch):
    started = []

    async def forever(name):
        started.append(name)
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "backfill_loop", lambda: forever("backfill"))
    monkeypatch.setattr(main, "digest_loop", lambda bot: forever("digest"))
    monkeypatch.setattr(main, "retry_loop", lambda run_job: forever("retry"))
    monkeypatch.setattr(main, "reminder_loop", lambda bot, keyboard_for: forever("reminders"))

    async def set_my_commands(commands):
        pass

    app = SimpleNamespace(bot=SimpleNamespace(set_my_commands=set_my_commands), bot_data={})

    async def lifecycle():
        await main._post_init(app)
        await asyncio.sleep(0)
        tasks = app.bot_data["background_tasks"]
        assert sorted(started) == ["backfill", "digest", "reminders", "retry"]
        await main._post_stop(app)
        return tasks

    tasks = asyncio.run(lifecycle())
    assert all(task.cancelled() for task in tasks)


def test_post_stop_without_tasks_is_a_no_op():
    asyncio.run(main._post_stop(SimpleNamespace(bot_data={})))


def test_action_button_pattern_covers_every_action():
    import re

    pattern = next(
        h.pattern.pattern for handlers in main.build_app().handlers.values() for h in handlers
        if getattr(h, "callback", None) is main.handle_action_callback
    )
    for action in ("rename", "cat", "newcat", "note", "transcript", "remind"):
        assert re.match(pattern, f"act:{action}:12")
