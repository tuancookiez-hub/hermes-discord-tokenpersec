"""discord-tps — publish tok/s and the active model on the Discord bot presence.

Rides the gateway's own discord.py Bot through register_platform_handler, so
presence is published on the one live connection — no competing second client.
The post_api_request hook feeds a rolling window that yields the same tok/s
number the desktop/terminal status bars show.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

logger = logging.getLogger("hermes_plugins.discord_tps")

# Rolling window of (output_tokens, api_duration) — matches agent/turn_usage.py.
_WINDOW = 10
_MAX_SESSIONS = 32
# session_id -> {samples, model, seen}; insertion order == recency, last is active.
_sessions: dict[str, dict] = {}
_tasks: dict[int, asyncio.Task] = {}  # id(bot) -> presence task


def _short_model(model: str) -> str:
    """Drop the vendor prefix: 'stepfun/step-5-preview:free' -> 'step-5-preview:free'."""
    return model.rsplit("/", 1)[-1]


def _presence_text(idle_after: int, idle_text: str) -> str:
    s = next(reversed(_sessions.values()), None)
    if s is None:
        return idle_text
    model = _short_model(s["model"])
    if time.time() - s["seen"] > idle_after:
        return f"{idle_text} · {model}" if model else idle_text
    out = sum(o for o, _ in s["samples"])
    dur = sum(d for _, d in s["samples"])
    return f"{out / dur if dur else 0:.0f} tok/s · {model}"


# ── hook ────────────────────────────────────────────────────────────────────


def _on_post_api_request(**kwargs: Any) -> None:
    sid = str(kwargs.get("session_id") or "default")
    # Pop and re-insert so the dict stays ordered by recency.
    s = _sessions.pop(sid, None) or {"samples": deque(maxlen=_WINDOW), "model": "", "seen": 0.0}
    _sessions[sid] = s
    if len(_sessions) > _MAX_SESSIONS:
        del _sessions[next(iter(_sessions))]

    usage = kwargs.get("usage")
    out = float((usage.get("output_tokens") if isinstance(usage, dict) else 0) or 0)
    dur = float(kwargs.get("api_duration") or 0)
    if out > 0 and dur > 0:
        s["samples"].append((out, dur))
    s["model"] = str(kwargs.get("model") or s["model"])
    s["seen"] = time.time()


# ── presence publisher (runs on the gateway bot's own event loop) ───────────


async def _publish(bot: Any, cfg: dict) -> None:
    import discord

    try:
        await bot.wait_until_ready()
    except Exception as exc:
        logger.debug("discord-tps: never became ready: %s", exc)
        return

    atype = getattr(discord.ActivityType, cfg["activity_type"], discord.ActivityType.playing)
    last = None
    while not bot.is_closed():
        try:
            text = _presence_text(cfg["idle_after"], cfg["idle_text"])[:128]
            if text != last:
                if cfg["activity_type"] == "custom":
                    activity = discord.CustomActivity(name=text)
                else:
                    activity = discord.Activity(type=atype, name=text)
                await bot.change_presence(activity=activity)
                last = text
        except Exception as exc:
            logger.warning("discord-tps: presence update failed: %s", exc)
        await asyncio.sleep(cfg["interval"])


# ── registration ─────────────────────────────────────────────────────────────


def register(ctx: Any) -> None:
    def get(key: str, default: Any) -> Any:
        try:
            return ctx.get_config(key, default)
        except Exception:
            return default

    cfg = {
        "activity_type": str(get("activity_type", "playing")),
        # Discord allows ~5 presence updates per 20s; don't go below 10s.
        "interval": max(10, int(get("interval", 20))),
        "idle_after": int(get("idle_after", 300)),
        "idle_text": str(get("idle_text", "idle") or "idle"),
    }
    ctx.register_hook("post_api_request", _on_post_api_request)

    def wire(bot: Any, adapter: Any) -> None:
        task = _tasks.get(id(bot))
        if task is not None and not task.done():
            return
        loop = getattr(bot, "loop", None) or asyncio.get_running_loop()
        _tasks[id(bot)] = loop.create_task(_publish(bot, cfg))
        logger.info("discord-tps: publishing tok/s + model every %ss", cfg["interval"])

    ctx.register_platform_handler("discord", wire)
    logger.info("discord-tps: armed (%s, every %ss)", cfg["activity_type"], cfg["interval"])
