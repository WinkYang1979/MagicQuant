# MagicQuant Agent Memory

VERSION: v0.1.0  
DEPENDS: docs/PROJECT_MEMORY_INDEX.md, docs/STRATEGY_SCORECARD.md

This file is the canonical long-term memory for AI agents working on MagicQuant. It is not a strategy rule by itself. It is a guardrail so future Codex/Claude sessions do not forget hard-earned project lessons.

## How To Use

- Read this file before changing trading logic, signal wording, data fetching, or scheduler behavior.
- Treat these memories as high-priority context, but still verify against current code and data.
- Do not store secrets, API keys, Telegram tokens, or full account credentials here.
- If a memory conflicts with live code or fresh replay results, write down the conflict instead of silently choosing one.

## User Operating Preference

- The user prioritizes accurate direction signals over automated position sizing.
- The user decides position size and final buy/sell action personally.
- Avoid disclaimer-style filler such as "position is your decision" or "only for reference" in signal text.
- Useful signal text should answer: current direction, confidence honesty, entry area, invalidation/stop area, key support/resistance, and what changed since the last signal.
- During a position, the user wants fewer noisy take-profit prompts and more useful trend-validity updates.
- Holding follow-up should focus on: trend still valid, top risk, cost retest, invalidation, and data trust.

## Strategy Governance

- Do not change strategy logic from one screenshot or one emotional trading outcome.
- Clear bugs can be fixed directly; strategy behavior changes require replay/backtest and scorecard notes.
- Strategy changes must update `docs/STRATEGY_SCORECARD.md` with benchmark comparison when available.
- Keep the current best live strategy as benchmark. Historical favorite: v0.5.31 direction sensitivity, but only after K_5M data trust fixes.
- Separate "direction accuracy" work from "holding follow-up" work. Mixing both makes replay conclusions noisy.
- Research code belongs under `research/` and must not enter live watchlist or Telegram live trading flow without explicit approval.

## Known Incidents

### K_5M Freeze

- Root symptom: RSI/vol_ratio repeated across days and versions, producing false high-confidence signals.
- Defensive fix: DataQualityGate checks current trading day, K-line age, known stale values, and repeated indicator state.
- K_5M last timestamp must be visible in heartbeat, signal, detail, and review outputs.
- Bad data mode should pause technical direction signals; pure P/L risk alerts may remain, but must say technical indicators are unavailable.

### Stop/Target Too Close

- Previous bug: stop/target used recent tick stdev, effectively pinning stops to tiny floors.
- Fix direction: use true ATR or robust K-line volatility, especially for leveraged tools RKLX/RKLZ.
- Entry and invalidation prices must not be so close that normal noise immediately triggers a stop.

### Premarket Low Volume Strong Signal

- Premarket low-volume bullish signals must not be labeled "strong" purely because day change is large.
- If confidence is capped because volume/session quality is weak, say why in the signal.
- High premarket volume can justify stronger confidence, but only when the volume condition is genuinely met.

### Holding Follow-Up Gap

- Pain case: buying well, then selling near bottom before reversal because follow-up was late or noisy.
- Follow-up should not stack extra exit spam on top of old triggers. It should manage the position state.
- Cost retest and invalidation alerts are more useful than frequent tiny profit-target prompts.

## Data Rules

- Prefer Futu OpenAPI over third-party sources when Futu has the data.
- Any new data fetcher must log success, log detailed failure, and only Telegram-alert when the data matters operationally.
- `fetch_positions` can return list in error paths; normalize before use.
- Snapshot calls are quota-sensitive. Use Focus session cache before hitting API.
- `get_cur_kline` can return error strings; type-check before treating as DataFrame.

## Telegram Content Rules

- Pushes must combine technical parameters with plain-language interpretation.
- Avoid pure parameter dumps.
- For review reports, include the key conclusion and report path.
- Research reports should go to `TG_REVIEW_CHAT_ID`; live trading/system alerts can use `TG_CHAT_ID`.

## Current Research Direction

- VectorBT lab is isolated under `research/vectorbt_lab/`.
- Daily RKLB review should run around local 08:00 after data has settled.
- Weekly candidate research is useful, but does not change live strategy automatically.
- Code understanding tools such as CodeGraph/Understand-Anything should be read-only support, not live trading logic.

## Memory Hygiene

- Confirmed memories go here.
- Open questions and debate drafts go in `docs/discussion_*.md`.
- Reproducible benchmark results go in `docs/STRATEGY_SCORECARD.md`.
- If a remembered rule becomes wrong, update it with date and reason instead of leaving a stale rule.
