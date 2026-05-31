# -*- coding: utf-8 -*-
"""
RKLX 趋势持有 — 偏向躺平(收益优先)参数搜索（只读, 美元口径 + 近期加权）
─────────────────────────────────────────────────────────────────
方向(用户定): 趋势持有 + 偏向躺平。尽量逼近躺平RKLX收益, 出场尽量宽。
做法: 低 enter_dist(早进) + 宽 exit_margin/hold_stop(几乎不出) → 最大化捕获率。
度量: 近2/4/8周加权% + 8周协议美元 + 捕获率(vs 躺平RKLX) + churn + 最差周。
找"捕获率最高且 churn 仍受控(真持有)"的配置。
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.sim_weekly import indicators as ind
from core.sim_weekly.duel import run_duel, Contestant
from core.sim_weekly.contestants import BuyHoldContestant

RECENT = ["2026-05-18","2026-05-11","2026-05-04","2026-04-27",
          "2026-04-20","2026-04-13","2026-04-06","2026-03-30"]
CAP=10000.0
OUT=[]
def emit(s=""): OUT.append(str(s))


class RklxHold(Contestant):
    name="rklx_hold"
    def __init__(self, ema_slow=40, enter_dist=0.3, exit_margin=0.025, hold_stop=0.14):
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

def dollars8(bw):
    return sum(CAP*(bw[w]/100.0) for w in RECENT if bw.get(w) is not None)

def met(name,fac):
    a=run_duel({name:fac},RECENT)["per_contestant"][name]; bw=a.get("by_week",{})
    return dict(w2=rw(bw,RECENT[:2]),w4=rw(bw,RECENT[:4]),w8=rw(bw,RECENT[:8]),
                d8=dollars8(bw),worst=a.get("worst_week_pct",0),churn=a.get("total_trades",0),bw=bw)

def main():
    base=met("躺平RKLX",lambda:BuyHoldContestant("RKLX"))
    emit("=== RKLX 趋势持有 偏躺平搜索 (收益优先, 美元口径) ===")
    emit(f"基准 躺平RKLX: 近4周W {base['w4']:+.2f}% | 8周协议 ${base['d8']:+.0f} | 最差周 {base['worst']:.1f}% | churn {base['churn']}\n")
    emit(f"{'方案':<28}{'近2周%':>8}{'近4周%':>8}{'8周$':>9}{'捕获%':>7}{'最差周%':>8}{'churn':>6}")
    emit("-"*74)
    # 偏躺平: 低 enter(0.0~0.3) × 宽 exit(0.03~0.06) × 宽 stop(0.14~0.20)
    rows=[]
    for ed in (0.0,0.2,0.3):
        for em in (0.03,0.05,0.08):
            for hs in (0.14,0.18):
                m=met("v",lambda ed=ed,em=em,hs=hs:RklxHold(40,ed,em,hs))
                cap=m['d8']/base['d8']*100 if base['d8'] else 0
                rows.append((ed,em,hs,m,cap))
    rows.sort(key=lambda r:r[3]['d8'],reverse=True)
    for ed,em,hs,m,cap in rows:
        emit(f"{'入'+str(ed)+'/破'+str(em)+'/止'+str(int(hs*100)):<28}{m['w2']:>8.2f}{m['w4']:>8.2f}{m['d8']:>9.0f}{cap:>7.0f}{m['worst']:>8.2f}{m['churn']:>6}")
    best=rows[0]
    emit(f"\n最高8周美元: 入{best[0]}/破{best[1]}/止{int(best[2]*100)} = ${best[3]['d8']:+.0f} (躺平的{best[4]:.0f}%) churn{best[3]['churn']}")
    emit("逐周$ (最近→旧, 每周$10k):")
    for wk in RECENT:
        v=best[3]['bw'].get(wk); b=base['bw'].get(wk)
        if v is not None:
            emit(f"  {wk}: 最优 ${CAP*v/100:+.0f}  躺平 ${CAP*b/100:+.0f}")
    (ROOT/"research"/"_rklx_lean.txt").write_text("\n".join(OUT),encoding="utf-8")
    print("\n".join(OUT))

if __name__=="__main__":
    main()
