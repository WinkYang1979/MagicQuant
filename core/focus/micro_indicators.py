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
    
    输入: 5 分钟 K 线 DataFrame (需要有 open/high/low/close/volume)
         当前实时价(可能比最后一根 K 线的 close 更新)
    
    输出: dict with all indicators
    """
    if kl_5m is None or len(kl_5m) < 10:
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
        }

    close = kl_5m["close"].astype(float)
    high  = kl_5m["high"].astype(float)
    low   = kl_5m["low"].astype(float)
    open_ = kl_5m["open"].astype(float)
    vol   = kl_5m["volume"].astype(float)

    session_high = float(high.max())
    session_low  = float(low.min())

    dist_high = (current_price - session_high) / session_high * 100 if session_high else 0
    dist_low  = (current_price - session_low)  / session_low  * 100 if session_low else 0

    return {
        "rsi_5m":       calc_rsi_fast(close, 14),
        "vwap":         calc_vwap(kl_5m),
        "vol_ratio":    calc_volume_ratio_short(vol, 3, 10),
        "session_high": round(session_high, 4),
        "session_low":  round(session_low, 4),
        "dist_high":    round(dist_high, 2),   # 负数=离高点差多少%
        "dist_low":     round(dist_low, 2),    # 正数=离低点高多少%
        "candle":       detect_candle_pattern(open_, high, low, close),
        "data_ok":      True,
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
