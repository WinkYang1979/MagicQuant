"""SimWeekly 自包含回归测试。PYTHONIOENCODING=utf-8 python tests/test_sim_weekly.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.sim_weekly.fees import calc_fee
from core.sim_weekly.portfolio import SimPortfolio
from core.sim_weekly import indicators as ind
from core.sim_weekly import deciders


def test_fees():
    assert abs(calc_fee("buy", 100, 50) - 1.29) < 1e-9, "买入固定 $1.29"
    # 卖出 = 1.29 + SEC + TAF
    f = calc_fee("sell", 100, 50)
    assert f > 1.29, "卖出含 SEC/TAF 应 > 1.29"
    assert calc_fee("buy", 100, 0) == 0.0
    print("  OK fees")


def test_portfolio_buy_sell_pnl():
    pf = SimPortfolio(initial_capital=10000.0, slippage=0.0)
    pf.buy("RKLB", 50, 100.0, "t0", "test")
    assert "RKLB" in pf.positions and pf.positions["RKLB"]["qty"] == 50
    # 现金 = 10000 - 50*100 - 1.29
    assert abs(pf.cash - (10000 - 5000 - 1.29)) < 1e-6, pf.cash
    pf.sell("RKLB", 50, 110.0, "t1", "tp")
    assert "RKLB" not in pf.positions
    assert pf.realized_pnl() > 0, "涨10%卖出应盈利"
    print(f"  OK portfolio  realized={pf.realized_pnl()} fees={pf.total_fees}")


def test_cash_constraint():
    pf = SimPortfolio(initial_capital=1000.0, slippage=0.0)
    pf.buy("RKLX", 100, 80.0, "t0")   # 想买 8000,只有 1000
    assert pf.positions.get("RKLX", {}).get("qty", 0) <= 12, "应被现金约束缩减"
    assert pf.cash >= 0, "现金不能为负"
    print("  OK cash constraint")


def test_flatten():
    pf = SimPortfolio(initial_capital=10000.0, slippage=0.0)
    pf.buy("RKLZ", 100, 3.0, "t0")
    pf.flatten({"RKLZ": 3.3}, "t1")
    assert not pf.positions, "flatten 应清空持仓"
    print("  OK flatten")


def test_indicators():
    closes = [10 + i * 0.1 for i in range(40)]
    assert ind.ema(closes, 9) is not None
    assert ind.rsi(closes, 14) > 60, "单调上行 RSI 应偏高"
    bars = [{"high": c + 0.5, "low": c - 0.5, "close": c, "volume": 100} for c in closes]
    assert ind.atr(bars, 14) > 0
    assert ind.session_vwap(bars) is not None
    print("  OK indicators")


def test_equity_marks():
    pf = SimPortfolio(initial_capital=10000.0, slippage=0.0)
    pf.buy("RKLB", 10, 100.0, "t0")
    eq = pf.equity({"RKLB": 105.0})
    assert eq > 9900, eq
    print(f"  OK equity  eq@105={eq}")


def test_codex_decider_vetoes_weak_short_in_up_week():
    original = deciders.strat.decide
    deciders.strat.decide = lambda ctx: {
        "direction": "short",
        "instrument": "RKLZ",
        "conviction": 70,
        "stop_pct": 0.045,
        "reason": "forced weak short",
    }
    try:
        bars = []
        for idx in range(40):
            price = 100.0 + idx * 0.1
            bars.append({
                "time": f"2026-05-11 10:{idx % 60:02d}:00",
                "open": price,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": 1000,
            })
        target = deciders.CodexDecider().decide({"rklb_bars": bars, "rklb_today_bars": bars})
        assert target["direction"] == "flat", target
        assert "veto weak short" in target["reason"], target
    finally:
        deciders.strat.decide = original
    print("  OK codex veto")


if __name__ == "__main__":
    print("=== SimWeekly 测试 ===")
    test_fees()
    test_portfolio_buy_sell_pnl()
    test_cash_constraint()
    test_flatten()
    test_indicators()
    test_equity_marks()
    test_codex_decider_vetoes_weak_short_in_up_week()
    print("✅ 全部通过")
