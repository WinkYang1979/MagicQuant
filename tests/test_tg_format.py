"""Tests for SimWeekly Telegram format helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.sim_weekly.tg_format import (
    TradeAlertThrottle,
    fmt_daily,
    fmt_trade,
    fmt_trade_summary,
    fmt_weekly,
)


def _buy(ts="2026-05-29 10:00:00"):
    return {
        "ts": ts,
        "side": "buy",
        "ticker": "RKLX",
        "qty": 100,
        "price": 74.93,
        "fee": 1.2,
        "reason": "test entry",
    }


def _sell(ts="2026-05-29 10:15:00"):
    return {
        "ts": ts,
        "side": "sell",
        "ticker": "RKLX",
        "qty": 100,
        "price": 75.5,
        "fee": 1.2,
        "pnl": 54.0,
        "reason": "test exit",
    }


def _score(name="claude_rule"):
    trades = [_buy(), _sell()]
    return {
        "contestant": name,
        "return_pct": 0.54,
        "max_drawdown_pct": -1.2,
        "total_fees": 2.4,
        "trades": trades,
        "benchmark_buyhold_RKLB_pct": 0.1,
    }


def test_fmt_trade_buy_has_actor_and_paper_suffix():
    text = fmt_trade("claude_rule", _buy())
    assert "🤖 Claude · 买入" in text
    assert "RKLX" in text
    assert "理由:" in text
    assert "(纸面模拟)" in text


def test_fmt_trade_sell_has_pnl_and_hold_minutes():
    text = fmt_trade("openai_v1", _sell(), entry_trade=_buy())
    assert "🧠 OpenAI · 卖出" in text
    assert "盈亏 $54.00" in text
    assert "持仓 15 分" in text
    loss = _sell()
    loss["pnl"] = -44.31
    assert "盈亏 -$44.31" in fmt_trade("openai_v1", loss, entry_trade=_buy())


def test_fmt_daily_and_weekly_have_ranked_actor_labels():
    scores = {"claude_rule": _score("claude_rule"), "openai_v1": _score("openai_v1")}
    daily = fmt_daily("2026-05-29", scores)
    weekly = fmt_weekly("2026-05-25", scores)
    assert "双方 PK 日报" in daily
    assert "不作比赛裁定" in daily
    assert "🤖 Claude" in daily
    assert "🧠 OpenAI" in daily
    assert "双方 PK 周末总报告" in weekly
    assert "正式裁定只看用户指定测试集" in weekly


def test_trade_throttle_merges_third_trade_within_window():
    throttle = TradeAlertThrottle(window_sec=300, threshold=3)
    assert throttle.record("openai_v1", _buy("2026-05-29 10:00:00"), now=0)[0] == "single"
    assert throttle.record("openai_v1", _buy("2026-05-29 10:01:00"), now=60)[0] == "single"
    mode, trades = throttle.record("openai_v1", _sell("2026-05-29 10:02:00"), now=120)
    assert mode == "summary"
    assert len(trades) == 3
    summary = fmt_trade_summary("openai_v1", trades)
    assert "3 笔纸面成交摘要" in summary


if __name__ == "__main__":
    test_fmt_trade_buy_has_actor_and_paper_suffix()
    test_fmt_trade_sell_has_pnl_and_hold_minutes()
    test_fmt_daily_and_weekly_have_ranked_actor_labels()
    test_trade_throttle_merges_third_trade_within_window()
    print("OK tg_format")
