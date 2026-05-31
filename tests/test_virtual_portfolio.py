"""
MagicQuant Virtual Portfolio tests.
VERSION : v1.0.0
DEPENDS : json, pathlib, tempfile, core.arena.virtual_portfolio
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.arena.virtual_portfolio import (  # noqa: E402
    INITIAL_CAPITAL,
    render_daily_report,
    simulate_portfolio,
    write_outputs,
)


def _record(day: str, signal: str):
    return {
        "date": day,
        "signal_time": f"{day} 10:30:00",
        "champion_signal": signal,
    }


def _prices(entry: float, close: float):
    return {
        "2026-06-01": {
            "2026-06-01 10:30:00": entry,
            "2026-06-01 15:59:00": close,
        },
        "2026-06-02": {
            "2026-06-02 10:30:00": entry,
            "2026-06-02 15:59:00": close,
        },
    }


def test_empty_portfolio_stays_cash():
    history, trades, metrics = simulate_portfolio([], {}, {})
    assert history == []
    assert trades == []
    assert metrics.portfolio_value == INITIAL_CAPITAL
    assert metrics.open_positions == {}


def test_long_signal_buys_rklx_and_updates_value():
    history, trades, metrics = simulate_portfolio([_record("2026-06-01", "LONG")], _prices(10.0, 11.0), {})
    assert history[-1].asset == "RKLX"
    assert history[-1].open_positions == {}
    assert history[-1].portfolio_value == 110000.0
    assert metrics.return_pct == 10.0
    assert trades[0].side == "BUY"
    assert trades[0].asset == "RKLX"
    assert trades[1].side == "SELL"


def test_short_signal_buys_rklz_and_updates_value():
    history, trades, metrics = simulate_portfolio([_record("2026-06-01", "SHORT")], {}, _prices(20.0, 22.0))
    assert history[-1].asset == "RKLZ"
    assert history[-1].portfolio_value == 110000.0
    assert metrics.return_pct == 10.0
    assert trades[0].asset == "RKLZ"


def test_hold_signal_keeps_cash_and_no_trade():
    history, trades, metrics = simulate_portfolio([_record("2026-06-01", "HOLD")], _prices(10.0, 11.0), _prices(20.0, 22.0))
    assert history[-1].asset == "Cash"
    assert history[-1].portfolio_value == INITIAL_CAPITAL
    assert trades == []
    assert metrics.cash == INITIAL_CAPITAL


def test_report_and_outputs_include_required_metrics():
    history, trades, metrics = simulate_portfolio(
        [_record("2026-06-01", "LONG"), _record("2026-06-02", "HOLD")],
        _prices(10.0, 11.0),
        _prices(20.0, 22.0),
    )
    report = render_daily_report(history, trades, metrics)
    assert "Portfolio Value" in report
    assert "Profit Factor" in report
    assert "Open Positions" in report
    assert "would end at" in report

    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        history_path, trade_path, report_path = write_outputs(
            history,
            trades,
            metrics,
            tmp_path / "portfolio_history.jsonl",
            tmp_path / "trade_history.jsonl",
            tmp_path / "daily_portfolio_report.md",
        )
        assert history_path.exists()
        assert trade_path.exists()
        assert report_path.exists()
        first = json.loads(history_path.read_text(encoding="utf-8").splitlines()[0])
        assert first["asset"] == "RKLX"


if __name__ == "__main__":
    test_empty_portfolio_stays_cash()
    test_long_signal_buys_rklx_and_updates_value()
    test_short_signal_buys_rklz_and_updates_value()
    test_hold_signal_keeps_cash_and_no_trade()
    test_report_and_outputs_include_required_metrics()
    print("Virtual Portfolio tests passed")
