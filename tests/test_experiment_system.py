"""
MagicQuant experiment system tests.
VERSION : v1.0.0
DEPENDS : pathlib, tempfile, core.experiment.frozen_guard, benchmark/journal/reports/tools
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.arena.champion_history import build_champion_history, render_champion_history
from core.arena.ensemble import ArenaSignal
from core.experiment.frozen_guard import check_frozen_guard, render_guard_report, save_manifest
from core.universe.universe_config import get_universe, validate_symbol
from journal.human_trade_journal import HumanArenaJournalEntry, render_weekly_journal
from reports.benchmark.benchmark_comparison import BENCHMARK_NAMES, BenchmarkResult, render_benchmark_report
from reports.daily.daily_review_generator import render_daily_review
from reports.final.arena_final_verdict import EXTEND_TO_12_WEEKS, final_verdict_decision
from reports.weekly.investment_committee import render_committee_report
from tools.arena_replay import replay_date
from trial.arena_trial_controller import (
    BENCHMARK_A,
    BENCHMARK_B,
    BENCHMARK_C,
    TrialActualResult,
    TrialBenchmark,
    run_daily_trial,
)


def _benchmarks():
    return (
        TrialBenchmark(BENCHMARK_A, "frozen", 0.0),
        TrialBenchmark(BENCHMARK_B, "frozen", 0.0),
        TrialBenchmark(BENCHMARK_C, "frozen", 0.0),
    )


def _trial_records(tmp: Path, champion_pnl: float = 10.0, main_pnl: float = 2.0):
    reports_dir = tmp / "reports"
    data_dir = tmp / "data"
    bench_a, bench_b, bench_c = _benchmarks()
    rows = []
    cursor = date(2026, 6, 1)
    while len(rows) < 30:
        if cursor.weekday() < 5:
            rows.append(
                run_daily_trial(
                    cursor.isoformat(),
                    [ArenaSignal("h1_trend", "bull"), ArenaSignal("gpt", "bull")],
                    bench_a,
                    bench_b,
                    bench_c,
                    TrialActualResult(champion_pnl, 1.0, main_pnl, 0.0, champion_max_drawdown=-0.02, benchmark_b_max_drawdown=-0.03),
                    reports_dir=reports_dir,
                    data_dir=data_dir,
                )
            )
        cursor += timedelta(days=1)
    return rows, reports_dir, data_dir


def test_frozen_guard_manifest_round_trip_and_report():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "frozen_manifest.json"
        save_manifest(path)
        result = check_frozen_guard(path)
        assert result.allowed_for_official_stats is True
        report = render_guard_report(result)
        assert "Allowed For Official Stats: True" in report


def test_benchmark_report_requires_all_six_baselines():
    results = [BenchmarkResult(name, float(idx), -0.01, "unit") for idx, name in enumerate(BENCHMARK_NAMES)]
    report = render_benchmark_report(results)
    assert "Random Direction Baseline" in report
    assert "Always Short RKLZ" in report


def test_reports_journal_history_replay_and_universe():
    with TemporaryDirectory() as tmp:
        rows, _, data_dir = _trial_records(Path(tmp))
        assert get_universe() == ("RKLB",)
        validate_symbol("RKLB")
        try:
            validate_symbol("ASTS")
            raise AssertionError("ASTS should be reserved but not enabled")
        except ValueError:
            pass

        daily = render_daily_review(rows[0])
        committee = render_committee_report("2026-W23", rows[:5])
        history = render_champion_history(build_champion_history(rows[:5]))
        replay = replay_date(rows[0].date, data_dir)
        journal = render_weekly_journal(
            [
                HumanArenaJournalEntry(rows[0].date, "LONG", "RKLX", "skip", 0.0, 0.0, 0.0, 10.0, 10.0, 0.0, "unit"),
            ]
        )
        assert "Arena Signal: LONG" in daily
        assert "Continue Trial: yes" in committee
        assert "Champion History" in history
        assert "Champion Portfolio Formation" in replay
        assert "Missed Opportunity" in journal


def test_final_verdict_allows_extend_only_for_close_six_week_gap():
    with TemporaryDirectory() as tmp:
        rows, _, _ = _trial_records(Path(tmp), champion_pnl=9.5, main_pnl=10.0)
        decision, reasons = final_verdict_decision(rows)
        assert decision == EXTEND_TO_12_WEEKS
        assert any("below 10%" in reason for reason in reasons)


if __name__ == "__main__":
    test_frozen_guard_manifest_round_trip_and_report()
    test_benchmark_report_requires_all_six_baselines()
    test_reports_journal_history_replay_and_universe()
    test_final_verdict_allows_extend_only_for_close_six_week_gap()
    print("Experiment system tests passed")
