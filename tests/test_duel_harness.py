"""Duel harness 公平性/正确性测试。PYTHONIOENCODING=utf-8 python tests/test_duel_harness.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.sim_weekly.duel import Contestant, BarContext, run_week, _max_drawdown
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant
from core.sim_weekly.openai_contestant import OpenAIContestant


class _NoopContestant(Contestant):
    name = "noop"
    def on_bar(self, ctx):
        pass


class _BuggyContestant(Contestant):
    name = "buggy"
    def on_bar(self, ctx):
        raise ValueError("boom")


def test_noop_returns_flat():
    sc = run_week(_NoopContestant(), "2026-05-11")
    assert not sc.get("error"), sc
    assert sc["n_trades"] == 0, "不下单应零交易"
    assert abs(sc["return_pct"]) < 0.01, f"不下单收益应≈0,实得 {sc['return_pct']}"
    print(f"  OK noop  return={sc['return_pct']}%")


def test_buggy_contestant_isolated():
    # 选手抛异常不应让 harness 崩,记成 error 并继续结算
    sc = run_week(_BuggyContestant(), "2026-05-11")
    assert not sc.get("error"), "harness 不应因选手 bug 而失败"
    assert sc["errors"] > 0, "应记录选手错误"
    print(f"  OK buggy isolated  errors={sc['errors']}")


def test_buyhold_tracks_benchmark_direction():
    # buyhold 选手在首根 bar 的 close 买入,基准用 open→close,
    # 差异 = 首根 bar 的 open→close gap + 滑点(波动股可达数%),属真实执行效果。
    # 只断言:同向 + 在合理带内(< 首根 gap + 滑点的上限)。
    sc = run_week(BuyHoldContestant("RKLB"), "2026-05-11")
    bench = sc["benchmark_buyhold_RKLB_pct"]
    assert (sc["return_pct"] > 0) == (bench > 0), "buyhold 应与基准同向"
    assert abs(sc["return_pct"] - bench) < 6.0, f"差异应在首根gap+滑点带内,实得 {abs(sc['return_pct']-bench):.2f}%"
    print(f"  OK buyhold {sc['return_pct']}% vs bench {bench}% (首根gap+滑点差异属正常)")


def test_claude_runs_and_scores():
    sc = run_week(ClaudeRuleContestant(), "2026-05-11")
    assert not sc.get("error"), sc
    assert "return_pct" in sc and "max_drawdown_pct" in sc
    assert sc["errors"] == 0, "我方选手不应抛错"
    print(f"  OK claude  return={sc['return_pct']}% trades={sc['n_trades']} dd={sc['max_drawdown_pct']}%")


def test_openai_runs_independently():
    sc = run_week(OpenAIContestant(), "2026-05-11")
    assert not sc.get("error"), sc
    assert "return_pct" in sc and "max_drawdown_pct" in sc
    assert sc["contestant"] == OpenAIContestant.name
    assert sc["errors"] == 0, "OpenAI 选手不应抛错"
    print(f"  OK openai  return={sc['return_pct']}% trades={sc['n_trades']} dd={sc['max_drawdown_pct']}%")


def test_fairness_same_data_same_fees():
    # 两个选手在同一周必须拿到同一份基准(证明数据/费率共享)
    a = run_week(ClaudeRuleContestant(), "2026-04-27")
    b = run_week(BuyHoldContestant("RKLB"), "2026-04-27")
    assert a["benchmark_buyhold_RKLB_pct"] == b["benchmark_buyhold_RKLB_pct"], "同周基准必须一致"
    print(f"  OK fairness  both see bench={a['benchmark_buyhold_RKLB_pct']}%")


def test_max_drawdown_math():
    assert _max_drawdown([("t0", 100), ("t1", 110), ("t2", 88)]) == -20.0
    assert _max_drawdown([("t0", 100), ("t1", 105)]) == 0.0
    print("  OK max_drawdown math")


if __name__ == "__main__":
    print("=== Duel harness 测试 ===")
    test_noop_returns_flat()
    test_buggy_contestant_isolated()
    test_buyhold_tracks_benchmark_direction()
    test_claude_runs_and_scores()
    test_openai_runs_independently()
    test_fairness_same_data_same_fees()
    test_max_drawdown_math()
    print("✅ 全部通过")
