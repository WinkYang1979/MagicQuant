# SimWeekly Decider Compare

VERSION: v0.1.0
DEPENDS: core/sim_weekly/deciders.py, core/sim_weekly/engine.py, data/historical/*_1m.csv

Purpose: compare Claude RuleDecider and CodexDecider on identical paper replay weeks. This is research-only; no live trading logic is changed.

## Summary

| Decider | Weeks | Avg weekly return | Sum weekly return | Profitable weeks | Beat RKLB B&H | Avg max drawdown | Trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| Claude RuleDecider | 8 | +2.74% | +21.91% | 5/8 | 4/8 | -6.50% | 94 |
| CodexDecider | 8 | +2.01% | +16.09% | 4/8 | 3/8 | -7.71% | 89 |

## Weekly Detail

| Week | Claude % | Codex % | Delta | Claude trades | Codex trades | RKLB B&H | RKLX B&H |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-03-23 | -1.72% | -0.81% | +0.91% | 14 | 13 | -10.78% | -23.08% |
| 2026-03-30 | +10.11% | -0.91% | -11.02% | 11 | 11 | +9.77% | +18.10% |
| 2026-04-06 | -2.86% | +0.17% | +3.03% | 15 | 16 | +0.25% | -0.21% |
| 2026-04-13 | +10.18% | +12.14% | +1.96% | 10 | 11 | +26.36% | +55.74% |
| 2026-04-20 | +2.57% | -2.18% | -4.75% | 9 | 10 | -6.07% | -13.87% |
| 2026-04-27 | +5.03% | +5.65% | +0.62% | 10 | 10 | -1.13% | -3.82% |
| 2026-05-04 | +10.31% | +10.70% | +0.39% | 8 | 5 | +34.52% | +66.34% |
| 2026-05-11 | -11.71% | -8.67% | +3.04% | 17 | 13 | +18.34% | +36.48% |

## Decision

- Claude RuleDecider remains better on this replay set.
- This comparison is paper-only. Do not promote the winner to live strategy without daily signal coverage replay and scorecard review.
- If CodexDecider wins, next step is shadow logging before any Telegram/live integration.

## Output Files

- JSON detail: `C:\MagicQuant\data\sim_weekly\compare\sim_weekly_compare_latest.json`
