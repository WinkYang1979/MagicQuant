# Breakdown/Rebound Patch Replay

Scope: synthetic replay from saved `triggers.json` snapshots; no live strategy state is modified.

| Date | Added patch signals | Before T/L/M/W | After T/L/M/W | Wrong STRONG before→after |
|---|---:|---|---|---:|
| 2026-05-26 | 0 | 1/2/0/1 | 1/2/0/1 | 3→3 |
| 2026-05-27 | 0 | 1/2/0/2 | 1/2/0/2 | 1→1 |
| 2026-05-28 | 0 | 3/6/8/3 | 3/6/8/3 | 9→9 |
| 2026-05-29 | 1 | 0/2/3/0 | 1/1/3/0 | 0→0 |

Added on 2026-05-29:
- 2026-05-29 00:21:43 crash_rebound_watch/long/WEAK conf=50 price=144.17


## Total

- Added patch signals: 1
- Before TIMELY/LATE/MISS/WRONG_SIDE: 5/12/11/6
- After TIMELY/LATE/MISS/WRONG_SIDE: 6/11/11/6
- Wrong-side STRONG: 13 -> 13

Note: this replay can only add signals at archived snapshot times. It is conservative for new early signals between existing pushes.