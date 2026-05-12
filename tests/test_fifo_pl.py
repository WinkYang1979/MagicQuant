"""
v0.5.1: 验证 daily_briefing FIFO 真实盈亏算法
覆盖:
  1) 继承持仓 → 第一笔 SELL 应 FIFO 消费继承 lot
  2) 信号方向匹配:仅前向 30min 才算跟随
  3) 错过的强信号:已有同方向持仓 → 不算错过
  4) 错过的强信号:信号后 30min 内有同向操作 → 不算错过
  5) sell 数量超过 lot 队列 → unmatched_qty + warning
"""
import sys, json, tempfile, shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "root"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 用临时目录避开真实 data/review (避免污染)
TMP_ROOT = Path(tempfile.mkdtemp(prefix="mq_fifo_test_"))
TMP_DATA = TMP_ROOT / "data" / "review"
TMP_DATA.mkdir(parents=True)

# 必须 monkeypatch daily_briefing.BASE_DIR.parent 让它读临时 data
import daily_briefing
daily_briefing.BASE_DIR = TMP_ROOT / "root"   # parent=TMP_ROOT,data/review → TMP_DATA

from daily_briefing import (
    _load_initial_positions, _compute_fifo_pl, _build_yesterday_review,
)


def _write_summary(date_str: str, positions_final: dict):
    d = TMP_DATA / date_str
    d.mkdir(exist_ok=True)
    (d / "session_summary.json").write_text(json.dumps({
        "date": date_str,
        "positions_final": positions_final,
    }), encoding="utf-8")


# ── Test 1: 继承持仓 ────────────────────────────────────────────
print("=" * 60)
print("[Test 1] _load_initial_positions 读前一交易日 positions_final")
_write_summary("2026-05-12", {
    "RKLX": {"qty": 18, "cost": 67.78, "pl_val": -10, "pl_pct": -0.5},
    "RKLZ": {"qty": 100, "cost": 5.50, "pl_val": 50, "pl_pct": 5.0},
})
ip = _load_initial_positions("2026-05-13")
assert "US.RKLX" in ip and ip["US.RKLX"] == {"qty": 18, "cost": 67.78}, ip
assert "US.RKLZ" in ip and ip["US.RKLZ"] == {"qty": 100, "cost": 5.50}, ip
print(f"  ✅ 继承 {len(ip)} 个 ticker:{list(ip.keys())}")


# ── Test 2: 跨周末回溯 ──────────────────────────────────────────
print("\n" + "=" * 60)
print("[Test 2] 周末/节假日缺 session_summary,自动往前回溯")
# 2026-05-15 (Fri) 之前最近的 summary 是 5-12 (Mon)
ip2 = _load_initial_positions("2026-05-18")  # 假设 5-13~17 缺 (周末+节假日)
assert "US.RKLX" in ip2, "应回溯到 2026-05-12"
print("  ✅ 跨多天回溯到 2026-05-12")


# ── Test 3: FIFO 单 ticker 简单场景 (无继承) ─────────────────────
print("\n" + "=" * 60)
print("[Test 3] FIFO 无继承:BUY 100@10 → SELL 50@12 → 实现 +$100 (毛)")
deals = [
    {"code": "US.AAPL", "side": "BUY",  "qty": 100, "price": 10.0,
     "create_time": "2026-05-13 09:30:00"},
    {"code": "US.AAPL", "side": "SELL", "qty": 50,  "price": 12.0,
     "create_time": "2026-05-13 10:00:00"},
]
r = _compute_fifo_pl(deals, initial_positions={})
assert r["totals"]["realized_gross"] == 100.0, r["totals"]
# 费用:50 × $0.02 = $1.00
assert r["totals"]["fees"] == 1.0, r["totals"]
assert r["totals"]["realized_net"] == 99.0
sell_record = r["trades"][1]
assert sell_record["matched_lots"] == [
    {"qty": 50, "buy_price": 10.0, "source": "09:30:00"}
], sell_record["matched_lots"]
print(f"  ✅ gross=+$100, fee=$1.00, net=+$99")


# ── Test 4: FIFO 继承场景 (用户原 spec 示例) ────────────────────
print("\n" + "=" * 60)
print("[Test 4] 继承 RKLX 18股@$67.78 → BUY 44@67.78 → SELL 44@66.77")
deals = [
    {"code": "US.RKLX", "side": "BUY",  "qty": 44, "price": 67.78,
     "create_time": "2026-05-13 07:19:00"},
    {"code": "US.RKLX", "side": "SELL", "qty": 44, "price": 66.77,
     "create_time": "2026-05-13 08:36:00"},
    {"code": "US.RKLX", "side": "BUY",  "qty": 20, "price": 74.08,
     "create_time": "2026-05-13 10:25:00"},
    {"code": "US.RKLX", "side": "SELL", "qty": 38, "price": 78.50,
     "create_time": "2026-05-13 14:55:00"},
]
initial = {"US.RKLX": {"qty": 18, "cost": 67.78}}
r = _compute_fifo_pl(deals, initial)

# 第 1 笔 SELL @08:36 卖 44 → 消费 18 (继承) + 26 (07:19 lot)
sell1 = r["trades"][1]
assert sell1["matched_lots"] == [
    {"qty": 18, "buy_price": 67.78, "source": "继承"},
    {"qty": 26, "buy_price": 67.78, "source": "07:19:00"},
], sell1["matched_lots"]
# gross = 44 × (66.77 - 67.78) = -44.44
assert abs(sell1["gross_pl"] - (-44.44)) < 0.01, sell1["gross_pl"]

# 07:19 lot 剩 44-26 = 18 股
# 第 2 笔 SELL @14:55 卖 38 → 消费 18 (07:19 剩余) + 20 (10:25)
sell2 = r["trades"][3]
assert sell2["matched_lots"] == [
    {"qty": 18, "buy_price": 67.78, "source": "07:19:00"},
    {"qty": 20, "buy_price": 74.08, "source": "10:25:00"},
], sell2["matched_lots"]
# gross = 18×(78.50-67.78) + 20×(78.50-74.08) = 192.96 + 88.40 = 281.36
assert abs(sell2["gross_pl"] - 281.36) < 0.01, sell2["gross_pl"]

# 持仓变化:RKLX 18 → 0
assert r["position_changes"] == {"RKLX": (18, 0)}, r["position_changes"]

# 总:gross = -44.44 + 281.36 = +236.92,fee = 82 × 0.02 = $1.64
assert abs(r["totals"]["realized_gross"] - 236.92) < 0.01
assert abs(r["totals"]["fees"] - 1.64) < 0.01
print(f"  ✅ sell1 FIFO 匹配 18(继承) + 26(07:19) = -$44.44 (毛)")
print(f"  ✅ sell2 FIFO 匹配 18(07:19) + 20(10:25) = +$281.36 (毛)")
print(f"  ✅ 总 gross=+$236.92, fee=$1.64, net=+${r['totals']['realized_net']:.2f}")
print(f"  ✅ 持仓变化:RKLX 18 → 0")


# ── Test 5: unmatched sell (卖出数量超过 lot) ───────────────────
print("\n" + "=" * 60)
print("[Test 5] 卖 100 股但 lot 只有 50 → unmatched_qty=50 + warning")
deals5 = [
    {"code": "US.AAPL", "side": "BUY",  "qty": 50, "price": 10.0,
     "create_time": "2026-05-13 09:30:00"},
    {"code": "US.AAPL", "side": "SELL", "qty": 100, "price": 12.0,
     "create_time": "2026-05-13 10:00:00"},
]
r5 = _compute_fifo_pl(deals5, {})
sell = r5["trades"][1]
assert sell["unmatched_qty"] == 50, sell
assert r5["warnings"] and "AAPL" in r5["warnings"][0]
print(f"  ✅ unmatched_qty={sell['unmatched_qty']}, warning: {r5['warnings'][0]}")


# ── Test 6: 信号方向匹配 — 前向 30min ───────────────────────────
print("\n" + "=" * 60)
print("[Test 6] 信号方向匹配:仅信号 BEFORE 操作 ≤30min 才算跟随")
# 写 triggers.json
trig_dir = TMP_DATA / "2026-05-14"
trig_dir.mkdir(exist_ok=True)
triggers = [
    # 信号在操作之前 25min → 应匹配
    {"ts": "2026-05-14 09:05:00", "ticker": "US.RKLB", "direction": "long",
     "trigger": "direction_trend", "strength": "STRONG"},
    # 信号在操作之后 5min → 不应匹配 (前向 only)
    {"ts": "2026-05-14 10:00:00", "ticker": "US.RKLB", "direction": "long",
     "trigger": "swing_bottom", "strength": "STRONG"},
]
(trig_dir / "triggers.json").write_text(json.dumps(triggers), encoding="utf-8")
deals6 = [
    {"code": "US.RKLB", "side": "BUY", "qty": 10, "price": 100,
     "create_time": "2026-05-14 09:30:00"},
]
_write_summary("2026-05-13", {})
review = _build_yesterday_review("2026-05-14", deals6, triggers)
trade = review["trades"][0]
# 匹配的信号应该是 09:05 那条 (前向 25min),不是 10:00 那条
assert trade["trigger"] == "direction_trend", trade
assert trade["gap_min"] == 25.0
print(f"  ✅ trade matched 信号 = direction_trend (前 25min)")
print(f"  ✅ 10:00 的后向信号被正确忽略")


# ── Test 7: 错过的强信号 — 已有同方向持仓 ──────────────────────
print("\n" + "=" * 60)
print("[Test 7] 错过判定:已有同方向持仓 → 不算错过")
_write_summary("2026-05-15", {})
# 当日仅有 1 个 long 强信号,但已持仓 RKLB
triggers7 = [
    {"ts": "2026-05-16 09:00:00", "ticker": "US.RKLB", "direction": "long",
     "trigger": "direction_trend", "strength": "STRONG"},
]
# 写入"前一交易日"的 positions_final 让 initial_positions 含 RKLB
_write_summary("2026-05-15", {"RKLB": {"qty": 50, "cost": 100.0}})
review7 = _build_yesterday_review("2026-05-16", deals=[], triggers=triggers7)
assert review7["missed"] == [], f"已有 long 持仓不该算错过, missed={review7['missed']}"
print("  ✅ 同方向持仓 → 信号不算错过")


# ── Test 8: 错过的强信号 — 信号后 30min 内有操作 ─────────────────
print("\n" + "=" * 60)
print("[Test 8] 错过判定:信号后 30min 内有同向 BUY → 不算错过")
_write_summary("2026-05-17", {})
triggers8 = [
    {"ts": "2026-05-18 09:00:00", "ticker": "US.RKLB", "direction": "long",
     "trigger": "direction_trend", "strength": "STRONG"},
]
deals8 = [
    {"code": "US.RKLB", "side": "BUY", "qty": 10, "price": 100,
     "create_time": "2026-05-18 09:20:00"},
]
review8 = _build_yesterday_review("2026-05-18", deals8, triggers8)
assert review8["missed"] == [], f"30min 内有 BUY 不该算错过, missed={review8['missed']}"
print("  ✅ 信号后 20min 有 BUY → 不算错过")


# ── Test 9: 真正错过 — 无持仓 + 无操作 ──────────────────────────
print("\n" + "=" * 60)
print("[Test 9] 错过判定:无持仓 + 无操作 → 算错过")
_write_summary("2026-05-19", {})
triggers9 = [
    {"ts": "2026-05-20 09:00:00", "ticker": "US.RKLB", "direction": "long",
     "trigger": "direction_trend", "strength": "STRONG"},
]
review9 = _build_yesterday_review("2026-05-20", deals=[], triggers=triggers9)
assert len(review9["missed"]) == 1, f"应算错过, missed={review9['missed']}"
print(f"  ✅ 无持仓无操作 → missed={review9['missed'][0]['trigger']}")


# ── 清理 ─────────────────────────────────────────────────────────
shutil.rmtree(TMP_ROOT, ignore_errors=True)

print("\n" + "=" * 60)
print("✅ ALL PASS — FIFO 真实盈亏 + 信号方向匹配 + 错过判定 全部正确")
