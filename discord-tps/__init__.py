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
_sessions: dict[str, dict] = {}  # session_id -> {samples, model, seen, label}
_publishers: dict[int, Any] = {}


def _cfg(ctx: Any, key: str, default: Any) -> Any:
    try:
        return ctx.get_config(key, default)
    except Exception:
        return default


def _short_model(model: str) -> str:
    """Drop the vendor prefix: 'stepfun/step-5-preview:free' -> 'step-5-preview:free'."""
    return model.split("/")[-1] if model else ""


def _slot(sid: str) -> dict:
    s = _sessions.get(sid)
    if s is None:
        s = {"samples": deque(maxlen=_WINDOW), "model": "", "seen": 0.0, "label": f"S{len(_sessions) + 1}"}
        _sessions[sid] = s
    return s


def _tok_per_sec(samples: deque) -> float:
    if not samples:
        return 0.0
    out = sum(x[0] for x in samples)
    dur = sum(x[1] for x in samples)
    return out / dur if dur > 0 else 0.0


def _active() -> dict | None:
    """The most recently active session."""
    if not _sessions:
        return None
    return max(_sessions.values(), key=lambda s: s["seen"])


def _text(s: dict | None, idle_after: int, idle_base: str) -> str:
    if s is None or time.time() - s["seen"] > idle_after:
        model = _short_model(s["model"]) if s else ""
        base = idle_base or "idle"
        return f"{base} · {model}" if model else base
    return f"{_tok_per_sec(s['samples']):.0f} tok/s · {_short_model(s['model'])}"


# ── hook ────────────────────────────────────────────────────────────────────


def _on_post_api_request(**kwargs: Any) -> None:
    usage = kwargs.get("usage") if isinstance(kwargs.get("usage"), dict) else {}
    out = float(usage.get("output_tokens") or 0)
    dur = float(kwargs.get("api_duration") or 0)
    s = _slot(str(kwargs.get("session_id") or "default"))
    if out > 0 and dur > 0:
        s["samples"].append((out, dur))
    s["model"] = str(kwargs.get("model") or s["model"])
    s["seen"] = time.time()


# ── presence publisher (runs on the gateway bot's own event loop) ───────────


class _Publisher:
    def __init__(self, bot: Any, cfg: dict) -> None:
        self.bot = bot
        self.cfg = cfg
        self.task: asyncio.Task | None = None
        self.stopped = asyncio.Event()
        self.last = ""

    def start(self) -> None:
        if self.task and not self.task.done():
            return
        loop = getattr(self.bot, "loop", None) or asyncio.get_event_loop()
        self.task = loop.create_task(self._run())

    def stop(self) -> None:
        self.stopped.set()
        if self.task and not self.task.done():
            self.task.cancel()

    async def _run(self) -> None:
        ready = getattr(self.bot, "wait_until_ready", None)
        if ready is not None:
            try:
                await ready()
            except Exception as exc:
                logger.debug("discord-tps: never became ready: %s", exc)
                return
        interval = max(10, int(self.cfg.get("interval", 20)))
        while not self.stopped.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("discord-tps: presence update failed: %s", exc)
            try:
                await asyncio.wait_for(self.stopped.wait(), timeout=interval)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                raise

    def _text(self) -> str:
        return _text(
            _active(),
            int(self.cfg.get("idle_after", 300)),
            self.cfg.get("idle_text") or "idle",
        )

    async def _tick(self) -> None:
        text = self._text()
        if text == self.last:
            return
        closed = getattr(self.bot, "is_closed", None)
        if callable(closed) and self.bot.is_closed():
            self.stopped.set()
            return
        import discord

        kind = str(self.cfg.get("activity_type", "playing"))
        if kind == "custom":
            activity = discord.CustomActivity(name=text)
        else:
            atype = getattr(discord.ActivityType, kind, discord.ActivityType.playing)
            activity = discord.Activity(type=atype, name=text[:128])
        await self.bot.change_presence(activity=activity)
        self.last = text


def _wire(bot: Any, adapter: Any, cfg: dict) -> None:
    key = id(bot)
    existing = _publishers.get(key)
    if existing is not None:
        if existing.task and not existing.task.done():
            return
        existing.stop()
    pub = _Publisher(bot, cfg)
    _publishers[key] = pub
    pub.start()
    logger.info("discord-tps: publishing tok/s + model every %ss", cfg.get("interval", 20))


# ── registration ─────────────────────────────────────────────────────────────


def register(ctx: Any) -> None:
    cfg = {
        "activity_type": _cfg(ctx, "activity_type", "playing"),
        "interval": _cfg(ctx, "interval", 20),
        "idle_after": _cfg(ctx, "idle_after", 300),
        "idle_text": _cfg(ctx, "idle_text", "idle"),
    }
    ctx.register_hook("post_api_request", _on_post_api_request)

    def _wire_discord(bot: Any, adapter: Any) -> None:
        _wire(bot, adapter, cfg)

    ctx.register_platform_handler("discord", _wire_discord)
    logger.info("discord-tps: armed (%s, every %ss)", cfg["activity_type"], cfg["interval"])
