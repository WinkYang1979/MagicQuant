"""
MagicQuant Focus - swing_labeler.py
VERSION : v0.1.0
DATE    : 2026-05-21
DEPENDS : dataclasses, datetime

ATR 自适应波段标注。 / ATR-adaptive swing labelling for reviews.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


VERSION = "v0.1.0"


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Wave:
    direction: str
    start: datetime
    end: datetime
    start_price: float
    end_price: float
    pct: float
    high: float
    low: float
    dur_min: float
    threshold_pct: float


def calc_atr_pct(bars: list[Bar], period: int = 14) -> list[float | None]:
    """Return ATR as percent of close for each bar. / 返回每根 K 的 ATR 百分比。"""
    if not bars:
        return []

    true_ranges: list[float] = []
    for idx, bar in enumerate(bars):
        if idx == 0:
            tr = bar.high - bar.low
        else:
            prev_close = bars[idx - 1].close
            tr = max(
                bar.high - bar.low,
                abs(bar.high - prev_close),
                abs(bar.low - prev_close),
            )
        true_ranges.append(max(0.0, tr))

    out: list[float | None] = []
    for idx, bar in enumerate(bars):
        if idx + 1 < period or bar.close <= 0:
            out.append(None)
            continue
        atr = sum(true_ranges[idx + 1 - period:idx + 1]) / period
        out.append(atr / bar.close * 100)
    return out


def label_swings_atr(
    bars: list[Bar],
    atr_mult: float = 1.0,
    atr_period: int = 14,
    fallback_pct: float = 2.0,
    min_threshold_pct: float = 2.0,
    min_duration_min: float = 5.0,
) -> list[Wave]:
    """
    Label alternating up/down waves with ATR-adaptive reversal threshold.
    用 ATR 自适应反转阈值标注交替上/下波段；仅供复盘，不直接作为交易信号。
    """
    if len(bars) < 2:
        return []

    atr_pcts = calc_atr_pct(bars, atr_period)

    def threshold_for(idx: int) -> float:
        atr_pct = atr_pcts[idx] if 0 <= idx < len(atr_pcts) else None
        if atr_pct is None:
            return max(min_threshold_pct, fallback_pct)
        return max(min_threshold_pct, atr_pct * atr_mult)

    waves: list[Wave] = []
    trend: str | None = None
    pivot_idx = 0
    pivot_ts = bars[0].ts
    pivot_price = bars[0].open
    extreme_idx = 0
    extreme_ts = pivot_ts
    extreme_price = pivot_price
    extreme_high = bars[0].high
    extreme_low = bars[0].low

    def maybe_add(direction: str, start: datetime, end: datetime, start_price: float,
                  end_price: float, high: float, low: float, th_pct: float) -> None:
        dur_min = max(0.0, (end - start).total_seconds() / 60)
        pct = (end_price - start_price) / start_price * 100 if start_price > 0 else 0.0
        if dur_min < min_duration_min:
            return
        if abs(pct) < th_pct:
            return
        waves.append(Wave(direction, start, end, start_price, end_price, pct, high, low, dur_min, th_pct))

    for idx, bar in enumerate(bars[1:], start=1):
        threshold_pct = threshold_for(idx)
        threshold = threshold_pct / 100.0

        if trend is None:
            if bar.high >= pivot_price * (1 + threshold):
                trend = "up"
                extreme_idx = idx
                extreme_ts = bar.ts
                extreme_price = bar.high
                extreme_high = bar.high
                extreme_low = min(extreme_low, bar.low)
            elif bar.low <= pivot_price * (1 - threshold):
                trend = "down"
                extreme_idx = idx
                extreme_ts = bar.ts
                extreme_price = bar.low
                extreme_low = bar.low
                extreme_high = max(extreme_high, bar.high)
            continue

        if trend == "up":
            if bar.high > extreme_price:
                extreme_idx = idx
                extreme_ts = bar.ts
                extreme_price = bar.high
                extreme_high = bar.high
            extreme_low = min(extreme_low, bar.low)
            if bar.low <= extreme_price * (1 - threshold):
                maybe_add(
                    "up", pivot_ts, extreme_ts, pivot_price, extreme_price,
                    extreme_high, extreme_low, threshold_for(extreme_idx),
                )
                trend = "down"
                pivot_idx = extreme_idx
                pivot_ts = extreme_ts
                pivot_price = extreme_price
                extreme_idx = idx
                extreme_ts = bar.ts
                extreme_price = bar.low
                extreme_low = bar.low
                extreme_high = bar.high
        else:
            if bar.low < extreme_price:
                extreme_idx = idx
                extreme_ts = bar.ts
                extreme_price = bar.low
                extreme_low = bar.low
            extreme_high = max(extreme_high, bar.high)
            if bar.high >= extreme_price * (1 + threshold):
                maybe_add(
                    "down", pivot_ts, extreme_ts, pivot_price, extreme_price,
                    extreme_high, extreme_low, threshold_for(extreme_idx),
                )
                trend = "up"
                pivot_idx = extreme_idx
                pivot_ts = extreme_ts
                pivot_price = extreme_price
                extreme_idx = idx
                extreme_ts = bar.ts
                extreme_price = bar.high
                extreme_high = bar.high
                extreme_low = bar.low

    if trend is not None:
        final_threshold = threshold_for(extreme_idx)
        maybe_add(
            trend, pivot_ts, extreme_ts, pivot_price, extreme_price,
            max(extreme_high, pivot_price, extreme_price),
            min(extreme_low, pivot_price, extreme_price),
            final_threshold,
        )

    return waves
