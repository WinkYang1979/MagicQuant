# MagicQuant Project Memory Index

VERSION: v0.1.0  
DEPENDS: docs/AGENT_MEMORY.md

This index points AI agents to durable project memories. Prefer these files over scattered chat history.

## Canonical Memory

- `docs/AGENT_MEMORY.md` — stable long-term rules, user preferences, incidents, and strategy governance.
- `docs/STRATEGY_SCORECARD.md` — benchmark and before/after strategy comparison record.

## Recent Project Context

- `docs/discussion_2026-05-28_vectorbt_strategy_optimization.md` — vectorbt strategy optimization plan and guardrails.
- `CLAUDE_PLAN_2026-05-28_vectorbt_scheduler.md` — vectorbt scheduler plan that led to isolated daily/weekly research jobs.
- `CLAUDE_REVIEW_2026-05-28_vectorbt_strategy_plan_revisions.md` — Claude review notes for vectorbt strategy plan.
- `CLAUDE_PLAN_2026-05-23_holding_followup_priority.md` — holding follow-up priority and replay gates.
- `discussion_2026-05-21_signal_coverage_review.md` — direction signal coverage and wrong-side/miss analysis.

## Important Operational Files

- `research/vectorbt_lab/scheduler.py` — isolated research scheduler.
- `research/vectorbt_lab/daily_rklb_review.py` — daily RKLB review generator.
- `research/vectorbt_lab/fetch_1m_data.py` — isolated Futu 1m research data fetcher.
- `core/focus/swing_detector.py` — live trigger detection.
- `core/focus/pusher.py` — live Telegram signal formatting.
- `core/focus/position_followup.py` — holding follow-up state.
- `core/focus/data_quality.py` — K-line and indicator trust gate.

## Known Rule

Do not use this index as proof that current code behaves correctly. It is a map. Always verify with current code, tests, and replay logs before changing strategy behavior.
