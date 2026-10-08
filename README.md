# Hermes Plugin Catalog Submission — discord-tps

This repository holds **`discord-tps`**, a Hermes Agent plugin that publishes
live tokens-per-second and the active model onto a Discord bot's presence.

## Plugin location

The plugin lives in the [`discord-tps/`](./discord-tps/) subdirectory:

- `discord-tps/plugin.yaml` — manifest
- `discord-tps/__init__.py` — entrypoint
- `discord-tps/README.md` — user documentation

Install with:

```bash
hermes plugins install tuancookiez-hub/hermes-discord-tokenpersec --subdir discord-tps
```

## Validate locally

```bash
hermes plugins validate ./discord-tps --install-deps
```

## License

MIT
