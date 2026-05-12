"""
v0.5.26/v0.5.28: 验证亏损时 near_stop / drawdown 能正常推送,
                 且文案为亏损版 (emoji 🛑/📉、"目前亏损"措辞)。
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.focus.context import FocusSession
from core.focus.swing_detector import check_profit_target, DEFAULT_PARAMS
from core.focus.pusher import _fmt_profit_target


def make_session_with_loss(cost=74.08, current=71.83):
    """模拟 RKLX 20 股 @$74.08, 现价 $71.83 (-3.04%)"""
    s = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
    now = time.time()
    # 灌足 30+ 个价格点让 peak/drawdown 有数据
    # peak 设在 $76.5, 然后阴跌到 $71.83
    prices = [76.5, 76.2, 75.8, 75.0, 74.5, 73.8, 73.0, 72.5, 72.2, 72.0,
              71.9, 71.85, current]
    for p in prices:
        s.update_price("US.RKLX", p)
    # 写入持仓
    s.positions_snapshot = {
        "US.RKLX": {
            "qty": 20, "cost_price": cost, "current_price": current,
            "market_val": 20 * current,
            "pl_val": round((current - cost) * 20, 2),
            "pl_pct": round((current - cost) / cost * 100, 2),
        }
    }
    # FocusSession 的 get_position
    s.get_position = lambda tk: s.positions_snapshot.get(tk)
    s.get_position_age_sec = lambda tk: 7200  # 持仓 2 小时,过了 30min 门槛
    # 写入一个 follower target_state（模拟修复后 _fmt_signal_with_conflict 写的）
    s._target_state = {
        "US.RKLX": {
            "direction": "long",
            "t1": 80.00, "t2": 81.31, "stop": 72.20,  # stop 略高于现价,会触发 near_stop
            "set_at_price": 76.0, "set_at_ts": now - 3600,
        }
    }
    return s


# ── 测试 1: near_stop (亏损) 应该触发 ──────────────────────────
print("=" * 60)
print("[Test 1] 亏损 + 接近 stop ($72.20),现价 $71.83 — 应触发 near_stop")
s = make_session_with_loss(cost=74.08, current=71.83)
# 调用一次先消化冷却
hit = check_profit_target(s, "US.RKLX", indicators=None)
assert hit is not None, "❌ FAIL: 亏损时 near_stop 没触发 — bug 未修复"
assert hit["data"]["sub_reason"] in ("near_stop", "drawdown"), \
    f"❌ FAIL: sub_reason 应为 near_stop/drawdown, 实际 {hit['data']['sub_reason']}"
print(f"  ✅ 触发 sub_reason = {hit['data']['sub_reason']}")
print(f"  ✅ pl_pct = {hit['data']['pl_pct']:.2f}%  (亏损)")

# 验证 pusher 文案
msg = _fmt_profit_target(hit, session=s)
text = msg["text"]
print("\n--- 推送内容 ---")
print(text)
print("---")
assert "💰" not in text.split("\n")[0], "❌ 亏损时 title 不应出现 💰"
assert ("🛑" in text or "📉" in text), "❌ 亏损时 title 应出现 🛑 或 📉"
assert "目前亏损" in text, "❌ 应使用 '目前亏损' 措辞"
assert "目前盈利" not in text, "❌ 亏损时不应出现 '目前盈利'"
print("  ✅ title emoji / 措辞正确")


# ── 测试 2: 盈利时 near_target 仍正常 (不被新分支误伤) ───────────
print("\n" + "=" * 60)
print("[Test 2] 盈利 + 接近 T1 — 走原止盈路径, 文案为 💰 盈利版")
s2 = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
prices2 = [76.0, 76.5, 77.0, 77.5, 78.0, 78.5, 79.0, 79.3, 79.5, 79.6,
           79.65, 79.7]
for p in prices2:
    s2.update_price("US.RKLX", p)
s2.positions_snapshot = {
    "US.RKLX": {
        "qty": 20, "cost_price": 74.08, "current_price": 79.7,
        "market_val": 20 * 79.7,
        "pl_val": round((79.7 - 74.08) * 20, 2),
        "pl_pct": round((79.7 - 74.08) / 74.08 * 100, 2),
    }
}
s2.get_position = lambda tk: s2.positions_snapshot.get(tk)
s2.get_position_age_sec = lambda tk: 7200
s2._target_state = {
    "US.RKLX": {
        "direction": "long",
        "t1": 80.00, "t2": 81.31, "stop": 72.20,
        "set_at_price": 76.0, "set_at_ts": time.time() - 3600,
    }
}
hit2 = check_profit_target(s2, "US.RKLX", indicators=None)
assert hit2 is not None, "❌ FAIL: 盈利+接近T1 应触发 near_target"
assert hit2["data"]["sub_reason"] == "near_target", f"实际 {hit2['data']['sub_reason']}"
print(f"  ✅ 盈利路径 sub_reason = {hit2['data']['sub_reason']}")
msg2 = _fmt_profit_target(hit2, session=s2)
text2 = msg2["text"]
print("\n--- 盈利版推送 ---")
print(text2)
print("---")
assert "💰" in text2, "❌ 盈利时 title 应有 💰"
assert "目前盈利" in text2, "❌ 盈利时应使用 '目前盈利'"
print("  ✅ 盈利版文案正确")


# ── 测试 3: 亏损 + overbought_surge 应被屏蔽 ─────────────────
print("\n" + "=" * 60)
print("[Test 3] 亏损 + overbought_surge (盈利专属) — 应被屏蔽 return None")
s3 = make_session_with_loss(cost=74.08, current=71.83)
# 推远 stop 让 near_stop 不命中, 拉平 peak 让 drawdown 不命中
s3._target_state["US.RKLX"]["stop"] = 60.0
s3.peak_price["US.RKLX"] = s3.get_last_price("US.RKLX")  # 重置 peak
indicators = {"data_ok": True, "is_today": True, "rsi_5m": 85, "vol_ratio": 5.0}
hit3 = check_profit_target(s3, "US.RKLX", indicators=indicators)
assert hit3 is None, f"❌ FAIL: 亏损+overbought_surge 应被屏蔽, 实际 {hit3}"
print("  ✅ 亏损时 overbought_surge 被正确屏蔽")


print("\n" + "=" * 60)
print("✅ ALL PASS — 亏损告警放行 + 盈利路径不受影响 + 文案正确")
