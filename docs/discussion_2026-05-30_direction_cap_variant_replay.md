# Direction Trend STRONG-long Cap Replay

VERSION : v0.1.0
SCOPE   : offline analysis only; no live strategy changed

## Summary

- Dates: 2026-05-26, 2026-05-27, 2026-05-28, 2026-05-29, 2026-05-30
- Samples: direction_trend / long / STRONG / in-wave = 25
- Candidate action: downgrade STRONG to WEAK only; do not silence the signal.

## Daily Baseline

| Date | Waves | MISS | Wrong STRONG | STRONG-long samples |
|---|---:|---:|---:|---:|
| 2026-05-26 | 4 | 1 | 6 | 7 |
| 2026-05-27 | 5 | 0 | 1 | 7 |
| 2026-05-28 | 13 | 3 | 5 | 11 |
| 2026-05-29 | 2 | 0 | 0 | 0 |
| 2026-05-30 | 8 | 4 | 0 | 0 |

## Variant Results

| Variant | Wrong caught | Correct downgraded | Avg caught adverse | Readout |
|---|---:|---:|---:|---|
| A_gap_intraday | 0/12 (0.00%) | 0/13 (0.00%) | - | 方案甲: gap 强但盘中未确认 |
| B_structure_rollover | 9/12 (75.00%) | 5/13 (38.46%) | -2.69% | 方案乙: VWAP/动能/低高点结构转弱 |
| A_or_B | 9/12 (75.00%) | 5/13 (38.46%) | -2.69% | 甲或乙: 任一命中即降级 |

## Sample Rows

| Date | ET | Class | Conf | Price | Day% | Intra% | <VWAP | m10 | m15 | highDD | LH | A | B |
|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|---|---|
| 2026-05-26 | 05-26 05:54 | wrong_down | 80 | 142.94 | 13.94% | 0.66% | N | 0.04% | -0.04% | 0.53% | N | N | Y |
| 2026-05-26 | 05-26 06:20 | wrong_down | 80 | 143.39 | 14.30% | 0.98% | N | 0.39% | 0.27% | 0.22% | N | N | N |
| 2026-05-26 | 05-26 07:17 | wrong_down | 85 | 143.19 | 14.14% | 0.84% | N | -0.11% | 0.26% | 0.35% | N | N | Y |
| 2026-05-26 | 05-26 07:43 | wrong_down | 95 | 143.30 | 14.23% | 0.92% | N | -0.14% | -0.15% | 0.28% | N | N | Y |
| 2026-05-26 | 05-26 08:20 | wrong_down | 80 | 143.28 | 14.22% | 0.90% | N | 0.18% | 0.21% | 0.29% | N | N | N |
| 2026-05-26 | 05-26 08:29 | wrong_down | 80 | 143.19 | 14.14% | 0.84% | N | 0.06% | -0.05% | 0.35% | N | N | Y |
| 2026-05-26 | 05-26 09:36 | correct_up | 95 | 142.68 | 5.10% | 0.48% | N | 0.60% | 0.27% | 0.71% | N | N | N |
| 2026-05-27 | 05-26 10:06 | correct_up | 85 | 142.79 | 5.18% | 2.01% | N | - | - | -0.32% | N | N | N |
| 2026-05-27 | 05-26 10:42 | correct_up | 80 | 143.20 | 5.48% | 2.31% | N | 0.31% | 0.34% | 0.63% | N | N | N |
| 2026-05-27 | 05-26 11:00 | correct_up | 80 | 143.32 | 5.57% | 2.39% | N | 0.95% | 0.39% | 0.54% | N | N | N |
| 2026-05-27 | 05-26 13:50 | correct_up | 80 | 143.56 | 5.75% | 2.56% | N | -0.19% | -0.22% | 1.67% | N | N | Y |
| 2026-05-27 | 05-26 14:08 | correct_up | 80 | 143.76 | 5.89% | 2.71% | N | 0.04% | 0.01% | 1.53% | N | N | Y |
| 2026-05-27 | 05-26 14:26 | correct_up | 80 | 145.27 | 7.01% | 3.79% | N | 1.37% | 1.16% | 0.50% | N | N | N |
| 2026-05-27 | 05-26 14:44 | wrong_down | 95 | 144.08 | 6.13% | 2.94% | N | 0.64% | 0.09% | 1.32% | N | N | Y |
| 2026-05-28 | 05-27 12:56 | correct_up | 80 | 148.16 | 3.47% | 3.76% | N | 0.45% | 0.64% | 0.61% | N | N | N |
| 2026-05-28 | 05-27 13:22 | correct_up | 80 | 148.25 | 3.53% | 3.82% | N | 0.93% | -0.18% | 1.09% | N | N | Y |
| 2026-05-28 | 05-27 14:06 | correct_up | 80 | 147.84 | 3.24% | 3.53% | N | -0.03% | 0.27% | 1.36% | N | N | Y |
| 2026-05-28 | 05-27 14:43 | wrong_down | 80 | 148.56 | 3.74% | 4.04% | N | 0.08% | 0.17% | 0.88% | N | N | N |
| 2026-05-28 | 05-27 15:20 | correct_up | 80 | 147.96 | 3.33% | 3.62% | N | 0.90% | 0.91% | 1.28% | N | N | Y |
| 2026-05-28 | 05-27 15:35 | correct_up | 90 | 149.03 | 4.07% | 4.37% | N | 0.32% | 0.85% | 0.57% | N | N | N |
| 2026-05-28 | 05-27 15:50 | correct_up | 75 | 150.30 | 4.96% | 5.26% | N | 0.89% | 1.26% | -0.23% | N | N | N |
| 2026-05-28 | 05-28 04:26 | wrong_down | 80 | 147.96 | 3.32% | 0.78% | N | 0.31% | 0.48% | 1.51% | Y | N | Y |
| 2026-05-28 | 05-28 05:51 | wrong_down | 85 | 147.23 | 2.81% | 0.28% | N | 0.67% | 0.58% | 2.00% | N | N | Y |
| 2026-05-28 | 05-28 08:38 | wrong_down | 95 | 147.70 | 3.14% | 0.60% | N | 1.12% | 1.20% | 1.68% | N | N | Y |
| 2026-05-28 | 05-28 09:24 | wrong_down | 80 | 146.55 | 2.34% | -0.18% | N | 0.08% | -0.22% | 2.45% | N | N | Y |

## Decision Rule

- Promotion gate: wrong STRONG decreases materially, while correct STRONG downgrade stays low.
- This report does not judge fast-wave MISS fixes; it only evaluates direction_trend confidence honesty.
- If B or A_or_B downgrades too many correct_up samples, keep live logic at A only.
