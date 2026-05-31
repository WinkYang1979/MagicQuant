# -*- coding: utf-8 -*-
"""
近期加权评测框架(方法学, 只读, 不碰策略代码)
──────────────────────────────────────────────
用户方向: 回测周期 2-4 周, 越近权重越高(规避陈旧 regime 污染)。

提供 recency_score(): 对一组周的 per-week 收益做时间衰减加权,
  权重 w_i = decay^(周龄), 最近周龄=0。给后续所有策略 A/B 一把"正确的尺子"。
输出: Claude v1.2 vs 躺平RKLB/RKLX 在 近2周/近4周/近8周 三个窗口的加权对比。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.sim_weekly.duel import run_duel
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant

# 近期整周(从新到旧; 05-25 半周排除)
RECENT_WEEKS = ["2026-05-18", "2026-05-11", "2026-05-04", "2026-04-27",
                "2026-04-20", "2026-04-13", "2026-04-06", "2026-03-30"]

OUT = []
def emit(s=""): OUT.append(str(s))


def recency_weighted(per_week: dict, weeks: list, decay=0.85):
    """per_week: {week: return%}. weeks 从新到旧。w=decay^龄。返回(加权收益, 权重和)。"""
    num = den = 0.0
    for age, wk in enumerate(weeks):  # weeks[0]=最近, age=0
        v = per_week.get(wk)
        if v is None:
            continue
        w = decay ** age
        num += w * v
        den += w
    return (num / den if den else 0.0), den


def eval_contestant(name, factory, windows, decay=0.85):
    """对每个窗口算 加权收益 + 简单均值 + 最差周。"""
    out = run_duel({name: factory}, RECENT_WEEKS)
    bw = out["per_contestant"][name].get("by_week", {})
    res = {}
    for label, n in windows:
        wks = RECENT_WEEKS[:n]
        wavg, _ = recency_weighted(bw, wks, decay)
        vals = [bw[w] for w in wks if bw.get(w) is not None]
        res[label] = {
            "wavg": wavg,
            "mean": sum(vals)/len(vals) if vals else 0.0,
            "worst": min(vals) if vals else 0.0,
            "n": len(vals),
        }
    return res, bw


def main():
    decay = 0.85
    windows = [("近2周", 2), ("近4周", 4), ("近8周", 8)]
    emit(f"=== 近期加权评测 (decay={decay}, 最近周权重最高) ===")
    emit(f"近期整周: {RECENT_WEEKS}\n")

    contestants = [
        ("claude_rule", lambda: ClaudeRuleContestant()),
        ("buyhold_RKLB", lambda: BuyHoldContestant("RKLB")),
        ("buyhold_RKLX", lambda: BuyHoldContestant("RKLX")),
    ]

    all_res = {}
    all_bw = {}
    for name, fac in contestants:
        all_res[name], all_bw[name] = eval_contestant(name, fac, windows, decay)

    for label, _ in windows:
        emit(f"--- {label} ---")
        emit(f"{'选手':<16}{'加权收益%':>10}{'简单均值%':>10}{'最差周%':>9}")
        for name, _ in contestants:
            r = all_res[name][label]
            emit(f"{name:<16}{r['wavg']:>10.2f}{r['mean']:>10.2f}{r['worst']:>9.2f}")
        emit("")

    # 逐周明细(最近 8 周)
    emit("--- 逐周收益% (最近→最旧) ---")
    emit(f"{'周':<12}" + "".join(f"{n[:11]:>13}" for n,_ in contestants))
    for wk in RECENT_WEEKS:
        row = f"{wk:<12}"
        for name, _ in contestants:
            v = all_bw[name].get(wk)
            row += f"{(f'{v:+.2f}' if v is not None else '--'):>13}"
        emit(row)

    emit("\n方法学说明: 加权收益 = Σ(decay^周龄 × 周收益)/Σ权重, 最近周龄=0 权重=1。")
    emit("这是后续所有策略 A/B 的统一度量尺(替代旧的 11 周等权一锅炖)。")

    (ROOT / "research" / "_recency_result.txt").write_text("\n".join(OUT), encoding="utf-8")
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
