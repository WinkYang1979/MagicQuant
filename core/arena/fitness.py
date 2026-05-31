"""
MagicQuant Arena Lite fitness scoring.
VERSION : v1.0.0
DEPENDS : dataclasses, math, pathlib, statistics, typing, config.settings

Purpose / 用途:
Score Champion Portfolio and benchmarks with the same metrics. This is a
paper-performance judge only; it does not change live strategy behavior.
用同一指标评价冠军组合与基准；仅做纸面裁判，不改变实盘策略。
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class TradeResult:
    """Closed trade PnL sample. / 已平仓交易盈亏样本。"""

    pnl: float


@dataclass(frozen=True)
class FitnessMetrics:
    """Arena Lite ranking metrics. / Arena Lite 排行指标。"""

    pnl: float
    profit_factor: Optional[float]
    win_rate: Optional[float]
    sharpe: Optional[float]
    max_drawdown: float
    expectancy: float
    fitness_score: float


def _max_drawdown(equity_curve: List[float]) -> float:
    peak = None
    worst = 0.0
    for equity in equity_curve:
        peak = equity if peak is None else max(peak, equity)
        if peak and peak > 0:
            worst = min(worst, (equity - peak) / peak)
    return worst


def _sharpe(returns: List[float]) -> Optional[float]:
    if len(returns) < 2:
        return None
    vol = pstdev(returns)
    if vol == 0:
        return None
    return mean(returns) / vol * sqrt(len(returns))


def compute_fitness(
    trades: Iterable[TradeResult | float],
    equity_curve: Iterable[float],
    period_returns: Iterable[float] | None = None,
) -> FitnessMetrics:
    """Compute PnL, PF, win rate, Sharpe, drawdown, expectancy, and score. / 计算完整裁判指标。"""

    trade_pnls = [float(item.pnl if isinstance(item, TradeResult) else item) for item in trades]
    curve = [float(item) for item in equity_curve]
    returns = [float(item) for item in (period_returns or [])]
    pnl = sum(trade_pnls)
    wins = [item for item in trade_pnls if item > 0]
    losses = [item for item in trade_pnls if item < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (None if gross_win == 0 else float("inf"))
    win_rate = len(wins) / len(trade_pnls) if trade_pnls else None
    expectancy = pnl / len(trade_pnls) if trade_pnls else 0.0
    max_drawdown = _max_drawdown(curve)
    sharpe = _sharpe(returns)

    pf_component = min(profit_factor or 0.0, 3.0) * 25.0
    win_component = (win_rate or 0.0) * 20.0
    sharpe_component = max(min(sharpe or 0.0, 3.0), -3.0) * 10.0
    expectancy_component = expectancy
    drawdown_penalty = abs(max_drawdown) * 100.0
    fitness_score = pf_component + win_component + sharpe_component + expectancy_component - drawdown_penalty

    return FitnessMetrics(
        pnl=round(pnl, 4),
        profit_factor=None if profit_factor is None else round(profit_factor, 4),
        win_rate=None if win_rate is None else round(win_rate, 4),
        sharpe=None if sharpe is None else round(sharpe, 4),
        max_drawdown=round(max_drawdown, 4),
        expectancy=round(expectancy, 4),
        fitness_score=round(fitness_score, 4),
    )


def compare_to_benchmarks(champion: FitnessMetrics, benchmarks: Dict[str, FitnessMetrics]) -> Dict[str, bool]:
    """Compare Champion Portfolio against frozen benchmarks. / 对比冠军组合与冻结基准。"""

    return {name: champion.pnl > metrics.pnl for name, metrics in benchmarks.items()}


def final_go_fail(weekly_rows: Iterable[Dict[str, float]]) -> str:
    """Return GO only when six weekly OOS rows beat main strategy and PF > 1. / 仅 6 周达标时返回 GO。"""

    rows = list(weekly_rows)
    if len(rows) != 6:
        return "FAIL"
    for row in rows:
        if row.get("champion_pnl", 0.0) <= row.get("current_main_strategy_pnl", 0.0):
            return "FAIL"
        if row.get("champion_profit_factor", 0.0) <= 1.0:
            return "FAIL"
    return "GO"


def render_weekly_arena_report(
    date_range: str,
    champion: FitnessMetrics,
    benchmarks: Dict[str, FitnessMetrics],
    reason_analysis: str,
) -> str:
    """Render weekly_arena_report.md content. / 生成 weekly_arena_report.md 内容。"""

    lines = [
        "# Weekly Arena Report",
        "",
        f"Date Range: {date_range}",
        "",
        "Champion Portfolio:",
        f"- PnL: {champion.pnl}",
        f"- Profit Factor: {champion.profit_factor}",
        f"- Max Drawdown: {champion.max_drawdown}",
        f"- Fitness Score: {champion.fitness_score}",
        "",
        "Benchmarks:",
    ]
    for name, metrics in benchmarks.items():
        lines.append(f"- {name}: PnL {metrics.pnl}, PF {metrics.profit_factor}, MDD {metrics.max_drawdown}")
    lines.extend(["", "Win/Loss Reason Analysis:", reason_analysis, ""])
    return "\n".join(lines)


def write_weekly_arena_report(
    date_range: str,
    champion: FitnessMetrics,
    benchmarks: Dict[str, FitnessMetrics],
    reason_analysis: str,
    out_path: str | Path | None = None,
) -> Path:
    """Write weekly_arena_report.md under BASE_DIR/data/arena by default. / 默认写入 BASE_DIR/data/arena。"""

    if out_path is None:
        from config.settings import BASE_DIR

        out = Path(BASE_DIR) / "data" / "arena" / "weekly_arena_report.md"
    else:
        out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_weekly_arena_report(date_range, champion, benchmarks, reason_analysis), encoding="utf-8")
    return out
