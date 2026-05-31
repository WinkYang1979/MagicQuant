# SimWeekly Decider Compare

VERSION: v0.1.0
DEPENDS: core/sim_weekly/deciders.py, core/sim_weekly/engine.py, data/historical/*_1m.csv

Purpose: compare Claude RuleDecider and CodexDecider on identical paper replay weeks. This is research-only; no live trading logic is changed.

## Summary

| Decider | Weeks | Avg weekly return | Sum weekly return | Profitable weeks | Beat RKLB B&H | Avg max drawdown | Trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| Claude RuleDecider | 8 | +2.74% | +21.91% | 5/8 | 4/8 | -6.50% | 94 |
| CodexDecider | 8 | +2.93% | +23.46% | 6/8 | 4/8 | -7.48% | 79 |

## Weekly Detail

| Week | Claude % | Codex % | Delta | Claude trades | Codex trades | RKLB B&H | RKLX B&H |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-03-23 | -1.72% | +1.70% | +3.42% | 14 | 12 | -10.78% | -23.08% |
| 2026-03-30 | +10.11% | +10.52% | +0.41% | 11 | 11 | +9.77% | +18.10% |
| 2026-04-06 | -2.86% | -2.77% | +0.09% | 15 | 14 | +0.25% | -0.21% |
| 2026-04-13 | +10.18% | +9.51% | -0.67% | 10 | 7 | +26.36% | +55.74% |
| 2026-04-20 | +2.57% | +4.23% | +1.66% | 9 | 7 | -6.07% | -13.87% |
| 2026-04-27 | +5.03% | +1.95% | -3.08% | 10 | 9 | -1.13% | -3.82% |
| 2026-05-04 | +10.31% | +8.36% | -1.95% | 8 | 7 | +34.52% | +66.34% |
| 2026-05-11 | -11.71% | -10.04% | +1.67% | 17 | 12 | +18.34% | +36.48% |

## Decision

- CodexDecider wins this replay set.
- This comparison is paper-only. Do not promote the winner to live strategy without daily signal coverage replay and scorecard review.
- If CodexDecider wins, next step is shadow logging before any Telegram/live integration.

## Output Files

- JSON detail: `C:\MagicQuant\data\sim_weekly\compare\sim_weekly_compare_latest.json`
