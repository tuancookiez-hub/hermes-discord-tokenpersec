"""discord-tps — publish tok/s and the active model on the Discord bot presence.

Rides the gateway's own discord.py Bot through register_platform_handler, so
presence is published on the one live connection — no competing second client.
The post_api_request hook feeds a rolling window that yields the same tok/s
number the desktop/terminal status bars show.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import OrderedDict, deque
from typing import Any

logger = logging.getLogger("hermes_plugins.discord_tps")

# Rolling window of (output_tokens, api_duration), like the Hermes status bar average.
_WINDOW = 10
_MAX_SESSIONS = 32
_windows: OrderedDict[str, deque] = OrderedDict()  # session_id -> samples, LRU order
_lock = threading.Lock()  # hooks can fire from concurrent agent threads
# (tok/s, short model, seen) of the most recent call. Replaced in one assignment,
# so the publisher on the bot's loop never reads state the hook is mutating.
_latest: tuple[float, str, float] | None = None


# ── hook ────────────────────────────────────────────────────────────────────


def _on_post_api_request(**kwargs: Any) -> None:
    global _latest
    usage = kwargs.get("usage")
    out = float((usage.get("output_tokens") if isinstance(usage, dict) else 0) or 0)
    dur = float(kwargs.get("api_duration") or 0)
    if out <= 0 or dur <= 0:
        return  # failed/empty calls shouldn't steal the display

    sid = str(kwargs.get("session_id") or "default")
    with _lock:
        samples = _windows.setdefault(sid, deque(maxlen=_WINDOW))
        _windows.move_to_end(sid)
        if len(_windows) > _MAX_SESSIONS:
            _windows.popitem(last=False)
        samples.append((out, dur))
        rate = sum(o for o, _ in samples) / sum(d for _, d in samples)
    # Drop the vendor prefix: 'stepfun/step-5-preview:free' -> 'step-5-preview:free'.
    model = str(kwargs.get("model") or (_latest[1] if _latest else "")).rsplit("/", 1)[-1]
    _latest = (rate, model, time.time())


def _presence_text(idle_after: int, idle_text: str) -> str:
    if _latest is None:
        return idle_text
    rate, model, seen = _latest
    if time.time() - seen > idle_after:
        return f"{idle_text} · {model}" if model else idle_text
    return f"{rate:.0f} tok/s · {model}"


# ── presence publisher (runs on the gateway bot's own event loop) ───────────


async def _publish(bot: Any, cfg: dict) -> None:
    import discord

    try:
        await bot.wait_until_ready()
    except Exception as exc:
        logger.debug("discord-tps: never became ready: %s", exc)
        return

    if cfg["activity_type"] == "custom":
        make = lambda text: discord.CustomActivity(name=text)  # noqa: E731
    else:
        atype = getattr(discord.ActivityType, cfg["activity_type"], discord.ActivityType.playing)
        make = lambda text: discord.Activity(type=atype, name=text)  # noqa: E731

    last = None
    while not bot.is_closed():
        try:
            text = _presence_text(cfg["idle_after"], cfg["idle_text"])[:128]
            if text != last:
                await bot.change_presence(activity=make(text))
                last = text
        except Exception as exc:
            logger.warning("discord-tps: presence update failed: %s", exc)
        await asyncio.sleep(cfg["interval"])


# ── registration ─────────────────────────────────────────────────────────────


def register(ctx: Any) -> None:
    def get(key: str, default: Any, cast: type = str) -> Any:
        try:
            return cast(ctx.get_config(key, default))
        except Exception:
            logger.warning("discord-tps: bad or unreadable %s, using %r", key, default)
            return default

    cfg = {
        "activity_type": get("activity_type", "custom").strip().lower(),
        # Discord allows ~5 presence updates per 20s; don't go below 10s.
        "interval": max(10, get("interval", 20, int)),
        "idle_after": get("idle_after", 300, int),
        "idle_text": get("idle_text", "idle") or "idle",
    }
    ctx.register_hook("post_api_request", _on_post_api_request)

    def wire(bot: Any, adapter: Any) -> None:
        task = getattr(bot, "_discord_tps_task", None)
        if task is not None and not task.done():
            return
        loop = getattr(bot, "loop", None) or asyncio.get_event_loop()
        bot._discord_tps_task = loop.create_task(_publish(bot, cfg))
        logger.info("discord-tps: publishing tok/s + model every %ss", cfg["interval"])

    ctx.register_platform_handler("discord", wire)
    logger.info("discord-tps: armed (%s, every %ss)", cfg["activity_type"], cfg["interval"])
