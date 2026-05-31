# -*- coding: utf-8 -*-
"""
Claude regime-持有挡 原型回放
─────────────────────────────
诊断: 纯日内框架在上涨行情有天花板(调参极限 +1.30% vs 躺平RKLB +5.19%)。
出路: 趋势强的周转"持有挡"——吃 beta 不频繁进出; 弱/震荡周才日内择时。

原型: 子类化 ClaudeRuleContestant, 仅加一层 regime 门:
  每根 bar 判周趋势(RKLB 当周累计涨幅 + EMA 多头排列):
    - 强上行 → 持有挡: 满仓 RKLX 持有, 仅用宽追踪止损保护, 不做日内进出
    - 否则 → 退回原 v1.2 日内逻辑
分批止盈用追踪止损近似(让赢家跑+回撤才出)。
不改 baseline; 纯研究, 对比多档 regime 阈值。
"""
import io, sys, json
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
REGIME = {"2025-12-08":"牛","2026-01-12":"牛","2026-05-04":"牛","2026-05-11":"牛",
          "2025-12-22":"熊","2026-02-02":"熊","2026-03-09":"熊","2026-03-16":"熊",
          "2026-01-26":"震","2026-02-23":"震","2026-04-27":"震"}


class RegimeHoldContestant(ClaudeRuleContestant):
    """趋势强 → 持有 RKLX 骑趋势; 否则退回日内 v1.2。"""
    name = "claude_regime"

    def __init__(self, week_trend_pct=3.0, hold_stop_pct=0.10, ride_inst="RKLX", cfg=None):
        super().__init__(cfg)
        self.week_trend_pct = week_trend_pct   # 当周 RKLB 累计涨幅阈值
        self.hold_stop_pct = hold_stop_pct     # 持有挡宽追踪止损
        self.ride_inst = ride_inst
        self._week_open = None

    def reset(self, capital):
        super().reset(capital)
        self._week_open = None

    def _is_strong_uptrend(self, ctx):
        hist = ctx.history["RKLB"] + [ctx.bars_now["RKLB"]]
        if len(hist) < 25:
            return False
        if self._week_open is None:
            self._week_open = hist[0]["close"]
        cur = hist[-1]["close"]
        week_chg = (cur - self._week_open) / self._week_open * 100
        closes = [b["close"] for b in hist]
        e9, e21 = ind.ema(closes[-30:], 9), ind.ema(closes[-30:], 21)
        if e9 is None or e21 is None:
            return False
        # 强上行: 当周涨幅达阈值 且 EMA 多头排列 且 价在 e9 上方
        return week_chg >= self.week_trend_pct and e9 > e21 and cur >= e9

    def on_bar(self, ctx):
        pf = ctx.portfolio
        if self._is_strong_uptrend(ctx) and not ctx.is_last_bar:
            inst = self.ride_inst
            px = ctx.price(inst)
            held = self._held(pf)
            # 持有挡: 若空仓 → 满仓买入骑趋势; 若已持有 → 只更新宽追踪止损
            if held is None and px:
                # 先平掉非 ride 持仓(如 RKLZ 空头)
                for tk in list(pf.positions.keys()):
                    if tk != inst:
                        pf.sell(tk, pf.positions[tk]["qty"], ctx.price(tk) or pf.positions[tk]["cost_price"],
                                ctx.ts, reason="regime flip to hold")
                qty = int(pf.cash / (px * 1.001))
                if qty > 0:
                    pf.buy(inst, qty, px, ctx.ts, reason=f"regime hold ride {inst}",
                           stop=round(px * (1 - self.hold_stop_pct), 4))
                    if inst in pf.positions:
                        pf.positions[inst]["stop_pct"] = self.hold_stop_pct
            # 宽追踪止损(吃趋势, 回撤才出)
            for tk in list(pf.positions.keys()):
                pos = pf.positions[tk]; bar = ctx.bars_now.get(tk)
                if not bar: continue
                pos["peak"] = max(pos.get("peak", pos["cost_price"]), bar["high"])
                trail = round(pos["peak"] * (1 - self.hold_stop_pct), 4)
                pos["stop"] = trail if pos.get("stop") is None else max(pos["stop"], trail)
                if bar["low"] <= pos["stop"]:
                    pf.sell(tk, pos["qty"], pos["stop"], ctx.ts, reason="hold trail stop")
            return
        # 非强上行 → 原 v1.2 日内逻辑
        super().on_bar(ctx)


def agg(out, name):
    a = out["per_contestant"][name]; dd = abs(a.get("avg_max_dd_pct",0)) or 0.01
    return a, a["avg_return_pct"]/dd


def main():
    # rklxC70 安全增量先生效
    strat.RKLX_CONV = 70
    bh = run_duel({"buyhold_RKLB":lambda:BuyHoldContestant("RKLB"),
                   "buyhold_RKLX":lambda:BuyHoldContestant("RKLX")}, WEEKS)
    b,_ = agg(bh,"buyhold_RKLB"); x,_ = agg(bh,"buyhold_RKLX")
    print(f"基准: 躺平RKLB 均{b['avg_return_pct']:+.2f}% 风调{b['avg_return_pct']/(abs(b['avg_max_dd_pct'])or .01):.2f} 最差{b['worst_week_pct']:.1f}%")
    print(f"      躺平RKLX 均{x['avg_return_pct']:+.2f}% 最差{x['worst_week_pct']:.1f}%\n")

    print(f"{'方案':<30}{'均收益%':>9}{'风调':>7}{'最差周%':>9}{'正收益':>7}{'churn':>7}")
    print("-"*69)
    # baseline v1.2 + rklxC70
    out0 = run_duel({"claude_rule":lambda:ClaudeRuleContestant()}, WEEKS)
    a0,ra0 = agg(out0,"claude_rule")
    print(f"{'v1.2+rklxC70(无持有挡)':<30}{a0['avg_return_pct']:>9.2f}{ra0:>7.2f}{a0['worst_week_pct']:>9.2f}{a0['positive_weeks']:>4}/{a0['weeks']:<2}{a0['total_trades']:>7}")

    # regime-持有挡 多档阈值
    best = None
    for wt in (2.0, 3.0, 4.0, 5.0):
        for hs in (0.08, 0.10, 0.12):
            for ride in ("RKLX", "RKLB"):
                out = run_duel({"claude_regime": lambda wt=wt,hs=hs,ride=ride: RegimeHoldContestant(wt,hs,ride)}, WEEKS)
                a,ra = agg(out,"claude_regime")
                tag = f"持有挡 周>{wt}% stop{int(hs*100)}% {ride}"
                row = (a['avg_return_pct'], ra, a['worst_week_pct'], a['positive_weeks'], a['weeks'], a['total_trades'], tag, out)
                if a['avg_return_pct'] > 0 and (best is None or ra > best[1]):
                    best = row
                print(f"{tag:<30}{a['avg_return_pct']:>9.2f}{ra:>7.2f}{a['worst_week_pct']:>9.2f}{a['positive_weeks']:>4}/{a['weeks']:<2}{a['total_trades']:>7}")

    if best:
        print(f"\n=== 最优持有挡: {best[6]} | 均{best[0]:+.2f}% 风调{best[1]:.2f} ===")
        bw = best[7]["per_contestant"]["claude_regime"]["by_week"]
        for w in WEEKS:
            v=bw.get(w); print(f"  {w}({REGIME[w]}): {v:+.2f}%" if v is not None else f"  {w}: --")


if __name__ == "__main__":
    main()
