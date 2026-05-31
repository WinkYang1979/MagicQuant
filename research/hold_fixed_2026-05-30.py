# -*- coding: utf-8 -*-
"""
修复版"真正持有"原型 + 近期加权验证(只读, 验证达标才动生产代码)
──────────────────────────────────────────────────────────────
churn 根因(已诊断): 三状态边界震荡 + RKLX<->RKLB 微切换 + 瞬断退场 → 每周切换 47-52 次。
修复: 滞回带 + 入场后不换标的 + 仅趋势明确破(price < EMA_slow*(1-exit_margin))或追踪止损才退。
目标: churn 降到个位数/周 且 近期加权收益逼近躺平 RKLB。
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.sim_weekly import indicators as ind
from core.sim_weekly.duel import run_duel, Contestant
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant

RECENT_WEEKS = ["2026-05-18","2026-05-11","2026-05-04","2026-04-27",
                "2026-04-20","2026-04-13","2026-04-06","2026-03-30"]
OUT=[]
def emit(s=""): OUT.append(str(s))


class HoldFixedContestant(Contestant):
    """真正持有: 滞回入场, 入场后不换标的, 仅趋势明确破/追踪止损才退。"""
    name = "hold_fixed"
    def __init__(self, ema_slow=50, enter_dist=1.0, exit_margin=0.02,
                 hold_stop=0.12, ride="RKLX"):
        self.ema_slow=ema_slow; self.enter_dist=enter_dist
        self.exit_margin=exit_margin; self.hold_stop=hold_stop; self.ride=ride
    def reset(self, capital): pass

    def _ind(self, ctx):
        hist=ctx.history["RKLB"]+[ctx.bars_now["RKLB"]]
        if len(hist)<self.ema_slow: return None
        closes=[b["close"] for b in hist]
        e_slow=ind.ema(closes[-self.ema_slow-5:], self.ema_slow)
        e9,e21=ind.ema(closes[-30:],9),ind.ema(closes[-30:],21)
        if None in (e_slow,e9,e21) or e_slow<=0: return None
        return closes[-1], e_slow, e9, e21

    def on_bar(self, ctx):
        pf=ctx.portfolio
        held = next(iter(pf.positions)) if pf.positions else None
        info=self._ind(ctx)

        # 持仓中: 只在趋势明确破 或 追踪止损 才退(滞回: 不因 dist 微动换)
        if held:
            pos=pf.positions[held]; bar=ctx.bars_now.get(held)
            if bar:
                pos["peak"]=max(pos.get("peak",pos["cost_price"]),bar["high"])
                trail=round(pos["peak"]*(1-self.hold_stop),4)
                pos["stop"]=trail if pos.get("stop") is None else max(pos["stop"],trail)
                # 趋势明确破: price 跌破 EMA_slow*(1-exit_margin)
                broke = info and info[0] < info[1]*(1-self.exit_margin)
                if bar["low"]<=pos["stop"] or broke or ctx.is_last_bar:
                    pf.sell(held,pos["qty"],
                            pos["stop"] if bar["low"]<=pos["stop"] else (ctx.price(held) or pos["cost_price"]),
                            ctx.ts, reason="hold stop" if bar["low"]<=pos["stop"] else "trend broke")
            return

        # 空仓: 滞回入场 — 需 e9>e21 且 price 高于 EMA_slow 达 enter_dist%
        if not ctx.is_last_bar and info:
            cur,e_slow,e9,e21=info
            dist=(cur-e_slow)/e_slow*100
            if e9>e21 and dist>=self.enter_dist:
                px=ctx.price(self.ride)
                if px:
                    qty=int(pf.cash/(px*1.001))
                    if qty>0:
                        pf.buy(self.ride,qty,px,ctx.ts,reason=f"hold enter {self.ride}",
                               stop=round(px*(1-self.hold_stop),4))
                        if self.ride in pf.positions:
                            pf.positions[self.ride]["stop_pct"]=self.hold_stop


def recency_w(bw, weeks, decay=0.85):
    num=den=0.0
    for age,wk in enumerate(weeks):
        v=bw.get(wk)
        if v is None: continue
        w=decay**age; num+=w*v; den+=w
    return num/den if den else 0.0

def metrics(name, fac):
    a=run_duel({name:fac},RECENT_WEEKS)["per_contestant"][name]
    bw=a.get("by_week",{})
    return dict(w2=recency_w(bw,RECENT_WEEKS[:2]), w4=recency_w(bw,RECENT_WEEKS[:4]),
                w8=recency_w(bw,RECENT_WEEKS[:8]), worst=a.get("worst_week_pct",0),
                churn=a.get("total_trades",0), bw=bw)

def main():
    emit("=== 修复版持有 vs 躺平 vs v1.2 (近期加权, decay0.85) ===\n")
    rows=[("躺平RKLB",lambda:BuyHoldContestant("RKLB")),
          ("躺平RKLX",lambda:BuyHoldContestant("RKLX")),
          ("v1.2日内",lambda:ClaudeRuleContestant())]
    # 修复版多档
    for ride in ("RKLX","RKLB"):
        for ed in (0.5,1.0):
            for em in (0.015,0.03):
                rows.append((f"修复持有 {ride}/入{ed}/出{em}",
                             lambda ride=ride,ed=ed,em=em:HoldFixedContestant(50,ed,em,0.12,ride)))
    emit(f"{'方案':<24}{'近2周W%':>9}{'近4周W%':>9}{'近8周W%':>9}{'最差周%':>9}{'churn':>7}")
    emit("-"*67)
    res={}
    for name,fac in rows:
        m=metrics(name,fac); res[name]=m
        emit(f"{name:<24}{m['w2']:>9.2f}{m['w4']:>9.2f}{m['w8']:>9.2f}{m['worst']:>9.2f}{m['churn']:>7}")
    # churn/周
    emit(f"\nchurn/周参考: 躺平≈{res['躺平RKLB']['churn']/8:.1f} | 目标修复版应接近(真持有)")
    (ROOT/"research"/"_hold_fixed.txt").write_text("\n".join(OUT),encoding="utf-8")
    print("\n".join(OUT))

if __name__=="__main__":
    main()
