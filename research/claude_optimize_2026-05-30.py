# -*- coding: utf-8 -*-
"""
Claude 选手策略优化器 —— 跨 regime 网格扫描, 目标: 盈利保底 + 利润最大化。
────────────────────────────────────────────────────────────────────
诊断: Claude 不是亏太多, 是牛市周赢太少(+0.91% vs 躺平RKLB +5.19%)。
主轴: 趋势骑乘(放宽止损让赢家跑 / 更敢用 RKLX 2x / 信念门)。

用真实 ClaudeRuleContestant + 注入 config + monkeypatch 策略常量, 跨 11 周回放。
不改任何 baseline 文件; 纯研究。
"""
import io, sys, json, itertools
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

# 基准(固定)
_BH = None
def benchmarks():
    global _BH
    if _BH is None:
        out = run_duel({"buyhold_RKLB": lambda: BuyHoldContestant("RKLB"),
                        "buyhold_RKLX": lambda: BuyHoldContestant("RKLX")}, WEEKS)
        _BH = {n: out["per_contestant"][n] for n in ("buyhold_RKLB","buyhold_RKLX")}
    return _BH


def run_cfg(long_max, short_min, rklx_conv, params):
    """跑一个配置: 设策略常量 + 注入 contestant config。返回聚合指标。"""
    strat.LONG_RSI_MAX = long_max
    strat.SHORT_RSI_MIN = short_min
    strat.RKLX_CONV = rklx_conv
    cfg = {"profile": params.get("profile", "neutral"),
           "hypothesis_id": "opt", "params": params}
    tmp = ROOT / "data" / "sim_weekly" / "_opt_tmp_config.json"
    tmp.write_text(json.dumps(cfg), encoding="utf-8")
    out = run_duel({"claude_rule": lambda: ClaudeRuleContestant(str(tmp))}, WEEKS)
    a = out["per_contestant"]["claude_rule"]
    dd = abs(a.get("avg_max_dd_pct", 0.0)) or 0.01
    return {"avg": a["avg_return_pct"], "ra": a["avg_return_pct"]/dd,
            "worst": a["worst_week_pct"], "dd": a["avg_max_dd_pct"],
            "pos": a["positive_weeks"], "tr": a["total_trades"], "w": a["weeks"],
            "by_week": a.get("by_week", {})}


def main():
    bh = benchmarks()
    rklb_avg = bh["buyhold_RKLB"]["avg_return_pct"]
    rklb_dd = abs(bh["buyhold_RKLB"]["avg_max_dd_pct"]) or 0.01
    print(f"基准: 躺平RKLB 均{rklb_avg:+.2f}% 风调{rklb_avg/rklb_dd:.2f} | "
          f"躺平RKLX 均{bh['buyhold_RKLX']['avg_return_pct']:+.2f}% 最差{bh['buyhold_RKLX']['worst_week_pct']:.1f}%\n")

    base_params = {"entry_conv": 70, "frac_strong": 0.75, "frac_weak": 0.45,
                   "stop_mult": 1.0, "cooldown_bars": 3,
                   "avoid_shorts_in_bull": False, "bull_long_rsi_max": 80}

    # 网格(聚焦趋势骑乘): stop_mult(让赢家跑) × rklx_conv(2x激进度) × frac × entry_conv
    grid = {
        "stop_mult":   [1.0, 1.5, 2.0, 2.5],
        "rklx_conv":   [82, 75, 70],
        "frac_strong": [0.75, 0.90],
        "entry_conv":  [70, 65],
    }
    long_max, short_min = 72, 40   # 固定上一轮拐点过滤结论

    results = []
    keys = list(grid)
    for combo in itertools.product(*[grid[k] for k in keys]):
        d = dict(zip(keys, combo))
        p = dict(base_params)
        p.update({"stop_mult": d["stop_mult"], "frac_strong": d["frac_strong"],
                  "entry_conv": d["entry_conv"]})
        r = run_cfg(long_max, short_min, d["rklx_conv"], p)
        r["cfg"] = f"stop{d['stop_mult']} rklxC{d['rklx_conv']} fS{d['frac_strong']} eC{d['entry_conv']}"
        results.append(r)

    # 排序: 先保底盈利, 再风险调整, 再均收益
    profitable = [r for r in results if r["avg"] > 0]
    profitable.sort(key=lambda r: (r["ra"], r["avg"]), reverse=True)

    print(f"=== 共 {len(results)} 组, 盈利 {len(profitable)} 组。Top 12(按风调)===")
    hdr = f"{'配置':<34}{'均收益%':>9}{'风调':>7}{'最差周%':>9}{'正收益':>7}{'交易':>6}"
    print(hdr); print("-"*len(hdr))
    for r in profitable[:12]:
        print(f"{r['cfg']:<34}{r['avg']:>9.2f}{r['ra']:>7.2f}{r['worst']:>9.2f}{r['pos']:>4}/{r['w']:<2}{r['tr']:>6}")

    # 同时按"均收益最大"排
    by_avg = sorted(profitable, key=lambda r: r["avg"], reverse=True)
    print(f"\n=== Top 6 按均收益最大 ===")
    print(hdr); print("-"*len(hdr))
    for r in by_avg[:6]:
        print(f"{r['cfg']:<34}{r['avg']:>9.2f}{r['ra']:>7.2f}{r['worst']:>9.2f}{r['pos']:>4}/{r['w']:<2}{r['tr']:>6}")

    # 清理临时
    (ROOT / "data" / "sim_weekly" / "_opt_tmp_config.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
