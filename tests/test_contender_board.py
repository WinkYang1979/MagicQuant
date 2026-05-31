"""
MagicQuant Contender Board tests.
VERSION : v1.0.0
DEPENDS : json, pathlib, tempfile, core.arena.contender_board
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.arena.contender_board import (  # noqa: E402
    DECLINING,
    KEEP,
    PROMOTE,
    RISING,
    WATCH,
    analyze_contenders,
    load_and_analyze,
    render_report,
    render_telegram_summary,
    write_outputs,
)


def _record(day, champion_pnl, h1="bull", h2="neutral", h3="neutral", gpt="bull", claude="bull", deepseek="neutral", kimi="neutral", entry=100.0, close=101.0):
    return {
        "date": f"2026-06-{day:02d}",
        "champion_id": "Champion Portfolio",
        "entry_price": entry,
        "close_price": close,
        "champion_pnl": champion_pnl,
        "actual_result": {"champion_pnl": champion_pnl},
        "strategy_votes": [
            {"member_id": "h1_trend", "direction": h1, "family": "Trend Family"},
            {"member_id": "h2_mean_reversion", "direction": h2, "family": "Mean Reversion Family"},
            {"member_id": "h3_volume_breakout", "direction": h3, "family": "Volume Family"},
            {"member_id": "gpt", "direction": gpt, "family": "AI Family"},
            {"member_id": "claude", "direction": claude, "family": "AI Family"},
            {"member_id": "deepseek", "direction": deepseek, "family": "AI Family"},
            {"member_id": "kimi", "direction": kimi, "family": "AI Family"},
        ],
    }


def test_empty_board_has_no_successor_and_keeps():
    analysis = analyze_contenders([], {"current_champion": "UNKNOWN", "health_score": 0})
    assert analysis.current_champion == "UNKNOWN"
    assert analysis.recommended_successor == "NONE"
    assert analysis.final_recommendation == KEEP
    assert analysis.top_strategies == ()


def test_single_challenger_watchlist_selects_best_non_champion():
    rows = [_record(idx, champion_pnl=1.0, h1="bull", entry=100.0, close=102.0) for idx in range(1, 8)]
    analysis = analyze_contenders(rows, {"current_champion": "Champion Portfolio", "health_score": 80})
    assert analysis.promotion_watchlist
    assert analysis.promotion_watchlist[0].strategy_id in {"h1_trend", "gpt", "claude"}
    assert analysis.recommended_successor != "Champion Portfolio"
    assert analysis.final_recommendation in {KEEP, WATCH}


def test_multi_challenger_top_three_are_ranked_by_score():
    rows = []
    for idx in range(1, 16):
        rows.append(_record(idx, champion_pnl=0.3, h1="bull", h2="bear", gpt="bull", claude="neutral", entry=100.0, close=102.0))
    analysis = analyze_contenders(rows, {"current_champion": "Champion Portfolio", "health_score": 72})
    scores = [row.contender_score for row in analysis.promotion_watchlist]
    assert scores == sorted(scores, reverse=True)
    assert len(analysis.promotion_watchlist) == 3


def test_strong_champion_low_threat_keeps_title():
    rows = [_record(idx, champion_pnl=4.0, h1="neutral", gpt="neutral", claude="neutral", entry=100.0, close=101.0) for idx in range(1, 21)]
    analysis = analyze_contenders(rows, {"current_champion": "Champion Portfolio", "health_score": 92})
    assert analysis.final_recommendation == KEEP
    assert analysis.threat_level in {"LOW", "MEDIUM"}


def test_declining_champion_with_rising_challenger_promotes():
    rows = []
    for idx in range(1, 16):
        rows.append(_record(idx, champion_pnl=1.0, h1="neutral", gpt="neutral", entry=100.0, close=101.0))
    for idx in range(16, 31):
        rows.append(_record(idx, champion_pnl=-1.0, h1="bull", gpt="bull", entry=100.0, close=103.0))
    analysis = analyze_contenders(rows, {"current_champion": "Champion Portfolio", "health_score": 45})
    assert analysis.final_recommendation == PROMOTE
    assert analysis.recommended_successor in {"h1_trend", "gpt", "claude"}
    assert any(row.momentum_status == RISING for row in analysis.promotion_watchlist)


def test_failing_challenger_is_marked_for_demotion():
    rows = []
    for idx in range(1, 16):
        rows.append(_record(idx, champion_pnl=1.0, h2="bull", entry=100.0, close=102.0))
    for idx in range(16, 31):
        rows.append(_record(idx, champion_pnl=1.0, h2="bull", entry=100.0, close=98.0))
    analysis = analyze_contenders(rows, {"current_champion": "Champion Portfolio", "health_score": 88})
    demotion_row = next(row for row in analysis.top_strategies if row.strategy_id == "h2_mean_reversion")
    assert demotion_row.momentum_status == DECLINING
    assert "h2_mean_reversion" in analysis.demotion_watchlist


def test_report_outputs_and_loader_use_existing_files():
    rows = [_record(idx, champion_pnl=0.5, h1="bull", entry=100.0, close=102.0) for idx in range(1, 8)]
    analysis = analyze_contenders(rows, {"current_champion": "Champion Portfolio", "health_score": 61})
    report = render_report(analysis)
    telegram = render_telegram_summary(analysis)
    assert "Current Champion" in report
    assert "Promotion Watchlist" in report
    assert "Final Recommendation" in report
    assert "当前冠军" in telegram

    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        trial_path = tmp_path / "historical_trial_results.jsonl"
        stability_path = tmp_path / "latest.json"
        trial_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        stability_path.write_text(json.dumps({"current_champion": "Champion Portfolio", "health_score": 61}), encoding="utf-8")
        loaded = load_and_analyze(trial_path, stability_path)
        report_path, latest_path = write_outputs(loaded, tmp_path / "contender_board.md", tmp_path / "latest.json")
        assert report_path.exists()
        assert latest_path.exists()
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        assert latest["current_champion"] == "Champion Portfolio"


if __name__ == "__main__":
    test_empty_board_has_no_successor_and_keeps()
    test_single_challenger_watchlist_selects_best_non_champion()
    test_multi_challenger_top_three_are_ranked_by_score()
    test_strong_champion_low_threat_keeps_title()
    test_declining_champion_with_rising_challenger_promotes()
    test_failing_challenger_is_marked_for_demotion()
    test_report_outputs_and_loader_use_existing_files()
    print("Contender Board tests passed")
