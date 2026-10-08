# discord-tps

Show live tokens-per-second and the active model on your Discord bot's presence.

![category: platform](https://img.shields.io/badge/category-platform-blue) ![license: MIT](https://img.shields.io/badge/license-MIT-green)

Your Hermes bot's presence turns into a live throughput meter — the same
tok/s number the desktop app and terminal status bar already show, published
straight onto the bot's Discord profile card.

## What it looks like

While the agent is working:

```
Hermes Lydia
Playing 64 tok/s · step-5-preview:free
```

After five minutes of no API activity:

```
Hermes Lydia
Playing idle · step-5-preview:free
```

## How it works

`discord-tps` registers two things, and nothing else:

- **`post_api_request` hook** — records `output_tokens` and `api_duration` from
  each provider call into a rolling 10-sample window. The tok/s figure is
  `sum(output_tokens) / sum(api_duration)`, matching the formula Hermes
  already uses in `agent/turn_usage.py`.
- **Discord platform handler** — via `ctx.register_platform_handler("discord", ...)`.
  The factory receives the gateway's **own already-connected** `discord.py` bot
  at connect time and publishes presence on that connection.

That second point is the important one. The plugin never opens a second
Discord connection and never reads your bot token — it rides the connection
the gateway already holds, so there is no extra login, no credential to
configure, and no `DISCORD_BOT_TOKEN` requirement.

## Requirements

- A Hermes gateway running with the **Discord platform enabled** (a bot token
  configured in `discord.token`). Without it there is no bot to publish on.
- `discord.py` is already a dependency of the Discord adapter, so this plugin
  declares no dependencies of its own.

## Installation

```bash
hermes plugins install tuancookiez-hub/hermes-discord-tokenpersec --subdir discord-tps
hermes plugins enable discord-tps
```

Restart the gateway (or reconnect Discord) and the presence goes live on the
next API call.

## Configuration

All settings live under `plugins.entries.discord-tps.settings` in
`config.yaml`, or via the CLI:

```bash
hermes config set plugins.entries.discord-tps.settings.<key> <value>
```

| Key | Default | Meaning |
|---|---|---|
| `activity_type` | `playing` | `playing`, `listening`, `watching`, `competing`, or `custom` |
| `interval` | `20` | Seconds between refreshes. Discord allows ~5 updates per 20s. |
| `idle_after` | `300` | Seconds of inactivity before the idle text shows. |
| `idle_text` | `idle` | Base idle text; the active model name is appended. |

### Activity types

`activity_type` picks the verb Discord renders:

- `playing` → `Playing 64 tok/s · step-5-preview:free`
- `listening` → `Listening to 64 tok/s · …`
- `watching` → `Watching 64 tok/s · …`
- `competing` → `Competing in 64 tok/s · …`
- `custom` → bare text with no verb

## Multiple sessions

The hook carries `session_id`, so when you talk to the bot in more than one
Discord thread the presence follows whichever session is currently active.
Each new session gets its own tok/s window, and the most recently active one
drives the display.

Model names are shortened for the presence line — the vendor prefix is
dropped, so `stepfun/step-5-preview:free` renders as `step-5-preview:free`.

## License

MIT
