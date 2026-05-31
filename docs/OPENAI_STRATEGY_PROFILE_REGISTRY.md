# OpenAI Strategy Profile Registry

VERSION: v0.1.0
DEPENDS: core/sim_weekly/openai_contestant.py, docs/STRATEGY_SCORECARD.md, data/sim_weekly/duel_backtest_*.json

Purpose:
- Record every meaningful OpenAI duel strategy profile as a searchable candidate.
- Preserve the testing method, objective function, time window, tags, and known failure modes.
- Avoid rediscovering the same parameters by memory or mood.

## Search Method

Default comparison algorithm:
1. Select candidate profiles.
2. Replay identical weeks with identical data, fees, slippage, and capital.
3. Compare week-by-week returns.
4. Compare cumulative weekly return spread.
5. Compare drawdown, losing sell count, and trade count.
6. Assign regime/time tags.
7. Pick by the user's stated objective:
   - Profit maximization: prefer highest cumulative weekly return unless drawdown violates an explicit limit.
   - Defense / capital preservation: prefer lower worst week, lower drawdown, and fewer losing sells.

Rolling windows:
- Fast warning window: latest 2 weeks, recency weighted.
- Formal review window: latest 4 weeks, recency weighted.
- Profit context window: latest 8 weeks when enough data exists.

## Profiles

### openai_duel_v1.9

Status: current default

Objective:
- Profit maximization with high-gap chase protection.

Execution discipline:
- RKLB is signal-only, never execution.
- RKLX is the default long execution instrument.
- RKLZ is supported but default allocation is 0; do not short unless a future profile proves stable edge.

Core parameters:
- `rklx_fraction`: 0.80
- `rklx_weak_fraction`: 0.30
- `rklx_stop_pct`: 0.09
- `rklx_min_week_change`: 3.0
- `rklx_high_gap_atr`: 2.5
- `rklx_high_gap_min_week_change`: 8.0
- `profit_lock_trigger_pct`: 0.04
- `profit_trail_gain_share`: 0.10
- `monday_no_new_after`: 14:30 ET
- `weekly_halt_drawdown_pct`: 0.10

Recent 8-week profile comparison:
- Window: 2026-04-06 through 2026-05-25.
- v1.9 total return: +32.98%.
- v1.9 compounded return: +34.87%.
- v1.9 final equity from $10,000: $13,486.90.
- v1.8 total return: +31.87%.
- v1.9 cumulative spread over v1.8: +1.11 percentage points simple, +1.53 percentage points compounded.

Tags:
- `profit_max`
- `rklx_long_only`
- `bull_week_rider`
- `high_gap_chase_guard`
- `large_up_week_capture`
- `no_default_short`
- `monday_late_guard`

Best-fit regimes:
- Big bull weeks / 大牛周.
- Confirmed RKLX ride conditions where high `gapATR` is backed by strong weekly RKLB strength.
- Weeks similar to 2026-04-13 and 2026-05-04.

Poor-fit regimes:
- Short-window chop.
- High `gapATR` fake breakouts where weekly RKLB strength is still below +8%.

Known risks:
- Improvement over v1.8 is modest, not a structural leap.
- Still trails buy-and-hold RKLX in very strong bull weeks.
- The guard may skip some early breakouts that later become real bull moves.

### openai_duel_v1.8

Status: archived candidate

Objective:
- Profit maximization.

Execution discipline:
- RKLB is signal-only, never execution.
- RKLX is the default long execution instrument.
- RKLZ is supported but default allocation is 0; do not short unless a future profile proves stable edge.

Core parameters:
- `rklx_fraction`: 0.80
- `rklx_weak_fraction`: 0.30
- `rklx_stop_pct`: 0.09
- `rklx_min_week_change`: 3.0
- `profit_lock_trigger_pct`: 0.04
- `profit_trail_gain_share`: 0.10
- `monday_no_new_after`: 14:30 ET
- `weekly_halt_drawdown_pct`: 0.10

Recent 8-week profile comparison:
- Window: 2026-04-06 through 2026-05-25.
- v1.8 total return: +31.87%.
- v1.7 total return: +2.43%.
- v1.8 cumulative spread over v1.7: +29.44 percentage points.

Tags:
- `profit_max`
- `rklx_long_only`
- `bull_week_rider`
- `large_up_week_capture`
- `no_default_short`
- `monday_late_guard`

Best-fit regimes:
- Big bull weeks / 大牛周.
- Confirmed RKLX ride conditions where missing upside is more costly than taking small defensive losses.
- Weeks similar to 2026-04-13 and 2026-05-04, where v1.8 captured far more upside than defensive profiles.

Poor-fit regimes:
- Very recent defensive 2-week window where short-term chop matters more than upside capture.
- Fast fake-breakout weeks where RKLX gives back early gains.
- Weeks similar to 2026-05-18 and 2026-05-25, where v1.7 was steadier.

Known risks:
- Can underperform a short-window defensive profile in the latest 2-week sample.
- Still trails buy-and-hold RKLX in very strong bull weeks, though with far lower drawdown.
- The Monday late-session guard helps, but other special time windows are evidence-only for now.

### openai_duel_v1.7

Status: archived candidate

Objective:
- Defensive recent-window optimization.

Core parameters:
- `rklx_fraction`: 0.30
- `rklx_weak_fraction`: 0.45
- `rklx_stop_pct`: 0.09
- `rklx_min_week_change`: 1.5
- `profit_trail_gain_share`: 0.25

Recent comparison:
- Latest 2 weeks: +1.13% total, better than v1.8.
- Latest 4 weeks: +10.04% total in direct parameter search; default scorecard replay showed +2.51% average.
- Latest 8 weeks: +2.43% total, far behind v1.8.

Tags:
- `defensive`
- `recent_2w`
- `reduced_worst_recent_week`
- `not_profit_max`

Best-fit regimes:
- Recent choppy periods where minimizing worst week matters more than maximizing upside.

Poor-fit regimes:
- Big bull weeks / 大牛周.
- Any objective where cumulative profit is the primary target.
