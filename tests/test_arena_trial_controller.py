"""
MagicQuant Arena Trial controller tests.
VERSION : v1.0.0
DEPENDS : pathlib, tempfile, trial.arena_trial_controller, core.arena.ensemble
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.arena.ensemble import ArenaSignal
from trial.arena_trial_controller import (
    BENCHMARK_A,
    BENCHMARK_B,
    BENCHMARK_C,
    FAIL,
    GO,
    TrialActualResult,
    TrialBenchmark,
    final_verdict,
    load_trial_records,
    render_final_verdict,
    run_daily_trial,
    run_from_payload,
    write_final_verdict,
)


def _benchmarks():
    return (
        TrialBenchmark(BENCHMARK_A, "frozen", 1.0),
        TrialBenchmark(BENCHMARK_B, "frozen", 2.0),
        TrialBenchmark(BENCHMARK_C, "frozen", 0.0),
    )


def test_daily_trial_records_required_fields_and_reports():
    with TemporaryDirectory() as tmp:
        reports_dir = Path(tmp)
        data_dir = Path(tmp) / "data"
        bench_a, bench_b, bench_c = _benchmarks()
        record = run_daily_trial(
            "2026-06-01",
            [
                ArenaSignal("h1_trend", "bull"),
                ArenaSignal("h2_mean_reversion", "neutral"),
                ArenaSignal("gpt", "bull"),
                ArenaSignal("claude", "bear"),
            ],
            bench_a,
            bench_b,
            bench_c,
            TrialActualResult(5.0, 1.0, 2.0, 0.0, "closed"),
            reports_dir=reports_dir,
            data_dir=data_dir,
        )
        assert record.date == "2026-06-01"
        assert record.champion_signal == "LONG"
        assert record.bull_votes == 2
        assert record.bear_votes == 1
        assert record.net_score == 1
        assert record.preferred_instrument == "RKLX"
        assert "gpt" in record.champion_members

        daily = (reports_dir / "daily_trial_log.md").read_text(encoding="utf-8")
        weekly = (reports_dir / "weekly_trial_summary.md").read_text(encoding="utf-8")
        assert "Champion Portfolio Signal" in daily
        assert "Benchmark A" in daily
        assert "Actual Result" in daily
        assert "2026-W23" in weekly
        assert len(load_trial_records(data_dir)) == 1


def test_trial_rejects_duplicate_daily_record():
    with TemporaryDirectory() as tmp:
        reports_dir = Path(tmp)
        data_dir = Path(tmp) / "data"
        bench_a, bench_b, bench_c = _benchmarks()
        kwargs = dict(
            trial_date="2026-06-02",
            signals=[ArenaSignal("h1_trend", "bull")],
            benchmark_a=bench_a,
            benchmark_b=bench_b,
            benchmark_c=bench_c,
            actual_result=TrialActualResult(1.0, 0.0, 0.0, 0.0),
            reports_dir=reports_dir,
            data_dir=data_dir,
        )
        run_daily_trial(**kwargs)
        try:
            run_daily_trial(**kwargs)
            raise AssertionError("duplicate trial day should fail")
        except ValueError as exc:
            assert "already exists" in str(exc)


def test_final_verdict_go_and_fail_are_explicit():
    go_records = []
    with TemporaryDirectory() as tmp:
        reports_dir = Path(tmp)
        data_dir = Path(tmp) / "data"
        bench_a, bench_b, bench_c = _benchmarks()
        trial_dates = []
        cursor = date(2026, 6, 1)
        while len(trial_dates) < 30:
            if cursor.weekday() < 5:
                trial_dates.append(cursor.isoformat())
            cursor += timedelta(days=1)
        for trial_date in trial_dates:
            record = run_daily_trial(
                trial_date,
                [ArenaSignal("h1_trend", "bull"), ArenaSignal("gpt", "bull")],
                bench_a,
                bench_b,
                bench_c,
                TrialActualResult(10.0, 1.0, 2.0, 0.0),
                reports_dir=reports_dir,
                data_dir=data_dir,
            )
            go_records.append(record)
        verdict, reasons = final_verdict(go_records)
        assert verdict == GO
        assert reasons == []
        text = render_final_verdict(go_records)
        assert "Final Conclusion: GO" in text

        path = write_final_verdict(reports_dir, data_dir)
        assert path.exists()

    fail_records = go_records[:29]
    verdict, reasons = final_verdict(fail_records)
    assert verdict == FAIL
    assert any("trading days" in reason for reason in reasons)


def test_run_from_payload_supports_frozen_family_champion_ids():
    payload = {
        "date": "2026-07-01",
        "allowed_member_ids": ["trend_champion", "ai_champion"],
        "signals": [
            {"member_id": "trend_champion", "direction": "bull"},
            {"member_id": "ai_champion", "direction": "bear"},
        ],
        "benchmarks": {
            "benchmark_a": {"status": "frozen", "pnl": 0.0},
            "benchmark_b": {"status": "frozen", "pnl": 0.0},
            "benchmark_c": {"status": "frozen", "pnl": 0.0},
        },
        "actual_result": {
            "champion_pnl": 0.0,
            "benchmark_a_pnl": 0.0,
            "benchmark_b_pnl": 0.0,
            "benchmark_c_pnl": 0.0,
            "note": "tie day",
        },
    }
    with TemporaryDirectory() as tmp:
        record = run_from_payload(payload, reports_dir=Path(tmp), data_dir=Path(tmp) / "data")
        assert record.champion_signal == "HOLD"
        assert record.preferred_instrument == "Cash"


if __name__ == "__main__":
    test_daily_trial_records_required_fields_and_reports()
    test_trial_rejects_duplicate_daily_record()
    test_final_verdict_go_and_fail_are_explicit()
    test_run_from_payload_supports_frozen_family_champion_ids()
    print("Arena Trial controller tests passed")
