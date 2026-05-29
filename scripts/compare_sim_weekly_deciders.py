"""
MagicQuant SimWeekly decider comparison.
VERSION: v0.1.0
DEPENDS: core.sim_weekly.engine, core.sim_weekly.deciders, data/historical/*_1m.csv

Compare Claude RuleDecider vs CodexDecider on identical replay weeks.
同一套周回放对比 Claude 规则版与 Codex 纸面操盘版。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "sim_weekly" / "compare"
DOCS_DIR = ROOT / "docs"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core.sim_weekly.deciders import CodexDecider, RuleDecider
from core.sim_weekly.engine import run_week


def _recent_mondays(n: int, last_data: str = "2026-05-15") -> list[str]:
    end = datetime.strptime(last_data, "%Y-%m-%d")
    monday = end - timedelta(days=end.weekday())
    return [(monday - timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(n)][::-1]


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "-"


def _fmt_money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$-"


def _run(decider, weeks: list[str]) -> list[dict]:
    rows = []
    for week in weeks:
        sc = run_week(week, 10000.0, decider=decider)
        sc["label"] = getattr(decider, "name", decider.__class__.__name__)
        rows.append(sc)
    return rows


def _trade_rows(label: str, rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for week in rows:
        week_start = week.get("week_start")
        for idx, trade in enumerate(week.get("trades") or [], 1):
            out.append({
                "decider": label,
                "week_start": week_start,
                "idx": idx,
                "ts": trade.get("ts"),
                "side": trade.get("side"),
                "ticker": trade.get("ticker"),
                "qty": trade.get("qty"),
                "price": trade.get("price"),
                "fee": trade.get("fee"),
                "pnl": trade.get("pnl", ""),
                "reason": trade.get("reason", ""),
            })
    return out


def write_trade_csv(rule_rows: list[dict], codex_rows: list[dict]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "sim_weekly_compare_trades_latest.csv"
    fields = ["decider", "week_start", "idx", "ts", "side", "ticker", "qty", "price", "fee", "pnl", "reason"]
    rows = _trade_rows("Claude RuleDecider", rule_rows) + _trade_rows("CodexDecider", codex_rows)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _summary(rows: list[dict]) -> dict:
    valid = [r for r in rows if not r.get("error")]
    if not valid:
        return {"weeks": 0, "avg_return": 0.0, "total_return": 0.0, "wins": 0, "avg_mdd": 0.0, "trades": 0}
    return {
        "weeks": len(valid),
        "avg_return": sum(float(r.get("return_pct") or 0.0) for r in valid) / len(valid),
        "total_return": sum(float(r.get("return_pct") or 0.0) for r in valid),
        "wins": sum(1 for r in valid if float(r.get("return_pct") or 0.0) > 0),
        "avg_mdd": sum(float(r.get("max_drawdown_pct") or 0.0) for r in valid) / len(valid),
        "trades": sum(int(r.get("n_trades") or 0) for r in valid),
        "beat_rklb": sum(1 for r in valid if float(r.get("return_pct") or 0.0) > float(r.get("benchmark_buyhold_RKLB_pct") or 0.0)),
    }


def build_report(weeks: list[str], rule_rows: list[dict], codex_rows: list[dict]) -> str:
    rule_sum = _summary(rule_rows)
    codex_sum = _summary(codex_rows)
    lines = [
        "# SimWeekly Decider Compare",
        "",
        "VERSION: v0.1.0",
        "DEPENDS: core/sim_weekly/deciders.py, core/sim_weekly/engine.py, data/historical/*_1m.csv",
        "",
        "Purpose: compare Claude RuleDecider and CodexDecider on identical paper replay weeks. This is research-only; no live trading logic is changed.",
        "",
        "## Summary",
        "",
        "| Decider | Weeks | Avg weekly return | Sum weekly return | Profitable weeks | Beat RKLB B&H | Avg max drawdown | Trades |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| Claude RuleDecider | {rule_sum['weeks']} | {_fmt_pct(rule_sum['avg_return'])} | {_fmt_pct(rule_sum['total_return'])} | {rule_sum['wins']}/{rule_sum['weeks']} | {rule_sum['beat_rklb']}/{rule_sum['weeks']} | {_fmt_pct(rule_sum['avg_mdd'])} | {rule_sum['trades']} |",
        f"| CodexDecider | {codex_sum['weeks']} | {_fmt_pct(codex_sum['avg_return'])} | {_fmt_pct(codex_sum['total_return'])} | {codex_sum['wins']}/{codex_sum['weeks']} | {codex_sum['beat_rklb']}/{codex_sum['weeks']} | {_fmt_pct(codex_sum['avg_mdd'])} | {codex_sum['trades']} |",
        "",
        "## Weekly Detail",
        "",
        "| Week | Claude % | Codex % | Delta | Claude trades | Codex trades | RKLB B&H | RKLX B&H |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    by_rule = {r.get("week_start"): r for r in rule_rows}
    by_codex = {r.get("week_start"): r for r in codex_rows}
    for week in weeks:
        r = by_rule.get(week, {})
        c = by_codex.get(week, {})
        if r.get("error") or c.get("error"):
            lines.append(f"| {week} | error | error | - | - | - | - | - |")
            continue
        rp = float(r.get("return_pct") or 0.0)
        cp = float(c.get("return_pct") or 0.0)
        lines.append(
            f"| {week} | {_fmt_pct(rp)} | {_fmt_pct(cp)} | {_fmt_pct(cp - rp)} | "
            f"{r.get('n_trades', 0)} | {c.get('n_trades', 0)} | "
            f"{_fmt_pct(r.get('benchmark_buyhold_RKLB_pct'))} | {_fmt_pct(r.get('benchmark_buyhold_RKLX_pct'))} |"
        )

    decision = "CodexDecider wins this replay set." if codex_sum["avg_return"] > rule_sum["avg_return"] else "Claude RuleDecider remains better on this replay set."
    lines += [
        "",
        "## Trade Ledger",
        "",
        "完整逐笔流水已导出到 CSV，包含每笔买入/卖出的时间、价格、数量、手续费、卖出 PnL 和触发原因。",
        "",
        f"- CSV: `{OUT_DIR / 'sim_weekly_compare_trades_latest.csv'}`",
        "",
        "## Decision",
        "",
        f"- {decision}",
        "- This comparison is paper-only. Do not promote the winner to live strategy without daily signal coverage replay and scorecard review.",
        "- If CodexDecider wins, next step is shadow logging before any Telegram/live integration.",
        "",
        "## Output Files",
        "",
        f"- JSON detail: `{OUT_DIR / 'sim_weekly_compare_latest.json'}`",
        f"- Trade ledger CSV: `{OUT_DIR / 'sim_weekly_compare_trades_latest.csv'}`",
    ]
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare SimWeekly deciders.")
    parser.add_argument("weeks", nargs="*", help="Week start dates, e.g. 2026-05-11.")
    parser.add_argument("--recent", type=int, default=8, help="Recent full weeks when no week list is provided.")
    parser.add_argument("--last-data", default="2026-05-15", help="Latest historical date for auto recent weeks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    weeks = args.weeks or _recent_mondays(args.recent, args.last_data)
    rule_rows = _run(RuleDecider(), weeks)
    codex_rows = _run(CodexDecider(), weeks)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    detail = {"weeks": weeks, "rule": rule_rows, "codex": codex_rows}
    (OUT_DIR / "sim_weekly_compare_latest.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    trade_csv = write_trade_csv(rule_rows, codex_rows)

    report = build_report(weeks, rule_rows, codex_rows)
    dated = DOCS_DIR / f"sim_weekly_decider_compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    latest = DOCS_DIR / "sim_weekly_decider_compare_latest.md"
    dated.write_text(report, encoding="utf-8")
    latest.write_text(report, encoding="utf-8")
    print(report)
    print(f"[compare] trades: {trade_csv}")
    print(f"[compare] saved: {dated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
