# discord-tps

**discord-tps** is a Hermes Agent plugin that shows live tokens-per-second and the
active model on a Discord bot's presence.

## Plugin location

The plugin lives in the [`discord-tps/`](./discord-tps/) subdirectory:

- `discord-tps/plugin.yaml` — manifest
- `discord-tps/__init__.py` — entrypoint
- `discord-tps/README.md` — user documentation
- `discord-tps/LICENSE` — MIT license

Install with:

```bash
hermes plugins install tuancookiez-hub/hermes-discord-tokenpersec --subdir discord-tps
```

## Validate locally

```bash
hermes plugins validate ./discord-tps --install-deps
```

## CI

`.github/workflows/ci.yml` runs on every push and PR:

- **test**: ruff, the unit tests in `tests/`, and `ci/check_entry.py`, which checks that the catalog entry matches `plugin.yaml` and pins a reachable commit with no plugin changes after it.
- **catalog-gates**: the same two gates as Hermes' Plugin Catalog CI, run from a Hermes checkout (`HERMES_REF`): the structural entry check and `hermes plugins validate`'s admission checks.

## Plugin catalog

`discord-tps` is listed in the Hermes plugin catalog
([NousResearch/hermes-agent#135259](https://github.com/NousResearch/hermes-agent/pull/135259)).
`plugin-catalog-entry.yaml` mirrors the live `plugin-catalog/discord-tps.yaml` there.

- `sha` must be the full 40-character commit that contains the plugin code being listed.
- Every update bumps both `sha` and `version` in a new PR.

Surfaces used:

- `post_api_request` hook (declared in `capabilities`).
- `ctx.register_platform_handler("discord", ...)`, which receives the gateway's own
  discord.py client. No second connection, no token access, no network calls besides
  presence updates on that connection, and no telemetry.

## License

MIT. See [LICENSE](./LICENSE).
