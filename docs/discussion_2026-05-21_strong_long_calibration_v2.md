# STRONG Long Calibration v2

VERSION : v0.1.0
DATE    : 2026-05-21
DEPENDS : scripts/review_signal_coverage.py, data/review/YYYY-MM-DD/triggers.json

## Scope

- Read-only analysis only. No strategy code, trigger, DEFAULT_PARAMS, or dispatch changes.
- Uses gap-segmented review waves; gap/out-of-session signals are excluded from calibration.
- Premarket samples are reported separately and are not mixed into RTH calibration.
- Main question: can RTH direction_trend STRONG-long wrong_down signals be separated from correct_up at firing time?

## Preset Decision Gate

- direction_trend: a structure rule must catch >=70% of wrong_down while killing <15% of correct_up. Otherwise prefer confidence/STRONG cap.
- intraday_reversal / swing_bottom: if in-session wrong sample is below ~5, do not design a gate in this round.
- 05-19 redline: any candidate that increases MISS on 2026-05-19 is rejected.

## Available Review Dates

- Dates scanned: 23
- Range: 2026-04-24 -> 2026-05-21

| Date | In-session STRONG long samples | Regular | Premarket |
|---|---:|---:|---:|
| 2026-05-12 | 3 | 3 | 0 |
| 2026-05-13 | 1 | 1 | 0 |
| 2026-05-14 | 12 | 12 | 0 |
| 2026-05-15 | 13 | 13 | 0 |
| 2026-05-18 | 20 | 0 | 20 |
| 2026-05-19 | 5 | 3 | 2 |
| 2026-05-20 | 10 | 7 | 0 |
| 2026-05-21 | 20 | 15 | 1 |

## Trigger-Level Calibration

### direction_trend / regular

- correct_up: 36
- wrong_down: 10
- no_wave: 1
- 判定: No measured feature/combination reached the preset gate (catch >=70% wrong_down and kill <15% correct_up). Verdict: structure gate is not supported; prefer confidence/STRONG cap.

Feature overlap:

| Feature | Correct N | Correct med | Correct IQR | Correct min..max | Wrong N | Wrong med | Wrong IQR | Wrong min..max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| price_vs_vwap% | 36 | 2.41 | 1.89..3.04 | -1.09..5.64 | 10 | 2.37 | 1.25..2.49 | -0.97..5.50 |
| high_dd% | 36 | 0.89 | 0.33..1.77 | -0.36..5.74 | 10 | 1.14 | 1.03..2.35 | 0.49..2.90 |
| move10% | 36 | 0.54 | 0.07..0.94 | -0.76..2.76 | 10 | 0.05 | -0.74..0.42 | -2.08..0.53 |
| move15% | 35 | 0.85 | -0.12..1.29 | -0.61..5.02 | 10 | -0.26 | -0.56..-0.09 | -1.53..0.58 |
| rsi | 36 | 61.15 | 54.70..65.40 | 52.00..72.50 | 10 | 54.00 | 52.50..56.10 | 52.00..69.70 |
| rsi_slope | 34 | 3.55 | -1.70..7.80 | -12.60..21.90 | 9 | -5.50 | -9.60..-1.30 | -12.90..4.60 |
| day_chg% | 36 | 5.29 | 3.52..6.66 | 2.00..15.98 | 10 | 5.05 | 3.16..6.14 | 2.45..16.15 |
| vol_ratio | 36 | 0.79 | 0.67..1.02 | 0.18..1.52 | 10 | 0.69 | 0.56..1.07 | 0.38..1.32 |
| above_vwap | 36 | 34/36 | 94.4% | - | 10 | 8/10 | 80.0% | - |
| lower_highs | 34 | 6/34 | 17.6% | - | 9 | 3/9 | 33.3% | - |
| rsi_down | 34 | 9/34 | 26.5% | - | 9 | 7/9 | 77.8% | - |

Candidate sweep:

| Candidate rule | Wrong hit | Correct killed | Recovered | Executable recovery | Median refill delay | Median space left |
|---|---:|---:|---:|---:|---:|---:|
| day_chg >= 2% and weakness_count >= 1 | 9/10 (90.0%) | 14/36 (38.9%) | 13/14 | 1/14 | 136.15 min | 12.65% |
| high_dd >= 0.8% | 9/10 (90.0%) | 20/36 (55.6%) | 17/20 | 1/20 | 170.42 min | 3.96% |
| high_dd >= 0.5% | 9/10 (90.0%) | 25/36 (69.4%) | 21/25 | 0/25 | 136.15 min | 7.28% |
| move15 <= 0.0% | 8/10 (80.0%) | 9/36 (25.0%) | 9/9 | 0/9 | 106.07 min | 15.63% |
| day_chg >= 2% and weakness_count >= 2 | 8/10 (80.0%) | 11/36 (30.6%) | 11/11 | 0/11 | 136.15 min | 12.65% |
| day_chg >= 3% and weakness_count >= 1 | 8/10 (80.0%) | 11/36 (30.6%) | 10/11 | 0/11 | 136.15 min | 11.27% |
| high_dd >= 1.0% | 8/10 (80.0%) | 16/36 (44.4%) | 13/16 | 0/16 | 144.25 min | 9.89% |
| RSI slope == down | 7/10 (70.0%) | 9/36 (25.0%) | 9/9 | 0/9 | 121.13 min | 31.13% |
| day_chg >= 3% and weakness_count >= 2 | 7/10 (70.0%) | 10/36 (27.8%) | 10/10 | 0/10 | 136.15 min | 11.27% |
| move15 <= -0.3% | 5/10 (50.0%) | 5/36 (13.9%) | 5/5 | 0/5 | 136.15 min | 15.63% |
| move10 <= 0.0% | 5/10 (50.0%) | 6/36 (16.7%) | 6/6 | 0/6 | 136.15 min | 14.31% |
| day_chg >= 2% and weakness_count >= 3 | 4/10 (40.0%) | 4/36 (11.1%) | 4/4 | 0/4 | 86.29 min | 31.16% |
| day_chg >= 5% and weakness_count >= 1 | 4/10 (40.0%) | 6/36 (16.7%) | 6/6 | 0/6 | 204.52 min | 5.62% |
| day_chg >= 5% and weakness_count >= 2 | 4/10 (40.0%) | 6/36 (16.7%) | 6/6 | 0/6 | 204.52 min | 5.62% |
| high_dd >= 1.2% | 4/10 (40.0%) | 14/36 (38.9%) | 12/14 | 0/14 | 144.25 min | 9.89% |
| move10 <= -0.7% | 3/10 (30.0%) | 1/36 (2.8%) | 1/1 | 0/1 | 136.15 min | 12.65% |
| move10 <= -0.5% | 3/10 (30.0%) | 2/36 (5.6%) | 2/2 | 0/2 | 121.11 min | 21.30% |
| move15 <= -0.5% | 3/10 (30.0%) | 2/36 (5.6%) | 2/2 | 0/2 | 125.16 min | 19.93% |

### direction_trend / premarket

- correct_up: 20
- wrong_down: 2
- no_wave: 0
- 判定: Candidate separation exists under preset gate: price_vs_vwap <= 0.0%, price_vs_vwap <= 0.3%, price_vs_vwap <= 0.5%. Must still pass 05-19 redline before strategy use.

Feature overlap:

| Feature | Correct N | Correct med | Correct IQR | Correct min..max | Wrong N | Wrong med | Wrong IQR | Wrong min..max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| price_vs_vwap% | 0 | - | - | - | 2 | -0.42 | -0.47..-0.36 | -0.47..-0.36 |
| high_dd% | 20 | 23.07 | 22.98..24.06 | 22.98..24.15 | 2 | 1.94 | 1.91..1.96 | 1.91..1.96 |
| move10% | 20 | -22.73 | -23.02..-22.15 | -23.87..-21.66 | 2 | 0.19 | 0.15..0.23 | 0.15..0.23 |
| move15% | 20 | -22.75 | -22.99..-22.33 | -23.74..-21.77 | 2 | 0.42 | 0.19..0.66 | 0.19..0.66 |
| rsi | 20 | 58.00 | 58.00..58.00 | 58.00..58.00 | 2 | 52.45 | 52.30..52.60 | 52.30..52.60 |
| rsi_slope | 0 | - | - | - | 2 | 6.85 | 1.40..12.30 | 1.40..12.30 |
| day_chg% | 0 | - | - | - | 2 | 3.04 | 3.02..3.07 | 3.02..3.07 |
| vol_ratio | 20 | 1.50 | 1.50..1.50 | 1.50..1.50 | 2 | 0.76 | 0.51..1.01 | 0.51..1.01 |
| above_vwap | 0 | 0/0 | - | - | 2 | 0/2 | 0.0% | - |
| lower_highs | 0 | 0/0 | - | - | 2 | 0/2 | 0.0% | - |
| rsi_down | 0 | 0/0 | - | - | 2 | 0/2 | 0.0% | - |

Candidate sweep:

| Candidate rule | Wrong hit | Correct killed | Recovered | Executable recovery | Median refill delay | Median space left |
|---|---:|---:|---:|---:|---:|---:|
| day_chg >= 2% and weakness_count >= 1 | 2/2 (100.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| day_chg >= 3% and weakness_count >= 1 | 2/2 (100.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| price_vs_vwap <= 0.0% | 2/2 (100.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| price_vs_vwap <= 0.3% | 2/2 (100.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| price_vs_vwap <= 0.5% | 2/2 (100.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| high_dd >= 0.5% | 2/2 (100.0%) | 20/20 (100.0%) | 0/20 | 0/20 | - min | -% |
| high_dd >= 0.8% | 2/2 (100.0%) | 20/20 (100.0%) | 0/20 | 0/20 | - min | -% |
| high_dd >= 1.0% | 2/2 (100.0%) | 20/20 (100.0%) | 0/20 | 0/20 | - min | -% |
| high_dd >= 1.2% | 2/2 (100.0%) | 20/20 (100.0%) | 0/20 | 0/20 | - min | -% |
| high_dd >= 1.5% | 2/2 (100.0%) | 20/20 (100.0%) | 0/20 | 0/20 | - min | -% |
| RSI slope == down | 0/2 (0.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| day_chg >= 2% and weakness_count >= 2 | 0/2 (0.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| day_chg >= 2% and weakness_count >= 3 | 0/2 (0.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| day_chg >= 3% and weakness_count >= 2 | 0/2 (0.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| day_chg >= 3% and weakness_count >= 3 | 0/2 (0.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| day_chg >= 5% and weakness_count >= 1 | 0/2 (0.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| day_chg >= 5% and weakness_count >= 2 | 0/2 (0.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |
| day_chg >= 5% and weakness_count >= 3 | 0/2 (0.0%) | 0/20 (0.0%) | 0/0 | 0/0 | - min | -% |

### intraday_reversal / regular

- correct_up: 5
- wrong_down: 2
- no_wave: 0
- 判定: In-session wrong sample is 2, below the ~5 evidence floor. Verdict: do not design a gate for intraday_reversal yet.

Feature overlap:

| Feature | Correct N | Correct med | Correct IQR | Correct min..max | Wrong N | Wrong med | Wrong IQR | Wrong min..max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| price_vs_vwap% | 5 | 2.90 | 2.42..3.16 | 2.10..4.04 | 2 | 4.28 | 3.86..4.71 | 3.86..4.71 |
| high_dd% | 5 | 0.40 | 0.07..0.60 | 0.03..2.11 | 2 | 1.99 | 1.93..2.05 | 1.93..2.05 |
| move10% | 5 | 0.61 | 0.24..0.70 | 0.06..1.49 | 2 | -0.94 | -1.45..-0.44 | -1.45..-0.44 |
| move15% | 5 | 0.99 | 0.42..1.30 | 0.16..1.30 | 2 | -0.35 | -1.09..0.40 | -1.09..0.40 |
| rsi | 5 | 62.70 | 61.00..64.10 | 53.50..64.30 | 2 | 56.15 | 51.50..60.80 | 51.50..60.80 |
| rsi_slope | 5 | 5.80 | 1.10..6.60 | 0.40..7.90 | 2 | -8.45 | -19.20..2.30 | -19.20..2.30 |
| day_chg% | 5 | -5.69 | -6.19..-5.35 | -6.61..-3.29 | 2 | -3.17 | -3.23..-3.12 | -3.23..-3.12 |
| vol_ratio | 5 | 0.85 | 0.82..0.93 | 0.82..0.95 | 2 | 0.89 | 0.84..0.93 | 0.84..0.93 |
| above_vwap | 5 | 5/5 | 100.0% | - | 2 | 2/2 | 100.0% | - |
| lower_highs | 5 | 0/5 | 0.0% | - | 2 | 2/2 | 100.0% | - |
| rsi_down | 5 | 0/5 | 0.0% | - | 2 | 1/2 | 50.0% | - |

Candidate sweep:

| Candidate rule | Wrong hit | Correct killed | Recovered | Executable recovery | Median refill delay | Median space left |
|---|---:|---:|---:|---:|---:|---:|
| lower_highs == True | 2/2 (100.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move10 <= -0.3% | 2/2 (100.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move10 <= 0.0% | 2/2 (100.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| high_dd >= 0.8% | 2/2 (100.0%) | 1/5 (20.0%) | 0/1 | 0/1 | - min | -% |
| high_dd >= 1.0% | 2/2 (100.0%) | 1/5 (20.0%) | 0/1 | 0/1 | - min | -% |
| high_dd >= 1.2% | 2/2 (100.0%) | 1/5 (20.0%) | 0/1 | 0/1 | - min | -% |
| high_dd >= 1.5% | 2/2 (100.0%) | 1/5 (20.0%) | 0/1 | 0/1 | - min | -% |
| high_dd >= 0.5% | 2/2 (100.0%) | 2/5 (40.0%) | 0/2 | 0/2 | - min | -% |
| RSI slope == down | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move10 <= -0.5% | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move10 <= -0.7% | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move10 <= -1.0% | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move15 <= -0.3% | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move15 <= -0.5% | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move15 <= -0.7% | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move15 <= -1.0% | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| move15 <= 0.0% | 1/2 (50.0%) | 0/5 (0.0%) | 0/0 | 0/0 | - min | -% |
| high_dd >= 2.0% | 1/2 (50.0%) | 1/5 (20.0%) | 0/1 | 0/1 | - min | -% |

### intraday_reversal / premarket

- correct_up: 0
- wrong_down: 0
- no_wave: 0
- 判定: In-session wrong sample is 0, below the ~5 evidence floor. Verdict: do not design a gate for intraday_reversal yet.

Feature overlap:

- No in-session sample.

### swing_bottom / regular

- correct_up: 0
- wrong_down: 0
- no_wave: 0
- 判定: In-session wrong sample is 0, below the ~5 evidence floor. Verdict: do not design a gate for swing_bottom yet.

Feature overlap:

- No in-session sample.

### swing_bottom / premarket

- correct_up: 0
- wrong_down: 0
- no_wave: 1
- 判定: In-session wrong sample is 0, below the ~5 evidence floor. Verdict: do not design a gate for swing_bottom yet.

Feature overlap:

- No in-session sample.

## 05-19 Redline

If a candidate rule makes 2026-05-19 more silent, reject it even if it helps 2026-05-21.

| Rule | Suppressed on 05-19 | MISS before -> after | WRONG before -> after | Verdict |
|---|---:|---:|---:|---|
| - | 0 | - | - | No rule passed the preset gate, so 05-19 redline is not triggered. |

## Final Recommendation

- Recommendation: **Confidence/STRONG cap**
- Reason: No RTH direction_trend feature/combination passed the preset separation gate. Do not add a hard structure gate from this sample.
- Practical implication: if confidence cap is chosen later, cap the label/score without muting the directional signal, so 05-19-style silence does not get worse.
