"""
MagicQuant Champion History system.
VERSION : v1.0.0
DEPENDS : argparse, dataclasses, json, pathlib, typing, config.settings, trial.arena_trial_controller
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, List

from trial.arena_trial_controller import TrialDayRecord, _week_key, load_trial_records


@dataclass(frozen=True)
class ChampionHistoryEntry:
    date: str
    champion_portfolio: str
    dominant_signal_source: str
    daily_result: float
    week: str
    weekly_champion: str
    win_streak: int
    max_drawdown_record: float


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def default_data_path() -> Path:
    return _base_dir() / "data" / "arena" / "champion_history.jsonl"


def default_report_path() -> Path:
    return _base_dir() / "reports" / "arena" / "champion_history.md"


def build_champion_history(records: Iterable[TrialDayRecord]) -> List[ChampionHistoryEntry]:
    rows = sorted(records, key=lambda row: row.date)
    streak = 0
    worst_dd = 0.0
    entries: List[ChampionHistoryEntry] = []
    weekly_totals: dict[str, float] = {}
    for row in rows:
        weekly_totals[_week_key(row)] = weekly_totals.get(_week_key(row), 0.0) + row.actual_result.champion_pnl
    for row in rows:
        if row.actual_result.champion_pnl > 0:
            streak += 1
        else:
            streak = 0
        worst_dd = min(worst_dd, row.actual_result.champion_max_drawdown)
        members = list(row.champion_members)
        dominant = members[0] if members else "none"
        week = _week_key(row)
        entries.append(
            ChampionHistoryEntry(
                row.date,
                row.champion_signal,
                dominant,
                row.actual_result.champion_pnl,
                week,
                "Champion Portfolio" if weekly_totals[week] > 0 else "Benchmark",
                streak,
                worst_dd,
            )
        )
    return entries


def write_champion_history(entries: Iterable[ChampionHistoryEntry], data_path: Path | None = None) -> Path:
    out = data_path or default_data_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True) for entry in entries) + "\n", encoding="utf-8")
    return out


def render_champion_history(entries: Iterable[ChampionHistoryEntry]) -> str:
    lines = [
        "# Champion History",
        "",
        "| Date | Champion Portfolio | Dominant Source | Daily Result | Week | Weekly Champion | Win Streak | Max Drawdown Record |",
        "| --- | --- | --- | ---: | --- | --- | ---: | ---: |",
    ]
    for row in entries:
        lines.append(
            f"| {row.date} | {row.champion_portfolio} | {row.dominant_signal_source} | {row.daily_result:+.2f} | "
            f"{row.week} | {row.weekly_champion} | {row.win_streak} | {row.max_drawdown_record:+.2f} |"
        )
    return "\n".join(lines) + "\n"


def write_champion_history_report(entries: Iterable[ChampionHistoryEntry], report_path: Path | None = None) -> Path:
    out = report_path or default_report_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_champion_history(entries), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Arena champion history.")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    entries = build_champion_history(load_trial_records(Path(args.data_dir) if args.data_dir else None))
    write_champion_history(entries)
    write_champion_history_report(entries)
    print(f"[champion_history] wrote {default_report_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
