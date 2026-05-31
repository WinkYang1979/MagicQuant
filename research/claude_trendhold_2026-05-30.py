# -*- coding: utf-8 -*-
"""
Claude 多日趋势持有框架 原型回放(换框架, 非日内进出)
──────────────────────────────────────────────────────
harness 约束: 按周独立回测($10k/周, 周五强平)。所以"多日趋势持有"=
  周内用慢趋势信号选对标的并持有不 churn, 趋势破才走。

诊断光谱(已验证真实数据):
  躺平RKLX +10.29%/最差-17.4% | 躺平RKLB +5.19%/最差-7.02% | v1.2日内 +0.91%/最差-6.8%
目标: 捕获 RKLB 大部分上涨, 砍掉坏周 → 风调 > 躺平RKLB 的 0.50。

原型 TrendHoldContestant:
  每根 bar 用 RKLB 慢趋势(price vs EMA_slow + EMA9>EMA21 + 多日动量)判 regime:
    强上行 → 持有 RKLX(2x) | 温和上行 → 持有 RKLB | 否则 → 空仓(现金)
  宽追踪止损保护; 同 regime 不动(不 churn)。不做空(RKLZ 留作后续)。
评估: 全样本 + 去掉最好一周(反过拟合) + regime 分层。纯研究, 真实 harness 实跑。
"""
import io, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.sim_weekly import indicators as ind
from core.sim_weekly.duel import run_duel, Contestant
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant

WEEKS = ["2025-12-08", "2025-12-22", "2026-01-12", "2026-01-26",
         "2026-02-02", "2026-02-23", "2026-03-09", "2026-03-16",
         "2026-04-27", "2026-05-04", "2026-05-11"]
REGIME = {"2025-12-08":"牛","2026-01-12":"牛","2026-05-04":"牛","2026-05-11":"牛",
          "2025-12-22":"熊","2026-02-02":"熊","2026-03-09":"熊","2026-03-16":"熊",
          "2026-01-26":"震","2026-02-23":"震","2026-04-27":"震"}


class TrendHoldContestant(Contestant):
    """多日趋势持有: 慢信号选标的并持有, 趋势破才走, 不做日内 churn。"""
    name = "trend_hold"

    def __init__(self, ema_slow=50, strong_dist=1.0, mild_dist=0.0,
                 hold_stop=0.10, allow_rklx=True):
        self.ema_slow = ema_slow          # 慢趋势 EMA 周期(根 5m bar; ~50根=多日)
        self.strong_dist = strong_dist    # price 高于 ema_slow 多少% → 强上行(用RKLX)
        self.mild_dist = mild_dist         # price 高于 ema_slow 多少% → 温和上行(用RKLB)
        self.hold_stop = hold_stop
        self.allow_rklx = allow_rklx

    def reset(self, capital):
        pass

    def _regime(self, ctx):
        hist = ctx.history["RKLB"] + [ctx.bars_now["RKLB"]]
        if len(hist) < self.ema_slow:
            return None
        closes = [b["close"] for b in hist]
        e_slow = ind.ema(closes[-self.ema_slow-5:], self.ema_slow)
        e9, e21 = ind.ema(closes[-30:], 9), ind.ema(closes[-30:], 21)
        if None in (e_slow, e9, e21) or e_slow <= 0:
            return None
        cur = closes[-1]
        dist = (cur - e_slow) / e_slow * 100
        up_struct = e9 > e21 and cur > e_slow
        if up_struct and dist >= self.strong_dist and self.allow_rklx:
            return "RKLX"
        if up_struct and dist >= self.mild_dist:
            return "RKLB"
        return None  # 空仓

    def on_bar(self, ctx):
        pf = ctx.portfolio
        target = None if ctx.is_last_bar else self._regime(ctx)
        held = next(iter(pf.positions)) if pf.positions else None

        # 趋势破 / 换标的 → 平当前
        if held and held != target:
            pf.sell(held, pf.positions[held]["qty"],
                    ctx.price(held) or pf.positions[held]["cost_price"], ctx.ts,
                    reason="trend exit" if target is None else "trend switch")
            held = None

        # 有目标且空仓 → 满仓买入持有
        if target and held is None and not ctx.is_last_bar:
            px = ctx.price(target)
            if px:
                qty = int(pf.cash / (px * 1.001))
                if qty > 0:
                    pf.buy(target, qty, px, ctx.ts, reason=f"trend hold {target}",
                           stop=round(px * (1 - self.hold_stop), 4))
                    if target in pf.positions:
                        pf.positions[target]["stop_pct"] = self.hold_stop

        # 宽追踪止损
        for tk in list(pf.positions.keys()):
            pos = pf.positions[tk]; bar = ctx.bars_now.get(tk)
            if not bar:
                continue
            pos["peak"] = max(pos.get("peak", pos["cost_price"]), bar["high"])
            trail = round(pos["peak"] * (1 - self.hold_stop), 4)
            pos["stop"] = trail if pos.get("stop") is None else max(pos["stop"], trail)
            if bar["low"] <= pos["stop"]:
                pf.sell(tk, pos["qty"], pos["stop"], ctx.ts, reason="hold trail stop")


def metrics(name, fac):
    a = run_duel({name: fac}, WEEKS)["per_contestant"][name]
    dd = abs(a.get("avg_max_dd_pct", 0)) or 0.01
    bw = a.get("by_week", {})
    vals = [v for v in bw.values() if v is not None]
    loo = (sum(vals) - max(vals)) / (len(vals) - 1) if len(vals) > 1 else 0
    return dict(avg=a["avg_return_pct"], ra=a["avg_return_pct"]/dd, worst=a["worst_week_pct"],
                loo=loo, tr=a["total_trades"], beat=a["beat_buyhold_weeks"], w=a["weeks"], bw=bw)


def main():
    print(f"=== Claude 多日趋势持有框架 · {len(WEEKS)}周 真实 harness 实跑 ===\n")
    rows = []
    rows.append(("躺平RKLB(基准)", metrics("bh", lambda: BuyHoldContestant("RKLB"))))
    rows.append(("躺平RKLX", metrics("bx", lambda: BuyHoldContestant("RKLX"))))
    rows.append(("v1.2 日内", metrics("v12", lambda: ClaudeRuleContestant())))
    # 趋势持有多档
    for es in (40, 50, 60):
        for sd in (0.5, 1.0, 2.0):
            for hs in (0.08, 0.12):
                tag = f"趋势持有 ema{es}/强{sd}%/stop{int(hs*100)}"
                rows.append((tag, metrics(tag, lambda es=es,sd=sd,hs=hs: TrendHoldContestant(es, sd, 0.0, hs))))

    hdr = f"{'方案':<30}{'均%':>7}{'风调':>6}{'最差%':>7}{'去最好周':>9}{'churn':>6}{'胜RKLB':>7}"
    print(hdr); print("-"*len(hdr))
    for name, m in rows:
        print(f"{name:<30}{m['avg']:>7.2f}{m['ra']:>6.2f}{m['worst']:>7.2f}{m['loo']:>9.2f}{m['tr']:>6}{m['beat']:>4}/{m['w']:<2}")

    # 找出: 盈利 且 去掉最好周仍 > v1.2 的 loo(0.x) 且 风调 > 躺平RKLB(0.50)
    v12 = next(m for n,m in rows if n=="v1.2 日内")
    bh = next(m for n,m in rows if n.startswith("躺平RKLB"))
    print(f"\n判据: 去掉最好周>0(稳健盈利) 且 风调>躺平RKLB({bh['ra']:.2f})")
    winners = [(n,m) for n,m in rows if "趋势持有" in n and m["loo"]>0 and m["ra"]>bh["ra"]]
    if winners:
        winners.sort(key=lambda x: x[1]["ra"], reverse=True)
        print(f"  达标方案 {len(winners)} 个, 最优: {winners[0][0]} 风调{winners[0][1]['ra']:.2f}")
        bm = winners[0][1]
        for w in WEEKS:
            v = bm["bw"].get(w); print(f"    {w}({REGIME[w]}): {v:+.2f}%" if v is not None else "")
    else:
        print("  ⚠️ 无方案同时满足'去最好周>0'和'风调>躺平RKLB' — 趋势持有框架在此数据上也未跑赢基准。")


if __name__ == "__main__":
    main()
