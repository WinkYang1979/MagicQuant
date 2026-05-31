"""tests/smoke_heartbeat_v0_5_33.py — v0.5.33 心跳渲染冒烟测试"""
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class MockSession:
    active = True
    master = "US.RKLB"
    followers = ["US.RKLX", "US.RKLZ"]
    session_high = {"US.RKLB": 95.0}
    session_low = {"US.RKLB": 88.0}
    prices = {}
    quote_snapshot = {}
    last_trigger_time = {}
    start_time = time.time() - 600
    loop_count = 120
    trigger_count = 3
    push_count = 3

    def get_last_price(self, tk):
        return {"US.RKLB": 92.5, "US.RKLX": 74.34, "US.RKLZ": 12.10}.get(tk)

    def get_position(self, tk):
        if tk == "US.RKLX":
            return {"qty": 36, "cost_price": 76.45, "pl_pct": -2.37, "pl_val": -75.96}
        return None

    def get_peak_drawdown_pct(self, tk):
        return None

    def get_price_change_pct(self, tk, sec):
        return 0.4

    def can_trigger(self, k, cooldown_sec):
        return True


from core.focus.heartbeat import format_heartbeat
from core.focus.focus_manager import IndicatorFreezeDetector

ind = {"data_ok": True, "rsi_5m": 58.2, "macd_hist": 0.05, "vol_ratio": 1.45,
       "is_today": True, "candle": {}}

print("=" * 60)
print("CASE 1: 普通观望(指标正常)")
print("=" * 60)
s = MockSession()
print(format_heartbeat(s, ind))

print()
print("=" * 60)
print("CASE 2: 指标冻结中")
print("=" * 60)
fz = IndicatorFreezeDetector(threshold=5)
fz.frozen = True
fz.freeze_started_ts = time.time() - 240
s._indicator_freeze = fz
print(format_heartbeat(s, ind))

print()
print("=" * 60)
print("CASE 3: 持仓接近止损 (15min ago)")
print("=" * 60)
fz.frozen = False
s.last_trigger_time = {"stop_loss_US.RKLX_approaching": time.time() - 900}
print(format_heartbeat(s, ind))

print()
print("=" * 60)
print("CASE 4: 盘前 fallback (is_today=False, vol_ratio 4.2 异常放量)")
print("=" * 60)
s.last_trigger_time = {}
ind_pre = dict(ind, is_today=False, vol_ratio=4.2)
print(format_heartbeat(s, ind_pre))
