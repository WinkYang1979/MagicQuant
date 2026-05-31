# VectorBT + Optuna Research Project Memory

Date: 2026-05-29  
Scope: `research/vectorbt_lab/` only  
Status: research-only, not connected to live trading

## 1. Purpose

This project was created to mine and validate RKLB short-term trading strategies offline, using historical 1m/5m data and paper execution through:

- Long RKLB view -> buy RKLX
- Short RKLB view -> buy RKLZ

It must not modify:

- `core/focus/`
- live Telegram signal logic
- risk controls
- watchlist
- real orders

The main goal is to prevent emotion-driven strategy edits by forcing every candidate strategy through repeatable historical validation.

## 2. Current Files

Main research files:

- `C:\MagicQuant\research\vectorbt_lab\optuna_strategy_miner.py`
- `C:\MagicQuant\research\vectorbt_lab\strategy_miner_multi_run.py`
- `C:\MagicQuant\research\vectorbt_lab\scheduler.py`

Tests:

- `C:\MagicQuant\tests\test_strategy_miner_multi_run.py`
- `C:\MagicQuant\tests\test_vectorbt_scheduler.py`
- `C:\MagicQuant\tests\test_vectorbt_lab.py`

Latest deep-run output:

- Report: `C:\MagicQuant\research\vectorbt_lab\output\strategy_miner_multi_run_deep_20260529\strategy_miner_multi_run_report.md`
- Summary JSON: `C:\MagicQuant\research\vectorbt_lab\output\strategy_miner_multi_run_deep_20260529\strategy_miner_multi_run_summary.json`
- Aggregate CSV: `C:\MagicQuant\research\vectorbt_lab\output\strategy_miner_multi_run_deep_20260529\strategy_miner_multi_run_aggregate.csv`
- Trade ledger: `C:\MagicQuant\research\vectorbt_lab\output\strategy_miner_multi_run_deep_20260529\strategy_miner_multi_run_trades.csv`
- Cross-seed cells: `C:\MagicQuant\research\vectorbt_lab\output\strategy_miner_multi_run_deep_20260529\strategy_miner_multi_run_cross_seed.csv`

## 3. Implemented Validation Method

`strategy_miner_multi_run.py` is now the preferred validation entry.

It does:

- Multi-seed Optuna search
- Rolling OOS validation
- Cross-seed OOS matrix
- Fee-adjusted PnL ranking
- Trade ledger with MAE/MFE and bars-to-MAE/MFE
- Promotion gate check
- Scorecard append
- Summary JSON for scheduler Telegram weekly report

Default weekly mode:

```powershell
python research\vectorbt_lab\strategy_miner_multi_run.py --trials 80 --scorecard
```

Deep manual mode:

```powershell
python research\vectorbt_lab\strategy_miner_multi_run.py --trials 200 --seeds 11,22,33,44,55,66,77,88,99,111 --scorecard
```

Scheduler deep mode:

```powershell
python research\vectorbt_lab\scheduler.py --force-weekly --deep --once
```

## 4. Promotion Gates

A strategy can only become a shadow candidate if all gates pass:

- Cross-seed positive OOS cells >= 18
- Rolling OOS positive folds >= 3
- Median OOS trades >= 15
- Median profit factor > 1.1
- p-value < 0.20 or trade Sharpe > 0.5
- Signal density per day >= 0.3
- Live relevance replay passed

Important: even if research OOS passes, it still cannot enter shadow unless live-relevance replay passes.

## 5. Deep Run Result: 2026-05-29

Command actually run:

```powershell
python research\vectorbt_lab\strategy_miner_multi_run.py --trials 200 --seeds 11,22,33,44,55,66,77,88,99,111 --out-dir research\vectorbt_lab\output\strategy_miner_multi_run_deep_20260529 --scorecard
```

Runtime: about 55 minutes.

Result:

- Decision: `research_only`
- Best template: `breakout`
- No strategy is allowed into shadow.

Aggregate results:

| Rank | Strategy | Cross Cells | Median OOS PnL | Worst Seed OOS | Median Trades | Median PF | p-value | Sharpe | Density/day |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | breakout | 22/50 | -2292.35 | -7608.15 | 106.0 | 0.84 | 0.7806 | -0.78 | 1.06 |
| 2 | trend_follow | 17/50 | -2925.44 | -8248.20 | 308.0 | 0.93 | 0.7045 | -0.54 | 3.08 |
| 3 | vwap_reclaim | 13/50 | -1765.01 | -3954.24 | 42.0 | 0.76 | 0.7796 | -0.81 | 0.42 |
| 4 | crash_rebound | 5/50 | -5403.71 | -9830.84 | 30.5 | 0.23 | 1.0000 | -4.20 | 0.305 |

Interpretation:

- Full-sample PnL looked positive for some templates, but rolling OOS failed.
- `breakout` passed cross-cell count, trade count, and signal density.
- `breakout` failed positive-fold stability, profit factor, significance/Sharpe, and live replay.
- Therefore, no template should be shadowed yet.

Plain-language conclusion:

The current mined templates are not robust enough. They find trades, but the edge does not survive rolling OOS. Do not use these results to replace or override the live RKLB strategy.

## 6. What Changed In Code

### `optuna_strategy_miner.py`

Added to trade ledger:

- `bars_to_mae`
- `bars_to_mfe`

This helps answer:

- How soon does maximum loss usually appear?
- How soon does maximum favorable move usually appear?
- Are stops too tight or too slow?

### `strategy_miner_multi_run.py`

Upgraded from simple latest-20-day holdout to:

- rolling OOS folds
- cross-seed matrix
- stricter promotion gate
- summary JSON output
- scorecard append

### `scheduler.py`

Added:

- `--deep`
- 90-minute timeout for deep miner
- strategy miner weekly summary merged into weekly-success Telegram
- no extra Telegram stream from miner during scheduler weekly run

## 7. Verified Tests

Commands executed successfully:

```powershell
python -m py_compile research\vectorbt_lab\optuna_strategy_miner.py research\vectorbt_lab\strategy_miner_multi_run.py research\vectorbt_lab\scheduler.py tests\test_strategy_miner_multi_run.py tests\test_vectorbt_scheduler.py
python tests\test_strategy_miner_multi_run.py
python tests\test_vectorbt_scheduler.py
python tests\test_vectorbt_lab.py
```

Results:

- `test_strategy_miner_multi_run.py`: 8 tests OK
- `test_vectorbt_scheduler.py`: 9 tests OK
- `test_vectorbt_lab.py`: 4 tests OK

Smoke run also passed:

```powershell
python research\vectorbt_lab\strategy_miner_multi_run.py --trials 2 --seeds 11,22 --folds 2 --oos-days 5 --fold-step-days 5 --out-dir research\vectorbt_lab\output\strategy_miner_multi_run_smoke_v2
```

## 8. Important Design Decisions

1. Research result is not live strategy.

Even if Optuna finds a good result, it cannot change live behavior automatically.

2. Full sample profit is not trusted.

Rolling OOS and cross-seed stability are the main filters.

3. Live relevance is mandatory.

Before shadow mode, a candidate must pass replay against known pain points:

- no wrong STRONG during held windows
- no worsening of missed major waves
- no degradation on 05-19 style "silent" days

4. Telegram reporting should be quiet.

Weekly research summary is merged into scheduler weekly success message. Miner should not create a separate Telegram stream during scheduled weekly runs.

## 9. Next Recommended Steps

P0:

- Do not promote any current mined template.
- Inspect the `strategy_miner_multi_run_trades.csv` for why `breakout` loses OOS despite high trade count.
- Add live-relevance replay adapter for mined strategies before any shadow decision.

P1:

- Add additional templates closer to the live RKLB behavior:
  - gap-hold continuation
  - panic flush reversal
  - post-news trend day continuation
  - VWAP reclaim with trend filter
- Re-run deep validation after adding each family.

P2:

- Use `bars_to_mae` / `bars_to_mfe` distributions to tune realistic stop and hold-time constraints.
- Add QuantStats-style equity reports after a candidate passes research gates.

## 10. Current Bottom Line

The research framework is now useful, but the current strategy templates are not good enough.

The most important discovery from the 2026-05-29 deep run is negative but valuable:

Do not trust single-run Optuna wins. The rolling OOS test exposed that current templates do not have a stable edge.

