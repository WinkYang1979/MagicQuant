# Minute Replay Candidate Strategy

Purpose: test whether a minute-level breakdown/rebound candidate can reduce MISS/LATE without increasing wrong-side STRONG.

| Date | K source | Prod replay | Candidate added | Before T/L/M/W | Candidate T/L/M/W | Wrong STRONG before→candidate |
|---|---|---:|---:|---|---|---:|
| 2026-05-26 | K_1M Futu fetched | 28 | 0 | 2/1/1/0 | 2/1/1/0 | 6→6 |
| 2026-05-27 | K_1M local archive | 44 | 0 | 1/2/0/2 | 1/2/0/2 | 1→1 |
| 2026-05-28 | K_1M Futu fetched | 55 | 0 | 4/4/3/2 | 4/4/3/2 | 5→5 |
| 2026-05-29 | K_1M Futu fetched | 8 | 3 | 1/1/0/0 | 1/1/0/0 | 0→0 |

## Total

- Production minute replay signals: 135
- Candidate added signals: 3
- Before TIMELY/LATE/MISS/WRONG_SIDE: 8/8/4/4
- Candidate TIMELY/LATE/MISS/WRONG_SIDE: 8/8/4/4
- Wrong-side STRONG: 12 -> 12

## Decision Notes

- If TIMELY rises and wrong-side STRONG does not rise, the candidate is eligible for discussion.
- If MISS falls only by spamming weak alerts, keep it in research and do not merge.
- This report tests direction timing only; VectorBT/QuantStats should test trade PnL next.

## Candidate Signals 2026-05-29

- 2026-05-28 10:19:00 candidate_rebound_entry_watch/long/STRONG conf=80 price=145.3
- 2026-05-28 10:31:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=144.185
- 2026-05-28 10:44:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=145.21
