# -*- coding: utf-8 -*-
"""
RKLX 趋势持有 + 浮盈锁定 / 金字塔加仓 A/B(只读, 真实美元口径)
─────────────────────────────────────────────────────────────
学 OpenAI 今晚思路(各自实现): 浮盈锁定改最差周, 金字塔加仓搏更高收益。
baseline = Claude v1.4 生产逻辑(EMA40/入0/破8%/止18%, 只交易RKLX)。
变体:
  LOCK: 浮盈达 lock_trig% → 追踪止损收紧到 tight%(锁住大部分浮盈)
  SCALE: 初始 init_frac 仓, 浮盈达 add_trig% 加仓, 最多 max_adds 次
  BOTH: 两者叠加
度量: 8周协议美元 + 最差周 + churn + 近4周加权。目标: 美元≥baseline 且 最差周改善。
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.sim_weekly import indicators as ind
from core.sim_weekly.duel import run_duel, Contestant
from core.sim_weekly.contestants import BuyHoldContestant

RECENT=['2026-05-18','2026-05-11','2026-05-04','2026-04-27','2026-04-20','2026-04-13','2026-04-06','2026-03-30']
CAP=10000.0
OUT=[]
def emit(s=""): OUT.append(str(s))


class RklxV14(Contestant):
    """复刻 v1.4 + 可选 浮盈锁定 / 金字塔加仓。"""
    name="rklx_v14x"
    def __init__(self, ema_slow=40, enter=0.0, exit_m=0.08, hold_stop=0.18,
                 lock_trig=None, lock_tight=None,        # 浮盈锁定
                 init_frac=1.0, add_trig=None, add_frac=0.30, max_adds=0):  # 加仓
        self.ema_slow=ema_slow; self.enter=enter; self.exit_m=exit_m; self.hold_stop=hold_stop
        self.lock_trig=lock_trig; self.lock_tight=lock_tight
        self.init_frac=init_frac; self.add_trig=add_trig; self.add_frac=add_frac; self.max_adds=max_adds
    def reset(self,cap): self.adds=0
    def _ind(self,ctx):
        h=ctx.history["RKLB"]+[ctx.bars_now["RKLB"]]
        if len(h)<self.ema_slow: return None
        c=[b["close"] for b in h]
        es=ind.ema(c[-self.ema_slow-5:],self.ema_slow); e9,e21=ind.ema(c[-30:],9),ind.ema(c[-30:],21)
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
                stop_pct=self.hold_stop
                # 浮盈锁定: 现价较成本浮盈达标 → 收紧追踪止损
                if self.lock_trig is not None:
                    gain=(bar["high"]-pos["cost_price"])/pos["cost_price"]
                    if gain>=self.lock_trig:
                        stop_pct=self.lock_tight
                trail=round(pos["peak"]*(1-stop_pct),4)
                pos["stop"]=trail if pos.get("stop") is None else max(pos["stop"],trail)
                broke=info and info[0]<info[1]*(1-self.exit_m)
                if bar["low"]<=pos["stop"] or broke or ctx.is_last_bar:
                    pf.sell(held,pos["qty"],pos["stop"] if bar["low"]<=pos["stop"] else (ctx.price(held) or pos["cost_price"]),
                            ctx.ts,reason="lock/stop" if bar["low"]<=pos["stop"] else "broke")
                    return
                # 金字塔加仓: 浮盈达 add_trig 且未满次数 且有现金
                if self.add_trig is not None and self.adds<self.max_adds and pf.cash>0:
                    gain=(bar["close"]-pos["cost_price"])/pos["cost_price"]
                    if gain>=self.add_trig*(self.adds+1):
                        px=ctx.price("RKLX")
                        if px:
                            q=int(pf.cash*self.add_frac/(px*1.001))
                            if q>0:
                                pf.buy("RKLX",q,px,ctx.ts,reason=f"scale-in #{self.adds+1}")
                                self.adds+=1
            return
        if not ctx.is_last_bar and info:
            cur,es,e9,e21=info; dist=(cur-es)/es*100
            if e9>e21 and dist>=self.enter:
                px=ctx.price("RKLX")
                if px:
                    budget=pf.cash*self.init_frac
                    q=int(budget/(px*1.001))
                    if q>0:
                        pf.buy("RKLX",q,px,ctx.ts,reason="rklx hold",stop=round(px*(1-self.hold_stop),4))
                        if "RKLX" in pf.positions: pf.positions["RKLX"]["stop_pct"]=self.hold_stop


def w4(bw,decay=0.85):
    n=d=0.0
    for age,wk in enumerate(RECENT[:4]):
        v=bw.get(wk)
        if v is None: continue
        x=decay**age; n+=x*v; d+=x
    return n/d if d else 0
def d8(bw): return sum(CAP*bw[wk]/100 for wk in RECENT if bw.get(wk) is not None)
def met(fac):
    a=run_duel({'x':fac},RECENT)['per_contestant']['x']; bw=a.get('by_week',{})
    return d8(bw),a['total_trades'],a['worst_week_pct'],w4(bw)

def main():
    bh=met(lambda:BuyHoldContestant('RKLX'))
    emit("=== RKLX +浮盈锁定/加仓 A/B (真实美元) ===")
    emit(f"躺平RKLX: 8周${bh[0]:+.0f} churn{bh[1]} 最差{bh[2]:.1f}% 近4周{bh[3]:.1f}%\n")
    emit(f"{'方案':<30}{'8周$':>9}{'churn':>6}{'最差周%':>9}{'近4周%':>8}")
    emit("-"*62)
    configs=[
        ("baseline v1.4", dict()),
        ("LOCK 浮盈8%→止5%", dict(lock_trig=0.08,lock_tight=0.05)),
        ("LOCK 浮盈12%→止6%", dict(lock_trig=0.12,lock_tight=0.06)),
        ("LOCK 浮盈15%→止8%", dict(lock_trig=0.15,lock_tight=0.08)),
        ("SCALE 初70%+2次@3%", dict(init_frac=0.70,add_trig=0.03,add_frac=0.5,max_adds=2)),
        ("SCALE 初60%+2次@2%", dict(init_frac=0.60,add_trig=0.02,add_frac=0.5,max_adds=2)),
        ("BOTH 锁12/6+加70%", dict(lock_trig=0.12,lock_tight=0.06,init_frac=0.70,add_trig=0.03,add_frac=0.5,max_adds=2)),
    ]
    base_d=None
    for name,kw in configs:
        d,c,wr,w=met(lambda kw=kw:RklxV14(**kw))
        if name.startswith("baseline"): base_d=d
        flag=""
        if base_d is not None and d>=base_d and wr>-20.61: flag=" ← 美元≥base且最差周改善"
        emit(f"{name:<30}{d:>+9.0f}{c:>6}{wr:>9.2f}{w:>8.2f}{flag}")
    emit("\n判据: 8周美元≥baseline 且 最差周 > -20.61%(v1.4) = 真改善。")
    (ROOT/"research"/"_lock_scale.txt").write_text("\n".join(OUT),encoding="utf-8")
    print("\n".join(OUT))

if __name__=="__main__":
    main()
