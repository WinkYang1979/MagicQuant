# -*- coding: utf-8 -*-
"""
Claude 选手策略 A/B(自包含,显式定义各 decide 变体,不依赖磁盘当前 strat.decide)
─────────────────────────────────────────────────────────────────────────
对比维度:做多上限(long_max)、做空下限(short_min)、强趋势是否豁免做空下限(strong_exempt)。
当前已落地 40800ae = 长75 / 短38 / strong豁免=True。
跨 11 周(8周冻结集+3近期, 跨牛/熊/震荡)出中立记分板。
"""
import io, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.sim_weekly import strategy as strat
from core.sim_weekly import indicators as ind
from core.sim_weekly.duel import run_duel
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant

WEEKS = ["2025-12-08", "2025-12-22", "2026-01-12", "2026-01-26",
         "2026-02-02", "2026-02-23", "2026-03-09", "2026-03-16",
         "2026-04-27", "2026-05-04", "2026-05-11"]


def make_decide(long_max, short_min, strong_exempt):
    def decide(ctx):
        bars = ctx["rklb_bars"]; today = ctx["rklb_today_bars"]
        flat = {"direction":"flat","instrument":None,"conviction":0,"stop_pct":0.0,"reason":"no-setup"}
        if len(bars) < 25:
            return {**flat,"reason":"warmup"}
        closes = [float(b["close"]) for b in bars]
        e9,e21 = ind.ema(closes[-30:],9), ind.ema(closes[-30:],21)
        rsi = ind.rsi(closes[-40:],14); a = ind.atr(bars[-30:],14)
        vwap = ind.session_vwap(today) if today else None
        price = closes[-1]
        if None in (e9,e21,rsi,a,vwap) or a<=0 or price<=0:
            return {**flat,"reason":"indicators-na"}
        gap_atr = abs(e9-e21)/a; dist = (price-vwap)/vwap*100
        slope = strat._rsi_slope(closes); strong = gap_atr >= 1.0
        def _stop(inst):
            base = strat.STOP_PCT[inst]
            return round(min(base*1.8,0.09),4) if strong else base
        if e9>e21 and price>vwap and 50<=rsi<=long_max:
            conv = strat._conviction(gap_atr,rsi,dist,up=True,rsi_slope=slope)
            inst = "RKLX" if conv>=strat.RKLX_CONV else "RKLB"
            return {"direction":"long","instrument":inst,"conviction":conv,"stop_pct":_stop(inst),
                    "strong":strong,"reason":f"5m up rsi{rsi:.0f}"}
        short_ok = e9<e21 and price<vwap and rsi<=50 and (rsi>=short_min or (strong_exempt and strong))
        if short_ok:
            conv = strat._conviction(gap_atr,rsi,dist,up=False,rsi_slope=slope)
            return {"direction":"short","instrument":"RKLZ","conviction":conv,"stop_pct":_stop("RKLZ"),
                    "strong":strong,"reason":f"5m down rsi{rsi:.0f}"}
        return flat
    return decide


def run(label, decide_fn):
    strat.decide = decide_fn
    out = run_duel({"claude_rule": lambda: ClaudeRuleContestant(),
                    "buyhold_RKLB": lambda: BuyHoldContestant("RKLB")}, WEEKS)
    a = out["per_contestant"]["claude_rule"]
    dd = abs(a.get("avg_max_dd_pct",0.0)) or 0.01
    return {"label":label,"avg":a.get("avg_return_pct",0),"median":a.get("median_return_pct",0),
            "ra":a.get("avg_return_pct",0)/dd,"worst":a.get("worst_week_pct",0),
            "pos":a.get("positive_weeks",0),"beat":a.get("beat_buyhold_weeks",0),
            "w":a.get("weeks",0),"dd":a.get("avg_max_dd_pct",0),"tr":a.get("total_trades",0)}


def main():
    print(f"=== Claude 策略 A/B · {len(WEEKS)} 周(冻结集+近期, 跨regime)===\n")
    cfgs = [
        ("baseline 长75/短25",            make_decide(75, 25, False)),
        ("40800ae 长75/短38+豁免",        make_decide(75, 38, True)),
        ("长75/短38无豁免",               make_decide(75, 38, False)),
        ("长72/短38+豁免",                make_decide(72, 38, True)),
        ("长72/短38无豁免",               make_decide(72, 38, False)),
        ("长72/短40无豁免",               make_decide(72, 40, False)),
    ]
    res = [run(l,f) for l,f in cfgs]
    strat.decide = make_decide(75,25,False)

    hdr = f"{'方案':<22}{'均收益%':>9}{'中位%':>8}{'风调':>7}{'最差周%':>9}{'正收益':>7}{'胜躺平':>7}{'回撤%':>8}{'交易':>6}"
    print(hdr); print("-"*len(hdr))
    for r in res:
        print(f"{r['label']:<22}{r['avg']:>9.2f}{r['median']:>8.2f}{r['ra']:>7.2f}{r['worst']:>9.2f}"
              f"{r['pos']:>4}/{r['w']:<2}{r['beat']:>4}/{r['w']:<2}{r['dd']:>8.2f}{r['tr']:>6}")
    print("\n注: 风调=均收益/|均回撤|; 胜躺平=跑赢买入持有RKLB周数。")
    print("豁免=强趋势(gapATR>=1)时即便 RSI<下限仍允许做空(趋势延续)。")


if __name__ == "__main__":
    main()
