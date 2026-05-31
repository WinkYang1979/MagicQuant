"""
v0.5.24 单元测试: profit_target 上下文感知止盈

覆盖分支:
  1) 小盈利 < $5 → 不触发
  2) 扣费后亏损 → 不触发
  3) 短持仓(<30min) + 紧急条件 → 触发 (豁免)
  4) 接近 T1 < 1% → near_target
  5) 突破 T1 → broke_target
  6) 超买放量 (RSI>=78, vol>=3) → overbought_surge
  7) 超买放量 + 让利润奔跑 → 抑制
  8) 高点回撤 >= 2% → drawdown
  9) 接近 stop < 1% → near_stop
 10) 档位文案:tier1 (1/3)  tier2 (1/2)  tier3 (3/4)  tier4 (全仓)
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
from core.focus.context import FocusSession
from core.focus.swing_detector import check_profit_target, DEFAULT_PARAMS
from core.focus.pusher import _fmt_profit_target


TK = "US.RKLB"


def _make_session(qty=100, cost=100.0, current=103.0, pl_val=300.0, pl_pct=3.0,
                  hold_sec=3600, t1=None, stop=None, direction="long"):
    """构造一个带持仓 + 价格历史 + target_state 的 session"""
    s = FocusSession(master_ticker=TK, followers=[])
    # 持仓
    s.positions_snapshot = {
        TK: {
            "ticker": TK, "qty": qty, "cost_price": cost,
            "current_price": current, "pl_val": pl_val, "pl_pct": pl_pct,
        }
    }
    # 持仓时间
    s._position_open_time[TK] = time.time() - hold_sec
    # 价格历史 (用于 peak_drawdown / new_high 判断)
    now = time.time()
    for i in range(20):
        s.prices.setdefault(TK, []).append((now - (20 - i), current - 0.2 + i * 0.01))
    s.prices[TK].append((now, current))
    s.session_high[TK] = current
    s.session_low[TK] = current - 1
    s.peak_price[TK] = current
    s.trough_price[TK] = current - 1
    # target_state
    if t1 or stop:
        s._target_state = {
            TK: {
                "direction": direction, "t1": t1, "t2": None, "stop": stop,
                "set_at_price": cost, "set_at_ts": now - 60,
            }
        }
    return s


def _ind(rsi=50, vol=1.0, ok=True):
    return {"data_ok": ok, "rsi_5m": rsi, "vol_ratio": vol}


def test_small_profit_suppressed():
    """1) 浮盈 $3 < $5 → 抑制"""
    s = _make_session(qty=100, cost=100, current=100.03, pl_val=3.0, pl_pct=0.03,
                      t1=103.0)
    hit = check_profit_target(s, TK, _ind(), DEFAULT_PARAMS)
    assert hit is None, f"小盈利应抑制,实际 {hit}"
    print("✅ [1] 浮盈 $3 < $5 → 抑制")


def test_fee_negative_suppressed():
    """2) 浮盈 $10 但 200 股 roundtrip fee $8 → 实际 $2 < $5 ...
       让 fee 触发抑制:浮盈 $6 但 200 股 fee=$8 → 扣费后亏损"""
    # 200 股 × 0.02 × 2 = $8 双边费
    s = _make_session(qty=200, cost=100, current=100.03, pl_val=6.0, pl_pct=0.03,
                      t1=103.0)
    hit = check_profit_target(s, TK, _ind(), DEFAULT_PARAMS)
    assert hit is None, f"扣费后亏损应抑制,实际 {hit}"
    print("✅ [2] 扣费后亏损 → 抑制")


def test_near_target_urgent_short_hold():
    """3) 持仓仅 10 分钟,但接近 T1 < 1% → 紧急条件豁免持仓时间"""
    # current 102.5, t1 103 → 距 0.49%
    s = _make_session(qty=100, cost=100, current=102.5, pl_val=250.0, pl_pct=2.5,
                      hold_sec=600, t1=103.0)
    hit = check_profit_target(s, TK, _ind(), DEFAULT_PARAMS)
    assert hit and hit["data"]["sub_reason"] == "near_target", f"应触发 near_target,实际 {hit}"
    assert hit["data"]["short_hold"] is True, "应标记短持仓"
    print(f"✅ [3] 短持仓 + 接近T1 → 触发 near_target (short_hold=True)")


def test_break_target():
    """4) 突破 T1 → broke_target"""
    s = _make_session(qty=100, cost=100, current=104.0, pl_val=400.0, pl_pct=4.0,
                      t1=103.0)
    hit = check_profit_target(s, TK, _ind(), DEFAULT_PARAMS)
    assert hit and hit["data"]["sub_reason"] == "broke_target", f"实际 {hit}"
    assert hit["data"]["tier"] == 2, f"4% 应为 tier 2,实际 {hit['data']['tier']}"
    assert abs(hit["data"]["sell_ratio"] - 0.5) < 0.01, "tier2 半仓"
    print(f"✅ [4] 突破 T1 → broke_target  tier={hit['data']['tier']} sell_qty={hit['data']['sell_qty']}")


def test_overbought_surge():
    """5) RSI 80 量比 4x + 无趋势锁定 → overbought_surge"""
    # 不设 _target_state → _is_trend_locked_long=False → let_run=False
    s = _make_session(qty=100, cost=100, current=105.0, pl_val=500.0, pl_pct=5.0)
    # 兜底 T1=cost*1.03=103,current=105 已超 T1 → 会先命中 broke_target
    # 把 cost 改高让兜底 T1 远离 current,确保走到 overbought 分支
    # current=105, 让兜底 T1 (cost*1.03) > current 即可
    s.positions_snapshot[TK]["cost_price"] = 105.0  # T1=108.15
    hit = check_profit_target(s, TK, _ind(rsi=80, vol=4.0), DEFAULT_PARAMS)
    assert hit and hit["data"]["sub_reason"] == "overbought_surge", f"实际 {hit}"
    print(f"✅ [5] RSI 80 vol 4x → overbought_surge")


def test_let_run_suppresses_overbought():
    """6) 趋势锁多 + 距 T1 > 2% + 创新高 + 过热 → 让利润奔跑,抑制"""
    s = _make_session(qty=100, cost=100, current=105.0, pl_val=500.0, pl_pct=5.0,
                      t1=110.0, direction="long")
    # session._target_state direction=long,set_at_ts 在 30 分钟内,_is_trend_locked_long 应返回 True
    # 距 T1: (110-105)/105 = 4.76% > 2%  ✓
    # making new high: session_high == current ✓
    # 但因为 _target_state 是 long → trend_locked_long → True
    hit = check_profit_target(s, TK, _ind(rsi=80, vol=4.0), DEFAULT_PARAMS)
    assert hit is None, f"应被 let_run 抑制,实际 {hit}"
    print("✅ [6] let_run 抑制 overbought_surge")


def test_drawdown():
    """7) 高点回撤 >= 2% → drawdown"""
    s = _make_session(qty=100, cost=100, current=103.0, pl_val=300.0, pl_pct=3.0,
                      t1=110.0)
    # 手动把 peak 抬高到 105.5 → drawdown = (103-105.5)/105.5 ≈ -2.37%
    s.peak_price[TK] = 105.5
    hit = check_profit_target(s, TK, _ind(), DEFAULT_PARAMS)
    assert hit and hit["data"]["sub_reason"] == "drawdown", f"实际 {hit}"
    print(f"✅ [7] peak 回撤 2.37% → drawdown")


def test_near_stop():
    """8) 接近 stop < 1% → near_stop"""
    s = _make_session(qty=100, cost=100, current=101.5, pl_val=150.0, pl_pct=1.5,
                      t1=110.0, stop=101.0)
    # 距 stop: (101.5 - 101) / 101.5 = 0.49% < 1%
    # peak 改为 current 避免 drawdown 抢先触发
    s.peak_price[TK] = 101.5
    hit = check_profit_target(s, TK, _ind(), DEFAULT_PARAMS)
    assert hit and hit["data"]["sub_reason"] == "near_stop", f"实际 {hit}"
    print(f"✅ [8] 距 stop 0.49% → near_stop")


def test_tier_progression():
    """9) 各档位 sell_ratio 验证"""
    cases = [
        # (pl_pct, expected_tier, expected_ratio)
        (2.0, 1, 1/3),     # tier1 <3%
        (5.0, 2, 0.5),     # tier2 3-8%
        (10.0, 3, 0.75),   # tier3 8-15%
        (20.0, 4, 1.0),    # tier4 >15%
    ]
    for pl_pct, exp_tier, exp_ratio in cases:
        current = 100 * (1 + pl_pct / 100)
        s = _make_session(qty=100, cost=100, current=current,
                          pl_val=pl_pct * 100, pl_pct=pl_pct,
                          t1=current * 1.10)  # T1 远,避免命中 broke_target
        # 用突破 T1 触发,设 t1=current-0.01 让它必定命中 broke_target
        s._target_state = {TK: {"direction":"long","t1": current - 0.01,
                                "t2": None, "stop": None,
                                "set_at_price": 100, "set_at_ts": time.time() - 60}}
        hit = check_profit_target(s, TK, _ind(), DEFAULT_PARAMS)
        assert hit, f"pl_pct={pl_pct} 应触发"
        assert hit["data"]["tier"] == exp_tier, \
            f"pl_pct={pl_pct} 期望 tier={exp_tier} 实际 {hit['data']['tier']}"
        assert abs(hit["data"]["sell_ratio"] - exp_ratio) < 0.01, \
            f"pl_pct={pl_pct} 期望 ratio={exp_ratio} 实际 {hit['data']['sell_ratio']}"
        print(f"✅ [9] pl_pct={pl_pct}% → tier={exp_tier} ratio={exp_ratio:.2f} "
              f"sell_qty={hit['data']['sell_qty']}")


def test_message_format():
    """10) pusher 输出文案合理性 — 包含 sub_reason 标题、tier 描述、why 解释"""
    s = _make_session(qty=100, cost=100, current=104.0, pl_val=400.0, pl_pct=4.0,
                      t1=103.0)
    hit = check_profit_target(s, TK, _ind(), DEFAULT_PARAMS)
    msg = _fmt_profit_target(hit, s)
    text = msg["text"]
    print("\n--- 推送文案样例 (broke_target tier2) ---")
    print(text)
    print("-----------------------------------------")
    assert "突破目标位" in text
    assert "卖" in text and "股" in text
    assert "💡" in text  # why 提示
    print("✅ [10] 文案包含原因/动作/为什么")


def run_all():
    test_small_profit_suppressed()
    test_fee_negative_suppressed()
    test_near_target_urgent_short_hold()
    test_break_target()
    test_overbought_surge()
    test_let_run_suppresses_overbought()
    test_drawdown()
    test_near_stop()
    test_tier_progression()
    test_message_format()
    print("\n🎉 全部测试通过")


if __name__ == "__main__":
    run_all()
