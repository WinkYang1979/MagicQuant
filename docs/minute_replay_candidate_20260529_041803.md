# Minute Replay Candidate Strategy Variants

Purpose: compare several minute-level breakdown/rebound candidates before any live strategy update.

## Daily Results

| Date | K source | Prod replay | Profile | Candidate added | Before T/L/M/W | Candidate T/L/M/W | Wrong STRONG before→candidate |
|---|---|---:|---|---:|---|---|---:|
| 2026-05-26 | K_1M local archive | 28 | A_STRICT | 0 | 2/1/1/0 | 2/1/1/0 | 6→6 |
| 2026-05-26 | K_1M local archive | 28 | B_BALANCED | 0 | 2/1/1/0 | 2/1/1/0 | 6→6 |
| 2026-05-26 | K_1M local archive | 28 | C_AGGRESSIVE_WATCH | 0 | 2/1/1/0 | 2/1/1/0 | 6→6 |
| 2026-05-27 | K_1M local archive | 44 | A_STRICT | 0 | 1/2/0/2 | 1/2/0/2 | 1→1 |
| 2026-05-27 | K_1M local archive | 44 | B_BALANCED | 0 | 1/2/0/2 | 1/2/0/2 | 1→1 |
| 2026-05-27 | K_1M local archive | 44 | C_AGGRESSIVE_WATCH | 0 | 1/2/0/2 | 1/2/0/2 | 1→1 |
| 2026-05-28 | K_1M local archive | 55 | A_STRICT | 0 | 4/4/3/2 | 4/4/3/2 | 5→5 |
| 2026-05-28 | K_1M local archive | 55 | B_BALANCED | 1 | 4/4/3/2 | 4/4/3/2 | 5→5 |
| 2026-05-28 | K_1M local archive | 55 | C_AGGRESSIVE_WATCH | 2 | 4/4/3/2 | 4/4/3/2 | 5→5 |
| 2026-05-29 | K_1M local archive | 8 | A_STRICT | 3 | 1/1/0/0 | 1/1/0/0 | 0→0 |
| 2026-05-29 | K_1M local archive | 8 | B_BALANCED | 5 | 1/1/0/0 | 1/1/0/0 | 0→0 |
| 2026-05-29 | K_1M local archive | 8 | C_AGGRESSIVE_WATCH | 12 | 1/1/0/0 | 1/1/0/0 | 0→0 |

## Summary

- Production minute replay signals: 135
- Baseline TIMELY/LATE/MISS/WRONG_SIDE: 8/8/4/4
- Baseline wrong-side STRONG: 12

| Profile | Added | T/L/M/W | TIMELY Δ | MISS Δ | Wrong STRONG Δ | Decision |
|---|---:|---|---:|---:|---:|---|
| A_STRICT | 3 | 8/8/4/4 | +0 | +0 | +0 | REJECT |
| B_BALANCED | 6 | 8/8/4/4 | +0 | +0 | +0 | REJECT |
| C_AGGRESSIVE_WATCH | 14 | 8/8/4/4 | +0 | +0 | +0 | REJECT |

## Decision

REJECT ALL: no variant improved TIMELY/MISS enough to justify live alerts.

## Decision Notes

- A variant must raise TIMELY or reduce MISS without increasing wrong-side STRONG.
- If a variant only adds weak alerts without coverage improvement, keep it in research.
- This report tests direction timing only; VectorBT/QuantStats should test trade PnL next.

## Candidate Signals - A_STRICT

### 2026-05-29

- 2026-05-28 10:19:00 candidate_rebound_entry_watch/long/STRONG conf=80 price=145.3
- 2026-05-28 10:31:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=144.185
- 2026-05-28 10:44:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=145.21

## Candidate Signals - B_BALANCED

### 2026-05-28

- 2026-05-27 10:33:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=139.47

### 2026-05-29

- 2026-05-28 10:19:00 candidate_rebound_entry_watch/long/STRONG conf=80 price=145.3
- 2026-05-28 10:36:00 candidate_rebound_entry_watch/long/STRONG conf=80 price=145.05
- 2026-05-28 10:52:00 candidate_rebound_entry_watch/long/STRONG conf=80 price=146.24
- 2026-05-28 11:16:00 candidate_rebound_entry_watch/long/STRONG conf=65 price=146.47
- 2026-05-28 11:48:00 candidate_rebound_entry_watch/long/STRONG conf=80 price=146.215

## Candidate Signals - C_AGGRESSIVE_WATCH

### 2026-05-28

- 2026-05-27 10:21:00 candidate_breakdown_follow/short/WEAK conf=60 price=141.2001
- 2026-05-27 10:31:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=138.92

### 2026-05-29

- 2026-05-28 10:19:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=145.3
- 2026-05-28 10:34:00 candidate_breakdown_follow/short/WEAK conf=60 price=143.84
- 2026-05-28 10:39:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=144.95
- 2026-05-28 10:59:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=146.69
- 2026-05-28 11:19:00 candidate_rebound_entry_watch/long/WEAK conf=45 price=146.8
- 2026-05-28 11:41:00 candidate_rebound_entry_watch/long/WEAK conf=45 price=147.173
- 2026-05-28 12:17:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=147.1
- 2026-05-28 12:40:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=146.77
- 2026-05-28 13:14:00 candidate_breakdown_follow/short/WEAK conf=55 price=147.285
- 2026-05-28 13:18:00 candidate_rebound_entry_watch/long/WEAK conf=60 price=146.9933
- 2026-05-28 13:35:00 candidate_breakdown_follow/short/WEAK conf=60 price=146.56
- 2026-05-28 13:38:00 candidate_rebound_entry_watch/long/WEAK conf=55 price=146.745
