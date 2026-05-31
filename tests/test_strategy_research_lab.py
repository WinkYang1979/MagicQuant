"""
MagicQuant Strategy Research Lab tests.
VERSION : v1.0.0
DEPENDS : pathlib, tempfile, research.strategy_research_lab
"""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.strategy_research_lab import (  # noqa: E402
    Bar,
    ResearchLab,
    build_research_queue,
    generate_reports,
)


def _bar(day: str, minute: int, close: float, volume: float = 1000.0) -> Bar:
    from datetime import datetime, timedelta

    ts = datetime.strptime(day + " 09:30:00", "%Y-%m-%d %H:%M:%S") + timedelta(minutes=minute)
    return Bar(ts, close, close + 0.1, close - 0.1, close, volume)


def _records():
    rows = []
    for idx in range(1, 8):
        rows.append(
            {
                "date": f"2026-06-{idx:02d}",
                "signal_time": f"2026-06-{idx:02d} 10:30:00",
                "entry_price": 100.0,
                "close_price": 102.0 if idx % 2 else 98.0,
                "champion_pnl": 4.0 if idx % 2 else -4.0,
                "benchmark_a_pnl": 2.0 if idx % 2 else -2.0,
                "champion_signal": "LONG" if idx % 2 else "SHORT",
                "family_contributions": {"Trend Family": 2.0, "AI Family": 2.0},
                "strategy_votes": [
                    {"member_id": "h1_trend", "direction": "bull", "family": "Trend Family", "reason": "day_return=0.01"},
                    {"member_id": "h2_mean_reversion", "direction": "neutral", "family": "Mean Reversion Family", "reason": "rsi=55"},
                    {"member_id": "h3_volume_breakout", "direction": "bull" if idx % 3 == 0 else "neutral", "family": "Volume Family", "reason": "volume_ratio=1.6"},
                    {"member_id": "gpt", "direction": "bull", "family": "AI Family"},
                    {"member_id": "claude", "direction": "bull", "family": "AI Family"},
                    {"member_id": "deepseek", "direction": "neutral", "family": "AI Family"},
                    {"member_id": "kimi", "direction": "bear", "family": "AI Family"},
                ],
            }
        )
    return rows


def _bars():
    days = {}
    for idx in range(1, 8):
        day = f"2026-06-{idx:02d}"
        days[day] = [_bar(day, minute, 100.0 + minute * 0.02, 1000 + minute) for minute in range(390)]
    return days


def test_research_lab_builds_all_reports():
    lab = ResearchLab(_bars(), _bars(), _bars(), _records())
    reports = lab.build_all()
    assert len(reports) == 10
    assert "REPORT_VOLUME_BREAKOUT.md" in reports
    assert "Executive Summary" in reports["REPORT_ARENA_META.md"]
    assert "Research Queue Status: WAITING_FOR_HUMAN_REVIEW" in reports["REPORT_PARAMETER_SURFACE.md"]


def test_research_queue_blocks_direct_optimization():
    queue = build_research_queue(["REPORT_VOLUME_BREAKOUT.md"])
    assert "Observation First, Optimization Later" in queue
    assert "No parameter changes are approved" in queue
    assert "WAITING_FOR_HUMAN_REVIEW" in queue


def test_generate_reports_writes_expected_files():
    with TemporaryDirectory() as tmp:
        out = Path(tmp)
        written = generate_reports(out)
        assert len(written) == 11
        assert (out / "REPORT_AI_SIGNAL_STUDY.md").exists()
        assert (out / "RESEARCH_QUEUE.md").exists()


if __name__ == "__main__":
    test_research_lab_builds_all_reports()
    test_research_queue_blocks_direct_optimization()
    test_generate_reports_writes_expected_files()
    print("Strategy Research Lab tests passed")
