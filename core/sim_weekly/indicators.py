"""轻量纯-python 技术指标(无 pandas 依赖),供 SimWeekly 自包含使用。

bar = {"time","open","high","low","close","volume"} (float/str)。
所有函数对输入做防御,数据不足时返回 None / 合理兜底。
"""
from __future__ import annotations

from typing import List, Optional


def ema(values: List[float], n: int) -> Optional[float]:
    if not values or len(values) < n:
        return None
    k = 2.0 / (n + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def rsi(closes: List[float], n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (n - 1) + max(d, 0.0)) / n
        avg_l = (avg_l * (n - 1) + max(-d, 0.0)) / n
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 2)


def atr(bars: List[dict], n: int = 14) -> Optional[float]:
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l = float(bars[i]["high"]), float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-n:]
    return round(sum(recent) / len(recent), 4)


def session_vwap(bars: List[dict]) -> Optional[float]:
    """对传入的(同一交易日)bars 计算 VWAP。调用方负责只传当日 bars。"""
    if not bars:
        return None
    pv = vol = 0.0
    for b in bars:
        tp = (float(b["high"]) + float(b["low"]) + float(b["close"])) / 3.0
        v = float(b.get("volume", 0) or 0)
        pv += tp * v
        vol += v
    if vol <= 0:
        return float(bars[-1]["close"])
    return round(pv / vol, 4)
