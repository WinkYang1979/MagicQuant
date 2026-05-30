"""SimWeekly 决策策略 v1.2 —— 自包含规则版(进取,抗横跳,拐点过滤)。

输出**方向**(long/short/flat)+ 表达工具 + 信念 + 止损带。
engine 据此做"持有/翻转/进场",同方向不切工具、不因信念抖动平仓(让赢家跑)。
后续可用 deciders.AgentCommitteeDecider 替换,接口一致。

v1.2 (2026-05-30): RSI 拐点过滤 —— 做多上限 75→72(不追过热波峰)、
  做空下限 25→40 硬下限(不空在超卖波谷)。根因: 震荡日策略在 RSI 极值
  逆袭被反转打脸(5-29 两笔超卖做空 RSI33/37 占当日亏损 88%)。
  11 周冻结集+近期回放(6方案A/B, 跨牛/熊/震荡): 均收益 -0.09%→+0.91%、
  风调 -0.01→+0.15、最差周 -11.71%→-6.75%、churn 142→121。
  不设 strong 趋势豁免(A/B 证明豁免会放回亏损的超卖趋势单, 风调反降)。

decide(ctx) -> {"direction","instrument","conviction","stop_pct","reason"}
  direction: "long"/"short"/"flat"
  instrument: "RKLB"/"RKLX"/"RKLZ"/None
"""
from __future__ import annotations

from typing import List

from . import indicators as ind

STOP_PCT = {"RKLB": 0.025, "RKLX": 0.045, "RKLZ": 0.045}
RKLX_CONV = 82       # 多头信念 >= 此值用 2x 工具 RKLX,否则 RKLB
LONG_RSI_MAX = 72    # v1.2: 做多 RSI 上限,高于此不追多(过热波峰)
SHORT_RSI_MIN = 40   # v1.2: 做空 RSI 下限,低于此不追空(超卖波谷,无 strong 豁免)


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

    # v1.2 拐点过滤: 做多不追过热(rsi<=72)、做空不空超卖(rsi>=40, 硬下限无豁免)
    if e9 > e21 and price > vwap and 50 <= rsi <= LONG_RSI_MAX:
        conv = _conviction(gap_atr, rsi, dist_vwap_pct, up=True, rsi_slope=rsi_delta)
        inst = "RKLX" if conv >= RKLX_CONV else "RKLB"
        return {"direction": "long", "instrument": inst, "conviction": conv,
                "stop_pct": _stop(inst), "strong": strong,
                "reason": f"5m up e9>e21 px>vwap rsi{rsi:.0f} gapATR{gap_atr:.1f}{' STRONG' if strong else ''}"}
    if e9 < e21 and price < vwap and SHORT_RSI_MIN <= rsi <= 50:
        conv = _conviction(gap_atr, rsi, dist_vwap_pct, up=False, rsi_slope=rsi_delta)
        return {"direction": "short", "instrument": "RKLZ", "conviction": conv,
                "stop_pct": _stop("RKLZ"), "strong": strong,
                "reason": f"5m down e9<e21 px<vwap rsi{rsi:.0f} gapATR{gap_atr:.1f}{' STRONG' if strong else ''}"}
    return flat
