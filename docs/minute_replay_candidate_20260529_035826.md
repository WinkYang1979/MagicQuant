# Minute Replay Candidate Strategy

Purpose: test whether a minute-level breakdown/rebound candidate can reduce MISS/LATE without increasing wrong-side STRONG.

| Date | K source | Prod replay | Candidate added | Before T/L/M/W | Candidate T/L/M/W | Wrong STRONG before→candidate |
|---|---|---:|---:|---|---|---:|
| 2026-05-26 | K_5M trigger snapshots fallback | 66 | 0 | 1/2/0/1 | 1/2/0/1 | 3→3 |
| 2026-05-27 | K_1M local archive | 44 | 0 | 1/2/0/2 | 1/2/0/2 | 1→1 |
| 2026-05-28 | K_5M trigger snapshots fallback | 66 | 0 | 3/6/8/3 | 5/4/6/5 | 9→15 |
| 2026-05-29 | K_5M trigger snapshots fallback | 14 | 4 | 0/2/3/0 | 0/2/3/0 | 0→0 |

## Total

- Production minute replay signals: 190
- Candidate added signals: 4
- Before TIMELY/LATE/MISS/WRONG_SIDE: 5/12/11/6
- Candidate TIMELY/LATE/MISS/WRONG_SIDE: 7/10/9/8
- Wrong-side STRONG: 13 -> 19

## Decision Notes

- If TIMELY rises and wrong-side STRONG does not rise, the candidate is eligible for discussion.
- If MISS falls only by spamming weak alerts, keep it in research and do not merge.
- This report tests direction timing only; VectorBT/QuantStats should test trade PnL next.

## Candidate Signals 2026-05-29

- 2026-05-28 10:05:00 candidate_breakdown_follow/short/STRONG conf=80 price=142.81
- 2026-05-28 10:20:00 candidate_breakdown_follow/short/STRONG conf=95 price=145.53
- 2026-05-28 10:30:00 candidate_rebound_entry_watch/long/WEAK conf=45 price=144.0
- 2026-05-28 10:45:00 candidate_rebound_entry_watch/long/WEAK conf=55 price=145.46
