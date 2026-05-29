"""SimWeekly Duel 离线回测擂台 —— 多周 PK,出中立记分板。纯只读,不碰实盘。

用法:
    python scripts/sim_weekly_duel_backtest.py                  # 默认 8 周,Claude vs 基准
    python scripts/sim_weekly_duel_backtest.py 2026-05-11       # 指定单周
OpenAI 选手就位后,在 CONTESTANTS 里加一行 import 即可同台。
"""
import io
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.sim_weekly.duel import run_duel
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant
from core.sim_weekly.openai_contestant import OpenAIContestant

# 选手注册表:{显示名: 工厂函数}。 / Contestant registry.
CONTESTANTS = {
    "claude_rule":   lambda: ClaudeRuleContestant(),
    "openai_v1":     lambda: OpenAIContestant(),
    "buyhold_RKLB":  lambda: BuyHoldContestant("RKLB"),
    "buyhold_RKLX":  lambda: BuyHoldContestant("RKLX"),
}


def _recent_mondays(n: int, last_data="2026-05-15"):
    end = datetime.strptime(last_data, "%Y-%m-%d")
    monday = end - timedelta(days=end.weekday())
    return [(monday - timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(n)][::-1]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    weeks = args if args else _recent_mondays(8)

    out = run_duel(CONTESTANTS, weeks)
    agg = out["per_contestant"]

    print(f"=== SimWeekly Duel 记分板 ({len(weeks)} 周) ===\n")
    hdr = f"{'选手':<16}{'周数':>5}{'均收益%':>9}{'风调':>8}{'中位%':>8}{'最差周%':>9}{'正收益周':>9}{'胜躺平':>8}{'均回撤%':>9}{'总交易':>7}"
    print(hdr)
    print("-" * len(hdr))

    def _risk_adjusted(row: dict) -> float:
        dd = abs(row.get("avg_max_dd_pct", 0.0))
        return row.get("avg_return_pct", -1e9) / max(dd, 0.01)

    # 按风险调整收益排序,避免单边牛市裸收益误导。 / Sort by risk-adjusted return.
    for name in sorted(agg, key=lambda n: _risk_adjusted(agg[n]), reverse=True):
        a = agg[name]
        if not a.get("weeks"):
            print(f"{name:<16}{'(无数据)':>10}")
            continue
        print(f"{name:<16}{a['weeks']:>5}{a['avg_return_pct']:>9.2f}{_risk_adjusted(a):>8.2f}{a['median_return_pct']:>8.2f}"
              f"{a['worst_week_pct']:>9.2f}{a['positive_weeks']:>6}/{a['weeks']:<2}"
              f"{a['beat_buyhold_weeks']:>6}/{a['weeks']:<2}{a['avg_max_dd_pct']:>9.2f}{a['total_trades']:>7}")

    print("\n=== 逐周对照(收益%)===")
    wk_hdr = f"{'周一':<12}" + "".join(f"{n[:12]:>14}" for n in CONTESTANTS)
    print(wk_hdr)
    for wk in weeks:
        row = f"{wk:<12}"
        for name in CONTESTANTS:
            v = agg.get(name, {}).get("by_week", {}).get(wk)
            row += f"{(f'{v:+.2f}' if v is not None else '--'):>14}"
        print(row)

    os.makedirs("data/sim_weekly", exist_ok=True)
    out_path = f"data/sim_weekly/duel_backtest_{weeks[0]}_{weeks[-1]}.json"
    # 去掉 trades 明细以免文件过大,保留聚合
    slim = {"per_contestant": {n: {k: v for k, v in a.items() if k != "raw"}
                               for n, a in agg.items()}, "weeks": weeks}
    json.dump(slim, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(f"\n  saved -> {out_path}")


if __name__ == "__main__":
    main()
