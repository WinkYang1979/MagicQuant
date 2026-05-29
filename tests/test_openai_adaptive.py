"""Tests for OpenAI duel adaptive paper loop."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.sim_weekly.openai_contestant import OpenAIContestant
from scripts.sim_weekly_openai_nightly_review import _config_for_regime, run_review


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
    test_nightly_review_writes_hypothesis_log()
    test_nightly_review_backfills_previous_result()
    print("OK openai_adaptive")
