"""
MagicQuant Arena Lite tests.
VERSION : v1.0.0
DEPENDS : pathlib, tempfile, core.arena.roster, core.arena.ensemble, core.arena.fitness, core.arena.validation
"""
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.arena.ensemble import ArenaSignal, decide_champion_portfolio, render_daily_champion_report, write_daily_champion_report
from core.arena.fitness import compute_fitness, final_go_fail, render_weekly_arena_report, write_weekly_arena_report
from core.arena.roster import get_roster, validate_equal_weight
from core.arena.strategy_catalog import (
    AI_FAMILY,
    EVENT_FAMILY,
    MEAN_REVERSION_FAMILY,
    TREND_FAMILY,
    VOLUME_FAMILY,
    StrategyCatalogEntry,
    champion_strategy_ids,
    render_family_champion_report,
    select_family_champions,
    validate_catalog,
)
from core.arena.validation import (
    LUCKY_CHAMPION,
    TRUE_CHAMPION,
    ChampionRecord,
    append_champion_history,
    compute_stability_score,
    load_champion_history,
    render_validation_report,
    replay_champion_history,
    validate_champion,
    write_validation_report,
)


def test_roster_fixed_seven_equal_weight():
    roster = get_roster()
    assert len(roster) == 7
    validate_equal_weight(roster)
    assert [member.member_id for member in roster] == [
        "h1_trend",
        "h2_mean_reversion",
        "h3_volume_breakout",
        "gpt",
        "claude",
        "deepseek",
        "kimi",
    ]


def test_champion_portfolio_deduplicates_same_cluster():
    decision = decide_champion_portfolio(
        [
            ArenaSignal("h1_trend", "bull", cluster_key="trend_up"),
            ArenaSignal("gpt", "bull", cluster_key="trend_up"),
            ArenaSignal("claude", "bear", cluster_key="risk_down"),
            ArenaSignal("deepseek", "neutral"),
        ]
    )
    assert decision.bull_votes == 1
    assert decision.bear_votes == 1
    assert decision.neutral_votes == 1
    assert decision.net_score == 0
    assert decision.action == "HOLD"
    assert decision.preferred_instrument == "Cash"


def test_champion_portfolio_outputs_long_short_hold():
    long_decision = decide_champion_portfolio(
        [
            ArenaSignal("h1_trend", "bull"),
            ArenaSignal("h2_mean_reversion", "bear"),
            ArenaSignal("gpt", "bull"),
        ]
    )
    assert long_decision.action == "LONG"
    assert long_decision.preferred_instrument == "RKLX"

    short_decision = decide_champion_portfolio(
        [
            ArenaSignal("h1_trend", "bear"),
            ArenaSignal("h2_mean_reversion", "bear"),
            ArenaSignal("gpt", "bull"),
        ]
    )
    assert short_decision.action == "SHORT"
    assert short_decision.preferred_instrument == "RKLZ"


def test_fitness_metrics_and_go_fail_gate():
    champion = compute_fitness([100, -40, 80], [1000, 1100, 1060, 1140], [0.10, -0.0364, 0.0755])
    assert champion.pnl == 140
    assert champion.profit_factor == 4.5
    assert champion.win_rate == 0.6667
    assert champion.max_drawdown == -0.0364
    assert champion.expectancy == 46.6667
    assert champion.fitness_score > 0

    go_rows = [
        {"champion_pnl": 10, "current_main_strategy_pnl": 1, "champion_profit_factor": 1.1}
        for _ in range(6)
    ]
    fail_rows = go_rows[:5]
    assert final_go_fail(go_rows) == "GO"
    assert final_go_fail(fail_rows) == "FAIL"


def test_report_renderers_include_required_fields():
    decision = decide_champion_portfolio([ArenaSignal("h1_trend", "bull")])
    daily = render_daily_champion_report("2026-05-30", decision)
    assert "Champion Portfolio Signal: LONG" in daily
    assert "Buy & Hold RKLB" in daily
    assert "Current Main Strategy" in daily
    assert "No Trade" in daily

    metrics = compute_fitness([10, -5], [100, 110, 105], [0.10, -0.0455])
    weekly = render_weekly_arena_report(
        "2026-05-25 to 2026-05-29",
        metrics,
        {"Benchmark A Buy & Hold RKLB": metrics, "Benchmark B Current Main Strategy": metrics, "Benchmark C No Trade": metrics},
        "Champion won because net exposure matched the week direction.",
    )
    assert "Champion Portfolio" in weekly
    assert "Profit Factor" in weekly
    assert "Benchmark A" in weekly
    assert "Win/Loss Reason Analysis" in weekly

    with TemporaryDirectory() as tmp:
        daily_path = write_daily_champion_report("2026-05-30", decision, out_path=Path(tmp) / "today_champion.md")
        weekly_path = write_weekly_arena_report(
            "2026-05-25 to 2026-05-29",
            metrics,
            {"Benchmark A Buy & Hold RKLB": metrics},
            "No live strategy changed.",
            out_path=Path(tmp) / "weekly_arena_report.md",
        )
        assert daily_path.exists()
        assert weekly_path.exists()


def test_strategy_catalog_selects_family_champions_for_portfolio_vote():
    entries = [
        StrategyCatalogEntry("trend_a", TREND_FAMILY, "trend candidate", "active", 10.0),
        StrategyCatalogEntry("trend_b", TREND_FAMILY, "trend candidate", "candidate", 12.0),
        StrategyCatalogEntry("rev_a", MEAN_REVERSION_FAMILY, "reversion candidate", "active", 8.0),
        StrategyCatalogEntry("vol_a", VOLUME_FAMILY, "volume candidate", "active", 7.0),
        StrategyCatalogEntry("event_a", EVENT_FAMILY, "event candidate", "active", 5.0),
        StrategyCatalogEntry("ai_a", AI_FAMILY, "ai candidate", "active", 9.0),
    ]
    validate_catalog(entries)
    champions = select_family_champions(entries)
    assert champions[TREND_FAMILY].strategy_id == "trend_b"
    allowed_ids = champion_strategy_ids(entries)
    assert "trend_b" in allowed_ids
    assert "trend_a" not in allowed_ids

    decision = decide_champion_portfolio(
        [
            ArenaSignal("trend_b", "bull"),
            ArenaSignal("rev_a", "neutral"),
            ArenaSignal("vol_a", "bull"),
            ArenaSignal("event_a", "bear"),
            ArenaSignal("ai_a", "bull"),
        ],
        allowed_member_ids=allowed_ids,
    )
    assert decision.action == "LONG"
    report = render_family_champion_report(entries)
    assert "Trend Champion: trend_b" in report
    assert "AI Champion: ai_a" in report


def test_strategy_catalog_rejects_unclassified_or_overgrown_families():
    bad_family = [StrategyCatalogEntry("mystery", "Unknown Family", "bad", "active", 1.0)]
    try:
        validate_catalog(bad_family)
        raise AssertionError("unclassified strategy should fail")
    except ValueError as exc:
        assert "unknown family" in str(exc)

    too_many = [
        StrategyCatalogEntry(f"trend_{idx}", TREND_FAMILY, "too many", "active", float(idx))
        for idx in range(6)
    ]
    try:
        validate_catalog(too_many)
        raise AssertionError("overgrown family should fail")
    except ValueError as exc:
        assert "cannot exceed" in str(exc)


def test_validation_layer_separates_true_and_lucky_champions():
    true_rows = [
        ChampionRecord(f"2026-0{idx}-01", "champion_a", 100.0 + idx, 1.2, -0.02, 10.0)
        for idx in range(1, 7)
    ]
    stability = compute_stability_score(true_rows)
    assert stability.weeks == 6
    assert stability.beat_main_weeks == 6
    assert stability.pf_pass_weeks == 6

    true_result = validate_champion("champion_a", true_rows)
    assert true_result.verdict == TRUE_CHAMPION
    assert "stable cross-week profile" in true_result.reasons[0]

    lucky_rows = [
        ChampionRecord("2026-01-01", "champion_b", 500.0, 3.0, -0.01, 0.0),
        ChampionRecord("2026-01-08", "champion_b", -50.0, 0.8, -0.08, 0.0),
        ChampionRecord("2026-01-15", "champion_b", 20.0, 1.1, -0.03, 30.0),
    ]
    lucky_result = validate_champion("champion_b", lucky_rows)
    assert lucky_result.verdict == LUCKY_CHAMPION
    assert any("need 6" in reason for reason in lucky_result.reasons)
    assert any("Profit Factor" in reason for reason in lucky_result.reasons)


def test_champion_history_and_arena_replay_round_trip():
    rows = [
        ChampionRecord(f"2026-02-{idx:02d}", "champion_a", 90.0, 1.3, -0.02, 10.0)
        for idx in range(1, 7)
    ]
    with TemporaryDirectory() as tmp:
        history_path = Path(tmp) / "champion_history.jsonl"
        for row in rows:
            append_champion_history(row, history_path)

        loaded = load_champion_history(history_path)
        assert loaded == rows
        replay = replay_champion_history(loaded)
        assert replay["champion_a"].verdict == TRUE_CHAMPION

        report = render_validation_report(replay["champion_a"])
        assert "Verdict: TRUE_CHAMPION" in report
        report_path = write_validation_report(replay["champion_a"], Path(tmp) / "champion_validation.md")
        assert report_path.exists()


if __name__ == "__main__":
    test_roster_fixed_seven_equal_weight()
    test_champion_portfolio_deduplicates_same_cluster()
    test_champion_portfolio_outputs_long_short_hold()
    test_fitness_metrics_and_go_fail_gate()
    test_report_renderers_include_required_fields()
    test_strategy_catalog_selects_family_champions_for_portfolio_vote()
    test_strategy_catalog_rejects_unclassified_or_overgrown_families()
    test_validation_layer_separates_true_and_lucky_champions()
    test_champion_history_and_arena_replay_round_trip()
    print("Arena Lite tests passed")
