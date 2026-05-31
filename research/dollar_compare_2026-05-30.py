# -*- coding: utf-8 -*-
"""
真实美元收益对比(只读, 不碰策略代码)
──────────────────────────────────────
用户: 要看赚多少钱, 不是数值。比较 2/4/8 周 累计美元收益。
两种口径:
  A. duel协议(每周一重置$10k): 累计 = Σ($10k × 周收益%)  ← 比赛实际口径
  B. 复利(让$10k一直滚): 终值 = $10k × Π(1+周收益%)       ← 真账户视角
对象: 躺平RKLX(只允许的标的基准) / v1.2旧版 / RKLX趋势持有最优(es40/入0.3/出0.025/止14)
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
CAP = 10000.0
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


def get_bw(name, fac):
    a=run_duel({name:fac},RECENT)["per_contestant"][name]
    return a.get("by_week",{})


def dollars(bw, n):
    """返回 (按协议累加$, 复利终值$, 复利净赚$)"""
    wks=RECENT[:n]
    reset_sum=0.0; comp=CAP
    for wk in wks:
        v=bw.get(wk)
        if v is None: continue
        reset_sum += CAP*(v/100.0)
        comp *= (1+v/100.0)
    return reset_sum, comp, comp-CAP


def main():
    emit("=== 真实美元收益对比($10k本金, 近期整周) ===")
    emit(f"周: {RECENT}\n")
    players=[
        ("躺平RKLX(基准)", lambda:BuyHoldContestant("RKLX")),
        ("RKLX趋势持有(最优)", lambda:RklxHold(40,0.3,0.025,0.14)),
        ("v1.2旧版(对比)", lambda:ClaudeRuleContestant()),
    ]
    bws={n:get_bw(n,f) for n,f in players}

    for n in (2,4,8):
        emit(f"--- 近{n}周 ---")
        emit(f"{'选手':<22}{'协议累加$':>12}{'复利终值$':>12}{'复利净赚$':>12}")
        for name,_ in players:
            rs,comp,net=dollars(bws[name],n)
            emit(f"{name:<22}{rs:>+12.0f}{comp:>12.0f}{net:>+12.0f}")
        emit("")

    # 逐周美元(协议口径, 每周$10k)
    emit("--- 逐周美元盈亏(每周$10k本金, 协议口径) ---")
    emit(f"{'周':<12}" + "".join(f"{n[:14]:>16}" for n,_ in players))
    for wk in RECENT:
        row=f"{wk:<12}"
        for name,_ in players:
            v=bws[name].get(wk)
            row += f"{(f'{CAP*v/100:+.0f}' if v is not None else '--'):>16}"
        emit(row)

    emit("\n说明:")
    emit("  协议累加$ = Σ($10k×周收益%) — duel 每周一重置$10k, 这是比赛实际口径")
    emit("  复利终值$ = $10k 一直滚 — 真账户视角(若不重置)")
    emit("  数据=真实 harness 实跑; RKLX趋势持有=es40/入0.3/出0.025/止14(近4周最优)")

    (ROOT/"research"/"_dollar_compare.txt").write_text("\n".join(OUT),encoding="utf-8")
    print("\n".join(OUT))


if __name__=="__main__":
    main()
