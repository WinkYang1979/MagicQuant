"""
MagicQuant Edge Attribution Analyzer tests.
VERSION : v1.0.0
DEPENDS : pathlib, tempfile, core.analysis.edge_attribution
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analysis.edge_attribution import (
    HIGH,
    LOW,
    MODERATE,
    STRONG,
    WEAK,
    analyze_edge,
    load_and_analyze,
    render_report,
    write_outputs,
)


def _record(day, pnl, family_contrib, time_bucket="Opening Session", direction="LONG", ai_votes=None):
    return {
        "date": f"2026-06-{day:02d}",
        "champion_signal": direction,
        "champion_members": ["h1_trend", "claude"],
        "time_bucket": time_bucket,
        "family_contributions": family_contrib,
        "actual_result": {"champion_pnl": pnl},
        "ai_votes": ai_votes or {"Claude": direction, "GPT": direction},
    }


def test_empty_data_returns_weak_unknown():
    analysis = analyze_edge([], [], [], [], [])
    assert analysis.current_champion == "UNKNOWN"
    assert analysis.total_pnl == 0.0
    assert analysis.edge_status == WEAK
    assert analysis.luck_score == 0
    assert "unproven" in analysis.conclusion


def test_single_family_advantage_is_concentrated():
    rows = [_record(idx, 10.0, {"Trend Family": 10.0}) for idx in range(1, 11)]
    analysis = analyze_edge([], [], [], [], rows)
    trend = next(row for row in analysis.family_attribution if row.name == "Trend Family")
    assert trend.contribution_pct == 100.0
    assert analysis.concentration_risk == HIGH
    assert analysis.edge_status == WEAK


def test_multi_family_balanced_edge_is_strong_low_luck():
    rows = []
    for idx in range(1, 11):
        rows.append(
            _record(
                idx,
                10.0,
                {
                    "Trend Family": 3.0,
                    "Volume Family": 3.0,
                    "AI Family": 2.0,
                    "Mean Reversion Family": 1.0,
                    "Event Family": 1.0,
                },
                time_bucket="Opening Session" if idx <= 5 else "Morning Session",
            )
        )
    analysis = analyze_edge([], [], [], [], rows)
    assert analysis.total_pnl == 100.0
    assert analysis.concentration_risk == LOW
    assert analysis.luck_score == 10
    assert analysis.edge_status == STRONG
    assert next(row for row in analysis.time_attribution if row.name == "Opening Session").contribution_pct == 50.0


def test_high_luck_score_from_one_extreme_day():
    rows = [_record(1, 90.0, {"Trend Family": 45.0, "AI Family": 45.0})]
    rows.extend(_record(idx, 1.0, {"Trend Family": 0.5, "AI Family": 0.5}) for idx in range(2, 11))
    analysis = analyze_edge([], [], [], [], rows)
    assert analysis.luck_score >= 90
    assert analysis.edge_status == WEAK


def test_direction_and_ai_attribution():
    rows = [
        _record(1, 10.0, {"AI Family": 10.0}, direction="LONG", ai_votes={"Claude": "LONG", "GPT": "SHORT"}),
        _record(2, -4.0, {"AI Family": -4.0}, direction="SHORT", ai_votes={"Claude": "LONG", "GPT": "SHORT"}),
        _record(3, 6.0, {"AI Family": 6.0}, direction="SHORT", ai_votes={"Claude": "SHORT", "GPT": "SHORT"}),
    ]
    analysis = analyze_edge([], [], [], [], rows)
    long_bucket = next(row for row in analysis.direction_attribution if row.name == "LONG")
    short_bucket = next(row for row in analysis.direction_attribution if row.name == "SHORT")
    assert long_bucket.pnl == 10.0
    assert short_bucket.pnl == 2.0
    claude = next(row for row in analysis.ai_attribution if row.name == "Claude")
    assert claude.participation_count == 3
    assert claude.agreement_rate == 0.6667


def test_report_and_load_from_existing_files():
    rows = [_record(idx, 5.0, {"Trend Family": 2.5, "AI Family": 2.5}) for idx in range(1, 6)]
    analysis = analyze_edge([], [], [], [], rows)
    report = render_report(analysis)
    assert "Strategy Family Attribution" in report
    assert "Time Attribution" in report
    assert "AI Attribution" in report
    assert "EDGE STATUS:" in report

    with TemporaryDirectory() as tmp:
        trial_path = Path(tmp) / "arena_trial_records.jsonl"
        trial_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        loaded = load_and_analyze(
            Path(tmp) / "champion_history.jsonl",
            Path(tmp) / "fitness_scores.jsonl",
            Path(tmp) / "strategy_rankings.jsonl",
            Path(tmp) / "benchmark_results.json",
            trial_path,
        )
        assert loaded.total_pnl == 25.0
        report_path = Path(tmp) / "champion_edge_report.md"
        latest_path = Path(tmp) / "latest.json"
        write_outputs(loaded, report_path, latest_path)
        assert report_path.exists()
        assert json.loads(latest_path.read_text(encoding="utf-8"))["total_pnl"] == 25.0


if __name__ == "__main__":
    test_empty_data_returns_weak_unknown()
    test_single_family_advantage_is_concentrated()
    test_multi_family_balanced_edge_is_strong_low_luck()
    test_high_luck_score_from_one_extreme_day()
    test_direction_and_ai_attribution()
    test_report_and_load_from_existing_files()
    print("Edge Attribution tests passed")
