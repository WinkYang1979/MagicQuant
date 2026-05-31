# MagicQuant Codebase Layout

VERSION : v0.1.0
DEPENDS : AGENTS.md

This repository contains active production code, research scripts, generated data, and historical deployment copies. Use this map to avoid editing the wrong version.

## Production Code

- `bot/`: Telegram bot entrypoint and command handling.
- `config/`: shared runtime settings and path constants.
- `core/`: active trading, focus, risk, quote, and agent logic.
- `dashboard/`: active dashboard surface.
- `tests/`: regression tests for active code.

## Research And Operations

- repository-root scripts such as `run_rklb_analysis.py`, `strategy_optimizer.py`, and `verify_signals.py`: manual research or operational helpers.
- `root/`: daily briefing and compatibility scripts still referenced by tests.
- `docs/`: human-facing notes and project documentation.

## Generated Or Historical Areas

- `data/`: runtime state, review output, historical bars, and generated reports. Do not treat JSON/HTML here as source logic.
- `DEPLOY_AI_RACE/`, `files/`, `core_focus/`: historical or deployment copies. Prefer the active `core/`, `bot/`, and `dashboard/` paths unless a task explicitly targets these copies.
- `TradingAgents/build/`: build output. Source lives under `TradingAgents/tradingagents/`.

## Editing Rule

When making production behavior changes, default to `bot/`, `config/`, `core/`, `dashboard/`, and `tests/`. Mention duplicate historical copies when relevant, but do not update them unless the user asks for deployment-copy synchronization.

## Version Header Template

Every new Python source file should start with a module docstring containing:

```text
VERSION : vX.Y.Z
DEPENDS : package.module, other_dependency
```

For tests, `DEPENDS` should name the production modules under test. For scripts, it should name the key runtime APIs or files they require.
