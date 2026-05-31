"""
MagicQuant Arena Virtual Portfolio Engine.
VERSION : v1.0.0
DEPENDS : argparse, csv, dataclasses, datetime, json, math, pathlib, typing,
          config.settings

Purpose / 用途:
Convert frozen Arena signals into paper trades, daily portfolio history, and
portfolio reports. This engine is paper-only: it does not send orders, alter
strategies, tune parameters, or touch live trading logic.
把冻结 Arena 信号转换成纸面交易、每日组合历史和组合报告；本引擎仅纸面模拟，
不下单、不改策略、不调参数、不接触实盘交易逻辑。
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, time
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional


INITIAL_CAPITAL = 100_000.0
SUPPORTED_ASSETS = ("RKLX", "RKLZ", "Cash")
RTH_START = time(9, 30)
RTH_END = time(16, 0)


@dataclass(frozen=True)
class VirtualTrade:
    """One paper trade. / 一笔纸面交易。"""

    date: str
    side: str
    asset: str
    quantity: float
    price: float
    value: float
    reason: str


@dataclass(frozen=True)
class PortfolioDay:
    """End-of-day portfolio state. / 每日收盘组合状态。"""

    date: str
    arena_signal: str
    asset: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    quantity: float
    cash: float
    portfolio_value: float
    daily_pnl: float
    daily_return: float
    cumulative_return: float
    drawdown: float
    open_positions: dict


@dataclass(frozen=True)
class PortfolioMetrics:
    """Portfolio metrics required by MQ-PAPER-TRADING-001. / 纸面组合所需指标。"""

    portfolio_value: float
    return_pct: float
    drawdown_pct: float
    win_rate: Optional[float]
    profit_factor: Optional[float]
    cash: float
    open_positions: dict
    total_trades: int
    trading_days: int


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def default_paths() -> dict[str, Path]:
    base = _base_dir()
    return {
        "trial_records": base / "data" / "arena" / "historical_trial_results.jsonl",
        "rklx": base / "data" / "historical" / "RKLX_1m.csv",
        "rklz": base / "data" / "historical" / "RKLZ_1m.csv",
        "portfolio_history": base / "data" / "portfolio" / "portfolio_history.jsonl",
        "trade_history": base / "data" / "portfolio" / "trade_history.jsonl",
        "daily_report": base / "reports" / "portfolio" / "daily_portfolio_report.md",
    }


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")


def _load_price_map(path: Path) -> Dict[str, Dict[str, float]]:
    prices: Dict[str, Dict[str, float]] = {}
    if not path.exists():
        return prices
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                ts = _parse_time(row["time_key"])
                if not (RTH_START <= ts.time() < RTH_END):
                    continue
                day = ts.strftime("%Y-%m-%d")
                minute = ts.strftime("%Y-%m-%d %H:%M:00")
                close = float(row["close"])
            except (KeyError, ValueError):
                continue
            prices.setdefault(day, {})[minute] = close
    return prices


def _last_price_for_day(price_map: Dict[str, Dict[str, float]], day: str) -> Optional[float]:
    rows = price_map.get(day) or {}
    if not rows:
        return None
    return rows[sorted(rows)[-1]]


def _price_at_or_after(price_map: Dict[str, Dict[str, float]], day: str, signal_time: str) -> Optional[float]:
    rows = price_map.get(day) or {}
    if not rows:
        return None
    target = signal_time[:16] + ":00"
    if target in rows:
        return rows[target]
    for key in sorted(rows):
        if key >= target:
            return rows[key]
    return _last_price_for_day(price_map, day)


def _asset_for_signal(signal: str) -> str:
    value = str(signal or "HOLD").upper()
    if value == "LONG":
        return "RKLX"
    if value == "SHORT":
        return "RKLZ"
    return "Cash"


def _pf(values: Iterable[float]) -> Optional[float]:
    rows = list(values)
    wins = sum(value for value in rows if value > 0)
    losses = abs(sum(value for value in rows if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _win_rate(values: Iterable[float]) -> Optional[float]:
    rows = [value for value in values if value != 0]
    if not rows:
        return None
    return sum(1 for value in rows if value > 0) / len(rows)


def _safe_round(value: Optional[float], digits: int = 4):
    if value is None:
        return None
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    return round(float(value), digits)


def simulate_portfolio(
    trial_records: Iterable[dict],
    rklx_prices: Dict[str, Dict[str, float]],
    rklz_prices: Dict[str, Dict[str, float]],
    initial_capital: float = INITIAL_CAPITAL,
) -> tuple[List[PortfolioDay], List[VirtualTrade], PortfolioMetrics]:
    """Run daily paper trading simulation. / 运行每日纸面组合模拟。"""

    cash = float(initial_capital)
    peak = cash
    history: List[PortfolioDay] = []
    trades: List[VirtualTrade] = []
    daily_pnls: List[float] = []

    price_maps = {"RKLX": rklx_prices, "RKLZ": rklz_prices}
    for row in sorted(trial_records, key=lambda item: item.get("date", "")):
        day = str(row.get("date") or "")
        signal = str(row.get("champion_signal") or "HOLD").upper()
        asset = _asset_for_signal(signal)
        signal_time = str(row.get("signal_time") or f"{day} 10:30:00")
        start_value = cash
        entry_price = None
        exit_price = None
        quantity = 0.0

        if asset != "Cash":
            price_map = price_maps.get(asset, {})
            entry_price = _price_at_or_after(price_map, day, signal_time)
            exit_price = _last_price_for_day(price_map, day)
            if entry_price and exit_price and entry_price > 0:
                quantity = cash / entry_price
                trades.append(VirtualTrade(day, "BUY", asset, round(quantity, 6), round(entry_price, 4), round(cash, 4), f"Arena {signal}"))
                cash = quantity * exit_price
                trades.append(VirtualTrade(day, "SELL", asset, round(quantity, 6), round(exit_price, 4), round(cash, 4), "End-of-day paper flatten"))
            else:
                asset = "Cash"
                quantity = 0.0

        portfolio_value = cash
        daily_pnl = portfolio_value - start_value
        daily_pnls.append(daily_pnl)
        peak = max(peak, portfolio_value)
        drawdown = (portfolio_value - peak) / peak if peak > 0 else 0.0
        history.append(
            PortfolioDay(
                day,
                signal,
                asset,
                None if entry_price is None else round(entry_price, 4),
                None if exit_price is None else round(exit_price, 4),
                round(quantity, 6),
                round(cash, 4),
                round(portfolio_value, 4),
                round(daily_pnl, 4),
                round(daily_pnl / start_value, 6) if start_value else 0.0,
                round((portfolio_value - initial_capital) / initial_capital, 6) if initial_capital else 0.0,
                round(drawdown, 6),
                {},
            )
        )

    last = history[-1] if history else None
    metrics = PortfolioMetrics(
        portfolio_value=round(last.portfolio_value if last else initial_capital, 4),
        return_pct=round(((last.portfolio_value if last else initial_capital) - initial_capital) / initial_capital * 100.0, 4),
        drawdown_pct=round((last.drawdown if last else 0.0) * 100.0, 4),
        win_rate=_safe_round(_win_rate(daily_pnls), 4),
        profit_factor=_safe_round(_pf(daily_pnls), 4),
        cash=round(last.cash if last else initial_capital, 4),
        open_positions=last.open_positions if last else {},
        total_trades=len(trades),
        trading_days=len(history),
    )
    return history, trades, metrics


def render_daily_report(history: List[PortfolioDay], trades: List[VirtualTrade], metrics: PortfolioMetrics) -> str:
    """Render daily_portfolio_report.md. / 生成每日纸面组合报告。"""

    last = history[-1] if history else None
    recent = history[-10:]
    lines = [
        "# Daily Portfolio Report",
        "",
        "Mode: Paper Trading Only",
        f"Initial Capital: ${INITIAL_CAPITAL:,.2f}",
        f"Portfolio Value: ${metrics.portfolio_value:,.2f}",
        f"Return: {metrics.return_pct:+.2f}%",
        f"Drawdown: {metrics.drawdown_pct:+.2f}%",
        f"Win Rate: {_safe_round(metrics.win_rate, 4)}",
        f"Profit Factor: {_safe_round(metrics.profit_factor, 4)}",
        f"Cash: ${metrics.cash:,.2f}",
        f"Open Positions: {metrics.open_positions if metrics.open_positions else 'None'}",
        f"Trading Days: {metrics.trading_days}",
        f"Total Trades: {metrics.total_trades}",
        "",
        "Answer:",
        _answer_line(metrics),
        "",
        "Latest Day:",
    ]
    if last:
        lines.extend(
            [
                f"- Date: {last.date}",
                f"- Arena Signal: {last.arena_signal}",
                f"- Asset: {last.asset}",
                f"- Daily PnL: ${last.daily_pnl:,.2f}",
                f"- Daily Return: {last.daily_return * 100:+.2f}%",
            ]
        )
    else:
        lines.append("- No portfolio history yet.")
    lines.extend(
        [
            "",
            "Recent Portfolio History:",
            "| Date | Signal | Asset | Portfolio Value | Daily PnL | Drawdown |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    for day in recent:
        lines.append(
            f"| {day.date} | {day.arena_signal} | {day.asset} | "
            f"${day.portfolio_value:,.2f} | ${day.daily_pnl:,.2f} | {day.drawdown * 100:+.2f}% |"
        )
    lines.extend(
        [
            "",
            "Paper Assumption:",
            "- Each day uses the Arena signal at signal_time.",
            "- LONG buys RKLX, SHORT buys RKLZ, HOLD stays in Cash.",
            "- Positions are flattened to Cash at the same day's close.",
            "- This is a research ledger, not live trading advice or execution.",
            "",
        ]
    )
    return "\n".join(lines)


def _answer_line(metrics: PortfolioMetrics) -> str:
    if metrics.portfolio_value > INITIAL_CAPITAL:
        return f"Yes. Following Arena every day would end at ${metrics.portfolio_value:,.2f}, above the initial $100,000."
    if metrics.portfolio_value < INITIAL_CAPITAL:
        return f"No. Following Arena every day would end at ${metrics.portfolio_value:,.2f}, below the initial $100,000."
    return "Flat. Following Arena every day would end exactly at the initial capital."


def _write_jsonl(path: Path, rows: Iterable[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = list(rows)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in data) + ("\n" if data else ""), encoding="utf-8")
    return path


def write_outputs(
    history: List[PortfolioDay],
    trades: List[VirtualTrade],
    metrics: PortfolioMetrics,
    portfolio_history_path: Path | None = None,
    trade_history_path: Path | None = None,
    daily_report_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Write portfolio_history, trade_history, and report. / 写组合历史、交易历史和报告。"""

    paths = default_paths()
    history_path = portfolio_history_path or paths["portfolio_history"]
    trade_path = trade_history_path or paths["trade_history"]
    report_path = daily_report_path or paths["daily_report"]
    _write_jsonl(history_path, [asdict(row) for row in history])
    _write_jsonl(trade_path, [asdict(row) for row in trades])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_daily_report(history, trades, metrics), encoding="utf-8")
    return history_path, trade_path, report_path


def run_engine(initial_capital: float = INITIAL_CAPITAL) -> tuple[List[PortfolioDay], List[VirtualTrade], PortfolioMetrics]:
    """Load default data and simulate. / 读取默认数据并模拟。"""

    paths = default_paths()
    return simulate_portfolio(
        _load_jsonl(paths["trial_records"]),
        _load_price_map(paths["rklx"]),
        _load_price_map(paths["rklz"]),
        initial_capital=initial_capital,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Arena virtual paper portfolio.")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    args = parser.parse_args()
    history, trades, metrics = run_engine(args.initial_capital)
    history_path, trade_path, report_path = write_outputs(history, trades, metrics)
    print(f"[virtual_portfolio] wrote {history_path}")
    print(f"[virtual_portfolio] wrote {trade_path}")
    print(f"[virtual_portfolio] wrote {report_path}")
    print(_answer_line(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
