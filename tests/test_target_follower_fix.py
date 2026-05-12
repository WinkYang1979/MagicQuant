"""
v0.5.28 bug fix 验证:
确认 _fmt_signal_with_conflict 现在用 follower 价位算 targets，不再把 master 价错标到 RKLX
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.focus import pusher
from core.focus.context import FocusSession

# 构造一个 session 模拟今晚 00:19:29 的实际状态
session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
session.update_cash(5000.0, 5000.0)  # 给 5000 让仓位建议能正常算出

# 灌入 RKLB / RKLX 的近期价格历史（让 _calc_price_targets 有数据可算）
# 重现 00:19 时刻数据 — RKLB ~$117-120, RKLX ~$71-76
now = time.time()
for i, (rklb, rklx) in enumerate([
    (115.88, 70.82), (116.01, 71.00), (116.45, 71.29), (116.89, 72.08),
    (117.08, 72.85), (117.61, 73.20), (117.91, 73.40), (118.07, 73.16),
    (118.21, 73.84), (118.39, 74.30), (118.57, 74.50), (118.67, 74.64),
    (118.95, 74.78), (119.06, 74.64), (119.13, 74.50), (119.33, 75.00),
    (119.86, 75.50), (119.90, 75.72), (120.12, 76.10), (120.35, 76.38),
]):
    session.update_price("US.RKLB", rklb)
    session.update_price("US.RKLX", rklx)
    session.update_price("US.RKLZ", 3.05 - i*0.005)

# 构造一个 direction_trend long [STRONG] 信号 hit
hit = {
    "ticker": "US.RKLB",
    "trigger": "direction_trend",
    "direction": "long",
    "strength": "STRONG",
    "data": {
        "has_indicators": True,
        "rsi": 52.7, "vwap": 117.98, "vol_ratio": 0.33,
        "regime": "choppy",
    },
}

out = pusher._fmt_signal_with_conflict(
    hit, session, "long",
    "🚀 <b>RKLB 方向信号 (看多)</b> [强烈]",
    "RSI 52.7  ·  VWAP $117.98  ·  量比 0.33x",
)
text = out["text"]
print("="*60)
print(text)
print("="*60)

# 断言:RKLX 域目标价应该贴近 $76-78,绝不能是 $119/$120
import re
m = re.search(r"RKLX 目标 T1 \$([\d.]+)", text)
assert m, "找不到 RKLX 目标 T1 行"
t1 = float(m.group(1))
print(f"\n[CHECK] RKLX 目标 T1 = ${t1:.2f}")
assert 70 < t1 < 90, f"❌ FAIL: RKLX T1 应在 $70-$90 区间 (follower 价域), 实际 ${t1:.2f}"

m = re.search(r"RKLX 止损 \$([\d.]+)", text)
assert m, "找不到 RKLX 止损 行"
stop = float(m.group(1))
print(f"[CHECK] RKLX 止损 = ${stop:.2f}")
assert 60 < stop < 76, f"❌ FAIL: RKLX 止损 应低于入场价(~$76) 且在 follower 价域, 实际 ${stop:.2f}"

# 入场价 RKLX 现价 ~ $76.38(最后一条)
follower_entry = session.get_last_price("US.RKLX")
assert stop < follower_entry, f"❌ FAIL: 多头止损必须低于入场价 ({stop:.2f} >= {follower_entry:.2f})"

# _target_state 同时存在 master 和 follower 两份
assert "US.RKLB" in session._target_state, "❌ master target_state 缺失(影响 target_advance)"
assert "US.RKLX" in session._target_state, "❌ follower target_state 缺失(影响 follower profit_target)"

rklb_state = session._target_state["US.RKLB"]
rklx_state = session._target_state["US.RKLX"]
print(f"[CHECK] master state: t1=${rklb_state['t1']:.2f}  stop=${rklb_state['stop']:.2f}")
print(f"[CHECK] follower state: t1=${rklx_state['t1']:.2f}  stop=${rklx_state['stop']:.2f}")
assert rklb_state["t1"] > 110, "master t1 应在 RKLB 价域"
assert rklx_state["t1"] < 90, "follower t1 应在 RKLX 价域"

print("\n✅ ALL PASS — bug 已修复:targets 显示和 _target_state 都按域分开")
