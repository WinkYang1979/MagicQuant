# -*- coding: utf-8 -*-
"""Phase 2: 最优候选稳健性核验 —— 逐周分布 + 留一法 + 牛熊震荡分层。
确认 stop2.5/rklxC70/fS0.9/eC65 不是靠单周运气, 选稳健点定稿。"""
import io, sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.sim_weekly import strategy as strat
from core.sim_weekly.duel import run_duel
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant

WEEKS = ["2025-12-08", "2025-12-22", "2026-01-12", "2026-01-26",
         "2026-02-02", "2026-02-23", "2026-03-09", "2026-03-16",
         "2026-04-27", "2026-05-04", "2026-05-11"]
# regime 标签(memory: 含牛/熊/震荡)
REGIME = {"2025-12-08":"牛","2026-01-12":"牛","2026-05-04":"牛","2026-05-11":"牛",
          "2025-12-22":"熊","2026-02-02":"熊","2026-03-09":"熊","2026-03-16":"熊",
          "2026-01-26":"震","2026-02-23":"震","2026-04-27":"震"}


def run_cfg(long_max, short_min, rklx_conv, params, weeks):
    strat.LONG_RSI_MAX = long_max; strat.SHORT_RSI_MIN = short_min; strat.RKLX_CONV = rklx_conv
    cfg = {"profile": params.get("profile","neutral"), "hypothesis_id":"opt","params":params}
    tmp = ROOT/"data"/"sim_weekly"/"_opt2_tmp.json"; tmp.write_text(json.dumps(cfg),encoding="utf-8")
    out = run_duel({"claude_rule": lambda: ClaudeRuleContestant(str(tmp))}, weeks)
    a = out["per_contestant"]["claude_rule"]; dd=abs(a.get("avg_max_dd_pct",0)) or 0.01
    return {"avg":a["avg_return_pct"],"ra":a["avg_return_pct"]/dd,"worst":a["worst_week_pct"],
            "pos":a["positive_weeks"],"tr":a["total_trades"],"w":a["weeks"],"by_week":a.get("by_week",{})}


CANDIDATES = {
    # name: (long_max, short_min, rklx_conv, stop_mult, frac_strong, entry_conv)
    "A 激进 stop2.5/rklx70/f0.9/e65": (72,40,70,2.5,0.90,65),
    "B 稳健 stop2.0/rklx75/f0.9/e70": (72,40,75,2.0,0.90,70),
    "C 中庸 stop2.0/rklx75/f0.75/e70":(72,40,75,2.0,0.75,70),
}
BASE = {"cooldown_bars":3,"avoid_shorts_in_bull":False,"bull_long_rsi_max":80,"frac_weak":0.45}


def cfg_params(stop_mult, frac_strong, entry_conv):
    p=dict(BASE); p.update({"stop_mult":stop_mult,"frac_strong":frac_strong,"entry_conv":entry_conv}); return p


def main():
    # 基准
    bh=run_duel({"buyhold_RKLB":lambda:BuyHoldContestant("RKLB")},WEEKS)["per_contestant"]["buyhold_RKLB"]
    print(f"基准 躺平RKLB: 均{bh['avg_return_pct']:+.2f}% 风调{bh['avg_return_pct']/(abs(bh['avg_max_dd_pct'])or 0.01):.2f}\n")

    for name,(lm,sm,rc,stop,fs,ec) in CANDIDATES.items():
        full=run_cfg(lm,sm,rc,cfg_params(stop,fs,ec),WEEKS)
        # regime 分层
        reg={"牛":[],"熊":[],"震":[]}
        for w,v in full["by_week"].items():
            if v is not None: reg[REGIME[w]].append(v)
        # 留一法: 去掉最好一周后均收益(防单周依赖)
        vals=[v for v in full["by_week"].values() if v is not None]
        loo=(sum(vals)-max(vals))/(len(vals)-1) if len(vals)>1 else 0
        print(f"=== {name} ===")
        print(f"  全样本: 均{full['avg']:+.2f}% 风调{full['ra']:.2f} 最差{full['worst']:.2f}% 正{full['pos']}/{full['w']} churn{full['tr']}")
        print(f"  去掉最好一周后均收益: {loo:+.2f}%  (>0 说明不靠单周)")
        for r in ("牛","熊","震"):
            xs=reg[r];
            if xs: print(f"  {r}市 {len(xs)}周: 均{sum(xs)/len(xs):+.2f}% [{min(xs):+.1f}~{max(xs):+.1f}]")
        print()
    (ROOT/"data"/"sim_weekly"/"_opt2_tmp.json").unlink(missing_ok=True)


if __name__=="__main__":
    main()
