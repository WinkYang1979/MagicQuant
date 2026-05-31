"""
MagicQuant Champion Stability Analyzer tests.
VERSION : v1.0.0
DEPENDS : pathlib, tempfile, core.analysis.champion_stability
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analysis.champion_stability import (
    DANGER,
    HEALTHY,
    HIGH,
    KEEP,
    LOW,
    REPLACE,
    WATCH,
    analyze_stability,
    load_and_analyze,
    render_report,
    write_outputs,
)


def _history(ids):
    return [
        {"date": f"2026-06-{idx + 1:02d}", "champion_id": champion_id, "daily_result": 10.0, "max_drawdown": -0.02}
        for idx, champion_id in enumerate(ids)
    ]


def _fitness(champion_id="S003", days=20, pf_start=1.8, pf_step=0.0, pnl_start=10.0, pnl_step=0.0, dd_start=-0.02, dd_step=0.0):
    rows = []
    for idx in range(days):
        rows.append(
            {
                "date": f"2026-06-{idx + 1:02d}",
                "strategy_id": champion_id,
                "profit_factor": round(pf_start + pf_step * idx, 4),
                "win_rate": 0.72,
                "max_drawdown": round(dd_start + dd_step * idx, 4),
                "pnl": round(pnl_start + pnl_step * idx, 4),
            }
        )
    return rows


def test_empty_data_returns_replace():
    analysis = analyze_stability([], [], [], [])
    assert analysis.current_champion == "UNKNOWN"
    assert analysis.health_score == 0
    assert analysis.status == DANGER
    assert analysis.failure_signals.warning_level == HIGH
    assert analysis.recommendation == REPLACE


def test_single_healthy_champion_gets_keep():
    history = _history(["S003"] * 20)
    fitness = _fitness("S003", days=20, pf_start=1.9, pnl_start=12.0, dd_start=-0.02)
    analysis = analyze_stability(history, fitness, [], [])
    assert analysis.current_champion == "S003"
    assert analysis.lifetime.current_lifetime == 20
    assert analysis.turnover_count_30d == 0
    assert analysis.status == HEALTHY
    assert analysis.failure_signals.warning_level == LOW
    assert analysis.recommendation == KEEP


def test_frequent_switching_champion_warns():
    ids = ["S001", "S002"] * 10
    history = _history(ids)
    fitness = _fitness("S002", days=20, pf_start=1.4, pnl_start=4.0, dd_start=-0.04)
    analysis = analyze_stability(history, fitness, [], [])
    assert analysis.turnover_count_30d == 19
    assert analysis.failure_signals.frequent_turnover is True
    assert analysis.recommendation in {WATCH, REPLACE}


def test_pf_decline_and_drawdown_expansion_raise_warning():
    history = _history(["S003"] * 20)
    fitness = _fitness("S003", days=20, pf_start=2.0, pf_step=-0.06, pnl_start=20.0, pnl_step=-0.8, dd_start=-0.01, dd_step=-0.003)
    analysis = analyze_stability(history, fitness, [], [])
    assert analysis.failure_signals.pf_declining is True
    assert analysis.failure_signals.pnl_declining is True
    assert analysis.failure_signals.drawdown_expanding is True
    assert analysis.failure_signals.warning_level == HIGH
    assert analysis.recommendation == REPLACE


def test_report_and_file_outputs_include_required_fields():
    history = _history(["S003"] * 8)
    fitness = _fitness("S003", days=8, pf_start=1.6, pnl_start=8.0, dd_start=-0.03)
    analysis = analyze_stability(history, fitness, [], [])
    report = render_report(analysis)
    assert "Champion: S003" in report
    assert "Health Score:" in report
    assert "Turnover Rate:" in report
    assert "Recommendation:" in report

    with TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "champion_stability_report.md"
        latest_path = Path(tmp) / "latest.json"
        write_outputs(analysis, report_path, latest_path)
        assert report_path.exists()
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        assert latest["current_champion"] == "S003"


def test_load_and_analyze_uses_existing_files_only():
    with TemporaryDirectory() as tmp:
        champion_path = Path(tmp) / "champion_history.jsonl"
        fitness_path = Path(tmp) / "fitness_scores.jsonl"
        champion_path.write_text("\n".join(json.dumps(row) for row in _history(["S003"] * 6)) + "\n", encoding="utf-8")
        fitness_path.write_text("\n".join(json.dumps(row) for row in _fitness("S003", days=6, pf_start=1.5)) + "\n", encoding="utf-8")
        analysis = load_and_analyze(champion_path, fitness_path, Path(tmp) / "strategy_rankings.jsonl", Path(tmp) / "benchmark_results.json")
        assert analysis.current_champion == "S003"


if __name__ == "__main__":
    test_empty_data_returns_replace()
    test_single_healthy_champion_gets_keep()
    test_frequent_switching_champion_warns()
    test_pf_decline_and_drawdown_expansion_raise_warning()
    test_report_and_file_outputs_include_required_fields()
    test_load_and_analyze_uses_existing_files_only()
    print("Champion Stability tests passed")
