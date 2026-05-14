"""
v0.5.23 单元测试: 目标升级机制
模拟 session 设置 _target_state，模拟价格突破，验证 check_target_advance 触发并刷新状态
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
from core.focus.context import FocusSession
from core.focus.swing_detector import check_target_advance
from core.focus.pusher import _fmt_target_advance, format_trigger_message


def stub_indicators_ok():
    return {"data_ok": True}


def make_session_with_state(ticker="US.RKLB", direction="long",
                            entry=115.0, t1=120.0, t2=125.0, stop=112.0):
    s = FocusSession(master_ticker=ticker, followers=["US.RKLX"])
    # 注入一些价格历史让 _calc_price_targets 有数据可用
    now = time.time()
    base = entry
    for i in range(30):
        s.update_price(ticker, base - 0.5 + (i * 0.05))
    s.update_price(ticker, entry)  # 最后一次设为 entry
    # 注入状态
    s._target_state = {
        ticker: {
            "direction":    direction,
            "t1":           t1,
            "t2":           t2,
            "stop":         stop,
            "set_at_price": entry,
            "set_at_ts":    now - 10,
        }
    }
    return s


def test_long_breakout():
    print("\n=== Test 1: 多头突破 T1 ===")
    s = make_session_with_state(entry=115.0, t1=120.0, t2=125.0, stop=112.0)
    # 价格还没破 T1
    s.update_price("US.RKLB", 118.5)
    hit = check_target_advance(s, "US.RKLB", stub_indicators_ok())
    print(f"  价格 118.5 (< T1 120) → hit = {hit}")
    assert hit is None, "未突破时不应触发"

    # 价格破 T1
    s.update_price("US.RKLB", 121.0)
    hit = check_target_advance(s, "US.RKLB", stub_indicators_ok())
    print(f"  价格 121.0 (> T1 120) → trigger={hit['trigger'] if hit else None}")
    assert hit and hit["trigger"] == "target_advance", "应触发 target_advance"
    assert hit["data"]["old_t1"] == 120.0
    assert hit["data"]["current"] == 121.0

    # 模拟推送（这会写回新状态）
    msg = format_trigger_message(hit, s)
    print(f"\n--- Telegram 推送内容 ---")
    print(msg["text"])

    # 验证 state 已刷新
    new_state = s._target_state["US.RKLB"]
    print(f"\n  新状态 t1={new_state['t1']} t2={new_state['t2']} stop={new_state['stop']}")
    assert new_state["t1"] != 120.0, "T1 应已刷新"
    assert new_state["set_at_price"] == 121.0

    # v0.5.31: cool_key 由 per-T1 改为 per-ticker —— T1 棘轮升级到新值后,
    #          30 min 冷却内仍不应重推 (v0.5.30 的 per-T1 key 在 T1 上移时
    #          每次都是新 key, 30min 冷却形同虚设, 是开盘刷屏根因)
    new_t1 = new_state["t1"]
    s.update_price("US.RKLB", new_t1 + 5)  # 突破新 T1
    hit2 = check_target_advance(s, "US.RKLB", stub_indicators_ok())
    print(f"\n  突破新 T1 ${new_t1} (冷却内) → hit = {hit2 and hit2['trigger']}")
    assert hit2 is None, "T1 升级后 30 min 内仍不应重推 (per-ticker 冷却)"

    # 冷却过期 (清空 last_trigger_time 模拟) → 同 ticker 才可再次触发
    s.last_trigger_time = {}
    s.update_price("US.RKLB", new_t1 + 6)
    hit3 = check_target_advance(s, "US.RKLB", stub_indicators_ok())
    print(f"  冷却清空后突破新 T1 → hit = {hit3 and hit3['trigger']}")
    assert hit3 and hit3["trigger"] == "target_advance", "冷却过期后应可再触发"


def test_short_breakdown():
    print("\n=== Test 2: 空头跌破 T1 ===")
    s = make_session_with_state(entry=115.0, t1=110.0, t2=105.0, stop=118.0,
                                direction="short")
    s.update_price("US.RKLB", 108.5)  # 跌破 T1
    hit = check_target_advance(s, "US.RKLB", stub_indicators_ok())
    print(f"  价格 108.5 (< T1 110, 空头) → trigger={hit['trigger'] if hit else None}")
    assert hit and hit["trigger"] == "target_advance"
    msg = format_trigger_message(hit, s)
    print(f"\n--- Telegram 推送内容 ---")
    print(msg["text"])


def test_no_state():
    print("\n=== Test 3: 无 _target_state → 不触发 ===")
    s = FocusSession(master_ticker="US.RKLB", followers=[])
    hit = check_target_advance(s, "US.RKLB", stub_indicators_ok())
    print(f"  hit = {hit}")
    assert hit is None


def test_advance_chain():
    print("\n=== Test 4: 连续突破多档（破 T1 → 新状态 → 再破新 T1）===")
    s = make_session_with_state(entry=115.0, t1=120.0, t2=125.0, stop=112.0)

    # 第一次突破
    s.update_price("US.RKLB", 121.0)
    hit1 = check_target_advance(s, "US.RKLB", stub_indicators_ok())
    format_trigger_message(hit1, s)
    new_t1 = s._target_state["US.RKLB"]["t1"]
    print(f"  第一次破: 新 T1 = ${new_t1}")

    # 等冷却过去（实测里 60s，测试里直接绕过 can_trigger 时间检查）
    s.last_trigger_time = {}  # 清空冷却

    # 价格继续上涨到新 T1 之上
    push_price = new_t1 + 1
    s.update_price("US.RKLB", push_price)
    hit2 = check_target_advance(s, "US.RKLB", stub_indicators_ok())
    if hit2:
        format_trigger_message(hit2, s)
        new_t1_2 = s._target_state["US.RKLB"]["t1"]
        print(f"  第二次破: 价格 ${push_price} → 又新 T1 = ${new_t1_2}")
        assert new_t1_2 != new_t1, "第二次升级 T1 应再变"
    else:
        print(f"  第二次价格 ${push_price} 未再升级（可能新 T1 算出来仍等于上次）")


if __name__ == "__main__":
    test_no_state()
    test_long_breakout()
    test_short_breakdown()
    test_advance_chain()
    print("\n✅ 全部通过")
