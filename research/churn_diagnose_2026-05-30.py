# -*- coding: utf-8 -*-
"""
诊断: 趋势持有为何 churn(明明该持有却反复进出) — 只读, 不碰策略
─────────────────────────────────────────────────────────────
对单周 RKLB, 复现 trend-hold 的 regime 序列, 数它每 5m bar 的目标标的怎么变,
找出 churn 来源(边界震荡 RKLX<->RKLB<->cash)。给"如何真正持有"提供依据。
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.sim_weekly import indicators as ind
from core.sim_weekly.duel import _load_5m, _week_days, _in_rth
from datetime import datetime

OUT=[]
def emit(s=""): OUT.append(str(s))

def regime(closes, ema_slow, strong_dist, mild_dist):
    if len(closes) < ema_slow: return None
    e_slow = ind.ema(closes[-ema_slow-5:], ema_slow)
    e9, e21 = ind.ema(closes[-30:],9), ind.ema(closes[-30:],21)
    if None in (e_slow,e9,e21) or e_slow<=0: return None
    cur=closes[-1]; dist=(cur-e_slow)/e_slow*100
    up = e9>e21 and cur>e_slow
    if up and dist>=strong_dist: return "RKLX"
    if up and dist>=mild_dist: return "RKLB"
    return None

WEEKS=["2026-05-04","2026-04-27","2026-04-20","2026-05-11"]
for wk in WEEKS:
    monday=datetime.strptime(wk,"%Y-%m-%d")
    bars=_load_5m("RKLB", set(_week_days(monday)))
    tl=sorted(bars.keys())
    closes=[]; seq=[]
    for ts in tl:
        closes.append(bars[ts]["close"])
        seq.append(regime(closes,50,1.0,0.0))
    # 数切换次数(相邻不同即一次潜在 churn)
    switches=sum(1 for i in range(1,len(seq)) if seq[i]!=seq[i-1])
    # 各状态占比
    from collections import Counter
    c=Counter(str(x) for x in seq)
    emit(f"=== {wk} ({len(tl)}根5m bar) ===")
    emit(f"  regime 切换次数: {switches}  (每次切换≈1买+1卖=2笔)")
    emit(f"  状态占比: {dict(c)}")
    # 看边界震荡: 连续段长度
    runs=[]; cur=seq[0]; ln=1
    for x in seq[1:]:
        if x==cur: ln+=1
        else: runs.append((str(cur),ln)); cur=x; ln=1
    runs.append((str(cur),ln))
    short_runs=[r for r in runs if r[1]<=2]
    emit(f"  状态段总数: {len(runs)}, 其中≤2根的短段(震荡源): {len(short_runs)}")
    emit("")

(ROOT/"research"/"_churn_diag.txt").write_text("\n".join(OUT),encoding="utf-8")
print("\n".join(OUT))
