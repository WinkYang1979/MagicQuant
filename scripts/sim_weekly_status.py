"""
MagicQuant SimWeekly status reporter.
VERSION: v0.1.0
DEPENDS: data/sim_weekly/live_state.json, data/sim_weekly/week_*.json, data/sim_weekly/replay_*.json

Read-only paper-trading visibility report. / 只读模拟盘可见性报告。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
SIM_DIR = BASE_DIR / "data" / "sim_weekly"
SHARED_SNAPSHOT = BASE_DIR / "data" / "shared" / "market_snapshot.json"
REPORT_DIR = SIM_DIR / "reports"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _fmt_money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$-"


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "-"


def _snapshot_prices() -> dict[str, float]:
    payload = _read_json(SHARED_SNAPSHOT, {})
    quotes = payload.get("quotes") if isinstance(payload, dict) else {}
    out: dict[str, float] = {}
    for ticker in ("RKLB", "RKLX", "RKLZ"):
        item = (quotes or {}).get(ticker) or (quotes or {}).get(f"US.{ticker}") or {}
        price = item.get("price") or item.get("last")
        try:
            if price:
                out[ticker] = float(price)
        except Exception:
            pass
    return out


def _estimate_equity(portfolio: dict, prices: dict[str, float]) -> float:
    cash = float(portfolio.get("cash") or 0.0)
    equity = portfolio.get("equity")
    if equity is not None:
        try:
            return float(equity)
        except Exception:
            pass
    total = cash
    positions = portfolio.get("positions") or {}
    if isinstance(positions, dict):
        for ticker, pos in positions.items():
            try:
                qty = float(pos.get("qty") or 0.0)
                cost = float(pos.get("cost_price") or 0.0)
                total += qty * float(prices.get(str(ticker), cost))
            except Exception:
                continue
    return total


def _latest_file(pattern: str) -> Path | None:
    files = sorted(SIM_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _trade_line(trade: dict) -> str:
    side = "买入" if trade.get("side") == "buy" else "卖出"
    ticker = trade.get("ticker", "-")
    qty = trade.get("qty", "-")
    price = trade.get("price", "-")
    pnl = trade.get("pnl")
    pnl_text = f" / PnL {_fmt_money(pnl)}" if pnl is not None else ""
    reason = trade.get("reason") or "-"
    return f"- {trade.get('ts', '-')} {side} {ticker} x{qty} @ {price}{pnl_text} ({reason})"


def _live_account_line(path: Path, label: str, prices: dict[str, float]) -> list[str]:
    state = _read_json(path, {})
    if not state:
        return [f"- {label}: 无状态文件"]
    portfolio = state.get("portfolio") or {}
    equity = _estimate_equity(portfolio, prices)
    ret_pct = (equity - 10000.0) / 10000.0 * 100.0
    trades = portfolio.get("trades") or []
    positions = portfolio.get("positions") or {}
    pos_text = "无"
    if isinstance(positions, dict) and positions:
        parts = []
        for ticker, pos in positions.items():
            parts.append(f"{ticker} {pos.get('qty', 0)}股@{pos.get('cost_price', '-')}")
        pos_text = " / ".join(parts)
    return [
        f"- {label}: 权益 {_fmt_money(equity)} ({_fmt_pct(ret_pct)})，成交 {len(trades)}，持仓 {pos_text}",
    ]


def build_report(max_trades: int = 8) -> str:
    state_path = SIM_DIR / "live_state.json"
    state = _read_json(state_path, {})
    portfolio = state.get("portfolio") or {}
    trades = portfolio.get("trades") or []
    positions = portfolio.get("positions") or {}
    prices = _snapshot_prices()
    equity = _estimate_equity(portfolio, prices)
    initial = 10000.0
    ret_pct = (equity - initial) / initial * 100.0 if initial else 0.0
    state_mtime = datetime.fromtimestamp(state_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if state_path.exists() else "-"

    lines = [
        "📘 SimWeekly 模拟盘状态",
        f"更新时间: {state_mtime}",
        f"本周: {state.get('week_start') or '-'}",
        f"状态: {'已结算' if state.get('settled') else '运行/待结算'}",
        "",
        "💼 当前模拟账户",
        f"权益: {_fmt_money(equity)} ({_fmt_pct(ret_pct)})",
        f"现金: {_fmt_money(portfolio.get('cash', 0))}",
        f"手续费: {_fmt_money(portfolio.get('total_fees', 0))}",
        f"5m bars: {len(state.get('bars') or [])}",
        f"模拟成交: {len(trades)}",
    ]

    if positions:
        lines.append("持仓:")
        for ticker, pos in positions.items():
            qty = pos.get("qty", 0)
            cost = pos.get("cost_price", 0)
            price = prices.get(str(ticker))
            price_text = f" / 现价 {_fmt_money(price)}" if price is not None else ""
            lines.append(f"- {ticker}: {qty} 股 @ {_fmt_money(cost)}{price_text}")
    else:
        lines.append("持仓: 无")

    if trades:
        lines += ["", f"🧾 最近 {min(max_trades, len(trades))} 笔模拟成交"]
        for trade in trades[-max_trades:]:
            lines.append(_trade_line(trade))
    else:
        lines += ["", "🧾 本周暂无模拟成交"]

    duel_paths = [
        (SIM_DIR / "live_duel_claude_rule.json", "Claude 实时纸面"),
        (SIM_DIR / "live_duel_openai_v1.json", "OpenAI 实时纸面"),
    ]
    if any(path.exists() for path, _label in duel_paths):
        lines += ["", "⚔️ 实时双账户对战"]
        for path, label in duel_paths:
            lines += _live_account_line(path, label, prices)

    week_path = _latest_file("week_*.json")
    if week_path:
        week = _read_json(week_path, {})
        lines += [
            "",
            "📊 最近周结算",
            f"{week.get('week_start', '-')}  收益 {_fmt_pct(week.get('return_pct'))}",
            f"交易 {week.get('n_trades', 0)} 笔 / 胜率 {week.get('win_rate_pct') if week.get('win_rate_pct') is not None else '-'}%",
            f"对照 RKLB 买入持有 {_fmt_pct(week.get('benchmark_buyhold_RKLB_pct'))}",
        ]

    replay_rows = []
    for path in sorted(SIM_DIR.glob("replay_*.json")):
        item = _read_json(path, {})
        if item:
            replay_rows.append(item)
    if replay_rows:
        recent = replay_rows[-8:]
        avg = sum(float(x.get("return_pct") or 0.0) for x in recent) / len(recent)
        wins = sum(1 for x in recent if float(x.get("return_pct") or 0.0) > 0)
        lines += [
            "",
            "🧪 最近离线回放",
            f"{len(recent)} 周平均收益: {_fmt_pct(avg)} / 盈利周 {wins}/{len(recent)}",
            f"最好: {max(recent, key=lambda x: float(x.get('return_pct') or 0)).get('week_start')} {_fmt_pct(max(float(x.get('return_pct') or 0) for x in recent))}",
            f"最差: {min(recent, key=lambda x: float(x.get('return_pct') or 0)).get('week_start')} {_fmt_pct(min(float(x.get('return_pct') or 0) for x in recent))}",
        ]

    if not state_path.exists():
        lines += ["", "⚠️ 结论: 未发现 live_state.json，实时模拟盘可能没有启动。"]
    elif not trades:
        lines += ["", "结论: 实时模拟盘有状态文件，但本周尚未产生模拟买卖。"]
    else:
        lines += ["", "结论: 实时模拟盘已产生模拟成交，可继续观察效果。"]

    return "\n".join(lines)


def write_report(text: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    dated = REPORT_DIR / f"sim_weekly_status_{today}.md"
    latest = REPORT_DIR / "sim_weekly_status_latest.md"
    content = text + "\n"
    dated.write_text(content, encoding="utf-8")
    latest.write_text(content, encoding="utf-8")
    return dated


def send_telegram(text: str) -> bool:
    try:
        from core.sim_weekly.tg_format import send_private
    except Exception as exc:
        print(f"[sim_weekly_status] telegram helper unavailable: {exc}")
        return False
    return bool(send_private(text))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report SimWeekly paper trading status.")
    parser.add_argument("--telegram", action="store_true", help="Send report to TG_REVIEW_CHAT_ID.")
    parser.add_argument("--max-trades", type=int, default=8, help="Max recent trades to show.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = build_report(max_trades=max(1, args.max_trades))
    path = write_report(text)
    print(text)
    print(f"\n[sim_weekly_status] report saved: {path}")
    if args.telegram:
        ok = send_telegram(text)
        print(f"[sim_weekly_status] telegram sent={ok}")
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
