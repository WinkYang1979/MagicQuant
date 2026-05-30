"""SimWeekly 决策策略 v1.1 —— 自包含规则版(进取,但抗横跳)。

输出**方向**(long/short/flat)+ 表达工具 + 信念 + 止损带。
engine 据此做"持有/翻转/进场",同方向不切工具、不因信念抖动平仓(让赢家跑)。
后续可用 deciders.AgentCommitteeDecider 替换,接口一致。

decide(ctx) -> {"direction","instrument","conviction","stop_pct","reason"}
  direction: "long"/"short"/"flat"
  instrument: "RKLB"/"RKLX"/"RKLZ"/None
"""
from __future__ import annotations

from typing import List

from . import indicators as ind

STOP_PCT = {"RKLB": 0.025, "RKLX": 0.045, "RKLZ": 0.045}
RKLX_CONV = 82      # 多头信念 >= 此值用 2x 工具 RKLX,否则 RKLB
SHORT_RSI_FLOOR = 38  # 超卖不追空:RKLB RSI < 38 时禁做空(移植主策略血泪教训,
                      # 05-29 复盘:rsi26/29/33/37 四笔做空全亏,反弹打脸)


def _rsi_slope(closes: List[float]) -> float | None:
    """Recent RSI slope for confidence honesty. / 近期 RSI 斜率，用于置信度诚实降级。"""
    try:
        if len(closes) < 45:
            return None
        vals = []
        for end in (-3, -2, -1):
            vals.append(ind.rsi(closes[:end] if end != -1 else closes, 14))
        if any(v is None for v in vals):
            return None
        return float(vals[-1]) - float(vals[0])
    except Exception:
        return None


def _conviction(gap_atr: float, rsi: float, dist_vwap_pct: float, up: bool,
                rsi_slope: float | None = None) -> int:
    score = 50
    score += min(25, gap_atr * 25)
    score += min(15, abs(dist_vwap_pct) * 5)
    if up:
        if 55 <= rsi <= 70:
            if not (rsi_slope is not None and rsi_slope < -2):
                score += 10
        elif rsi > 75:        score -= 15
    else:
        if 30 <= rsi <= 45:
            if not (rsi_slope is not None and rsi_slope > 2):
                score += 10
        elif rsi < 25:        score -= 15
    return int(max(0, min(100, score)))


def decide(ctx: dict) -> dict:
    bars: List[dict] = ctx["rklb_bars"]
    today_bars: List[dict] = ctx["rklb_today_bars"]
    flat = {"direction": "flat", "instrument": None, "conviction": 0, "stop_pct": 0.0, "reason": "no-setup"}
    if len(bars) < 25:
        return {**flat, "reason": "warmup"}

    closes = [float(b["close"]) for b in bars]
    e9, e21 = ind.ema(closes[-30:], 9), ind.ema(closes[-30:], 21)
    rsi = ind.rsi(closes[-40:], 14)
    a = ind.atr(bars[-30:], 14)
    vwap = ind.session_vwap(today_bars) if today_bars else None
    price = closes[-1]
    if None in (e9, e21, rsi, a, vwap) or a <= 0 or price <= 0:
        return {**flat, "reason": "indicators-na"}

    gap_atr = abs(e9 - e21) / a
    dist_vwap_pct = (price - vwap) / vwap * 100
    rsi_delta = _rsi_slope(closes)

    # 强趋势(ema 间距 >= 1 个 ATR)放宽止损带,别被正常回踩洗出去(让赢家跑)
    strong = gap_atr >= 1.0

    def _stop(inst):
        base = STOP_PCT[inst]
        return round(min(base * 1.8, 0.09), 4) if strong else base

    if e9 > e21 and price > vwap and 50 <= rsi <= 75:
        conv = _conviction(gap_atr, rsi, dist_vwap_pct, up=True, rsi_slope=rsi_delta)
        inst = "RKLX" if conv >= RKLX_CONV else "RKLB"
        return {"direction": "long", "instrument": inst, "conviction": conv,
                "stop_pct": _stop(inst), "strong": strong,
                "reason": f"5m up e9>e21 px>vwap rsi{rsi:.0f} gapATR{gap_atr:.1f}{' STRONG' if strong else ''}"}
    # 超卖做空 regime 化:RSI<38 时,仅"强下跌延续"(gapATR>=1)才允许追空;
    # 震荡/弱势里超卖做空=追 RKLZ 进反弹被打(05-29 四笔全亏的根因)。
    # 强下跌里超卖继续跌(02-02),该放行。
    short_ok = e9 < e21 and price < vwap and rsi <= 50 and (rsi >= SHORT_RSI_FLOOR or strong)
    if short_ok:
        conv = _conviction(gap_atr, rsi, dist_vwap_pct, up=False, rsi_slope=rsi_delta)
        return {"direction": "short", "instrument": "RKLZ", "conviction": conv,
                "stop_pct": _stop("RKLZ"), "strong": strong,
                "reason": f"5m down e9<e21 px<vwap rsi{rsi:.0f} gapATR{gap_atr:.1f}{' STRONG' if strong else ''}"}
    return flat
