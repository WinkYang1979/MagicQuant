"""SimWeekly 离线回放 —— 历史 1m 数据跑一周或多周,出记分卡 + 汇总。纯只读。

用法:
    python scripts/sim_weekly_replay.py                      # 自动跑最近 8 个完整周
    python scripts/sim_weekly_replay.py 2026-05-11           # 指定某周(周一)
    python scripts/sim_weekly_replay.py 2026-05-11 --trades  # 附交易清单
"""
import io
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.sim_weekly.engine import run_week, format_scorecard


def _recent_mondays(n: int, last_data="2026-05-15"):
    end = datetime.strptime(last_data, "%Y-%m-%d")
    monday = end - timedelta(days=end.weekday())     # 本周一
    return [(monday - timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(n)][::-1]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_trades = "--trades" in sys.argv
    weeks = args if args else _recent_mondays(8)

    rows = []
    for wk in weeks:
        sc = run_week(wk, 10000.0)
        if sc.get("error"):
            print(f"  {wk}: {sc['error']}")
            continue
        print(format_scorecard(sc)); print()
        os.makedirs("data/sim_weekly", exist_ok=True)
        json.dump(sc, open(f"data/sim_weekly/replay_{wk}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2, default=str)
        if show_trades:
            for t in sc["trades"]:
                pnl = f" pnl${t['pnl']}" if t["side"] == "sell" else ""
                print(f"    {t['ts']} {t['side']:4s} {t['ticker']:4s} {t['qty']}@{t['price']}{pnl} {t.get('reason','')}")
            print()
        rows.append(sc)

    if len(rows) > 1:
        print("=== 汇总(策略 vs 躺平) ===")
        print(f"  {'周一':12s} {'策略%':>8s} {'RKLB%':>8s} {'RKLX%':>8s} {'笔数':>5s} {'胜率':>6s} {'回撤%':>7s}")
        for sc in rows:
            print(f"  {sc['week_start']:12s} {sc['return_pct']:>8.2f} "
                  f"{sc['benchmark_buyhold_RKLB_pct']:>8} {sc['benchmark_buyhold_RKLX_pct']:>8} "
                  f"{sc['n_trades']:>5} {str(sc['win_rate_pct']):>6} {sc['max_drawdown_pct']:>7}")
        avg = sum(s["return_pct"] for s in rows) / len(rows)
        beat = sum(1 for s in rows if s["return_pct"] > (s["benchmark_buyhold_RKLB_pct"] or 0))
        print(f"  平均策略周收益 {avg:+.2f}%  ·  跑赢 RKLB 躺平 {beat}/{len(rows)} 周")


if __name__ == "__main__":
    main()
