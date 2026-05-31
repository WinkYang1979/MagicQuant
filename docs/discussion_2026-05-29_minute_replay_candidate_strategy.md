# 2026-05-29 Minute Replay Candidate Strategy

VERSION : v0.1
DEPENDS : scripts/minute_replay_candidate_signals.py, scripts/review_signal_coverage.py, data/review/*/kline_1m_RKLB.json

## Goal

The user concern is valid: conservative signals are not enough if the system misses large tradable waves. This test uses K_1M plus K_5M-derived indicators to check whether a simple minute-level overlay can reduce MISS/LATE before any live strategy change.

## Candidate Variants

Three research-only profiles were tested:

- `A_STRICT`: strict thresholds, closest to the first candidate.
- `B_BALANCED`: looser thresholds, meant to catch more early turns.
- `C_AGGRESSIVE_WATCH`: aggressive watch-only thresholds, meant to test whether "more alerts" helps coverage.
- `D_TARGETED_BREAKDOWN`: uses aggressive early-breakdown detection, but keeps rebound logic restrained.

Each profile adds two research-only alerts:

- `candidate_breakdown_follow`: short-side warning when price is below VWAP, day change is negative, the last 5-15 minutes are falling, and volume is not dead.
- `candidate_rebound_entry_watch`: long-side watch when a large down day rebounds from the session low with improving 1m structure.

These candidates do not change `core/focus/` live behavior. They are replay-only.

## Data

Dates tested:

- 2026-05-26
- 2026-05-27
- 2026-05-28
- 2026-05-29

K source:

- K_1M local archive for all four dates after Futu fetch/reuse.

Report:

- `docs/minute_replay_candidate_20260529_042724.md`

## Result

Baseline:

- TIMELY/LATE/MISS/WRONG_SIDE: 8/8/4/4
- Wrong-side STRONG: 12

| Profile | Added | T/L/M/W | TIMELY delta | MISS delta | Wrong STRONG delta |
| --- | ---: | --- | ---: | ---: | ---: |
| `A_STRICT` | 3 | 9/7/4/4 | +1 | +0 | +0 |
| `B_BALANCED` | 6 | 10/6/4/4 | +2 | +0 | +0 |
| `C_AGGRESSIVE_WATCH` | 14 | 10/7/3/4 | +2 | -1 | +0 |
| `D_TARGETED_BREAKDOWN` | 6 | 9/8/3/4 | +1 | -1 | +0 |

The first run incorrectly stored candidate timestamps as ET while the coverage engine expected local time. After fixing this measurement bug, all four candidates showed some improvement.

## Decision

Do not merge any variant directly into live yet.

Reason:

- `C_AGGRESSIVE_WATCH` has the best raw coverage but adds 14 alerts, which risks returning to noisy Telegram behavior.
- `D_TARGETED_BREAKDOWN` has a better first shadow profile: 6 added alerts, 1 fewer MISS, 1 more TIMELY, and no added wrong-side STRONG.
- A live strategy update still needs a shadow/live-text design and one more replay pass over a wider window.

This is exactly why minute-level replay is useful: it caught a measurement bug first, then gave us multiple strategy choices instead of one emotional patch.

## What Did Work

The smaller focused patch in `core/focus/swing_detector.py` did improve one rebound wave in the snapshot replay:

- Before: 5/12/11/6
- After: 6/11/11/6
- Wrong-side STRONG unchanged: 13 -> 13

That patch remains a bounded improvement.

## Next Candidate Direction

The next candidate should not be another broad threshold overlay. It should target one specific MISS class at a time:

1. Identify each remaining MISS wave from K_1M replay.
2. For each MISS, extract the first 5-10 minutes of the wave.
3. Compare it with matched false-start periods that should not alert.
4. Build one narrow rule only if the features separate cleanly.

Candidate B should be redesigned, not just loosened. It should likely focus on:

- failed breakdown continuation after VWAP rejection, or
- reclaim after capitulation low with higher-low confirmation.

Any candidate must pass:

- TIMELY increases or MISS decreases.
- Wrong-side STRONG does not increase.
- Added alerts remain small.

Recommended next step:

- Put `D_TARGETED_BREAKDOWN` into shadow mode first.
- Keep `C_AGGRESSIVE_WATCH` as a research upper-bound, not a live Telegram candidate.
- If D improves live shadow coverage for several sessions without spam, then discuss merging a restrained version into `swing_detector`.

## Implementation Status

Implemented on 2026-05-29:

- `D_TARGETED_BREAKDOWN` is now shadow-only in `core/focus/swing_detector.py`.
- It records to `data/review/YYYY-MM-DD/shadow_signals.json`.
- It does not return a formal hit and does not reach Telegram.
- A regression test confirms shadow records are not included in `run_all_triggers()` output.

Validation:

- `py_compile core/focus/swing_detector.py tests/test_signal_upgrade_v0_5_34.py`
- `python tests/test_signal_upgrade_v0_5_34.py` -> 39 tests OK
