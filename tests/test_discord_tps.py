"""Unit tests for discord-tps against a fake discord module and bot."""

from __future__ import annotations

import asyncio
import enum
import importlib.util
import sys
import types
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "discord-tps" / "__init__.py"


class _ActivityType(enum.Enum):
    playing = 0
    listening = 2
    watching = 3
    competing = 5


class _Activity:
    def __init__(self, type, name):
        self.type, self.name = type, name


class _CustomActivity:
    def __init__(self, name):
        self.type, self.name = "custom", name


sys.modules["discord"] = types.SimpleNamespace(
    ActivityType=_ActivityType, Activity=_Activity, CustomActivity=_CustomActivity
)


class Ctx:
    def __init__(self, conf=None):
        self.conf = conf or {}
        self.hooks = {}
        self.handlers = {}

    def get_config(self, key, default):
        return self.conf.get(key, default)

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_platform_handler(self, name, fn):
        self.handlers[name] = fn


class Bot:
    def __init__(self):
        self.closed = False
        self.activities = []

    async def wait_until_ready(self):
        pass

    def is_closed(self):
        return self.closed

    async def change_presence(self, activity):
        self.activities.append((activity.type, activity.name))


@pytest.fixture
def plugin(monkeypatch):
    spec = importlib.util.spec_from_file_location("discord_tps", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(mod.asyncio, "sleep", lambda _t: real_sleep(0.01))
    return mod


def call(ctx, sid="a", model="vendor/model-x", out=100, dur=2.0):
    ctx.hooks["post_api_request"](
        session_id=sid, model=model, usage={"output_tokens": out}, api_duration=dur
    )


def run_bot(plugin, conf, steps):
    """Wire a bot, run each step with a tick in between, then close it."""

    async def main():
        ctx = Ctx(conf)
        plugin.register(ctx)
        bot = Bot()
        ctx.handlers["discord"](bot, None)
        task = bot._discord_tps_task
        ctx.handlers["discord"](bot, None)  # second wire is a no-op
        assert bot._discord_tps_task is task
        await asyncio.sleep(0.03)
        for step in steps:
            step(ctx)
            await asyncio.sleep(0.03)
        bot.closed = True
        await asyncio.sleep(0.03)
        assert task.done()
        return bot.activities

    return asyncio.run(main())


def test_default_is_custom_with_idle_then_rate(plugin):
    acts = run_bot(plugin, {}, [call])
    assert acts == [("custom", "idle"), ("custom", "50 tok/s · model-x")]


def test_verb_activity_type_case_insensitive(plugin):
    acts = run_bot(plugin, {"activity_type": " Watching "}, [call])
    assert acts[-1] == (_ActivityType.watching, "50 tok/s · model-x")


def test_failed_call_does_not_take_over(plugin):
    def failed(ctx):
        ctx.hooks["post_api_request"](session_id="b", model="x/y", usage=None, api_duration=1)

    acts = run_bot(plugin, {}, [call, failed])
    assert acts[-1] == ("custom", "50 tok/s · model-x")


def test_rolling_rate_and_idle_text(plugin):
    ctx = Ctx({"idle_after": 0})
    plugin.register(ctx)
    call(ctx, out=100, dur=2)
    call(ctx, out=50, dur=2)
    assert plugin._latest[0] == pytest.approx(37.5)
    assert plugin._presence_text(3600, "idle") == "38 tok/s · model-x"
    assert plugin._presence_text(-1, "idle") == "idle · model-x"


def test_session_cap(plugin):
    ctx = Ctx()
    plugin.register(ctx)
    for i in range(plugin._MAX_SESSIONS + 10):
        call(ctx, sid=str(i))
    assert len(plugin._windows) == plugin._MAX_SESSIONS
    assert "0" not in plugin._windows


def test_bad_config_falls_back(plugin):
    ctx = Ctx({"interval": "fast", "idle_after": None, "idle_text": ""})
    plugin.register(ctx)  # must not raise
    assert "post_api_request" in ctx.hooks and "discord" in ctx.handlers
