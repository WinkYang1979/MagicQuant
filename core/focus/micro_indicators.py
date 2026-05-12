"""
MagicQuant Focus — 微观指标计算
Dare to dream. Data to win.

针对日内波段做 T 的快速指标:
  - 5 分钟 RSI(反应快)
  - VWAP(日内标配)
  - 短期量比
  - 距今日高/低
  - K 线形态(锤子/流星)
"""

import pandas as pd
import numpy as np
from typing import Optional


def calc_rsi_fast(close: pd.Series, period: int = 14) -> float:
    """快速 RSI(适合 5 分钟级别)"""
    if len(close) < period + 1:
        return 50.0
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = (100 - 100/(1+rs)).iloc[-1]
    if pd.isna(rsi):
        return 50.0
    return round(float(rsi), 1)


def calc_vwap(kl: pd.DataFrame) -> float:
    """日内 VWAP = Σ(price × volume) / Σ(volume)"""
    if kl is None or len(kl) == 0:
        return 0.0
    typical = (kl["high"].astype(float) + kl["low"].astype(float) + kl["close"].astype(float)) / 3
    volume  = kl["volume"].astype(float)
    cum_pv  = (typical * volume).sum()
    cum_v   = volume.sum()
    if cum_v <= 0:
        return 0.0
    return round(float(cum_pv / cum_v), 4)


def calc_volume_ratio_short(volume: pd.Series, n_recent: int = 3, n_base: int = 10) -> float:
    """
    短期量比 = 最近 N 根的均量 / 前 M 根的均量
    用于识别放量/缩量
    """
    if len(volume) < n_recent + n_base:
        return 1.0
    recent = volume.tail(n_recent).mean()
    base   = volume.iloc[-(n_recent + n_base):-n_recent].mean()
    if base <= 0:
        return 1.0
    return round(float(recent / base), 2)


def detect_candle_pattern(open_: pd.Series, high: pd.Series, 
                          low: pd.Series, close: pd.Series) -> Optional[dict]:
    """
    检测最后一根 K 线的反转形态
    返回: {"name": "锤子线", "type": "bullish", "strength": 0.8}
    """
    if len(close) < 2:
        return None

    o = float(open_.iloc[-1])
    h = float(high.iloc[-1])
    l = float(low.iloc[-1])
    c = float(close.iloc[-1])

    body        = abs(c - o)
    upper_wick  = h - max(o, c)
    lower_wick  = min(o, c) - l
    total_range = h - l

    if total_range == 0:
        return None

    body_ratio       = body / total_range
    upper_ratio      = upper_wick / total_range
    lower_ratio      = lower_wick / total_range

    # 锤子线:下影长,上影短,小实体,出现在下跌末端
    if lower_ratio > 0.6 and upper_ratio < 0.15 and body_ratio < 0.3:
        return {"name": "锤子线", "type": "bullish", "strength": 0.8}

    # 流星线:上影长,下影短,小实体,出现在上涨末端
    if upper_ratio > 0.6 and lower_ratio < 0.15 and body_ratio < 0.3:
        return {"name": "流星线", "type": "bearish", "strength": 0.8}

    # 十字星:实体极小,上下影对称
    if body_ratio < 0.1 and 0.3 < upper_ratio < 0.7:
        return {"name": "十字星", "type": "neutral", "strength": 0.5}

    # 长下影:实体小,下影长,支撑明显
    if lower_ratio > 0.5 and body_ratio < 0.4:
        return {"name": "长下影", "type": "bullish", "strength": 0.6}

    # 长上影:实体小,上影长,压力明显
    if upper_ratio > 0.5 and body_ratio < 0.4:
        return {"name": "长上影", "type": "bearish", "strength": 0.6}

    return None


def calc_all_micro(kl_5m: pd.DataFrame, current_price: float) -> dict:
    """
    一次性计算所有微观指标
    v0.5.27 (2026-05-12): 解耦各指标数据要求,修开盘后 50 min has_indicators=False
      - RSI / vol_ratio / candle: 用全量 K(含昨日尾盘),滚动周期跨日反而稳定
      - VWAP / session_high/low: 用 et_today 当日子集(必须当日重置)
      - data_ok = 全量 K ≥ 15 (RSI(14) 可用门槛,跟当日数据解耦)
      - vwap_ok = 当日子集 ≥ 3 (VWAP 是否就绪,下游可选用)
      - is_today = 当日子集非空 (兼容 v0.5.25 swing_top/bottom RTH skip)

    Decouple per-indicator data requirements
    Goal: RSI/vol/vwap available at open instead of waiting 50 min

    输入: 5 分钟 K 线 DataFrame (需要有 open/high/low/close/volume)
         当前实时价(可能比最后一根 K 线的 close 更新)
         DataFrame.attrs["et_today"] = "YYYY-MM-DD" (由 _fetch_5m_kline 写入,
                                                   缺失时回退到 has_today_data 标记)

    输出: dict with all indicators
    """
    # v0.5.27: 门槛从 <10 改为 <15 — RSI(14) 需要至少 15 根才稳定
    # 全量 K 通常 ≥ 200 根,远超门槛;只有 Futu 异常或盘前刚启动时才会走兜底
    if kl_5m is None or len(kl_5m) < 15:
        return {
            "rsi_5m":       50.0,
            "vwap":         current_price,
            "vol_ratio":    1.0,
            "session_high": current_price,
            "session_low":  current_price,
            "dist_high":    0.0,
            "dist_low":     0.0,
            "candle":       None,
            "data_ok":      False,
            "vwap_ok":      False,
            "is_today":     False,
        }

    close = kl_5m["close"].astype(float)
    high  = kl_5m["high"].astype(float)
    low   = kl_5m["low"].astype(float)
    open_ = kl_5m["open"].astype(float)
    vol   = kl_5m["volume"].astype(float)

    # ── 全量 K 算 RSI / vol_ratio / candle (跨日 OK,更稳) ──
    rsi       = calc_rsi_fast(close, 14)
    vol_ratio = calc_volume_ratio_short(vol, 3, 10)
    candle    = detect_candle_pattern(open_, high, low, close)

    # ── 当日子集算 VWAP / session_high/low (必须当日重置,防跨日污染) ──
    # 优先用 attrs.et_today + time_key 过滤;回退到 attrs.has_today_data (兼容老测试)
    attrs    = getattr(kl_5m, "attrs", {}) or {}
    et_today = attrs.get("et_today")

    if et_today and "time_key" in kl_5m.columns:
        today_mask = kl_5m["time_key"].astype(str).str.startswith(et_today)
        kl_today   = kl_5m[today_mask]
        is_today   = len(kl_today) > 0
    else:
        # 老测试路径:无 time_key 列,用 has_today_data 标记
        is_today  = bool(attrs.get("has_today_data", True))
        kl_today  = kl_5m if is_today else kl_5m.iloc[0:0]

    n_today = len(kl_today)
    vwap_ok = n_today >= 3

    if vwap_ok:
        vwap         = calc_vwap(kl_today)
        session_high = float(kl_today["high"].astype(float).max())
        session_low  = float(kl_today["low"].astype(float).min())
    elif is_today:
        # 当日 1-2 根:VWAP 不稳,用 current_price 兜底;但 high/low 可用
        vwap         = current_price
        session_high = float(kl_today["high"].astype(float).max())
        session_low  = float(kl_today["low"].astype(float).min())
    else:
        # 当日无数据 (盘前/盘后):全部用 current_price 兜底
        vwap         = current_price
        session_high = current_price
        session_low  = current_price

    dist_high = (current_price - session_high) / session_high * 100 if session_high else 0
    dist_low  = (current_price - session_low)  / session_low  * 100 if session_low else 0

    return {
        "rsi_5m":       rsi,
        "vwap":         round(float(vwap), 4),
        "vol_ratio":    vol_ratio,
        "session_high": round(session_high, 4),
        "session_low":  round(session_low, 4),
        "dist_high":    round(dist_high, 2),   # 负数=离高点差多少%
        "dist_low":     round(dist_low, 2),    # 正数=离低点高多少%
        "candle":       candle,
        "data_ok":      True,
        "vwap_ok":      vwap_ok,               # v0.5.27: VWAP 是否就绪
        "is_today":     is_today,              # v0.5.25: 当日子集是否非空
    }


if __name__ == "__main__":
    # 自测
    import numpy as np
    np.random.seed(42)
    data = {
        "open":   np.random.uniform(28, 30, 30),
        "high":   np.random.uniform(29, 31, 30),
        "low":    np.random.uniform(27, 29, 30),
        "close":  np.random.uniform(28, 30, 30),
        "volume": np.random.uniform(100000, 500000, 30),
    }
    df = pd.DataFrame(data)
    df["high"] = df[["open","close","high"]].max(axis=1) + 0.5
    df["low"]  = df[["open","close","low"]].min(axis=1) - 0.5

    result = calc_all_micro(df, current_price=29.10)
    print("微观指标测试:")
    for k, v in result.items():
        print(f"  {k}: {v}")
