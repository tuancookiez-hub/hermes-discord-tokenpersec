# Add discord-tps to the plugin catalog

## What it does

Shows live tokens-per-second and the active model as the Discord bot's presence.

## Hermes surfaces used

- `post_api_request` hook: reads only `session_id`, `model`, `usage.output_tokens`, and `api_duration`.
- `register_platform_handler("discord")`: receives the native discord.py client at `connect()` and calls only `wait_until_ready`, `is_closed`, and `change_presence`. It stores its task on the client object as `_discord_tps_task` to avoid duplicate publishers.

## Risky behavior

Changes the bot's public Discord presence to show live tok/s and the active model name (visible to anyone who can see the bot). Otherwise none: no credentials read, no extra connections, no filesystem or network I/O beyond presence updates on the gateway's existing connection, no telemetry, no self-update. Presence updates are throttled to at most one per `interval` seconds (minimum 10) and sent only when the text changes.

## Validation

- [ ] `hermes plugins validate ./discord-tps --install-deps` passes at the pinned SHA
