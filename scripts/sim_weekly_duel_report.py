"""SimWeekly Duel 逐笔流水日报 —— 配对买入↔卖出,出每笔"几点/什么价买、几点/什么价卖、赚亏"。

不是简单百分比:每笔交易展开成 entry/exit/持仓时长/扣费后盈亏。
可读离线回测(任意周),也可读实时 ledger(live 跑出来的 duel_ledger_<date>.json)。

用法:
  python scripts/sim_weekly_duel_report.py 2026-05-11        # 离线回测某周,出逐笔报告
  python scripts/sim_weekly_duel_report.py --ledger <path>   # 读实时 ledger json
  python scripts/sim_weekly_duel_report.py 2026-05-11 --tg   # 额外打印 Telegram 文本
"""
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.sim_weekly.duel import run_week
from core.sim_weekly.contestants import ClaudeRuleContestant, BuyHoldContestant
from core.sim_weekly.openai_contestant import OpenAIContestant
from core.sim_weekly.tg_format import ACTOR, actor_label, fmt_daily, pair_trades, send_private

# 离线报告默认对手:双方 + 基准。 / Offline report contestants plus benchmark.
CONTESTANTS = {
    "claude_rule":  lambda: ClaudeRuleContestant(),
    "openai_v1":    lambda: OpenAIContestant(),
    "buyhold_RKLB": lambda: BuyHoldContestant("RKLB"),
}

DISPLAY_NAMES = {key: f"{label} ({key})" for key, label in ACTOR.items()}


def _hold_minutes(entry_ts, exit_ts):
    try:
        a = datetime.strptime(entry_ts[:19], "%Y-%m-%d %H:%M:%S")
        b = datetime.strptime(exit_ts[:19], "%Y-%m-%d %H:%M:%S")
        return int((b - a).total_seconds() / 60)
    except Exception:
        return None


def render_contestant(name: str, sc: dict) -> str:
    rounds = pair_trades(sc.get("trades", []))
    label = DISPLAY_NAMES.get(name, actor_label(name))
    lines = [
        f"### {label}",
        f"- 周收益 **{sc['return_pct']:+.2f}%** · 期末权益 ${sc['final_equity']:.2f} · 最大回撤 {sc['max_drawdown_pct']}%",
        f"- 往返 {len(rounds)} 笔 · 胜率 {sc.get('win_rate_pct')}% · 手续费 ${sc['total_fees']} · profit_factor {sc.get('profit_factor')}",
        "",
        "| # | 标的 | 买入时间 | 买价 | 卖出时间 | 卖价 | 股数 | 持仓(分) | 扣费后盈亏 | 出场原因 |",
        "|--:|---|---|--:|---|--:|--:|--:|--:|---|",
    ]
    for i, r in enumerate(rounds, 1):
        lines.append(
            f"| {i} | {r['ticker']} | {r['entry_ts'][5:16]} | {r['entry_px']} "
            f"| {r['exit_ts'][5:16]} | {r['exit_px']} | {r['qty']} | {r['hold_min']} "
            f"| {r['pnl']:+.2f} | {r['exit_reason']} |"
        )
    if not rounds:
        lines.append("| — | 本周无成交 | | | | | | | | |")
    return "\n".join(lines)


def render_telegram(date_label: str, scores: dict) -> str:
    """私聊 Telegram 文本:简短头 + 每方逐笔(配对)。"""
    return fmt_daily(date_label, scores)


def send_private_telegram(text: str) -> bool:
    """Send private Telegram report; missing token/chat silently skips. / 私聊推送，缺凭证静默跳过。"""
    return send_private(text)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_tg = "--tg" in sys.argv
    send_tg = "--send-tg" in sys.argv

    if "--ledger" in sys.argv:
        path = sys.argv[sys.argv.index("--ledger") + 1]
        ledger = json.load(open(path, encoding="utf-8"))
        scores = ledger["contestants"]      # {name: score_dict(含 trades)}
        date_label = ledger.get("date", "live")
    else:
        week = args[0] if args else "2026-05-11"
        date_label = f"周 {week}"
        scores = {}
        for name, factory in CONTESTANTS.items():
            sc = run_week(factory(), week)
            if not sc.get("error"):
                scores[name] = sc

    # markdown 全量报告
    md = [f"# 双方 PK 逐笔流水报告 · {date_label}", ""]
    for name, sc in scores.items():
        md.append(render_contestant(name, sc)); md.append("")
    out_dir = "data/sim_weekly/compare"
    os.makedirs(out_dir, exist_ok=True)
    md_path = f"{out_dir}/duel_report_{date_label.replace(' ','_').replace('周_','')}.md"
    Path(md_path).write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    print(f"\n  saved -> {md_path}")

    if show_tg:
        tg_text = render_telegram(date_label, scores)
        print("\n=== Telegram 私聊文本预览 ===")
        print(tg_text)

    if send_tg:
        tg_text = render_telegram(date_label, scores)
        ok = send_private_telegram(tg_text)
        print(f"\n  telegram sent -> {ok}")


if __name__ == "__main__":
    main()
