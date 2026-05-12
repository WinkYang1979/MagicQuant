"""
v0.5.27 回归测试：开盘后头 50 min has_indicators=False 修复验证

测试场景：
  A. 开盘 5 min (50 根昨日 + 1 根当日)   → data_ok=True, RSI 真实, vwap=current_price 兜底, vwap_ok=False
  B. 开盘 25 min (50 根昨日 + 5 根当日)  → data_ok=True, vwap 真实, vwap_ok=True
  C. 全量 K < 15 根 (Futu 异常)         → data_ok=False
  D. 盘前 (50 根昨日 + 0 根当日)         → data_ok=True, is_today=False
  E. 老测试兼容 (无 time_key + has_today_data) → 仍按老语义工作
"""

import sys
import importlib.util
from pathlib import Path

import pandas as pd

# 直接加载 micro_indicators.py,绕过 core/focus/__init__ (会拉起 futu 依赖)
_MOD_PATH = Path(__file__).resolve().parents[1] / "core" / "focus" / "micro_indicators.py"
_spec = importlib.util.spec_from_file_location("micro_indicators_under_test", _MOD_PATH)
_mod  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
calc_all_micro = _mod.calc_all_micro


def _build_kl(yesterday_bars: int, today_bars: int,
              et_today: str = "2026-05-12",
              et_yesterday: str = "2026-05-11"):
    """
    构造跨日 5m K 线 DataFrame, 模拟 _fetch_5m_kline 输出。
    收盘价交替涨跌,保证 RSI / vol_ratio 都跑出非兜底值。
    """
    import math
    rows = []
    base_price = 100.0
    # 昨日 RTH 尾盘 (含上下震荡, 避免 RSI 退化为 50)
    for i in range(yesterday_bars):
        p     = base_price + i * 0.1
        close = p + (0.3 if i % 2 == 0 else -0.4)   # 交替涨跌, 保 RSI 非兜底
        rows.append({
            "time_key": f"{et_yesterday} {14 + i // 12:02d}:{(i % 12) * 5:02d}:00",
            "open":   p,
            "high":   p + 0.6,
            "low":    p - 0.6,
            "close":  close,
            "volume": 100000 + (i % 5) * 30000,     # 量也波动, 防 vol_ratio 退化
        })
    # 今日开盘
    last_p = base_price + yesterday_bars * 0.1
    for i in range(today_bars):
        p     = last_p + i * 0.2
        close = p + (0.5 if i % 2 == 0 else -0.3)
        rows.append({
            "time_key": f"{et_today} 09:{30 + i * 5:02d}:00",
            "open":   p,
            "high":   p + 1.0,
            "low":    p - 0.3,
            "close":  close,
            "volume": 200000 + i * 5000,
        })
    kl = pd.DataFrame(rows)
    kl.attrs["et_today"]       = et_today
    kl.attrs["has_today_data"] = today_bars > 0
    return kl


def test_a_market_open_first_5min():
    """A. 开盘 5 min: 50 昨日 + 1 当日 → RSI/vol 立刻可用, VWAP 走兜底"""
    kl  = _build_kl(yesterday_bars=50, today_bars=1)
    ind = calc_all_micro(kl, current_price=105.5)

    assert ind["data_ok"] is True,    f"开盘瞬间 data_ok 应 True (RSI 可用), 实际={ind['data_ok']}"
    assert ind["vwap_ok"] is False,   f"当日 1 根 vwap_ok 应 False, 实际={ind['vwap_ok']}"
    assert ind["is_today"] is True,   f"当日有 1 根 is_today 应 True, 实际={ind['is_today']}"
    assert ind["rsi_5m"] != 50.0,     f"RSI 应跑出真实值,而不是兜底 50, 实际={ind['rsi_5m']}"
    assert ind["vol_ratio"] != 1.0,   f"vol_ratio 应跑出真实值, 实际={ind['vol_ratio']}"
    assert ind["vwap"] == 105.5,      f"VWAP 当日<3 根应兜底 current_price, 实际={ind['vwap']}"
    print(f"  ✅ A. 开盘 5min: data_ok=T  RSI={ind['rsi_5m']}  vol={ind['vol_ratio']}  vwap=兜底  is_today=T")


def test_b_market_open_25min():
    """B. 开盘 25 min: 50 昨日 + 5 当日 → VWAP 也就绪"""
    kl  = _build_kl(yesterday_bars=50, today_bars=5)
    ind = calc_all_micro(kl, current_price=110.0)

    assert ind["data_ok"] is True
    assert ind["vwap_ok"] is True,    f"当日 5 根 vwap_ok 应 True, 实际={ind['vwap_ok']}"
    assert ind["is_today"] is True
    assert ind["vwap"] != 110.0,      f"VWAP 应跑出真实值,不再兜底, 实际={ind['vwap']}"
    print(f"  ✅ B. 开盘 25min: data_ok=T vwap_ok=T  VWAP={ind['vwap']}  RSI={ind['rsi_5m']}")


def test_c_insufficient_data():
    """C. 全量 K < 15 (Futu 异常/重启刚启动): data_ok=False"""
    kl  = _build_kl(yesterday_bars=10, today_bars=2)
    ind = calc_all_micro(kl, current_price=100.0)

    assert ind["data_ok"] is False,   f"<15 根 data_ok 应 False, 实际={ind['data_ok']}"
    assert ind["rsi_5m"]  == 50.0,    "RSI 走兜底"
    assert ind["vwap"]    == 100.0,   "VWAP 走兜底 current_price"
    print(f"  ✅ C. 全量 12 根 (<15): data_ok=False, 全部兜底")


def test_d_pre_market():
    """D. 盘前: 50 昨日 + 0 当日 → data_ok=True (RSI 可用), is_today=False"""
    kl  = _build_kl(yesterday_bars=50, today_bars=0)
    ind = calc_all_micro(kl, current_price=100.0)

    assert ind["data_ok"] is True,    "盘前全量 K 充足 data_ok=True"
    assert ind["is_today"] is False,  "当日 0 根 is_today=False"
    assert ind["vwap_ok"] is False
    assert ind["vwap"]    == 100.0,   "VWAP 当日无数据走兜底"
    assert ind["session_high"] == 100.0
    print(f"  ✅ D. 盘前: data_ok=T  is_today=F  RSI={ind['rsi_5m']}  VWAP=兜底")


def test_e_legacy_compat_no_time_key():
    """E. 兼容老测试路径: 无 time_key 列, 仅 attrs.has_today_data"""
    # 构造 15 根, 没有 time_key 列, attrs.has_today_data=True
    kl = pd.DataFrame({
        "open":   [100 + i * 0.1 for i in range(15)],
        "high":   [100 + i * 0.1 + 0.5 for i in range(15)],
        "low":    [100 + i * 0.1 - 0.5 for i in range(15)],
        "close":  [100 + i * 0.1 + 0.2 for i in range(15)],
        "volume": [100000] * 15,
    })
    kl.attrs["has_today_data"] = True   # 没有 et_today, 走回退分支
    ind = calc_all_micro(kl, current_price=102.0)

    assert ind["data_ok"] is True
    assert ind["is_today"] is True,    "has_today_data=True → is_today=True"
    # 无 time_key → kl_today=kl 全量 → vwap_ok=True (>=3)
    assert ind["vwap_ok"] is True
    print(f"  ✅ E. 老测试兼容(无 time_key): data_ok=T  is_today=T  vwap_ok=T")


def test_f_legacy_compat_pre_market():
    """F. 兼容老测试: 无 time_key + has_today_data=False"""
    kl = pd.DataFrame({
        "open":   [100 + i * 0.1 for i in range(15)],
        "high":   [100 + i * 0.1 + 0.5 for i in range(15)],
        "low":    [100 + i * 0.1 - 0.5 for i in range(15)],
        "close":  [100 + i * 0.1 + 0.2 for i in range(15)],
        "volume": [100000] * 15,
    })
    kl.attrs["has_today_data"] = False
    ind = calc_all_micro(kl, current_price=102.0)

    assert ind["data_ok"]  is True   # RSI 仍可用
    assert ind["is_today"] is False  # 兼容老语义
    assert ind["vwap"]     == 102.0  # 当日无数据走兜底
    print(f"  ✅ F. 老测试兼容(盘前 fallback): data_ok=T  is_today=F  VWAP=兜底")


if __name__ == "__main__":
    print("\n=== v0.5.27 micro_indicators 开盘时段修复回归 ===\n")
    test_a_market_open_first_5min()
    test_b_market_open_25min()
    test_c_insufficient_data()
    test_d_pre_market()
    test_e_legacy_compat_no_time_key()
    test_f_legacy_compat_pre_market()
    print("\n=== 全部通过 ✅ ===\n")
