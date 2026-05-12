"""
v0.5.27 (重写): 验证亏损告警走 check_stop_loss_warning 通道,
               check_profit_target 仅服务盈利场景。
v0.5.26/v0.5.28 旧设计(亏损放行 near_stop/drawdown 走 profit_target)已废弃。
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.focus.context import FocusSession
from core.focus.swing_detector import (
    check_profit_target, check_stop_loss_warning, DEFAULT_PARAMS,
)
from core.focus.pusher import _fmt_profit_target, _fmt_stop_loss_warning


def make_session_with_loss(cost=74.08, current=71.83):
    """模拟 RKLX 20 股 @$74.08, 现价 $71.83 (-3.04%)"""
    s = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
    now = time.time()
    # 让 peak 真实超过 cost (模拟"曾经浮盈"场景下的回撤),
    # 但 pl_val 此刻为负 → drawdown 不应在 profit_target 里触发
    prices = [76.5, 76.2, 75.8, 75.0, 74.5, 73.8, 73.0, 72.5, 72.2, 72.0,
              71.9, 71.85, current]
    for p in prices:
        s.update_price("US.RKLX", p)
    s.positions_snapshot = {
        "US.RKLX": {
            "qty": 20, "cost_price": cost, "current_price": current,
            "market_val": 20 * current,
            "pl_val": round((current - cost) * 20, 2),
            "pl_pct": round((current - cost) / cost * 100, 2),
        }
    }
    s.get_position = lambda tk: s.positions_snapshot.get(tk)
    s.get_position_age_sec = lambda tk: 7200
    s._target_state = {
        "US.RKLX": {
            "direction": "long",
            "t1": 80.00, "t2": 81.31, "stop": 72.20,
            "set_at_price": 76.0, "set_at_ts": now - 3600,
        }
    }
    return s


# ── 测试 1: 亏损时 check_profit_target 完全静默 ──────────────────
print("=" * 60)
print("[Test 1] 亏损持仓 — check_profit_target 必须 return None")
s = make_session_with_loss(cost=74.08, current=71.83)
hit_pt = check_profit_target(s, "US.RKLX", indicators=None)
assert hit_pt is None, f"❌ FAIL: 亏损时 profit_target 不该触发, 实际 {hit_pt}"
print("  ✅ profit_target 在亏损时正确静默")


# ── 测试 2: 亏损时 check_stop_loss_warning 触发 ──────────────────
print("\n" + "=" * 60)
print("[Test 2] 亏损 -3.04% — check_stop_loss_warning 应触发 (>= 2%)")
hit_sl = check_stop_loss_warning(s, "US.RKLX")
assert hit_sl is not None, "❌ FAIL: stop_loss_warning 未触发"
assert hit_sl["trigger"] == "stop_loss_warning"
print(f"  ✅ sub_kind = {hit_sl['data']['sub_kind']}  level = {hit_sl['level']}")
print(f"  ✅ pl_pct = {hit_sl['data']['pl_pct']:.2f}%")

# 验证 pusher 文案
msg = _fmt_stop_loss_warning(hit_sl, session=s)
text = msg["text"]
print("\n--- 推送内容 ---")
print(text)
print("---")
assert "💰" not in text.split("\n")[0], "❌ 亏损 title 不该有 💰"
assert ("🛑" in text or "📉" in text), "❌ 应有 🛑 或 📉"
assert "目前亏损" in text, "❌ 应使用 '目前亏损' 措辞"
assert "目前盈利" not in text, "❌ 亏损不应出现 '目前盈利'"
print("  ✅ title emoji / 措辞正确")


# ── 测试 3: leftover 兜底 hard_stop 必须低于现价 ──────────────────
print("\n" + "=" * 60)
print("[Test 3] stop > current (止损高于现价) — leftover 应自动落到 current×0.98")
# 让 stop=$72.20, current=$71.83 → stop > current
# pusher 必须把 hard_stop 改成 round(current*0.98, 2) = $70.39
assert s._target_state["US.RKLX"]["stop"] == 72.20
assert s.positions_snapshot["US.RKLX"]["current_price"] == 71.83
print(f"  stop=$72.20 > current=$71.83 → 期望 hard_stop = $70.39")
# 找到 leftover_line
leftover_lines = [l for l in text.split("\n") if "若跌破" in l]
assert leftover_lines, "❌ 找不到 leftover 兜底行"
print(f"  实际:{leftover_lines[0]}")
assert "$70.39" in leftover_lines[0] or "70.39" in leftover_lines[0], \
    f"❌ leftover hard_stop 应为 $70.39 (current×0.98),实际 {leftover_lines[0]}"
print("  ✅ leftover 自动绕开了止损价高于现价的逻辑矛盾")


# ── 测试 4: 浮亏 < 2% 不触发 stop_loss_warning ──────────────────
print("\n" + "=" * 60)
print("[Test 4] 浮亏仅 -1.5% (< stop_loss_loss_pct 2%) — 不触发")
s4 = make_session_with_loss(cost=74.08, current=72.97)  # -1.5%
# 清掉 cooldown(用新 ticker)
s4.last_trigger_time = {}
hit4 = check_stop_loss_warning(s4, "US.RKLX")
assert hit4 is None, f"❌ FAIL: -1.5% 不该触发, 实际 {hit4}"
print("  ✅ 小幅浮亏正确静默")


# ── 测试 5: 浮亏 >= 3% 触发 URGENT (已破止损) ──────────────────
print("\n" + "=" * 60)
print("[Test 5] 浮亏 -5.91% (>= 3%) — 触发 URGENT/breached")
s5 = make_session_with_loss(cost=74.08, current=69.70)  # -5.91%
s5.last_trigger_time = {}
hit5 = check_stop_loss_warning(s5, "US.RKLX")
assert hit5 is not None and hit5["level"] == "URGENT"
assert hit5["data"]["sub_kind"] == "breached"
print(f"  ✅ level={hit5['level']}, sub_kind={hit5['data']['sub_kind']}")


# ── 测试 6: 盈利路径不受影响 ────────────────────────────────────
print("\n" + "=" * 60)
print("[Test 6] 盈利 + 接近 T1 — profit_target 仍走盈利路径")
s6 = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
for p in [76.0, 76.5, 77.0, 77.5, 78.0, 78.5, 79.0, 79.3, 79.5, 79.6, 79.7]:
    s6.update_price("US.RKLX", p)
s6.positions_snapshot = {
    "US.RKLX": {
        "qty": 20, "cost_price": 74.08, "current_price": 79.7,
        "market_val": 20 * 79.7,
        "pl_val": round((79.7 - 74.08) * 20, 2),
        "pl_pct": round((79.7 - 74.08) / 74.08 * 100, 2),
    }
}
s6.get_position = lambda tk: s6.positions_snapshot.get(tk)
s6.get_position_age_sec = lambda tk: 7200
s6._target_state = {
    "US.RKLX": {
        "direction": "long",
        "t1": 80.00, "t2": 81.31, "stop": 72.20,
        "set_at_price": 76.0, "set_at_ts": time.time() - 3600,
    }
}
hit6 = check_profit_target(s6, "US.RKLX", indicators=None)
assert hit6 is not None and hit6["data"]["sub_reason"] == "near_target"
msg6 = _fmt_profit_target(hit6, session=s6)
assert "💰" in msg6["text"] and "目前盈利" in msg6["text"]
print("  ✅ 盈利路径不受影响")


# ── 测试 7: peak > cost 才允许 drawdown 触发 ──────────────────
print("\n" + "=" * 60)
print("[Test 7] peak ≤ cost (持仓全程亏损) — drawdown 不触发")
s7 = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
# peak 全程在 $74.08 cost 之下
for p in [71.21, 71.10, 70.80, 70.50, 70.20, 70.00, 69.80, 69.70, 69.64]:
    s7.update_price("US.RKLX", p)
s7.positions_snapshot = {
    "US.RKLX": {
        "qty": 20, "cost_price": 74.08, "current_price": 69.64,
        "market_val": 20 * 69.64,
        "pl_val": round((69.64 - 74.08) * 20, 2),  # -88.8 (亏损)
        "pl_pct": round((69.64 - 74.08) / 74.08 * 100, 2),
    }
}
s7.get_position = lambda tk: s7.positions_snapshot.get(tk)
s7.get_position_age_sec = lambda tk: 7200
hit_pt7 = check_profit_target(s7, "US.RKLX", indicators=None)
assert hit_pt7 is None, f"❌ FAIL: profit_target 不该触发, 实际 {hit_pt7}"
print("  ✅ peak<cost + 亏损 → profit_target 静默")
# stop_loss_warning 接管
hit_sl7 = check_stop_loss_warning(s7, "US.RKLX")
assert hit_sl7 is not None
print(f"  ✅ stop_loss_warning 接管,level={hit_sl7['level']}")


print("\n" + "=" * 60)
print("✅ ALL PASS — v0.5.27 亏损告警走 stop_loss_warning + 文案正确")
