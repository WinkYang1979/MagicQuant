"""
MagicQuant Arena replay tool.
VERSION : v1.0.0
DEPENDS : argparse, pathlib, config.settings, trial.arena_trial_controller
"""
from __future__ import annotations

import argparse
from pathlib import Path

from trial.arena_trial_controller import TrialDayRecord, load_trial_records


def render_replay(record: TrialDayRecord) -> str:
    mechanical = [member for member in record.champion_members if member.startswith("h")]
    ai_votes = [member for member in record.champion_members if member not in mechanical]
    return "\n".join(
        [
            f"# Arena Replay {record.date}",
            "",
            f"Symbol: {record.symbol}",
            f"All Strategy Votes: {', '.join(record.champion_members)}",
            f"AI Votes: {', '.join(ai_votes) if ai_votes else 'none'}",
            f"Mechanical Votes: {', '.join(mechanical) if mechanical else 'none'}",
            "",
            "Champion Portfolio Formation:",
            f"- Bull Votes: {record.bull_votes}",
            f"- Bear Votes: {record.bear_votes}",
            f"- Net Score: {record.net_score}",
            f"- Final Signal: {record.champion_signal}",
            f"- Preferred Instrument: {record.preferred_instrument}",
            "",
            "Benchmark:",
            f"- Buy & Hold RKLB: {record.actual_result.benchmark_a_pnl:+.2f}",
            f"- Current Main Strategy: {record.actual_result.benchmark_b_pnl:+.2f}",
            f"- No Trade: {record.actual_result.benchmark_c_pnl:+.2f}",
            "",
            f"Final Result: {record.actual_result.champion_pnl:+.2f}",
            f"Real-money execution would have produced: {record.actual_result.champion_pnl:+.2f}",
            "",
        ]
    )


def replay_date(target_date: str, data_dir: Path | None = None) -> str:
    for record in load_trial_records(data_dir):
        if record.date == target_date:
            return render_replay(record)
    raise ValueError(f"no Arena Trial record for {target_date}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay one Arena Trial date.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    print(replay_date(args.date, Path(args.data_dir) if args.data_dir else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
