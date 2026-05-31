# -*- coding: utf-8 -*-
"""
RKLX-only 趋势持有 优化(只读, 近期加权尺子, 不碰生产代码)
─────────────────────────────────────────────────────────
约束: Claude 只交易 RKLX(用 RKLB 判趋势, 买卖 RKLX)。
诊断已确认: 强上行行情最优逼近=少动趋势持有。修复版 churn 已降到真持有(18-27)。
目标: 在 RKLX-only 下扫参数, 用近期加权(decay)找最逼近"躺平RKLX"的稳健配置。
对比基准: 躺平RKLX(收益天花板) / v1.2(旧版)。
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.sim_weekly import indicators as ind
from core.sim_weekly.duel import run_duel, Contestant
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant

RECENT = ["2026-05-18","2026-05-11","2026-05-04","2026-04-27",
          "2026-04-20","2026-04-13","2026-04-06","2026-03-30"]
OUT=[]
def emit(s=""): OUT.append(str(s))


class RklxHold(Contestant):
    """RKLB 判趋势, 持有 RKLX。滞回入场 + 趋势明确破/追踪止损退。"""
    name="rklx_hold"
    def __init__(self, ema_slow=50, enter_dist=0.5, exit_margin=0.015, hold_stop=0.12):
        self.ema_slow=ema_slow; self.enter_dist=enter_dist
        self.exit_margin=exit_margin; self.hold_stop=hold_stop
    def reset(self,cap): pass
    def _ind(self,ctx):
        h=ctx.history["RKLB"]+[ctx.bars_now["RKLB"]]
        if len(h)<self.ema_slow: return None
        c=[b["close"] for b in h]
        es=ind.ema(c[-self.ema_slow-5:],self.ema_slow)
        e9,e21=ind.ema(c[-30:],9),ind.ema(c[-30:],21)
        if None in (es,e9,e21) or es<=0: return None
        return c[-1],es,e9,e21
    def on_bar(self,ctx):
        pf=ctx.portfolio
        held=next(iter(pf.positions)) if pf.positions else None
        info=self._ind(ctx)
        if held:
            pos=pf.positions[held]; bar=ctx.bars_now.get(held)
            if bar:
                pos["peak"]=max(pos.get("peak",pos["cost_price"]),bar["high"])
                trail=round(pos["peak"]*(1-self.hold_stop),4)
                pos["stop"]=trail if pos.get("stop") is None else max(pos["stop"],trail)
                broke=info and info[0]<info[1]*(1-self.exit_margin)
                if bar["low"]<=pos["stop"] or broke or ctx.is_last_bar:
                    pf.sell(held,pos["qty"],
                            pos["stop"] if bar["low"]<=pos["stop"] else (ctx.price(held) or pos["cost_price"]),
                            ctx.ts, reason="stop" if bar["low"]<=pos["stop"] else "broke")
            return
        if not ctx.is_last_bar and info:
            cur,es,e9,e21=info; dist=(cur-es)/es*100
            if e9>e21 and dist>=self.enter_dist:
                px=ctx.price("RKLX")
                if px:
                    q=int(pf.cash/(px*1.001))
                    if q>0:
                        pf.buy("RKLX",q,px,ctx.ts,reason="rklx hold",
                               stop=round(px*(1-self.hold_stop),4))
                        if "RKLX" in pf.positions: pf.positions["RKLX"]["stop_pct"]=self.hold_stop


def rw(bw,wks,decay=0.85):
    n=d=0.0
    for age,wk in enumerate(wks):
        v=bw.get(wk)
        if v is None: continue
        w=decay**age; n+=w*v; d+=w
    return n/d if d else 0.0

def met(name,fac):
    a=run_duel({name:fac},RECENT)["per_contestant"][name]; bw=a.get("by_week",{})
    return dict(w2=rw(bw,RECENT[:2]),w4=rw(bw,RECENT[:4]),w8=rw(bw,RECENT[:8]),
                worst=a.get("worst_week_pct",0),churn=a.get("total_trades",0),bw=bw)

def main():
    emit("=== RKLX-only 趋势持有 参数扫描 (近期加权 decay0.85) ===")
    emit("约束: Claude 只交易 RKLX。基准=躺平RKLX(天花板)。\n")
    rows=[("躺平RKLX(基准)",lambda:BuyHoldContestant("RKLX")),
          ("v1.2旧版(对比)",lambda:ClaudeRuleContestant())]
    for es in (40,50,60):
        for ed in (0.3,0.5,1.0):
            for em in (0.015,0.025):
                for hs in (0.10,0.14):
                    rows.append((f"RKLX es{es}/入{ed}/出{em}/止{int(hs*100)}",
                                 lambda es=es,ed=ed,em=em,hs=hs:RklxHold(es,ed,em,hs)))
    res={}
    for name,fac in rows:
        res[name]=met(name,fac)
    base=res["躺平RKLX(基准)"]
    # 排序: 近4周加权收益降序(只看 RKLX 变体)
    variants=[(n,m) for n,m in res.items() if n.startswith("RKLX")]
    variants.sort(key=lambda x:x[1]["w4"],reverse=True)
    emit(f"{'方案':<26}{'近2周W%':>9}{'近4周W%':>9}{'近8周W%':>9}{'最差周%':>9}{'churn':>7}")
    emit("-"*69)
    for n in ["躺平RKLX(基准)","v1.2旧版(对比)"]:
        m=res[n]; emit(f"{n:<26}{m['w2']:>9.2f}{m['w4']:>9.2f}{m['w8']:>9.2f}{m['worst']:>9.2f}{m['churn']:>7}")
    emit("-"*69)
    for n,m in variants[:12]:
        emit(f"{n:<26}{m['w2']:>9.2f}{m['w4']:>9.2f}{m['w8']:>9.2f}{m['worst']:>9.2f}{m['churn']:>7}")
    # 捕获率: 最优变体近4周 / 躺平RKLX近4周
    if variants:
        best=variants[0]
        cap=best[1]["w4"]/base["w4"]*100 if base["w4"] else 0
        emit(f"\n最优(近4周): {best[0]} = {best[1]['w4']:+.2f}% vs 躺平RKLX {base['w4']:+.2f}% (捕获 {cap:.0f}%)")
        emit("逐周(最近→旧):")
        for wk in RECENT:
            v=best[1]["bw"].get(wk); b=base["bw"].get(wk)
            emit(f"  {wk}: 最优 {v:+.2f}%  躺平RKLX {b:+.2f}%" if v is not None else f"  {wk}: --")
    (ROOT/"research"/"_rklx_hold.txt").write_text("\n".join(OUT),encoding="utf-8")
    print("\n".join(OUT))

if __name__=="__main__":
    main()
