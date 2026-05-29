"""SimWeekly Duel weekend summary.
VERSION: v0.1.0
DEPENDS: data/sim_weekly/live_duel_*.json, core/sim_weekly/tg_format.py

Build a weekend summary from live duel states.
从实时 PK 状态生成周末双方总报告。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "sim_weekly"
OUT_DIR = SIM_DIR / "reports"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from core.sim_weekly.tg_format import actor_label, fmt_weekly, pair_trades, send_private


CONTESTANT_STATES = {
    "claude_rule": SIM_DIR / "live_duel_claude_rule.json",
    "openai_v1": SIM_DIR / "live_duel_openai_v1.json",
}


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _max_drawdown(curve) -> float:
    peak, mdd = -1e18, 0.0
    for _, equity in curve:
        peak = max(peak, float(equity))
        if peak > 0:
            mdd = min(mdd, (float(equity) - peak) / peak)
    return round(mdd * 100, 2)


def _score_state(name: str, state: dict) -> dict:
    portfolio = state.get("portfolio") or {}
    trades = portfolio.get("trades") or []
    curve = portfolio.get("equity_curve") or []
    final_equity = float(portfolio.get("equity") or portfolio.get("cash") or 10000.0)
    sells = [trade for trade in trades if trade.get("side") == "sell"]
    wins = [trade for trade in sells if float(trade.get("pnl") or 0.0) > 0]
    gross_win = sum(float(trade.get("pnl") or 0.0) for trade in wins)
    gross_loss = sum(float(trade.get("pnl") or 0.0) for trade in sells if float(trade.get("pnl") or 0.0) <= 0)
    return {
        "contestant": name,
        "week_start": state.get("week_start"),
        "final_equity": final_equity,
        "return_pct": round((final_equity - 10000.0) / 10000.0 * 100, 2),
        "n_trades": len([trade for trade in trades if trade.get("side") == "buy"]),
        "n_round_trips": len(sells),
        "win_rate_pct": round(len(wins) / len(sells) * 100, 1) if sells else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(gross_loss / max(1, len(sells) - len(wins)), 2),
        "profit_factor": round(gross_win / abs(gross_loss), 3) if gross_loss < 0 else None,
        "max_drawdown_pct": _max_drawdown(curve),
        "total_fees": round(float(portfolio.get("total_fees") or 0.0), 2),
        "errors": len([trade for trade in trades if trade.get("side") == "error"]),
        "trades": trades,
    }


def build_scores() -> tuple[str, dict]:
    scores = {}
    week = "unknown"
    for name, path in CONTESTANT_STATES.items():
        state = _read_json(path, {})
        if not state:
            continue
        week = state.get("week_start") or week
        scores[name] = _score_state(name, state)
    return week, scores


def _risk_adjusted(score: dict) -> float:
    dd = abs(float(score.get("max_drawdown_pct") or 0.0)) or 0.01
    return float(score.get("return_pct") or 0.0) / dd


def render_markdown(week: str, scores: dict) -> str:
    lines = [
        f"# SimWeekly Duel 周末总报告 · {week}",
        "",
        "| 排名 | 选手 | 收益% | 风调 | 最大回撤% | 往返 | 胜率 | 手续费 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = sorted(scores, key=lambda name: _risk_adjusted(scores[name]), reverse=True)
    for rank, name in enumerate(ranked, 1):
        score = scores[name]
        lines.append(
            f"| {rank} | {actor_label(name)} ({name}) | {score['return_pct']:+.2f} | "
            f"{_risk_adjusted(score):+.2f} | {score['max_drawdown_pct']:.2f} | "
            f"{score['n_round_trips']} | {score.get('win_rate_pct') if score.get('win_rate_pct') is not None else '-'} | "
            f"${score['total_fees']:.2f} |"
        )
    lines += ["", "## 逐笔摘要", ""]
    for name in ranked:
        score = scores[name]
        rounds = pair_trades(score.get("trades", []))
        lines += [f"### {actor_label(name)} ({name})", ""]
        if not rounds:
            lines += ["- 本周无成交", ""]
            continue
        for idx, row in enumerate(rounds, 1):
            lines.append(
                f"- #{idx} {row['ticker']} 买 {row['entry_ts']} @{row['entry_px']} -> "
                f"卖 {row['exit_ts']} @{row['exit_px']} qty {row['qty']} pnl {row.get('pnl')}"
            )
        lines.append("")
    lines += [
        "## 结论",
        "",
        "周末总报告只做纸面 PK 复盘；下周周一新 week_start 会重置 $10,000 资金重新开赛。",
        "",
    ]
    return "\n".join(lines)


def write_report(week: str, text: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_week = week.replace(":", "-").replace(" ", "_")
    path = OUT_DIR / f"duel_weekly_report_{safe_week}.md"
    latest = OUT_DIR / "duel_weekly_report_latest.md"
    path.write_text(text + "\n", encoding="utf-8")
    latest.write_text(text + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build SimWeekly duel weekend summary.")
    parser.add_argument("--telegram", action="store_true", help="Send private Telegram weekly summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    week, scores = build_scores()
    if not scores:
        print("[duel-weekly] no live duel states found")
        return 1
    markdown = render_markdown(week, scores)
    path = write_report(week, markdown)
    print(markdown)
    print(f"\n[duel-weekly] report saved: {path}")
    if args.telegram:
        ok = send_private(fmt_weekly(week, scores))
        print(f"[duel-weekly] telegram sent={ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
