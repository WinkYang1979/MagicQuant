# Strategy Scorecard / 策略版本评分表

VERSION : v0.1
DEPENDS : data/review/*/triggers.json, tests/fixtures/*
BASELINE_COMMIT : 36648f2bce88953c7885ee164dc789b5f5fc1b18
BASELINE_RECORDED_AT : 2026-05-23 weekend P0 review

## Core Rules / 核心规则

1. **Record the best live strategy. / 必须记录当前实盘表现最好的策略版本。**
   - Current benchmark: `v0.5.31 / v0.5.33 Friday baseline`
   - Reason: 上周五版本方向感更强，是当前对比基准；但存在 K_5M 数据冻结风险。

2. **Backtest before strategy changes. / 策略更新必须先用历史日志回测。**
   - Required fixtures:
     - `data/review/2026-05-14/triggers.json` trend-up sample
     - `data/review/2026-05-16/triggers.json` weak-market sample
     - `data/review/2026-05-18/triggers.json` stale-data accident sample
     - 最新一晚 `data/review/YYYY-MM-DD/triggers.json`
   - A strategy change is not valid until it shows equal or better overall behavior.

3. **Compare against the benchmark. / 每次策略更新必须给出和过去策略的准确率/表现对比。**
   - Do not rely on mood, screenshots, or one trade.
   - 每次更新后在本文件追加一条记录，说明：
     - changed logic
     - expected benefit
     - backtest dates
     - signal count change
     - accuracy / favorable-move comparison when available
     - whether it beats the benchmark

4. **Compare cumulative weekly return spread. / 必须比较历史周收益汇总差。**
   - For competing strategy versions, compare week-by-week returns and the cumulative return spread.
   - Latest 2-week / 4-week windows are useful, but a profit-max decision must include total return difference across the selected review window.
   - Prefer the strategy with higher cumulative return when the user objective is profit maximization, unless its drawdown or loss concentration violates an explicit risk limit.

5. **Tag every strategy profile. / 每个策略版本必须打标签。**
   - Record profile tags in `docs/OPENAI_STRATEGY_PROFILE_REGISTRY.md` and `data/sim_weekly/openai_strategy_profiles.json`.
   - Required tags: objective, execution instruments, best-fit regime, poor-fit regime, and known risks.
   - Example: `openai_duel_v1.8` is tagged as `profit_max`, `bull_week_rider`, and `large_up_week_capture`; it is poor-fit for `short_window_chop` and defensive objectives.

## Benchmark

| Version | Status | Strength | Known Risk |
| --- | --- | --- | --- |
| `v0.5.31 / v0.5.33 Friday baseline` | Benchmark | 方向信号更积极，上周五实盘观感最好 | K_5M 冻结时可能误导；数据可信度门禁不足 |
| `v0.5.35 defensive gate` | Current safety base | K_5M 透明显示、DataQualityGate、坏数据 risk-only | 方向信号偏保守，盘中反转表达不足 |

## Change Log

### 2026-05-31 - OpenAI high-gap chase guard v1.9

Strategy Change:
- OpenAI side only: `core/sim_weekly/openai_contestant.py`.
- Added high-gap chase guard for RKLX entries.
- Rule: when `gapATR >= 2.5`, require RKLB weekly change to be at least +8.0%; otherwise skip the RKLX entry.
- Motivation: recent losing trades showed high `gapATR` with only modest weekly strength often behaved like late chase / fake breakout.

Benchmark:
- Claude strategy unchanged by this OpenAI-side update.
- Shared duel runner/scoring unchanged.

Backtest Dates:
- Latest 4 weeks: 2026-05-04 through 2026-05-25.
- Latest 8 weeks: 2026-04-06 through 2026-05-25.

Signal Count Before / After:
- v1.8 latest 4 weeks: average +4.53%, worst -2.99%, 12 entries.
- v1.9 latest 4 weeks: average +4.78%, worst -2.00%, 12 entries.
- v1.8 latest 8 weeks: average +3.98%, worst -4.47%, 18 entries.
- v1.9 latest 8 weeks: average +4.12%, worst -4.35%, 18 entries.

Cumulative Weekly Return Difference:
- v1.8 latest 8-week total return: +31.87%, compounded +33.34%, final $13,333.90 from $10,000.
- v1.9 latest 8-week total return: +32.98%, compounded +34.87%, final $13,486.90 from $10,000.
- v1.9 cumulative spread over v1.8: +1.11 percentage points simple, +1.53 percentage points compounded.

Decision: use v1.9 as current OpenAI default
- Small but consistent improvement over v1.8 on both 4-week and 8-week profit windows.
- It preserves the v1.8 profit-max profile while filtering one class of high-gap fake-breakout chase.

### 2026-05-30 - OpenAI profit-max default v1.8

Strategy Change:
- OpenAI side only: `core/sim_weekly/openai_contestant.py`.
- Reverted the default parameter target from v1.7 defensive 2-week optimization back to the v1.6-style profit-max profile.
- Kept v1.6 governance improvements: no RKLB execution, default no RKLZ short allocation, Monday late-session guard, and 10% weekly risk halt.
- Restored higher confirmed RKLX allocation and stricter weekly-change gate: `rklx_fraction=0.80`, `rklx_weak_fraction=0.30`, `rklx_min_week_change=3.0`, `profit_trail_gain_share=0.10`.

Benchmark:
- Claude strategy unchanged.
- Shared duel runner/scoring unchanged by this strategy update.

Backtest Dates:
- Latest 2 weeks: 2026-05-18 through 2026-05-25.
- Latest 4 weeks: 2026-05-04 through 2026-05-25.
- Latest 8 weeks: 2026-04-06 through 2026-05-25.

Signal Count Before / After:
- v1.7 latest 2 weeks: average +0.57%, worst -1.11%, 4 entries.
- v1.8 latest 2 weeks: average -1.05%, worst -2.99%, 3 entries.
- v1.7 latest 4 weeks: average +2.51%, worst -1.11%, 15 entries.
- v1.8 latest 4 weeks: average +4.53%, worst -2.99%, 12 entries.
- v1.7 latest 8 weeks: average +0.30%, worst -8.36%, 26 entries.
- v1.8 latest 8 weeks: average +3.98%, worst -4.47%, 18 entries.

Cumulative Weekly Return Difference:
- v1.7 latest 8-week total return: +2.43%.
- v1.8 latest 8-week total return: +31.87%.
- v1.8 cumulative spread over v1.7: +29.44 percentage points.
- Week-by-week v1.8 minus v1.7:
  - 2026-04-06: +1.11
  - 2026-04-13: +13.21
  - 2026-04-20: +3.15
  - 2026-04-27: +3.89
  - 2026-05-04: +10.84
  - 2026-05-11: +0.46
  - 2026-05-18: -1.88
  - 2026-05-25: -1.34

Decision: use v1.8 as current OpenAI default
- The user clarified the target function is profit maximization.
- v1.8 is worse on the latest 2-week defensive metric, but materially better on the 4-week and 8-week profit windows.
- Keep the 2-week review as a warning signal, not the sole optimizer, when it conflicts with profit-max evidence.

### 2026-05-30 - OpenAI latest two-week defensive RKLX profile v1.7

Strategy Change:
- OpenAI side only: `core/sim_weekly/openai_contestant.py`.
- Re-optimized the default OpenAI profile for the latest 2-week window, with 4-week validation.
- Kept the discipline: no RKLB execution and default no RKLZ short allocation.
- Lowered strong-gap RKLX allocation to 30% because recent high-gap signals behaved more like chase entries.
- Raised non-strong trend RKLX allocation to 45% because recent lower-gap trend-continuation entries performed better.
- Lowered the RKLX weekly-change gate from +3.0% to +1.5%.
- Increased profit gain-share lock from 10% to 25% after the profit trigger engages.

Benchmark:
- Claude strategy unchanged.
- Shared duel runner/scoring unchanged by this strategy update.

Backtest Dates:
- Latest 2-week optimization window: 2026-05-18 through 2026-05-25.
- Formal 4-week validation window: 2026-05-04 through 2026-05-25.
- 8-week reference window: 2026-04-06 through 2026-05-25.

Signal Count Before / After:
- v1.6 latest 2 weeks: average -1.05%, sum -2.09%, worst -2.99%, 3 entries, 1 losing sell.
- v1.7 latest 2 weeks: average +0.57%, sum +1.13%, worst -1.11%, 4 entries, 1 losing sell.
- v1.6 latest 4 weeks: average +4.53%, worst -2.99%, 12 entries.
- v1.7 latest 4 weeks: average +2.51%, worst -1.11%, 15 entries.
- v1.7 latest 8 weeks: average +0.30%, worst -8.36%, 26 entries.

Accuracy or Favorable Move Before / After:
- The 2-week window improved materially and the worst recent week was reduced.
- The 4-week window stayed positive but gave up upside versus v1.6, especially in large bull weeks.
- The 8-week window confirms this is a recent defensive profile, not a universal long-horizon winner.

Decision: forward test as a recent-window profile
- This follows the user's 2-week / 4-week rolling-review preference.
- Watch closely: if the 4-week weighted review turns strongly bull, v1.6-style higher RKLX riding may be better than this defensive v1.7 profile.

### 2026-05-30 - OpenAI two/four-week weighted review discipline

Strategy Change:
- OpenAI side only: `scripts/sim_weekly_openai_nightly_review.py`.
- Added a 2-observation fast review cycle and a 4-observation formal review cycle.
- Each cycle uses recency weights from old to new (`[1, 2]` or `[1, 2, 3, 4]`), so the newest observation has the highest influence.
- The weighted cycles record benchmark regime, OpenAI return, OpenAI drawdown, Claude return, and time-bucket trade stats into `openai_adaptive_state.json` / adjustment log.
- Time buckets include RTH open, RTH midday, RTH close, Monday open, Monday late, Friday late, and non-RTH sessions when present in the ledger.
- Nightly regime selection may use the 4-cycle weighted regime after a full cycle is available. The 2-cycle review is an early warning, not a standalone reason to overfit.
- Fixed nightly config generation so it does not reintroduce RKLB execution parameters or default RKLZ short allocation.

Benchmark:
- Claude strategy unchanged.
- Shared duel runner/scoring unchanged by this review-discipline update.

Decision:
- Keep 2-cycle / 4-cycle weighted review as OpenAI paper-duel governance.
- Do not tune from a single day; use single-day observations as evidence, use 2-cycle for warning, and use 4-cycle as the default profile-change anchor.

### 2026-05-30 - OpenAI Monday late-session guard v1.6

Strategy Change:
- OpenAI side only: `core/sim_weekly/openai_contestant.py`.
- Added an explicit special-time framework for RKLX entries.
- Default enabled rule: do not open new RKLX positions on Monday after 14:30 ET.
- Default disabled after replay: broad RTH open and midday entry blocks. They were tested but hurt bull-week capture, so they remain configurable only.
- Non-RTH / premarket / postmarket segmentation is not scored here because the current offline duel replay uses RTH 5m bars. It needs a separate all-hours replay before becoming a default trading rule.

Benchmark:
- Claude strategy unchanged.
- Shared duel runner/scoring unchanged by this strategy update.

Backtest Dates:
- Recent replay: 2026-04-06 through 2026-05-25.
- Broader replay: 2026-02-09 through 2026-05-25.

Signal Count Before / After:
- v1.5 16-week replay: 44 entries, average return +0.24%, worst week -11.00%, average max drawdown -6.29%.
- v1.6 16-week replay: 41 entries, average return +1.05%, worst week -6.08%, average max drawdown -5.68%.
- v1.5 recent 8-week replay: 19 entries, average return +3.17%, worst week -11.00%.
- v1.6 recent 8-week replay: 18 entries, average return +3.98%, worst week -4.47%.

Accuracy or Favorable Move Before / After:
- v1.5 16-week losing sells: 17 / 44.
- v1.6 16-week losing sells: 15 / 41.
- The main improvement came from avoiding Monday late-session RKLX entries that previously carried overnight gap risk.

Rejected Time Rules:
- Blocking 09:30-10:00 ET reduced some open volatility but hurt 2026-04-20 and did not improve the overall recent replay.
- Blocking 11:30-13:00 ET hurt 2026-04-13 and 2026-05-25 badly; midday is not uniformly low-quality for this instrument.

Decision: forward test as OpenAI paper-duel v1.6
- Keep Monday late-session guard.
- Keep other time windows configurable but off until all-hours / non-RTH replay proves them.

### 2026-05-30 - OpenAI sparse RKLX bull ride v1.5

Strategy Change:
- OpenAI side only: `core/sim_weekly/openai_contestant.py`.
- Kept the execution boundary: RKLB is signal data only; OpenAI does not execute RKLB.
- Disabled new RKLZ entries by setting default short fraction to 0. RKLZ kept as a supported instrument, but OpenAI v1.5 does not allocate to it by default.
- Raised RKLX entry quality gate: RKLB weekly change must be at least +3.0% before OpenAI opens RKLX.
- Changed RKLX riding profile: fewer entries, larger confirmed RKLX allocation, wider 9% trail, later profit lock, and lower gain-share lock so strong winners can run.
- Added weekly risk halt at 10% drawdown to stop trading after a severe bad week starts.

Benchmark:
- Claude strategy unchanged.
- Shared duel runner/scoring unchanged by this strategy update.

Backtest Dates:
- Recent replay: 2026-04-06 through 2026-05-25.
- Broader replay: 2026-02-09 through 2026-05-25.
- Commands:
  - `python scripts/sim_weekly_duel_backtest.py 2026-04-06 2026-04-13 2026-04-20 2026-04-27 2026-05-04 2026-05-11 2026-05-18 2026-05-25`
  - `python scripts/sim_weekly_duel_backtest.py 2026-02-09 2026-02-16 2026-02-23 2026-03-02 2026-03-09 2026-03-16 2026-03-23 2026-03-30 2026-04-06 2026-04-13 2026-04-20 2026-04-27 2026-05-04 2026-05-11 2026-05-18 2026-05-25`

Signal Count Before / After:
- v1.4 16-week replay: 136 entries, average return -2.29%, average max drawdown -6.36%.
- v1.5 16-week replay: 44 entries, average return +0.24%, average max drawdown -6.29%.
- v1.4 recent 8-week replay: 69 entries, average return -1.58%, worst week -8.81%.
- v1.5 recent 8-week replay: 19 entries, average return +3.17%, worst week -11.00%.

Accuracy or Favorable Move Before / After:
- v1.4 16-week losing sells: 62 / 136.
- v1.5 16-week losing sells: 17 / 44.
- v1.5 recent 8-week losing sells: 5 / 19.
- v1.5 recent 8-week return beat Claude's average return (+3.17% vs +0.30%) but still did not beat buyhold RKLX in large bull weeks.

Worst New False Positive:
- 2026-04-27 remained a severe loss week at -11.00%. The 10% weekly halt stops further damage, but the first bad RKLX ride can still hurt.

Decision: forward test as OpenAI paper-duel v1.5
- This version prioritizes fewer trades, fewer losing trades, and stronger RKLX riding.
- It is not a final optimal strategy; the next target is reducing the remaining severe false-positive week without killing 2026-04-13 and 2026-05-04 bull-week upside.

### 2026-05-30 - OpenAI RKLX ride profit lock v1.4

Strategy Change:
- OpenAI side only: `core/sim_weekly/openai_contestant.py`.
- Kept the v1.3 boundary: RKLB is signal data only; OpenAI does not execute RKLB.
- Added profit-trail gain lock: after a position has meaningful MFE, the stop now protects a fixed share of the peak profit instead of falling back near cost.
- Increased RKLX sizing on already-filtered long signals: weak RKLX entries from 34% to 42%, strong RKLX entries from 52% to 64%.

Benchmark:
- Claude strategy unchanged.
- Shared duel runner/scoring unchanged by this strategy update.

Backtest Dates:
- Replay for week 2026-05-25.
- Command: `python scripts/sim_weekly_duel_backtest.py 2026-05-25`.

Signal Count Before / After:
- v1.3 guarded RKLX/RKLZ-only rule: 5 entries, +0.15%, max drawdown -2.70%.
- v1.4 RKLX ride profit lock: 6 entries, +4.07%, max drawdown -1.86%.

Accuracy or Favorable Move Before / After:
- v1.4 had 6 closed trades, 100% win rate in the 2026-05-25 replay.
- Buyhold references: RKLB +2.12%, RKLX +3.42%.
- v1.4 beat both buyhold references for this replay while keeping much lower drawdown than buyhold RKLX (-1.86% vs -21.54%).

Worst New False Positive:
- The improved result partly comes from larger RKLX sizing. If a filtered long signal fails before the new profit lock engages, the loss per trade can be larger than v1.3.

Decision: keep for OpenAI paper-duel forward test
- This is a riding/exit improvement, not a new hindsight entry rule.
- Next validation should watch whether the gain-share trail protects profits without chopping winners too early.

### 2026-05-30 - OpenAI RKLX/RKLZ execution-only rule v1.3

Strategy Change:
- OpenAI side only: RKLB is now signal data only, never an execution instrument.
- Long views execute through RKLX; short views execute through RKLZ.
- RKLZ guard tightened: RKLB RSI must be at least 48 before OpenAI may open RKLZ.
- RKLX weak-week guard added: OpenAI will not open RKLX when RKLB weekly change is below +0.5%.

Benchmark:
- Claude strategy unchanged.
- Shared duel runner/scoring unchanged by this strategy update.

Backtest Dates:
- What-if replay for week 2026-05-25.
- Command: `python scripts/sim_weekly_duel_backtest.py 2026-05-25`.

Signal Count Before / After:
- Prior OpenAI v1.2 what-if for 2026-05-25: 6 entries, -2.58%.
- Naive "replace RKLB long with RKLX" check: 8 entries, -4.68%.
- Final v1.3 guarded RKLX/RKLZ-only rule: 5 entries, +0.15%.

Accuracy or Favorable Move Before / After:
- v1.3 had 5 closed trades, 100% win rate, but gains were small.
- Buyhold references still beat it: RKLB +2.12%, RKLX +3.42%.
- Simple 1m lag check for 2026-05-25 week showed RKLB/RKLX same-minute return correlation 0.953; 1-5 minute RKLX lag correlations were near zero. The observed lag hypothesis is not proven by 1m close data and needs tick/order-book validation.

Worst New False Positive:
- The strategy can now underperform badly in strong RKLX trend weeks because it exits too early and only captures tiny slices.

Decision: keep as OpenAI paper-duel iteration only
- Good boundary fix: no RKLB execution.
- Not enough alpha yet: next work should improve RKLX ride/partial take-profit instead of simply increasing trade count.

### 2026-05-30 - OpenAI duel discipline guards v1.2

Strategy Change:
- OpenAI side only: `core/sim_weekly/openai_contestant.py`.
- Added RKLZ oversold guard: do not open new RKLZ when RKLB RSI is below 35.
- Added late-day inverse guard: do not open new RKLZ after 14:30 ET.
- Added profit-lock floor: after a position reaches +2% MFE, stop moves to at least cost +0.2%.
- Added same-bar reversal guard: an opposite signal may close a position, but OpenAI will not immediately open the reverse exposure on the same 5m bar.

Benchmark:
- Claude strategy was not changed.
- Shared duel runner/scoring was not tuned for OpenAI.
- Buyhold RKLB/RKLX retained as neutral references.

Backtest Dates:
- Default 8-week duel replay: 2026-03-23 through 2026-05-11.
- Command: `python scripts/sim_weekly_duel_backtest.py`.

Signal Count Before / After:
- Previous documented OpenAI 8-week run: 49 entries.
- After v1.2 guards: 54 entries.
- Claude unchanged in this run: 90 entries.

Accuracy or Favorable Move Before / After:
- Previous documented OpenAI average weekly return: -0.62%, average max drawdown -4.19%.
- After v1.2 guards: +0.26% average weekly return, average max drawdown -4.89%, positive weeks 3/8.
- Claude in same replay: +2.43% average weekly return, average max drawdown -6.47%, positive weeks 5/8.
- Buyhold RKLB/RKLX still dominate raw return in bull weeks: +8.03% / +15.49% average weekly return.

Worst New False Positive:
- OpenAI still loses badly on 2026-04-06 (-5.99%) and 2026-04-27 (-4.83%).
- The guards reduce the specific 2026-05-29 failure modes, but do not make OpenAI a champion candidate.

Decision: keep as OpenAI paper-duel iteration only
- Fair PK boundary: this changes only OpenAI's independent contestant strategy. Claude should adjust its own strategy separately.
- Shared framework change to disclose: `scripts/sim_weekly_duel_run.py` weekend settlement bug fixed so all contestants are flattened consistently after Friday all-hours cutoff or on weekend catch-up.

### 2026-05-29 — OpenAI live adaptive duel loop v0.1

Strategy Change:
- Changed paper-duel governance from frozen-parameter judging to a live forward-learning loop, per user direction.
- Added OpenAI-side nightly adaptive review in `scripts/sim_weekly_openai_nightly_review.py`.
- `OpenAIContestant` can now load a paper-only adaptive config for live duel runs:
  - `data/sim_weekly/openai_adaptive_config.json`
  - default offline backtests still use neutral parameters unless a config path is explicitly supplied.
- Live duel runner passes the adaptive config to OpenAI only; live focus strategy is untouched.

Benchmark:
- Forward paper duel: timestamped realtime `claude_rule` vs `openai_v1` ledger.
- Frozen historical testset is now a regime playbook calibration reference, not a final trophy.

Backtest Dates:
- No new backtest used for promotion.
- Current ledger date used for first nightly state: 2026-05-29.

Signal Count Before / After:
- No historical signal-count claim.
- Live runner behavior changes only after nightly config confirms a regime across multiple observations.

Accuracy or Favorable Move Before / After:
- Initial OpenAI nightly review wrote neutral config because only one chop observation was available:
  - observation: RKLB benchmark +0.41%
  - confirmed regime: unknown
  - next profile: neutral
  - hypothesis: single-day evidence is not enough to switch; keep neutral to avoid whipsaw.
- First bull-ride playbook is ready but requires multi-day bull confirmation:
  - wider RKLX/RKLB trailing stops
  - higher RKLX fraction
  - lower cooldown
  - avoid countertrend RKLZ while bull profile is active

Worst New False Positive:
- A bull profile can overstay a failing breakout if regime confirmation is wrong.
- Guardrails:
  - multi-day regime confirmation required
  - adjustment log records observation -> hypothesis -> tomorrow trial -> next-day result
  - changes apply only to paper duel, never to `core/focus/*` live strategy.

Decision: keep as paper-only adaptive loop
- This is not a live trading strategy change.
- It creates the audit trail needed to score "who learns better" over forward days.
- Next useful metric: percentage of nightly adjustments whose next-day result is positive or beats the other contestant, tracked in `openai_adjustment_log.json`.

### 2026-05-29 — Duel frozen cross-regime testset verdict

Strategy Change:
- No strategy logic changed in this entry.
- Recorded the frozen Duel testset result from `DUEL_TESTSET_2026-05-29.md`.
- Scope remains paper-only; live focus strategy, Telegram signal logic, risk controls, watchlist, shared duel harness, fees, portfolio, and `_score` were not changed.

Benchmark:
- Fair Duel benchmark: `ClaudeRuleContestant` vs `OpenAIContestant`, with `buyhold_RKLB` and `buyhold_RKLX` retained as reference lines.
- Ranking formula: `avg_return_pct / max(abs(avg_max_dd_pct), 0.01)`, with worst week and total trades as tie-breakers.

Backtest Dates:
- Frozen cross-regime testset:
  - 2025-12-08
  - 2025-12-22
  - 2026-01-12
  - 2026-01-26
  - 2026-02-02
  - 2026-02-23
  - 2026-03-09
  - 2026-03-16
- Composition: bull / bear / chop / mixed, outside the 2026-03-23 through 2026-05-11 training set.

Signal Count Before / After:
- `claude_rule`: 107 entries.
- `openai_v1`: 49 entries.
- `buyhold_RKLB`: 8 entries.
- `buyhold_RKLX`: 8 entries.

Accuracy or Favorable Move Before / After:

| Contestant | Avg Return | Risk Adj | Median | Worst Week | Positive Weeks | Beat RKLB | Avg Max DD | Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `buyhold_RKLX` | +2.84% | +0.13 | -4.33% | -17.40% | 2/8 | 2/8 | -22.26% | 8 |
| `buyhold_RKLB` | +1.20% | +0.11 | -1.53% | -7.02% | 2/8 | 3/8 | -11.11% | 8 |
| `claude_rule` | -0.58% | -0.09 | +0.84% | -9.72% | 4/8 | 3/8 | -6.73% | 107 |
| `openai_v1` | -0.62% | -0.15 | -0.38% | -5.88% | 3/8 | 3/8 | -4.19% | 49 |

Worst New False Positive:
- `claude_rule`: 2026-03-09 returned -9.72%, the deepest AI weekly loss.
- `openai_v1`: 2026-03-09 returned -5.88% and 2025-12-22 returned -3.67%, showing its conservative profile still loses in some chop/mixed regimes.

Decision: frozen testset verdict = draw / no champion
- `claude_rule` has slightly better frozen-testset average return and risk-adjusted score, plus more positive weeks, but churn is heavy at 107 entries and worst-week loss is deeper.
- `openai_v1` has slightly lower return, fewer positive weeks, but materially lower drawdown and fewer trades.
- The return gap is only 0.04 percentage points, so this does not justify declaring a winner.
- Forward live paper evidence now matters more: use real-time timestamped trades, daily reports, and weekly regime-labeled scorecards for at least 8 weeks before revisiting the verdict.

Integrity Note:
- OpenAI side had previously run a sanity cross-regime check that included 2026-02-02, 2026-02-23, and 2026-03-09 before this formal frozen testset document existed.
- No `OpenAIContestant` strategy parameters were changed after seeing those results; subsequent work was notification, runner, report, and scheduler plumbing only.
- Because this frozen testset has now been seen, it must not be reused after either side changes contestant parameters.

### 2026-05-29 — OpenAI independent Duel Contestant v1

Strategy Change:
- Added `OpenAIContestant` in `core/sim_weekly/openai_contestant.py` for the fair SimWeekly duel harness.
- The contestant implements its own `Contestant.on_bar()` logic: trend detection, RKLB/RKLX/RKLZ selection, sizing, cooldown, trailing stop, and opposite-signal exits.
- It does not import Claude's `contestants.py`, does not use the old shared `engine.py`, and does not replace live focus or Telegram logic.
- `scripts/sim_weekly_duel_backtest.py` now includes `openai_v1` and sorts the visible scoreboard by risk-adjusted return (`avg_return_pct / abs(avg_max_dd_pct)`) instead of raw return.

Benchmark:
- Fair-duel benchmark: `ClaudeRuleContestant` plus buy-and-hold `RKLB` / `RKLX`.
- Previous Codex `CodexDecider` is kept as a shadow decider note only; it is not considered a fair independent strategy because it reused the shared SimWeekly engine/risk layer.

Backtest Dates:
- Bull / strong-trend sample: 8 weekly replays from 2026-03-23 through 2026-05-11.
- Cross-regime sample: 6 weekly replays from 2026-02-02 through 2026-03-09.

Signal Count Before / After:
- 2026-03-23 through 2026-05-11:
  - `claude_rule`: 90 entries.
  - `openai_v1`: 46 entries.
- 2026-02-02 through 2026-03-09:
  - `claude_rule`: 80 entries.
  - `openai_v1`: 37 entries.

Accuracy or Favorable Move Before / After:
- 8-week strong-trend sample:
  - `claude_rule`: avg return +2.43%, avg max drawdown -6.47%, risk-adjusted score +0.38.
  - `openai_v1`: avg return +1.69%, avg max drawdown -4.30%, risk-adjusted score +0.39.
  - `openai_v1` reduced drawdown and trades, but did not improve raw return.
- 6-week cross-regime sample:
  - `claude_rule`: avg return -0.84%, avg max drawdown -8.30%, risk-adjusted score -0.10.
  - `openai_v1`: avg return -1.09%, avg max drawdown -4.40%, risk-adjusted score -0.25.
  - `openai_v1` reduced drawdown but lagged Claude on risk-adjusted return in this sample.

Worst New False Positive:
- 2026-04-06: `openai_v1` returned -7.74% versus `claude_rule` -6.34%.
- 2026-03-09: `openai_v1` returned -5.88% versus buyhold RKLB -1.40%, showing the short/guard logic can still lose in choppy rebounds.

Decision: shadow only
- `openai_v1` is now fairly seated in the independent duel harness, but it is not a live or champion candidate.
- Keep iterating only through the fair `Contestant` interface and continue judging by risk-adjusted return, cross-regime behavior, downside protection, and trading efficiency.

### 2026-05-29 - D_TARGETED_BREAKDOWN shadow-only live instrumentation

Change Type:
- Shadow-only live instrumentation; Telegram behavior unchanged.

Changed Logic:
- Added `check_targeted_breakdown_shadow()` in `core/focus/swing_detector.py`.
- The shadow profile records `D_TARGETED_BREAKDOWN` style early breakdown / restrained rebound observations.
- Shadow records are stored in memory and best-effort persisted to `data/review/YYYY-MM-DD/shadow_signals.json`.
- Shadow records do **not** enter `hits`, do **not** go to pusher, do **not** create buttons, and do **not** change live strategy output.

Expected Benefit:
- Collect live evidence for the best replay candidate without adding Telegram noise.
- Let future reviews compare actual missed waves against shadow candidates before deciding whether to merge D into live signals.

Validation:
- `py_compile` PASS:
  - `core/focus/swing_detector.py`
  - `tests/test_signal_upgrade_v0_5_34.py`
- `python tests/test_signal_upgrade_v0_5_34.py` PASS (39 tests).
- Regression test added: shadow signal records locally but never appears in returned `hits`.

Decision:
- Keep as shadow-only.
- Do not treat D as live signal until several sessions of `shadow_signals.json` prove it reduces MISS without spam.

### 2026-05-29 - Minute replay candidate variants for discussion

Change Type:
- Research-only strategy candidates; not merged into live trading.

Candidate Logic:
- Added `scripts/minute_replay_candidate_signals.py` to replay RKLB minute-by-minute from local/Futu K_1M data.
- Tested three candidate profiles:
  - `A_STRICT`: strict breakdown/rebound overlay.
  - `B_BALANCED`: looser balanced overlay.
  - `C_AGGRESSIVE_WATCH`: aggressive watch-only overlay.
  - `D_TARGETED_BREAKDOWN`: targeted early-breakdown profile with restrained rebound logic.
- All profiles tested two overlay alerts:
  - `candidate_breakdown_follow`: follow a sustained intraday breakdown below VWAP.
  - `candidate_rebound_entry_watch`: catch an early rebound after a large down day.

Validation:
- Compiled `scripts/minute_replay_candidate_signals.py`.
- Futu K_1M data was fetched or reused for 2026-05-26 / 05-27 / 05-28 / 05-29.
- Replay report: `docs/minute_replay_candidate_20260529_042724.md`.

Result:
- Production minute replay signals: 135
- Baseline TIMELY/LATE/MISS/WRONG_SIDE: 8/8/4/4
- Baseline wrong-side STRONG: 12

| Profile | Added | T/L/M/W | TIMELY delta | MISS delta | Wrong STRONG delta | Decision |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `A_STRICT` | 3 | 9/7/4/4 | +1 | +0 | +0 | discuss |
| `B_BALANCED` | 6 | 10/6/4/4 | +2 | +0 | +0 | discuss |
| `C_AGGRESSIVE_WATCH` | 14 | 10/7/3/4 | +2 | -1 | +0 | discuss, but noisier |
| `D_TARGETED_BREAKDOWN` | 6 | 9/8/3/4 | +1 | -1 | +0 | best shadow candidate |

Decision:
- Do not merge directly into live yet.
- `D_TARGETED_BREAKDOWN` is the best next shadow candidate because it reduces one MISS with six added alerts and no added wrong-side STRONG.
- `C_AGGRESSIVE_WATCH` scores highest on coverage but adds 14 alerts; keep it as an upper-bound/noise reference, not the first live candidate.

### 2026-05-29 - v0.5.36 focused breakdown/rebound timing patch

Change Type:
- Focused strategy timing patch plus conservative replay.

Changed Logic:
- `breakdown_warning` now has an early-breakdown path:
  - day change <= -2.0%
  - price below VWAP
  - recent move <= -0.45%
  - volume ratio >= 1.0
  - RSI <= 45
  - drawdown from session high >= 2.0%
- `crash_rebound_watch` is less delayed:
  - crash-day threshold -5.0% -> -4.0%
  - rebound-from-low threshold 2.0% -> 1.2%
  - recent rebound move 0.35% -> 0.30%
  - RSI upper band 62 -> 65
  - volume ratio floor 0.45 -> 0.35
- Added `scripts/replay_breakdown_rebound_patch.py` to replay this focused patch against saved review snapshots without changing live data.

Expected Benefit:
- Earlier sell-side warning when price is already below VWAP and structurally rolling over.
- Earlier bottom-rebound observation after a crash, especially on days like 2026-05-29 where the old logic waited too long.

Validation:
- `py_compile` PASS:
  - `core/focus/swing_detector.py`
  - `tests/test_signal_upgrade_v0_5_34.py`
  - `scripts/replay_breakdown_rebound_patch.py`
- `python tests/test_signal_upgrade_v0_5_34.py` PASS (38 tests).
- Replay: `python scripts/replay_breakdown_rebound_patch.py --dates 2026-05-26 2026-05-27 2026-05-28 2026-05-29`
  - Report: `docs/breakdown_rebound_patch_replay_20260529_034752.md`
  - Before TIMELY/LATE/MISS/WRONG_SIDE: 5/12/11/6
  - After TIMELY/LATE/MISS/WRONG_SIDE: 6/11/11/6
  - Wrong-side STRONG: 13 -> 13
  - Added signal: 2026-05-29 00:21:43 `crash_rebound_watch/long/WEAK`, improving that day’s rebound wave from LATE to TIMELY.

Residual Risk:
- Replay is conservative because it can only add synthetic signals at archived snapshot times; it cannot see every minute between historical pushes.
- This patch does not solve all MISS waves. Remaining gaps need fuller minute-level replay before changing core direction thresholds.

Decision:
- Keep as a bounded timing improvement.
- Do not loosen `direction_trend` guards from this alone; continue collecting skip logs and minute-level reviews.

### 2026-05-25 - v0.5.36 holding replay hard gates and target-state repair

Change Type:
- Bug fix plus production-path replay gate.

Changed Logic:
- `target_advance` now forces T1/T2 to roll forward after a breakout if the normal target calculator returns the old/current level.
- While a held RKLX/RKLZ/RKLB exposure already matches the master direction, same-direction `direction_trend` is downgraded to `WEAK` with `confidence_cap=65` and `held_same_direction_cap`.
- `position_followup` now writes a best-effort structured audit log to `data/review/YYYY-MM-DD/position_followup.json`.
- Daily ATR calculation resets after abnormal TR days instead of mixing pre/post split price regimes.
- Added `scripts/replay_holding_followup.py` to replay the 2026-05-22 RKLX 97 trade window through the production `run_all_triggers` path.

Validation:
- `py_compile` PASS:
  - `core/focus/pusher.py`
  - `core/focus/swing_detector.py`
  - `core/focus/position_followup.py`
  - `scripts/replay_holding_followup.py`
- `python tests/test_target_advance.py` PASS.
- `python -m unittest discover -s tests -p test_position_followup_v0_5_36.py` PASS (8 tests).
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py` PASS (36 tests).
- `python -m unittest discover -s tests -p test_loss_alert_passthrough.py` PASS (6 tests).
- `python scripts/replay_holding_followup.py --date 2026-05-23` PASS:
  - 10:44 top-risk cap: `score=50`, `strength=WEAK`, reason `post_top_warning_cap`.
  - 11:02 RSI rollover cap: `score=45`, `strength=WEAK`, reason `rsi_rolling_over`.
  - Holding window follow-up states: `INVALIDATED`, `COST_RETEST`, `INVALIDATED`, `INVALIDATED` (total 4).
  - Managed exit leaks: 0.
  - Held same-direction STRONG `direction_trend`: 0.

Residual Risk:
- Replay hard gate is currently anchored to the 2026-05-22 RKLX 97 trade. Broader 4-day replay remains the next validation step before any strategy-threshold change.
- `URGENT` stop-loss warnings are still allowed while holding; this is intentional risk passthrough, not follow-up noise.

Decision:
- Keep as confirmed bug fix and replay harness.
- Do not loosen/tighten direction strategy from this alone; use the harness to expand replay coverage first.

### 2026-05-24 - v0.5.36 holding follow-up and confidence honesty hotfix

Change Type:
- Live-safety hotfix for the 2026-05-22 RKLX 97 trade review.

Changed Logic:
- Added `core/focus/position_followup.py`.
  - Held positions can now emit `COST_RETEST`, `INVALIDATED`, or `DATA_UNTRUSTED`.
  - While a ticker is held, old exit-side noise (`profit_target_hit`, `drawdown_from_peak`, `near_resistance`, `overbought_surge`, `large_day_gain`) is taken over by the follow-up layer; `stop_loss_warning` remains only when `URGENT`.
- `direction_trend` long `STRONG` is downgraded after a recent top-risk warning (`near_resistance` / `large_day_gain` / `overbought_surge`) within 300s.
- `_confidence_score` no longer gives the normal long RSI bonus when RSI is rolling down from a high zone; mirrored logic added for short signals.
- SimWeekly `_conviction` now applies the same RSI-slope honesty idea.

Expected Benefit:
- Avoid the 10:43 top-warning -> 10:44 STRONG-long contradiction seen in the RKLX 97 trade.
- Add a missing cost-retest voice when a losing position rebounds back near cost.
- Reduce independent exit-side Telegram noise while holding.

Validation:
- `py_compile` PASS:
  - `core/focus/swing_detector.py`
  - `core/focus/pusher.py`
  - `core/focus/position_followup.py`
  - `core/sim_weekly/strategy.py`
- `python -m unittest discover -s tests -p test_position_followup_v0_5_36.py` PASS (4 tests).
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py` PASS (36 tests).
- `python -m unittest discover -s tests -p test_loss_alert_passthrough.py` PASS (6 tests).
- `python tests/test_compute_rr_v0_5_33.py` PASS.
- `python tests/test_rr_strong_bypass_v0_5_33.py` PASS.

Residual Risk:
- `target_advance` state refresh failure was fixed on 2026-05-25 and is now covered by `python tests/test_target_advance.py`.
- P0 follow-up is intentionally conservative: `TOP_WATCH` is not pushed yet; only `COST_RETEST`, `INVALIDATED`, and `DATA_UNTRUSTED` can create new Telegram messages.

Decision:
- Keep as a focused live-safety fix, then review the next session for message count and whether cost-retest/invalidated timing is useful.

### 2026-05-23 - weekend P0 validation and ATR anomaly skip

Change Type:
- Read-only validation tooling plus display-reference data hygiene.

Changed Logic:
- Added `scripts/weekend_p0_review.py` to generate weekend P0 validation output:
  - ATR stop/target hard checks.
  - RKLZ historical 1m anomaly scan.
  - rebound-delay offline candidate scan.
  - direction_trend confidence-cap candidate dry run.
  - SimWeekly live-state check.
- `_daily_atr_pct_from_local_history` now skips abnormal daily TR rows (`TR% >= 25%`) when calculating display ATR, so RKLZ split/bad-row style days do not poison stop/target references.

Expected Benefit:
- Keep target/invalid-reference prices useful without changing direction triggers.
- Avoid hiding RKLZ historical anomalies behind caps.
- Produce a stable weekend report before any strategy decision.

Validation:
- `python -m py_compile scripts/weekend_p0_review.py core/focus/pusher.py` PASS.
- `python -m scripts.weekend_p0_review` PASS.
- Output: `docs/weekend_p0_results_2026-05-23.md`.
- Hard checks passed:
  - RKLX/RKLZ sub-1% stop count = 0.
  - stop distance > 6% count = 0.
  - RKLX 79.96 anchor stop = $77.08.

Decision:
- Keep as P0 data/reference fix.
- No main strategy trigger threshold changed.

### 2026-05-21 - v0.5.36 direction invalidation display fix

Strategy Change:
- Direction-signal action copy now uses `失效价` instead of `止损`, so it is read as a direction invalidation reference rather than an immediate mechanical stop.
- Leveraged follower tools (`RKLX` / `RKLZ` / `TSLL`) now use a minimum invalidation gap of about `1.2%` for direction-signal target displays.
- If current price is within `0.8%` of the invalidation level, the message switches to `入场状态: 已贴近失效价` and says to wait for re-confirmation instead of showing a normal entry line.

Expected Benefit:
- Avoid the live problem where a correct direction signal shows an entry and a stop only ~0.4%-0.6% apart.
- Reduce hesitation caused by "the price already touched stop before I can execute."
- Keep the direction signal focused on direction quality; position size and exact sell timing remain user-controlled.

Benchmark:
- Current benchmark remains `v0.5.31 / v0.5.33 Friday baseline`.
- This update does not change direction trigger thresholds, but it changes risk/reference display and may affect R/R filtering in weak signals.

Validation:
- `py_compile` PASS:
  - `core/focus/pusher.py`
  - `tests/test_signal_upgrade_v0_5_34.py`
  - `tests/test_target_follower_fix.py`
- `python -m unittest discover -s tests -p test_target_follower_fix.py` PASS.
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py` PASS.

Decision: keep as risk-copy fix
- Needs next-day replay review to confirm it does not over-block useful weak signals.

### 2026-05-20 - v0.5.36 low-price target level fix

Strategy Change:
- Replace fixed `$5` target level with dynamic short-term levels:
  - price < $5: use $0.50 levels
  - price < $100: use $1 levels
  - price >= $100: use $5 levels
- Filter target candidates farther than 12% from entry to prevent absurd T2 values.

Expected Benefit:
- Prevent low-priced leveraged ETFs such as RKLZ around $2.50 from showing `$5.00` as T2.
- Keep target/stop display aligned with short-term trading horizons.

Validation:
- Added regression `test_low_price_follower_target_does_not_jump_to_five_dollars`.
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py` passes 28 tests.

Decision: keep
- Display/target reference correctness fix; no trigger threshold change.

### 2026-05-20 - v0.5.36 observation reference wording

Strategy Change:
- Heartbeat now labels daily move as `较昨收` instead of ambiguous `日内`.
- Heartbeat adds `短线5分钟` move when enough price history is available.
- Observation copy now says `较昨收涨幅/跌幅触发` so it is not confused with a 5-minute move.

Expected Benefit:
- Make the reference basis explicit:
  - `较昨收`: current price vs previous regular-session close from Futu quote snapshot.
  - `短线5分钟`: rolling 300-second price change from Focus session history.

Validation:
- Updated regression `test_diagnose_distance_uses_observation_copy`.
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py` passes 27 tests.

Decision: keep
- Display transparency only; no trigger threshold or trading logic change.

### 2026-05-20 - v0.5.36 premarket low-volume confidence cap

Strategy Change:
- Cap pre-market low-volume long signals at medium confidence.
- Rule: market session `pre` + direction `long` + `vol_ratio < 0.8` + confidence above 65 => confidence becomes 65 and title label changes to `[中等]`.
- Push copy explicitly says the signal was downgraded because of pre-market low volume.

Expected Benefit:
- Prevent pre-market low-volume bullish signals from appearing as strong/high-confidence calls.
- Keep the signal visible while making the liquidity weakness obvious.

Validation:
- Added regression `test_premarket_low_volume_long_is_downgraded_to_medium`.
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py` passes 26 tests.

Decision: keep as safety cap
- This changes signal presentation/confidence only; it does not change trigger frequency or core direction thresholds.

### 2026-05-20 - v0.5.36 follower target direction fix

Strategy Change:
- Fix display target/stop calculation for RKLB short signals that use RKLZ as the buy instrument.
- RKLZ/RKLX are always displayed as the instrument to buy, so follower target/stop levels must be calculated in the follower long domain.
- Example fixed case: RKLZ entry near $2.53 should show target above entry and stop below entry, not the reverse.

Expected Benefit:
- Prevent misleading short-signal copy where the inverse ETF target and stop are inverted.
- No change to trigger thresholds or signal frequency.

Validation:
- Added regression `test_short_rklb_uses_long_targets_for_rklz`.
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py` passes 25 tests.

Decision: keep
- This is a price-reference correctness fix, not an emotional strategy retune.

### 2026-05-20 - v0.5.36 panic rebound patch

Strategy Change:
- Add `panic_rebound` for crash-day bottom rebounds:
  - day change <= -5%
  - RSI <= 30
  - rebound from session low >= 0.6%
  - recent 120s move >= +0.6%
  - vol_ratio >= 0.8
- The alert is a rebound observation, not an automatic entry.
- It keeps K_5M DataQualityGate and does not add one-click order buttons.

Reason:
- Live review of 2026-05-20 local / 2026-05-19 ET 10:15-11:15 showed fresh K_5M data and a real rebound window.
- Existing logic avoided oversold shorting but failed to express "bottom rebound starting" clearly.

Expected Benefit:
- Catch violent selloff rebound windows earlier without reverting to noisy bottom-fishing.
- Make the system say something useful when price is bouncing from panic lows.

Validation:
- Added unit regression `test_panic_rebound_fires_after_crash_bounce`.
- This is a surgical patch for the live blind spot; broader benchmark replay still required before changing core direction thresholds.

Decision: hotfix candidate
- Fixes the specific false-silence case.
- Does not replace the current benchmark or tune from one screenshot.

### 2026-05-20 - v0.5.36 intraday crash hotfix

Strategy Change:
- Loosen `breakdown_warning` for crash days with fresh K_5M data.
- Add structural breakdown path:
  - day change <= -5%
  - price below VWAP
  - RSI <= 30
  - vol_ratio >= 0.8
  - drawdown from session high >= 5%
- Add `capitulation_bottom_watch`:
  - day change <= -8%
  - RSI <= 25
  - near session low within 1.5%
  - below VWAP
  - RSI rebound or bullish candle appears
- Bottom watch is neutral observation only; it does not create an order button.

Benchmark:
- v0.5.31 was too quiet on short direction when RSI < 38 and could turn support alerts into bottom-fishing noise.
- v0.5.36 keeps the K_5M gate and adds explicit crash-day semantics.

Backtest / Replay Dates:
- Live diagnostic target: 2026-05-20 local / 2026-05-19 ET RKLB crash.
- Today logs showed fresh K_5M, but no strong short and no bottom watch before this hotfix.

Signal Count Before / After:
- Before: 8 pushes by 00:25 local; 0 strong short direction, 0 bottom watch.
- After expected:
  - structural `breakdown_warning` should fire during the crash even if the last 120s tick window has already bounced.
  - `capitulation_bottom_watch` should fire once RSI/shape starts showing early stop-watch signs near the day low.

Validation:
- `py_compile` PASS:
  - `core/focus/swing_detector.py`
  - `core/focus/pusher.py`
  - `core/focus/data_quality.py`
  - `tests/test_signal_upgrade_v0_5_34.py`
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py`
  - 22 tests PASS
  - Includes structural breakdown and capitulation bottom watch regression tests.

Decision: keep as hotfix candidate
- Fixes false silence in violent selloff conditions.
- Does not remove K_5M data gate.
- Does not add one-click order buttons for crash/bottom-watch alerts.

### 2026-05-20 - v0.5.36 live-window replay against v0.5.31 good days

Strategy Change:
- No new logic change in this entry.
- Added `scripts/backtest_v0536_v0531_live_window.py` to replay the v0.5.31 live-good window.
- Purpose: verify whether v0.5.36 keeps enough v0.5.31-style direction signals while preserving the K_5M gate.

Benchmark:
- `v0.5.31`: historical live direction signals, all pushed.
- `v0.5.36`: same direction sensitivity, but blocked by current K_5M DataQualityGate approximation.

Backtest Dates:
- 2026-05-13 to 2026-05-15
- Price source: `data/historical/RKLB_1m.csv`
- Signal source: `data/review/YYYY-MM-DD/triggers.json`

Signal Count Before / After:
- v0.5.31 all: 40 pushed
- v0.5.36 gated: 39 pushed
- Blocked: 1 / 40, reason `market closed`

Accuracy or Favorable Move Before / After:

| Window | Version | Scored | Correct | Accuracy | avgMFE | avgMAE | avgRet |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5min | v0.5.31 | 23 | 14 | 60.9% | +0.37% | +0.33% | -0.07% |
| 5min | v0.5.36 | 23 | 14 | 60.9% | +0.37% | +0.33% | -0.07% |
| 10min | v0.5.31 | 24 | 12 | 50.0% | +0.45% | +0.56% | -0.18% |
| 10min | v0.5.36 | 23 | 12 | 52.2% | +0.46% | +0.57% | -0.19% |
| 15min | v0.5.31 | 24 | 11 | 45.8% | +0.48% | +0.66% | -0.27% |
| 15min | v0.5.36 | 23 | 11 | 47.8% | +0.50% | +0.67% | -0.28% |

Worst New False Positive:
- Not found in this replay. v0.5.36 did not add extra historical direction signals in this script; it only gates v0.5.31 live signals.

Decision: keep v0.5.36 candidate
- v0.5.36 preserves almost all v0.5.31 direction signal count in the live-good window.
- The K_5M gate did not over-block this sample.
- Accuracy is roughly equal to slightly better, but avgRet is still negative after 10-15 minutes; direction signal is useful for timely awareness, not enough as an automatic entry/exit system.

Artifacts:
- `docs/v0536_live_window_report_20260520_001824.md`
- `docs/v0536_live_window_detail_20260520_001824.csv`

Follow-up Windows:
- `2026-05-13` to `2026-05-18`
  - v0.5.31 all: 62 direction pushes
  - v0.5.36 gated: 39 direction pushes
  - v0.5.36 blocked all 2026-05-18 stale/bad-data direction pushes (`data_ok=False` / `is_today=False`)
  - Scored accuracy is unchanged vs the 05-13~05-15 window because `data/historical/RKLB_1m.csv` ends at 2026-05-18 13:34 ET and the blocked 05-18 records are not valid clean direction samples.
- `2026-05-13` to `2026-05-19`
  - v0.5.31 all: 67 direction pushes
  - v0.5.36 gated: 44 direction pushes
  - 05-19 adds 5 direction pushes, but cannot be accurately scored yet because local 1m history currently ends at 2026-05-18 13:34 ET.
  - Artifact: `docs/v0536_live_window_report_20260520_002403.md`

Answer:
- On the v0.5.31 good live window, v0.5.36 is slightly better on 10/15min accuracy and almost identical on 5min accuracy.
- Across the broader post-v0.5.31 window, the main improvement is safety: v0.5.36 blocks the stale/bad-data 05-18 direction signals. There is not yet enough clean 05-19 price data to claim a statistically obvious accuracy jump.

### 2026-05-19 - v0.5.36: restore v0.5.31 sensitivity + keep K_5M gate

Strategy Change:
- Restore the practical direction visibility expected from the v0.5.31 live baseline.
- Keep the v0.5.35 DataQualityGate: direction/entry/exit signals still require current K_5M data.
- Add `breakdown_warning` for fresh-data open-bell downside breaks:
  - day change <= -2.5%
  - price below VWAP
  - 120s move <= -1.0%
  - vol_ratio >= 2.0
- `breakdown_warning` is a direction/risk alert, not a one-click short entry. It has no order button.

Benchmark:
- Current benchmark remains `v0.5.31 / v0.5.33 Friday baseline` for direction sensitivity.
- Safety base remains `v0.5.35 defensive gate` for K_5M freshness and stale-data blocking.

Backtest / Replay Dates:
- Existing fixtures:
  - `tests/fixtures/review_2026_05_14_triggers.json`
  - `tests/fixtures/review_2026_05_16_triggers.json`
  - `tests/fixtures/review_2026_05_18_triggers.json`
- Live incident target:
  - 2026-05-19 09:35 ET RKLB breakdown, where v0.5.35 stayed too quiet.

Signal Count Before / After:
- No broad replay count change was accepted in this patch.
- This is a surgical visibility fix for a specific false-silence class: fresh K_5M + violent breakdown.

Accuracy or Favorable Move Before / After:
- Expected improvement is not from more generic signals.
- Expected improvement is that a fresh-data open breakdown produces an explicit bearish direction warning instead of only `near_support` / support-watch copy.

Worst New False Positive:
- Main risk: a capitulation wick can trigger `breakdown_warning` near the low.
- Mitigation:
  - Requires fresh K_5M gate.
  - Requires price below VWAP and vol_ratio >= 2.0.
  - Does not produce a one-click order button.
  - 15-minute cooldown prevents repeated panic alerts.

Validation:
- `py_compile` PASS:
  - `core/focus/swing_detector.py`
  - `core/focus/pusher.py`
  - `core/focus/focus_manager.py`
  - `core/focus/data_quality.py`
  - `tests/test_signal_upgrade_v0_5_34.py`
- `python -m unittest discover -s tests -p test_signal_upgrade_v0_5_34.py`
  - 20 tests PASS
  - Includes regression that `breakdown_warning` requires fresh data and produces no order button.
- `python backtest_v0531_vs_v0535.py`
  - Existing direction baseline unchanged: v0.5.31 10min 54.2%, v0.5.35 10min 52.2% on scored historical `direction_trend` records.
  - Report saved: `docs/v0531_vs_v0535_report_20260520_001103.txt`
  - Detail saved: `docs/v0531_vs_v0535_detail_20260520_001103.csv`

Decision: keep as v0.5.36 candidate
- This is not a full rollback to v0.5.31.
- It restores direction sensitivity where v0.5.35 was silent, while preserving the K_5M stale-data defense that v0.5.31 lacked.

### 2026-05-19 — v0.5.31 vs v0.5.35 短线方向准确率回测 (Backtest)

**Strategy Change**: 验证 v0.5.35 严格闸门是否比 v0.5.31 真的更准，决定是否回滚。
**Benchmark**: v0.5.31 (历史 live, 无 R/R / data_quality / chase 闸门)
**Backtest Dates**: 2026-04-24 ~ 2026-05-15 (18 个交易日, US.RKLB only)

**Signal Count Before / After**:
- v0.5.31 推送: 250 候选 → 全部推 (历史 live = 直推)
- v0.5.35 推送: 250 候选 → 通过 26 (89.6% 阻断)

**评分**: MFE > MAE in {5,10,15} min 窗口；价格源 `data/historical/RKLB_1m.csv`
**可评分样本**: 83/250 (overnight 时段 Polygon 免费版无 1m 数据)

**Accuracy / Avg Return @ 10min**:

| 版本 | 推送 | 准确 | 准确率 | avgMFE | avgMAE | avgRet |
|---|---:|---:|---:|---:|---:|---:|
| v0.5.31 | 83 | 43 | **51.8%** | +0.31% | -0.37% | -0.05% |
| v0.5.35 | 10 | 3 | 30.0% | +0.20% | -0.84% | -0.28% |

**Worst New False Positive**: 黑名单 `(57.9, 6.58)` 在 2026-05-15 一天内自然出现 13 次 (06:14~11:42 ET)，全为 long STRONG，胜率 8/13 = **61.5%**。这对值是 RKLB 自然波动中的合理读数，不是冻结值，**v0.5.35 误归为黑名单导致整天 13 条真信号被拦**。

**核心结论**:
1. v0.5.31 短线方向准确率 ≈ 50% (扔硬币), 平均收益 -0.05% — **跟单会亏钱**
2. v0.5.35 在小样本 (n=10) 上 30%，未显著优于 v0.5.31，但 90% 阻断率太高造成熄火
3. v0.5.35 的 `data_ok=False` 闸门原则上正确 (历史 detector 没 enforce 这道闸门)，但黑名单和 `decision_context` 空 record 的处理需要改

**Decision**: **shadow only**
- 不回滚 v0.5.31 — 它的方向准确率等于随机，盲跟单亏损
- 不直接采用 v0.5.35 现状 — 黑名单误杀 + 老记录 data_ok=None 误阻断
- 必须先修 3 处:
  1. **删除黑名单中的 (57.9, 6.58)** (高优先级, 1 行改动)
  2. heartbeat 改读 `session._last_data_quality` 共享态，而非自己 `evaluate_data_quality(update_repeat=False)` 漏掉 counter
  3. 复查 calc_all_micro 在正常 K_5M 下是否会误标 data_ok=False (今晚 21:17/21:27 现场)
- 方向信号不应该是唯一交易依据，准确率 50% 等于无信息量

**复现**:
```powershell
python backtest_v0531_vs_v0535.py
# data/backtest/v0531_vs_v0535_report.txt
# data/backtest/v0531_vs_v0535_detail.csv
```

---

### 2026-05-19 — Add `intraday_reversal`

Change:
- Add a narrow intraday reversal signal after `direction_trend` fails.
- Short reversal:
  - day change >= +0.8%
  - pullback from session high >= 5%
  - price < VWAP
  - RSI 35-50
  - vol_ratio >= 1.2
- Long reversal:
  - day change <= -0.8%
  - rebound from session low >= 5%
  - price > VWAP
  - RSI 50-65
  - vol_ratio >= 1.2
  - still at least 2% below session high

Backtest:

| Dataset | New Reversal Hits | Notes |
| --- | ---: | --- |
| 2026-05-14 | 0 | Does not disturb strong uptrend fixture |
| 2026-05-16 | 0 | Does not increase weak-market bottom-fishing noise |
| 2026-05-18 fixture | 0 | Accident fixture still blocked by data quality gate |
| 2026-05 full review logs | 2 | 2026-05-15 long, 2026-05-18 short |

Observed follow-through from review logs:

| Date | Signal | Entry | Favorable Move | Adverse Move | Result |
| --- | --- | ---: | ---: | ---: | --- |
| 2026-05-15 12:05 | long | 129.98 | +0.75% | -0.76% | Mild / neutral |
| 2026-05-18 23:46 | short | 129.05 | +22.51% | -2.51% | Strong improvement |

Decision:
- Keep as experimental improvement.
- Do not loosen further without a full replay script.

### 2026-05-19 — Direction visibility + clean review data

Change:
- Cleaned `data/review/2026-05-19/triggers.json`: removed test-generated fake records.
- Added a guard so `unittest` calls to `format_trigger_message()` no longer write to live review logs.
- Low cash no longer hides `direction_trend` / `intraday_reversal` long signals; the signal is shown, while sizing/order plans still respect cash limits.
- Relaxed short `intraday_reversal` for open-bell volatility:
  - vol_ratio threshold `1.2 -> 0.8`
  - RSI short upper bound `50 -> 55`
  - removed the need to bounce 1% from the session low before recognizing weakness.

Rationale:
- 2026-05-19 had large open-bell volatility, but direction signals were not visible enough.
- `MIN_BUDGET_USD` should prevent bad auto-sizing, not hide market direction.
- Review logs must remain clean, or backtest comparisons become meaningless.

Validation:

| Check | Result |
| --- | --- |
| Compile `swing_detector.py`, `pusher.py`, test file | PASS |
| `python -m unittest tests.test_signal_upgrade_v0_5_34` | 17 tests PASS |
| 2026-05-19 review cleanup | 40 -> 13 records, backup saved as `triggers.raw_with_test_noise.json` |

Decision:
- Keep. This is a visibility/safety correction, not a full benchmark replacement.

### 2026-05-20 - v0.5.36 crash rebound watch patch

Strategy Change:
- Add `crash_rebound_watch` for crash-day rebound observation:
  - RKLB day change <= -5%
  - rebound from session low >= 2.0%
  - recent 120s move >= +0.35%
  - RSI 35-62, vol_ratio >= 0.45
- This is direction/observation only; it has no order button and no sizing advice.

Benchmark:
- Keep v0.5.31 live sensitivity as the direction benchmark.
- Keep K_5M DataQualityGate from v0.5.35+.

Backtest Dates:
- Live review target: 2026-05-19 ET crash/rebound session.
- Immediate regression added with synthetic crash rebound reproducer.

Signal Count Before / After:
- Before: the first stronger rebound confirmation was `intraday_reversal` after low rebound >= 5%.
- After: a weaker observation can fire from >= 2% low rebound, before full VWAP/RSI confirmation.

Accuracy or Favorable Move Before / After:
- Not accepted as a profitable entry signal yet.
- It is an earlier visibility signal for manual judgment and AI judge follow-up.

Worst New False Positive:
- A dead-cat bounce after a -5% day can trigger the watch and then fail.
- Mitigation: wording says "反弹观察", no order button, and invalidation is "跌回日低附近".

Decision: keep as watch-only / review after replay.

---

### 2026-05-19 - Scorecard follow-up: reduce false blocks

Source:
- Claude replay compared v0.5.31 vs v0.5.35 and found v0.5.35 was too restrictive.
- v0.5.35 scored only 10 signals vs v0.5.31 scored 83 signals.
- v0.5.35 accuracy was 30.0% vs v0.5.31 accuracy 51.8%.
- Main regression: `FROZEN_VALUE_BLACKLIST` treated `(57.9, 6.58)` as a frozen pair, but 2026-05-15 logs show it appeared naturally 13 times with 61.5% win rate.

Change:
- Removed `(57.9, 6.58)` from `FROZEN_VALUE_BLACKLIST`.
- Added a regression test proving `(57.9, 6.58)` is no longer blocked when K_5M is current.
- Heartbeat now prefers `session._last_data_quality` from the main loop instead of recalculating data quality independently.

Rationale:
- Keep the 05-18 safety gate for genuinely stale data.
- Avoid blocking natural, historically profitable RSI/volume combinations.
- Keep heartbeat/status aligned with the same data-quality state used by signal gating.

Validation:

| Check | Result |
| --- | --- |
| `tests.test_signal_upgrade_v0_5_34` | 18 tests PASS |
| `tests/test_micro_indicators_open.py` | PASS |
| Compile `data_quality.py`, `focus_manager.py`, `heartbeat.py`, signal test | PASS |
| Replay `backtest_v0531_vs_v0535.py` after blacklist fix | PASS, printed report; file save blocked by local folder permission |

Replay result after blacklist fix:

| Window | Version | Scored Pushes | Correct | Accuracy | avgMFE | avgMAE | avgRet |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5min | v0.5.31 | 77 | 40 | 51.9% | +0.24% | +0.19% | -0.01% |
| 5min | v0.5.35-fixed | 22 | 12 | 54.5% | +0.35% | +0.33% | -0.09% |
| 10min | v0.5.31 | 83 | 43 | 51.8% | +0.31% | +0.37% | -0.05% |
| 10min | v0.5.35-fixed | 23 | 11 | 47.8% | +0.42% | +0.68% | -0.22% |
| 15min | v0.5.31 | 84 | 39 | 46.4% | +0.36% | +0.45% | -0.09% |
| 15min | v0.5.35-fixed | 23 | 10 | 43.5% | +0.46% | +0.75% | -0.27% |

Decision:
- Keep as a P0 correction.
- Do not roll back wholesale to v0.5.31.
- Do not keep v0.5.35 as originally scored; use this reduced-false-block variant as the next candidate for replay.
- Still not enough to declare v0.5.35-fixed better than v0.5.31 on direction accuracy; next work should target the remaining `data_ok=False` over-blocking.

---

### 2026-05-19 — Replay v2: 用 Futu 干净数据重测 + short STRONG edge 实为统计幻觉

**触发原因**: Claude 发现 `data/historical/*_1m.csv` 是 Polygon 免费版数据，与 Futu 4 天交叉对比有 0.1-2% bar 级误差 + 缺 16-227 根 extended-hours bar + 系统性少 5-6% 成交量。Polygon 脏数据会污染 5-15min 短线 MFE/MAE 判定。

**数据迁移**:
- 旧 Polygon 数据备份到 `data/historical_polygon_backup/`
- 用 Futu `request_history_kline(K_1M, extended_time=True)` 重拉过去 30 天 (`fetch_futu_history_1m.py`)
- 新 `data/historical/` = 21 个完整交易日 × 960 bars + 05-18 部分 (492 bars，Futu OpenD 在 12:12 ET 后无数据)

**Replay v2 准确率主表** (Futu 干净数据 vs Polygon 脏数据，同样 250 候选)：

| 窗口 | 版本 | Polygon 旧结果 | Futu 新结果 | 变化 |
|---|---|---:|---:|---:|
| 5min  | v0.5.31 | 51.9% | **61.7%** | +9.8 |
| 5min  | v0.5.35 | 33.3% | **60.9%** | +27.6 |
| 10min | v0.5.31 | 51.8% | 54.2% | +2.4 |
| 10min | v0.5.35 | 30.0% | **52.2%** | +22.2 |
| 15min | v0.5.31 | 46.4% | 51.2% | +4.8 |
| 15min | v0.5.35 | 30.0% | 47.8% | +17.8 |

**Replay v2 关键反转**:
1. **"v0.5.31 51.8% 大幅胜 v0.5.35 30%" 是 Polygon 脏数据制造的假象**。Futu 数据下两版准确率基本持平
2. v0.5.35 阻断率从 89.6% 降到 84.4% (因 `(57.9, 6.58)` 黑名单已删)
3. 5min v0.5.31 avgRet 从 -0.01% 微升到 **+0.02%** (第一次看到非负期望)

**短信号 STRONG edge 深挖** (`data/backtest/short_strong_eda.txt`):

n=32 short STRONG 信号 10min 准确率看似 65.6%，但拆开后：

| 来源 | n | win10% | avgRet10 | 真实性 |
|---|---:|---:|---:|---|
| **04-24 (RSI=50.0 / vol=1.00 默认占位)** | 25 | 68% | -0.013% | **占位值，detector 在指标失效时按 day_chg 兜底 short** |
| 04-30 | 1 | 100% | -0.169% | 单点 |
| 05-08 (RSI 38-48, vol 0.6-1.5, 真指标) | 6 | 50% | +0.077% | 7 |

**剔除占位值后真实样本 n=7 win=4，57% — 跟扔硬币区分不开。**

**根因**：`core/focus/micro_indicators.py` 第 132-134 行在 K_5M 不可用时返回 `rsi_5m=50.0, vol_ratio=1.0`。`check_direction_trend` 仍会基于 `day_chg <= -2.0` 触发 SHORT STRONG，导致信号在指标失效时仍然推送。这与 05-18 21:14-23:58 ET 推 21 条 RSI=58/vol=1.5 long STRONG 是同根问题（占位 + day_chg）。

**核心结论 — 不止 v0.5.35 严格的问题，是 direction_trend 信号本身**:

1. 在 RKLB 上，5-15 min 短线方向预测 **在所有版本、所有时段下都没有显著 edge**
2. v0.5.31 准确率 ~52-62%、v0.5.35 ~48-61% 都跟随机区分不大
3. 唯一"看起来有 edge"的子集 (short STRONG 65.6%) 经拆解是占位指标+趋势日的统计假象
4. avgRet 接近 0 — 即使 win%>50%，跟单后扣手续费/滑点会变成负期望

**Decision**: **shadow only / 暂停**
- 不回滚 v0.5.31
- 不进一步调宽 v0.5.35 的方向触发
- **待与 Codex 共同讨论后决定下一步方向**（详见 `discussion_2026-05-19_direction_trend_no_edge.md`）

**Open questions (留给 Codex)**:
- direction_trend 是否应该降级为辅助信号，主信号改 swing_bottom/swing_top + 持仓管理？
- `micro_indicators.py` 占位值机制是否应该禁止 detector 触发（即 `data_ok=False` 时 detector 完全静默）？
- 短线 RKLB 是否本就难做？应转向 4h+ 趋势日捕捉？

**复现**:
```powershell
python backtest_v0531_vs_v0535.py
# data/backtest/short_strong_eda.txt    # short STRONG 32 条拆解
# docs/v0531_vs_v0535_*.csv             # 完整明细
```

## Required Report Template

```text
Strategy Change:
Benchmark:
Backtest Dates:
Signal Count Before / After:
Accuracy or Favorable Move Before / After:
Worst New False Positive:
Decision: keep / revert / shadow only
```

---

### 2026-05-29 - Shadow wave-moment forward log v0.5.37

Strategy Change:
- Keep the C-shape Telegram formatter for future `wave_trough_rebound` / `wave_peak_rollover` alerts, with no order buttons.
- Default live promotion is OFF: `shadow_tg_enabled=False`.
- Every shadow wave candidate now records a forward case in `data/review/<date>/wave_forward_cases.json` with entry price, timestamp, direction, and indicator snapshot.

Benchmark:
- Previous behavior: shadow records were persisted only in `data/review/<date>/shadow_signals.json` and never notified.
- Live trading/order logic is unchanged.

Backtest Dates:
- Diagnostic replay and Claude/Codex review focused on 2026-05-29 RKLX/RKLB wave-miss screenshot and recorded review logs.

Signal Count Before / After:
- Before: 0 Telegram wave-moment alerts from shadow records.
- After: still 0 default Telegram wave-moment alerts; forward cases are recorded for calibration first.

Accuracy or Favorable Move Before / After:
- Not promoted yet. The previously suggested `vol_ratio>=0.8` gate is not accepted for live notification until accumulated forward outcomes prove it.

Worst New False Positive:
- None from Telegram by default because promotion is disabled. Remaining risk is only review-log volume.

Decision: shadow log only
- Consensus with Claude: do not build a new wave detector from one screenshot; reuse the existing shadow candidate stream, record forward outcomes first, and calibrate thresholds later.

---

### 2026-05-29 — SimWeekly CodexDecider paper overlay

Strategy Change:
- Added `CodexDecider` for paper simulation only. It starts from the existing SimWeekly `RuleDecider` signal and vetoes weak RKLZ shorts when RKLB is already positive for the week.
- No live trading logic, Telegram signal logic, or focus strategy changed.

Benchmark:
- Existing Claude `RuleDecider` inside `core/sim_weekly/strategy.py`.

Backtest Dates:
- 8 weekly replays from 2026-03-23 through 2026-05-11.
- Same engine, fees, slippage, historical 1m data, and $10,000 starting capital.

Signal Count Before / After:
- Claude RuleDecider: 94 simulated entries.
- CodexDecider: 79 simulated entries.

Accuracy or Favorable Move Before / After:
- Claude RuleDecider average weekly return: +2.74%, profitable weeks 5/8.
- CodexDecider average weekly return: +2.93%, profitable weeks 6/8.
- Claude RuleDecider sum weekly return: +21.91%.
- CodexDecider sum weekly return: +23.46%.
- Claude RuleDecider avg max drawdown: -6.50%.
- CodexDecider avg max drawdown: -7.48%.

Worst New False Positive:
- CodexDecider still loses badly on 2026-05-11: -10.04% versus Claude -11.71%, while RKLX buy-and-hold was +36.48%.
- This is improved but not solved; drawdown is slightly worse on average.

Decision: shadow only
- CodexDecider wins this 8-week replay by a small margin, but not enough for live promotion.
- Keep it as paper/shadow candidate and continue comparing in daily SimWeekly status reports.
- Full detail: `docs/sim_weekly_decider_compare_latest.md`.

---

### 2026-05-29 - VectorBT/Optuna strategy miner v0.1.2

Strategy Change:
- Added an offline research-only strategy miner under `research/vectorbt_lab/`.
- It searches bounded RKLB signal templates and expresses trades through RKLX/RKLZ paper fills.
- No live focus strategy, Telegram signal logic, or watchlist changed.

Benchmark:
- Current live focus strategy remains the benchmark.
- This miner is a research candidate generator, not a live replacement.

Backtest Dates:
- Historical 1m data merged from `data/historical/RKLB_1m.csv`, `RKLX_1m.csv`, and `RKLZ_1m.csv`.
- RKLZ availability starts from its listing window, so merged tests begin when all three instruments have usable data.

Signal Count Before / After:
- 4 templates searched with 80 Optuna trials each: breakout, vwap_reclaim, crash_rebound, trend_follow.
- Best walk-forward candidate: breakout, 27 test trades.

Accuracy or Favorable Move Before / After:
- breakout: fee-adjusted PnL +$3,126.49, return +31.26%, win rate 62.96%, profit factor 1.84, worst window -$45.94.
- vwap_reclaim: fee-adjusted PnL +$1,866.97, return +18.67%, win rate 60.00%, profit factor 2.09.
- trend_follow: fee-adjusted PnL +$1,102.38, return +11.02%, win rate 77.78%, but only 9 trades.
- crash_rebound: fee-adjusted PnL +$739.71, return +7.40%, win rate 44.44%.

Worst New False Positive:
- Not yet evaluated against live signal snapshots or user execution behavior.
- Intratrade drawdown is still approximated from closed equity, so this is not ready for live promotion.

Decision: research candidate only
- Promote breakout to a shadow replay candidate, not live.
- Next required checks: more days, intratrade drawdown, per-trade ledger review, and comparison against current live signal scorecard.
- Full detail: `research/vectorbt_lab/output/strategy_miner/strategy_miner_report.md`.

## 2026-05-28 23:32 ET - VectorBT/Optuna multi-seed validation v0.1.0

- Scope: research-only; no live focus strategy, Telegram signal logic, risk control, or watchlist changed.
- Run: 5 seeds x 80 trials, holdout=20 latest trading days.
- Decision: shadow_candidate.
- Plain-language conclusion: trend_follow 在多 seed 中稳定靠前，留出集多数为正，可进入 shadow 观察，不能直接替换实盘。
- Best stable template: trend_follow.
- Median holdout PnL: $2077.22; worst holdout PnL: $928.58; positive holdout runs: 5/5.
- Full detail: `research\vectorbt_lab\output\strategy_miner_multi_run\strategy_miner_multi_run_report.md`.

## 2026-05-29 01:58 ET - VectorBT/Optuna rolling OOS validation v0.2.0

- Scope: research-only; no live focus strategy, Telegram signal logic, risk control, or watchlist changed.
- Run: 10 seeds x 200 trials, rolling OOS folds=5.
- Decision: research_only.
- Plain-language conclusion: breakout remains research-only; one or more promotion gates failed.
- Best template: breakout.
- Median OOS PnL: $-2292.35; cross positive cells: 22/50; median trades: 106.0.
- Full detail: `research\vectorbt_lab\output\strategy_miner_multi_run_deep_20260529\strategy_miner_multi_run_report.md`.

## 2026-05-30 - v0.5.36 main-module safety patch after weekly replay

- Scope: live focus main module only; no watchlist, dispatch priority, Telegram routing, or core direction thresholds changed.
- Benchmark: current v0.5.36 safety base.
- Change 1: `direction_trend` keeps the direction hint but downgrades STRONG to WEAK when yesterday-close day change is gap-inflated and RTH intraday action fails to confirm:
  - long downgrade when `day_chg > 0`, `intraday_chg <= 0`, and price is below VWAP.
  - short downgrade when `day_chg < 0`, `intraday_chg >= 0`, and price is above VWAP.
- Change 2: `position_followup` INVALIDATED is now one-shot per unchanged position, with a new alert only after a fresh lower stage (another ~3% or >=1 ATR) or a changed position signature.
- Change 3: added DataFrame K-line regression through `run_all_triggers`, guarding the 05-28 "truth value of a DataFrame is ambiguous" loop error.
- Expected before/after:
  - 05-26 to 05-28 gap-driven wrong STRONG long signals should become WEAK, not silent.
  - 05-29 repeated INVALIDATED/stop-loss noise should shrink materially while preserving the first timely invalidation.
- Verification:
  - `test_direction_gap_confirmation_v0_5_36.py`: 3 tests OK.
  - `test_position_followup_v0_5_36.py`: 9 tests OK.
  - `test_dataframe_kline_inputs.py`: 5 tests OK.
  - `py_compile`: `core/focus/swing_detector.py`, `core/focus/position_followup.py`, `core/focus/pusher.py` OK.
- Decision: live safety patch candidate. It downgrades overstated confidence and reduces repeated holding alerts; it does not promote any research strategy or loosen signal frequency.

## 2026-05-30 - Direction trend cap variant replay

- Scope: offline measurement only; no additional live strategy change.
- Dates: 2026-05-26 through 2026-05-30.
- Samples: 25 `direction_trend / long / STRONG` signals inside labeled waves.
- Baseline problem: 12 wrong-down STRONG samples, 13 correct-up STRONG samples.
- Variant A (`gap_intraday`): caught 0/12 wrong, downgraded 0/13 correct.
- Variant B (`structure_rollover`): caught 9/12 wrong, but downgraded 5/13 correct.
- Variant A_or_B: same as B on this sample.
- Decision: do not promote B to live. It catches many bad strong-long signals, but the correct-signal downgrade rate is 38.46%, above the acceptable cost. Current live patch remains A-only while we search for a narrower structure rule.
- Full detail: `docs/discussion_2026-05-30_direction_cap_variant_replay.md`.
