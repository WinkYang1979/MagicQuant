"""Tests for OpenAI duel adaptive paper loop."""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.sim_weekly.duel import BarContext
from core.sim_weekly.engine import _load_5m
from core.sim_weekly.openai_contestant import OpenAIContestant
from core.sim_weekly.portfolio import SimPortfolio
from scripts.sim_weekly_openai_nightly_review import (
    _config_for_regime,
    _trade_time_bucket_stats,
    _weighted_cycle_review,
    run_review,
)


def _bar(ts: str, close: float) -> dict:
    return {"time": ts, "open": close, "high": close, "low": close, "close": close, "volume": 1000}


def _ctx(ts: str, bars_now: dict, history: dict | None = None, portfolio: SimPortfolio | None = None) -> BarContext:
    return BarContext(
        datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"),
        ts,
        bars_now,
        history or {"RKLB": [], "RKLX": [], "RKLZ": []},
        portfolio or SimPortfolio(),
        False,
    )


def test_bull_config_relaxes_riding_parameters():
    cfg = _config_for_regime("bull")
    params = cfg["params"]
    assert cfg["profile"] == "bull_ride"
    assert params["rklx_stop_pct"] > 0.06
    assert params["rklx_fraction"] > 0.52
    assert params["cooldown_bars"] < 5


def test_contestant_default_does_not_load_live_config():
    contestant = OpenAIContestant()
    assert contestant._profile == "neutral"


def test_contestant_loads_adaptive_config_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cfg.json"
        path.write_text(json.dumps(_config_for_regime("bull")), encoding="utf-8")
        contestant = OpenAIContestant(path)
        assert contestant._profile == "bull_ride"
        assert contestant._params["rklx_stop_pct"] > 0.06


def test_openai_cycle_review_weights_recent_observations_more():
    history = [
        {"date": "2026-05-01", "benchmark_buyhold_RKLB_pct": -6, "openai_return_pct": -2, "openai_max_drawdown_pct": -4, "claude_return_pct": 1},
        {"date": "2026-05-08", "benchmark_buyhold_RKLB_pct": -4, "openai_return_pct": -1, "openai_max_drawdown_pct": -3, "claude_return_pct": 1},
        {"date": "2026-05-15", "benchmark_buyhold_RKLB_pct": 4, "openai_return_pct": 2, "openai_max_drawdown_pct": -2, "claude_return_pct": 1},
        {"date": "2026-05-22", "benchmark_buyhold_RKLB_pct": 8, "openai_return_pct": 3, "openai_max_drawdown_pct": -1, "claude_return_pct": 1},
    ]

    review = _weighted_cycle_review(history)

    assert review["sample_count"] == 4
    assert review["recency_weights_old_to_new"] == [1, 2, 3, 4]
    assert review["weighted_regime"] == "bull"


def test_openai_fast_cycle_uses_last_two_observations():
    history = [
        {"date": "2026-05-01", "benchmark_buyhold_RKLB_pct": -8, "openai_return_pct": -3},
        {"date": "2026-05-08", "benchmark_buyhold_RKLB_pct": -6, "openai_return_pct": -2},
        {"date": "2026-05-15", "benchmark_buyhold_RKLB_pct": 4, "openai_return_pct": 1},
        {"date": "2026-05-22", "benchmark_buyhold_RKLB_pct": 8, "openai_return_pct": 2},
    ]

    review = _weighted_cycle_review(history, 2)

    assert review["dates"] == ["2026-05-15", "2026-05-22"]
    assert review["recency_weights_old_to_new"] == [1, 2]
    assert review["weighted_regime"] == "bull"


def test_openai_time_bucket_stats_from_trade_pairs():
    trades = [
        {"ts": "2026-04-27 15:15:00", "side": "buy", "ticker": "RKLX", "session": "rth"},
        {"ts": "2026-04-28 10:40:00", "side": "sell", "ticker": "RKLX", "pnl": -10, "session": "rth"},
        {"ts": "2026-05-01 15:15:00", "side": "buy", "ticker": "RKLX", "session": "rth"},
        {"ts": "2026-05-01 15:35:00", "side": "sell", "ticker": "RKLX", "pnl": 5, "session": "rth"},
        {"ts": "2026-05-02 03:00:00", "side": "buy", "ticker": "RKLX", "session": "prepost"},
        {"ts": "2026-05-02 03:20:00", "side": "sell", "ticker": "RKLX", "pnl": -2, "session": "prepost"},
    ]

    stats = _trade_time_bucket_stats(trades)

    assert stats["monday_late"]["losses"] == 1
    assert stats["friday_late"]["pnl"] == 5
    assert stats["non_rth_prepost"]["losses"] == 1


def test_openai_regime_config_preserves_no_rklb_no_short_discipline():
    for regime in ("bull", "bear", "chop"):
        params = _config_for_regime(regime)["params"]
        assert "rklb_fraction" not in params
        assert params["short_fraction"] == 0.0


def test_openai_blocks_oversold_rklz_entry():
    contestant = OpenAIContestant()
    closes = [150 - i * 0.6 for i in range(36)]
    history = {
        "RKLB": [_bar(f"2026-05-29 09:{30 + i:02d}:00", px) for i, px in enumerate(closes[:-1])],
        "RKLX": [],
        "RKLZ": [],
    }
    ctx = _ctx("2026-05-29 12:30:00", {"RKLB": _bar("2026-05-29 12:30:00", closes[-1])}, history)

    signal = contestant._signal(ctx)

    assert signal["direction"] == "flat"
    assert signal["reason"] == "oversold RKLZ guard"


def test_openai_blocks_late_day_rklz_entry():
    contestant = OpenAIContestant()
    closes = [150 - i * 0.25 for i in range(36)]
    history = {
        "RKLB": [_bar(f"2026-05-29 09:{30 + i:02d}:00", px) for i, px in enumerate(closes[:-1])],
        "RKLX": [],
        "RKLZ": [],
    }
    ctx = _ctx("2026-05-29 14:40:00", {"RKLB": _bar("2026-05-29 14:40:00", closes[-1])}, history)

    signal = contestant._signal(ctx)

    assert signal["direction"] == "flat"
    assert signal["reason"] == "late-day RKLZ guard"


def test_openai_long_signal_uses_rklx_not_rklb():
    contestant = OpenAIContestant()
    bars = _load_5m("RKLB", {"2026-05-26", "2026-05-27"})
    timeline = sorted(ts for ts in bars if ts <= "2026-05-27 13:05:00")
    history = {"RKLB": [bars[ts] for ts in timeline[:-1]], "RKLX": [], "RKLZ": []}
    ctx = _ctx("2026-05-27 13:05:00", {"RKLB": bars["2026-05-27 13:05:00"]}, history)

    signal = contestant._signal(ctx)

    assert signal["direction"] == "long"
    assert signal["ticker"] == "RKLX"


def test_openai_blocks_rklx_on_monday_late_session():
    contestant = OpenAIContestant()
    bars = _load_5m("RKLB", {"2026-04-27"})
    timeline = sorted(ts for ts in bars if ts <= "2026-04-27 15:15:00")
    history = {"RKLB": [bars[ts] for ts in timeline[:-1]], "RKLX": [], "RKLZ": []}
    ctx = _ctx("2026-04-27 15:15:00", {"RKLB": bars["2026-04-27 15:15:00"]}, history)

    signal = contestant._signal(ctx)

    assert signal["direction"] == "flat"
    assert signal["reason"] == "RKLX Monday late guard"


def test_openai_blocks_high_gap_low_week_chase():
    contestant = OpenAIContestant()
    bars = _load_5m("RKLB", {"2026-04-27", "2026-04-28", "2026-04-29", "2026-04-30"})
    timeline = sorted(ts for ts in bars if ts <= "2026-04-30 10:45:00")
    history = {"RKLB": [bars[ts] for ts in timeline[:-1]], "RKLX": [], "RKLZ": []}
    ctx = _ctx("2026-04-30 10:45:00", {"RKLB": bars["2026-04-30 10:45:00"]}, history)

    signal = contestant._signal(ctx)

    assert signal["direction"] == "flat"
    assert signal["reason"] == "RKLX high-gap chase guard"


def test_openai_profit_lock_moves_stop_above_cost():
    contestant = OpenAIContestant()
    pf = SimPortfolio()
    pf.positions["RKLX"] = {"qty": 10, "cost_price": 100.0, "open_ts": "2026-05-29 10:00:00", "stop": 96.0, "peak": 100.0, "stop_pct": 0.038}
    ctx = _ctx("2026-05-29 10:05:00", {"RKLX": {"time": "2026-05-29 10:05:00", "open": 100, "high": 106, "low": 104, "close": 105, "volume": 1000}}, portfolio=pf)

    contestant._manage_stops(ctx)

    assert pf.positions["RKLX"]["stop"] >= 100.6


def test_openai_opposite_signal_does_not_same_bar_reverse():
    contestant = OpenAIContestant()
    pf = SimPortfolio()
    pf.positions["RKLZ"] = {"qty": 100, "cost_price": 2.0, "open_ts": "2026-05-29 10:00:00", "stop": 1.9, "peak": 2.0, "stop_pct": 0.065}
    contestant._signal = lambda _ctx: {
        "direction": "long",
        "ticker": "RKLX",
        "fraction": 0.34,
        "stop_pct": 0.060,
        "reason": "test long",
    }
    bars_now = {
        "RKLB": _bar("2026-05-29 11:30:00", 140),
        "RKLX": _bar("2026-05-29 11:30:00", 100),
        "RKLZ": _bar("2026-05-29 11:30:00", 1.95),
    }
    ctx = _ctx("2026-05-29 11:30:00", bars_now, portfolio=pf)

    contestant.on_bar(ctx)

    assert "RKLZ" not in pf.positions
    assert "RKLX" not in pf.positions
    assert [t["side"] for t in pf.trades] == ["sell"]


def test_openai_weekly_risk_halt_blocks_new_entries():
    contestant = OpenAIContestant()
    contestant.reset(10000)
    contestant.peak_equity = 10000
    pf = SimPortfolio(initial_capital=10000)
    pf.cash = 8900
    bars_now = {
        "RKLB": _bar("2026-05-29 11:30:00", 140),
        "RKLX": _bar("2026-05-29 11:30:00", 100),
        "RKLZ": _bar("2026-05-29 11:30:00", 2),
    }
    ctx = _ctx("2026-05-29 11:30:00", bars_now, portfolio=pf)

    assert contestant._risk_halt_if_needed(ctx, {"RKLB": 140, "RKLX": 100, "RKLZ": 2}) is True
    assert contestant.week_halted is True


def test_nightly_review_writes_hypothesis_log():
    with tempfile.TemporaryDirectory() as tmp:
        sim = Path(tmp)
        ledger = sim / "duel_ledger_2026-05-29.json"
        ledger.write_text(json.dumps({
            "date": "2026-05-29",
            "contestants": {
                "openai_v1": {
                    "return_pct": 1.0,
                    "max_drawdown_pct": -2.0,
                    "n_trades": 2,
                    "benchmark_buyhold_RKLB_pct": 4.0,
                    "trades": [],
                },
                "claude_rule": {"return_pct": 0.5, "trades": []},
            },
        }), encoding="utf-8")
        import scripts.sim_weekly_openai_nightly_review as nightly

        old_sim = nightly.SIM_DIR
        old_state = nightly.STATE_PATH
        old_config = nightly.CONFIG_PATH
        old_log = nightly.LOG_PATH
        try:
            nightly.SIM_DIR = sim
            nightly.STATE_PATH = sim / "state.json"
            nightly.CONFIG_PATH = sim / "config.json"
            nightly.LOG_PATH = sim / "log.json"
            first = run_review("2026-05-29", apply=True)
            assert first["ok"]
            second = run_review("2026-05-29", apply=True)
            assert second["ok"]
            log = json.loads((sim / "log.json").read_text(encoding="utf-8"))
            assert "observation" in log[-1]
            assert "hypothesis" in log[-1]
            assert "tomorrow_trial" in log[-1]
        finally:
            nightly.SIM_DIR = old_sim
            nightly.STATE_PATH = old_state
            nightly.CONFIG_PATH = old_config
            nightly.LOG_PATH = old_log


def test_nightly_review_backfills_previous_result():
    with tempfile.TemporaryDirectory() as tmp:
        sim = Path(tmp)
        (sim / "duel_ledger_2026-05-29.json").write_text(json.dumps({
            "date": "2026-05-29",
            "contestants": {
                "openai_v1": {"return_pct": 0.5, "max_drawdown_pct": -1.0, "n_trades": 1, "benchmark_buyhold_RKLB_pct": 4.0, "trades": []},
                "claude_rule": {"return_pct": 0.2, "trades": []},
            },
        }), encoding="utf-8")
        (sim / "duel_ledger_2026-05-30.json").write_text(json.dumps({
            "date": "2026-05-30",
            "contestants": {
                "openai_v1": {"return_pct": 1.0, "max_drawdown_pct": -0.8, "n_trades": 2, "benchmark_buyhold_RKLB_pct": 5.0, "trades": []},
                "claude_rule": {"return_pct": 0.3, "trades": []},
            },
        }), encoding="utf-8")
        import scripts.sim_weekly_openai_nightly_review as nightly

        old_sim = nightly.SIM_DIR
        old_state = nightly.STATE_PATH
        old_config = nightly.CONFIG_PATH
        old_log = nightly.LOG_PATH
        try:
            nightly.SIM_DIR = sim
            nightly.STATE_PATH = sim / "state.json"
            nightly.CONFIG_PATH = sim / "config.json"
            nightly.LOG_PATH = sim / "log.json"
            assert run_review("2026-05-29", apply=True)["ok"]
            assert run_review("2026-05-30", apply=True)["ok"]
            log = json.loads((sim / "log.json").read_text(encoding="utf-8"))
            assert log[0]["next_day_result"]["evaluated_on"] == "2026-05-30"
            assert log[0]["next_day_result"]["beat_claude"] is True
        finally:
            nightly.SIM_DIR = old_sim
            nightly.STATE_PATH = old_state
            nightly.CONFIG_PATH = old_config
            nightly.LOG_PATH = old_log


if __name__ == "__main__":
    test_bull_config_relaxes_riding_parameters()
    test_contestant_default_does_not_load_live_config()
    test_contestant_loads_adaptive_config_file()
    test_openai_cycle_review_weights_recent_observations_more()
    test_openai_fast_cycle_uses_last_two_observations()
    test_openai_time_bucket_stats_from_trade_pairs()
    test_openai_regime_config_preserves_no_rklb_no_short_discipline()
    test_openai_blocks_oversold_rklz_entry()
    test_openai_blocks_late_day_rklz_entry()
    test_openai_long_signal_uses_rklx_not_rklb()
    test_openai_blocks_rklx_on_monday_late_session()
    test_openai_blocks_high_gap_low_week_chase()
    test_openai_profit_lock_moves_stop_above_cost()
    test_openai_opposite_signal_does_not_same_bar_reverse()
    test_openai_weekly_risk_halt_blocks_new_entries()
    test_nightly_review_writes_hypothesis_log()
    test_nightly_review_backfills_previous_result()
    print("OK openai_adaptive")
