"""
MagicQuant strategy_miner_multi_run.py
VERSION : v0.2.0
DEPENDS : pandas, research.vectorbt_lab.optuna_strategy_miner, research.vectorbt_lab._tg_notify(optional)

Research-only multi-seed validation for RKLB -> RKLX/RKLZ strategy templates.
研究专用多 seed 验证器：滚动 OOS、跨 seed 稳定性、交易流水与晋级门槛。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from optuna_strategy_miner import (
    INIT_CASH,
    SIGNAL_FUNCS,
    load_market,
    optimize_strategy,
    simulate,
)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1]
OUT_DIR = BASE_DIR / "output" / "strategy_miner_multi_run"
SCORECARD_PATH = PROJECT_ROOT / "docs" / "STRATEGY_SCORECARD.md"
ET = ZoneInfo("America/New_York")

DEFAULT_SEEDS = "11,22,33,44,55"
DEEP_SEEDS = "11,22,33,44,55,66,77,88,99,111"
DEFAULT_TRIALS = 80
DEFAULT_FOLDS = 5
DEFAULT_OOS_DAYS = 20
DEFAULT_FOLD_STEP_DAYS = 10

MIN_HOLDOUT_TRADES = 15
MIN_POSITIVE_OOS_CELLS = 18
MIN_POSITIVE_FOLDS = 3
MIN_PROFIT_FACTOR = 1.10
MIN_SIGNAL_DENSITY_PER_DAY = 0.30
MIN_SHARPE = 0.50
MAX_P_VALUE = 0.20


@dataclass(frozen=True)
class OOSFold:
    fold: int
    train_days: set
    oos_days: set
    start_day: object
    end_day: object


@dataclass
class RunResult:
    seed: int
    strategy: str
    params: dict
    train: dict
    oos: dict
    full: dict
    rank_score: float
    fold_summaries: list[dict]


def _num(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _stdev(values: list[float]) -> float:
    return float(statistics.stdev(values)) if len(values) >= 2 else 0.0


def _one_sided_p_value(values: list[float]) -> float:
    """Approximate one-sample positive-mean p-value. / 近似单样本正收益 p 值。"""
    clean = [float(v) for v in values if math.isfinite(float(v))]
    if len(clean) < 2:
        return 1.0
    sd = _stdev(clean)
    if sd <= 0:
        return 0.0 if _mean(clean) > 0 else 1.0
    z = _mean(clean) / (sd / math.sqrt(len(clean)))
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _trade_sharpe(values: list[float]) -> float:
    clean = [float(v) for v in values if math.isfinite(float(v))]
    sd = _stdev(clean)
    if not clean or sd <= 0:
        return 0.0
    return _mean(clean) / sd * math.sqrt(len(clean))


def rolling_holdout_folds(
    bars: pd.DataFrame,
    folds: int = DEFAULT_FOLDS,
    oos_days: int = DEFAULT_OOS_DAYS,
    step_days: int = DEFAULT_FOLD_STEP_DAYS,
) -> list[OOSFold]:
    """Build rolling OOS folds with no train/OOS overlap. / 构建训练与 OOS 不重叠的滚动窗口。"""
    days = list(bars["et_date"].drop_duplicates())
    if oos_days <= 0 or folds <= 0:
        return []
    last_start = len(days) - oos_days
    starts = [last_start - step_days * (folds - 1 - idx) for idx in range(folds)]
    out: list[OOSFold] = []
    for fold_idx, start in enumerate(starts, 1):
        if start <= 0 or start + oos_days > len(days):
            continue
        train_days = set(days[:start])
        oos = days[start: start + oos_days]
        out.append(OOSFold(fold_idx, train_days, set(oos), oos[0], oos[-1]))
    return out


def _bars_for_days(bars: pd.DataFrame, days: set) -> pd.DataFrame:
    return bars[bars["et_date"].isin(days)].reset_index(drop=True)


def _combine_summaries(fold_summaries: list[dict], trades: list[dict], oos_days: int) -> dict:
    pnls = [_num(item.get("fee_adjusted_pnl")) for item in fold_summaries]
    trade_pnls = [_num(trade.get("net_pnl")) for trade in trades]
    wins = [pnl for pnl in trade_pnls if pnl > 0]
    losses = [pnl for pnl in trade_pnls if pnl <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    trade_count = len(trades)
    total_pnl = sum(pnls)
    return {
        "windows": len(fold_summaries),
        "positive_folds": sum(1 for pnl in pnls if pnl > 0),
        "fee_adjusted_pnl": total_pnl,
        "return_pct": total_pnl / INIT_CASH * 100.0,
        "trade_count": trade_count,
        "win_rate": len(wins) / trade_count * 100.0 if trade_count else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        "max_drawdown": min((_num(item.get("max_drawdown")) for item in fold_summaries), default=0.0),
        "worst_window_pnl": min(pnls) if pnls else 0.0,
        "avg_window_pnl": _mean(pnls),
        "p_value": _one_sided_p_value(trade_pnls),
        "trade_sharpe": _trade_sharpe(trade_pnls),
        "signal_density_per_day": trade_count / max(1, oos_days),
    }


def _rank_score(summary: dict) -> float:
    """Rank by OOS quality. / 按滚动 OOS 质量排序。"""
    trades = _num(summary.get("trade_count"))
    if trades < MIN_HOLDOUT_TRADES:
        return -100_000.0 + trades
    return (
        _num(summary.get("fee_adjusted_pnl"))
        + _num(summary.get("profit_factor")) * 30.0
        + _num(summary.get("positive_folds")) * 150.0
        + _num(summary.get("trade_sharpe")) * 80.0
        + _num(summary.get("max_drawdown")) * 25.0
    )


def _summary_row(summary: dict, prefix: str) -> dict:
    return {
        f"{prefix}_pnl": round(_num(summary.get("fee_adjusted_pnl")), 2),
        f"{prefix}_return_pct": round(_num(summary.get("return_pct")), 2),
        f"{prefix}_trades": int(_num(summary.get("trade_count"))),
        f"{prefix}_win_rate": round(_num(summary.get("win_rate")), 2),
        f"{prefix}_profit_factor": round(_num(summary.get("profit_factor")), 2),
        f"{prefix}_max_drawdown": round(_num(summary.get("max_drawdown", summary.get("avg_max_drawdown", 0.0))), 2),
        f"{prefix}_positive_folds": int(_num(summary.get("positive_folds"))),
        f"{prefix}_p_value": round(_num(summary.get("p_value"), 1.0), 4),
        f"{prefix}_trade_sharpe": round(_num(summary.get("trade_sharpe")), 2),
        f"{prefix}_signal_density_per_day": round(_num(summary.get("signal_density_per_day")), 3),
    }


def _phase_trades(seed: int, strategy: str, phase: str, trades: list[dict], fold: int | None = None) -> list[dict]:
    out = []
    for trade in trades:
        row = dict(trade)
        row["seed"] = seed
        row["strategy"] = strategy
        row["phase"] = phase
        if fold is not None:
            row["fold"] = fold
        out.append(row)
    return out


def evaluate_params_on_folds(
    bars: pd.DataFrame,
    strategy: str,
    params: dict,
    folds: list[OOSFold],
) -> tuple[dict, list[dict], list[dict]]:
    fold_summaries: list[dict] = []
    all_trades: list[dict] = []
    for fold in folds:
        oos_bars = _bars_for_days(bars, fold.oos_days)
        summary, trades = simulate(oos_bars, strategy, params)
        summary["fold"] = fold.fold
        summary["start_day"] = str(fold.start_day)
        summary["end_day"] = str(fold.end_day)
        fold_summaries.append(summary)
        all_trades.extend(_phase_trades(0, strategy, "oos", trades, fold.fold))
    combined = _combine_summaries(fold_summaries, all_trades, len(folds) * (len(next(iter(folds)).oos_days) if folds else 0))
    return combined, fold_summaries, all_trades


def run_seed(seed: int, trials: int, bars: pd.DataFrame, folds: list[OOSFold], seed_dir: Path) -> tuple[list[RunResult], list[dict]]:
    if not folds:
        raise ValueError("no rolling OOS folds available")
    initial_train = _bars_for_days(bars, folds[0].train_days)
    if initial_train.empty:
        raise ValueError("initial training window is empty")
    results: list[RunResult] = []
    trades_out: list[dict] = []
    seed_dir.mkdir(parents=True, exist_ok=True)
    for offset, strategy in enumerate(SIGNAL_FUNCS, 1):
        print(f"[multi] seed={seed} strategy={strategy} trials={trials}")
        spec = optimize_strategy(initial_train, strategy, trials, seed + offset)
        oos_summary, fold_summaries, oos_trades = evaluate_params_on_folds(bars, strategy, spec.params, folds)
        full_summary, full_trades = simulate(bars, strategy, spec.params)
        results.append(
            RunResult(
                seed=seed,
                strategy=strategy,
                params=spec.params,
                train=spec.walk_summary,
                oos=oos_summary,
                full=full_summary,
                rank_score=_rank_score(oos_summary),
                fold_summaries=fold_summaries,
            )
        )
        for trade in oos_trades:
            trade["seed"] = seed
            trade["phase"] = "oos"
            trades_out.append(trade)
        trades_out.extend(_phase_trades(seed, strategy, "full", full_trades))
    rows = result_rows(results)
    write_seed_report(seed_dir, seed, rows)
    return results, trades_out


def result_rows(results: list[RunResult]) -> list[dict]:
    ranked = sorted(results, key=lambda item: item.rank_score, reverse=True)
    rows = []
    for rank, item in enumerate(ranked, 1):
        row = {
            "seed": item.seed,
            "rank": rank,
            "strategy": item.strategy,
            "rank_score": round(item.rank_score, 2),
            "params": json.dumps(item.params, ensure_ascii=False, sort_keys=True),
            "fold_summaries": json.dumps(item.fold_summaries, ensure_ascii=False),
        }
        row.update(_summary_row(item.train, "train"))
        row.update(_summary_row(item.oos, "oos"))
        row.update(_summary_row(item.full, "full"))
        rows.append(row)
    return rows


def _param_distance(items: list[dict]) -> float:
    params = [json.loads(row["params"]) if isinstance(row["params"], str) else row["params"] for row in items]
    if len(params) < 2:
        return 0.0
    keys = sorted({key for payload in params for key, val in payload.items() if isinstance(val, (int, float))})
    if not keys:
        return 0.0
    ranges = {}
    for key in keys:
        vals = [float(payload.get(key, 0.0)) for payload in params]
        span = max(vals) - min(vals)
        ranges[key] = span if span > 0 else 1.0
    distances = []
    for i in range(len(params)):
        for j in range(i + 1, len(params)):
            total = 0.0
            for key in keys:
                total += ((float(params[i].get(key, 0.0)) - float(params[j].get(key, 0.0))) / ranges[key]) ** 2
            distances.append(math.sqrt(total))
    return round(_median(distances), 4)


def cross_seed_oos_matrix(rows: list[dict], bars: pd.DataFrame, folds: list[OOSFold]) -> dict[str, dict]:
    """Apply every seed's top params to every OOS window. / 用每个 seed 的参数跑每个 OOS 窗口。"""
    out: dict[str, dict] = {}
    by_strategy: dict[str, list[dict]] = {}
    for row in rows:
        by_strategy.setdefault(str(row["strategy"]), []).append(row)
    for strategy, items in by_strategy.items():
        cells = []
        for row in items:
            params = json.loads(row["params"])
            for fold in folds:
                summary, _trades = simulate(_bars_for_days(bars, fold.oos_days), strategy, params)
                pnl = _num(summary.get("fee_adjusted_pnl"))
                cells.append({
                    "strategy": strategy,
                    "seed": int(row["seed"]),
                    "fold": fold.fold,
                    "pnl": round(pnl, 2),
                    "trades": int(_num(summary.get("trade_count"))),
                    "positive": pnl > 0,
                })
        out[strategy] = {
            "cells": cells,
            "positive_cells": sum(1 for cell in cells if cell["positive"]),
            "total_cells": len(cells),
            "median_cell_pnl": round(_median([_num(cell["pnl"]) for cell in cells]), 2),
        }
    return out


def aggregate_rows(rows: list[dict], cross_matrix: dict[str, dict] | None = None) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row["strategy"]), []).append(row)
    out = []
    for strategy, items in grouped.items():
        oos_pnls = [_num(row["oos_pnl"]) for row in items]
        oos_trades = [_num(row["oos_trades"]) for row in items]
        cross = (cross_matrix or {}).get(strategy, {})
        out.append({
            "strategy": strategy,
            "runs": len(items),
            "top1_count": sum(1 for row in items if int(row["rank"]) == 1),
            "top2_count": sum(1 for row in items if int(row["rank"]) <= 2),
            "positive_seed_count": sum(1 for row in items if _num(row["oos_pnl"]) > 0),
            "median_positive_folds": round(_median([_num(row["oos_positive_folds"]) for row in items]), 2),
            "mean_oos_pnl": round(_mean(oos_pnls), 2),
            "median_oos_pnl": round(_median(oos_pnls), 2),
            "worst_seed_oos_pnl": round(min(oos_pnls), 2) if oos_pnls else 0.0,
            "median_oos_trades": round(_median(oos_trades), 2),
            "median_profit_factor": round(_median([_num(row["oos_profit_factor"]) for row in items]), 2),
            "median_p_value": round(_median([_num(row["oos_p_value"], 1.0) for row in items]), 4),
            "median_trade_sharpe": round(_median([_num(row["oos_trade_sharpe"]) for row in items]), 2),
            "median_signal_density": round(_median([_num(row["oos_signal_density_per_day"]) for row in items]), 3),
            "mean_full_pnl": round(_mean([_num(row["full_pnl"]) for row in items]), 2),
            "cross_positive_cells": int(cross.get("positive_cells", 0)),
            "cross_total_cells": int(cross.get("total_cells", 0)),
            "cross_median_cell_pnl": _num(cross.get("median_cell_pnl")),
            "median_param_l2_distance": _param_distance(items),
        })
    return sorted(
        out,
        key=lambda row: (
            row["cross_positive_cells"],
            row["median_positive_folds"],
            row["median_oos_pnl"],
            row["top1_count"],
        ),
        reverse=True,
    )


def promotion_check(best: dict, live_relevance_passed: bool = False) -> tuple[bool, list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []

    def gate(ok: bool, label: str) -> None:
        (passed if ok else failed).append(label)

    gate(_num(best.get("cross_positive_cells")) >= MIN_POSITIVE_OOS_CELLS, f"cross OOS positive cells >= {MIN_POSITIVE_OOS_CELLS}")
    gate(_num(best.get("median_positive_folds")) >= MIN_POSITIVE_FOLDS, f"median positive folds >= {MIN_POSITIVE_FOLDS}")
    gate(_num(best.get("median_oos_trades")) >= MIN_HOLDOUT_TRADES, f"median OOS trades >= {MIN_HOLDOUT_TRADES}")
    gate(_num(best.get("median_profit_factor")) > MIN_PROFIT_FACTOR, f"median PF > {MIN_PROFIT_FACTOR}")
    gate(
        _num(best.get("median_p_value"), 1.0) < MAX_P_VALUE or _num(best.get("median_trade_sharpe")) > MIN_SHARPE,
        f"p < {MAX_P_VALUE} or trade Sharpe > {MIN_SHARPE}",
    )
    gate(_num(best.get("median_signal_density")) >= MIN_SIGNAL_DENSITY_PER_DAY, f"signal density/day >= {MIN_SIGNAL_DENSITY_PER_DAY}")
    gate(live_relevance_passed, "live relevance replay passed")
    return not failed, passed, failed


def best_decision(aggregate: list[dict], live_relevance_passed: bool = False) -> tuple[str, str, list[str], list[str]]:
    if not aggregate:
        return "reject", "No valid research result.", [], ["no aggregate result"]
    best = aggregate[0]
    ok, passed, failed = promotion_check(best, live_relevance_passed=live_relevance_passed)
    if ok:
        return (
            "shadow_candidate",
            f"{best['strategy']} passed rolling OOS, cross-seed stability, and live relevance gates. Shadow only; no live replacement.",
            passed,
            failed,
        )
    if failed == ["live relevance replay passed"]:
        return (
            "research_only_pending_live_relevance",
            f"{best['strategy']} passed research gates but still needs live-relevance replay before shadow.",
            passed,
            failed,
        )
    return (
        "research_only",
        f"{best['strategy']} remains research-only; one or more promotion gates failed.",
        passed,
        failed,
    )


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_seed_report(seed_dir: Path, seed: int, rows: list[dict]) -> Path:
    path = seed_dir / "seed_report.md"
    lines = [
        f"# Strategy Miner Seed {seed}",
        "",
        "Research-only. This seed report does not change live trading.",
        "",
        "| Rank | Strategy | Rolling OOS PnL | OOS Trades | Positive Folds | Full PnL | Params |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['rank']} | {row['strategy']} | ${row['oos_pnl']:.2f} | {row['oos_trades']} | {row['oos_positive_folds']} | ${row['full_pnl']:.2f} | `{row['params']}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _fold_table(folds: list[OOSFold]) -> list[str]:
    lines = [
        "| Fold | Train Days | OOS Start | OOS End | OOS Days |",
        "|---:|---:|---|---|---:|",
    ]
    for fold in folds:
        lines.append(f"| {fold.fold} | {len(fold.train_days)} | {fold.start_day} | {fold.end_day} | {len(fold.oos_days)} |")
    return lines


def write_report(
    out_dir: Path,
    rows: list[dict],
    aggregate: list[dict],
    cross_matrix: dict[str, dict],
    decision: str,
    reason: str,
    passed: list[str],
    failed: list[str],
    folds: list[OOSFold],
    seeds: list[int],
    trials: int,
) -> Path:
    report_path = out_dir / "strategy_miner_multi_run_report.md"
    best = aggregate[0] if aggregate else {}
    lines = [
        "# VectorBT/Optuna Rolling OOS Strategy Validation",
        "",
        "VERSION: v0.2.0",
        "DEPENDS: optuna_strategy_miner.py, data/historical/RKLB_1m.csv, RKLX_1m.csv, RKLZ_1m.csv",
        "",
        "This is research-only. It does not change live focus strategy, Telegram trading signals, risk controls, or watchlist.",
        "",
        "## Plain-Language Summary",
        "",
        f"- Run size: {len(seeds)} seeds x {trials} trials x {len(SIGNAL_FUNCS)} templates.",
        f"- OOS method: {len(folds)} rolling windows; each window uses future bars not present in that fold's train set.",
        f"- Decision: {decision}.",
        f"- Interpretation: {reason}",
        "",
        "## Rolling OOS Windows",
        "",
        *_fold_table(folds),
        "",
        "## Stability Ranking",
        "",
        "| Rank | Strategy | Cross + Cells | Median OOS | Worst Seed OOS | Median Trades | Median PF | p-value | Sharpe | Density/day | Param L2 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(aggregate, 1):
        lines.append(
            f"| {rank} | {row['strategy']} | {row['cross_positive_cells']}/{row['cross_total_cells']} | ${row['median_oos_pnl']:.2f} | ${row['worst_seed_oos_pnl']:.2f} | {row['median_oos_trades']:.1f} | {row['median_profit_factor']:.2f} | {row['median_p_value']:.3f} | {row['median_trade_sharpe']:.2f} | {row['median_signal_density']:.2f} | {row['median_param_l2_distance']:.2f} |"
        )
    lines += [
        "",
        "## Promotion Gate",
        "",
        "Passed:",
        *[f"- {item}" for item in passed],
        "",
        "Failed / pending:",
        *[f"- {item}" for item in failed],
        "",
        "Important: research OOS profit alone is not enough. Live-relevance replay must pass before a candidate enters shadow mode.",
        "",
        "## Cross-Seed OOS Matrix",
    ]
    for strategy, matrix in cross_matrix.items():
        lines += [
            "",
            f"### {strategy}",
            "",
            f"- Positive cells: {matrix['positive_cells']}/{matrix['total_cells']}",
            f"- Median cell PnL: ${matrix['median_cell_pnl']:.2f}",
        ]
    lines += [
        "",
        "## Files",
        "",
        f"- Per-run ranking: `{out_dir / 'strategy_miner_multi_run_rows.csv'}`",
        f"- Aggregate ranking: `{out_dir / 'strategy_miner_multi_run_aggregate.csv'}`",
        f"- Trade ledger: `{out_dir / 'strategy_miner_multi_run_trades.csv'}`",
        f"- Cross-seed cells: `{out_dir / 'strategy_miner_multi_run_cross_seed.csv'}`",
    ]
    if best:
        lines += [
            "",
            "## Current Best",
            "",
            f"- Template: {best['strategy']}",
            f"- Median rolling OOS PnL: ${best['median_oos_pnl']:.2f}",
            f"- Cross-seed positive cells: {best['cross_positive_cells']}/{best['cross_total_cells']}",
            f"- Action: {decision}; never auto-replace live strategy.",
        ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def write_summary_json(out_dir: Path, report_path: Path, aggregate: list[dict], decision: str, reason: str, passed: list[str], failed: list[str]) -> Path:
    best = aggregate[0] if aggregate else {}
    path = out_dir / "strategy_miner_multi_run_summary.json"
    payload = {
        "version": "v0.2.0",
        "report_path": str(report_path),
        "decision": decision,
        "reason": reason,
        "passed": passed,
        "failed": failed,
        "best": best,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_scorecard(report_path: Path, aggregate: list[dict], decision: str, reason: str, seeds: list[int], trials: int, folds: list[OOSFold]) -> None:
    best = aggregate[0] if aggregate else {}
    SCORECARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = SCORECARD_PATH.read_text(encoding="utf-8") if SCORECARD_PATH.exists() else "# Strategy Scorecard\n"
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
    block = [
        "",
        f"## {now} - VectorBT/Optuna rolling OOS validation v0.2.0",
        "",
        "- Scope: research-only; no live focus strategy, Telegram signal logic, risk control, or watchlist changed.",
        f"- Run: {len(seeds)} seeds x {trials} trials, rolling OOS folds={len(folds)}.",
        f"- Decision: {decision}.",
        f"- Plain-language conclusion: {reason}",
    ]
    if best:
        block.extend([
            f"- Best template: {best['strategy']}.",
            f"- Median OOS PnL: ${best['median_oos_pnl']:.2f}; cross positive cells: {best['cross_positive_cells']}/{best['cross_total_cells']}; median trades: {best['median_oos_trades']:.1f}.",
        ])
    block.append(f"- Full detail: `{report_path}`.")
    SCORECARD_PATH.write_text(existing + "\n".join(block) + "\n", encoding="utf-8")


def build_telegram_text(summary: dict) -> str:
    best = summary.get("best") or {}
    if not best:
        return "VectorBT/Optuna rolling OOS completed, but no valid candidate was produced."
    return (
        "VectorBT/Optuna rolling OOS completed\n"
        f"Best: {best.get('strategy')}\n"
        f"OOS median PnL: ${_num(best.get('median_oos_pnl')):.2f}\n"
        f"Cross-seed cells: {best.get('cross_positive_cells')}/{best.get('cross_total_cells')}\n"
        f"Trades: {best.get('median_oos_trades')} | PF: {best.get('median_profit_factor')}\n"
        f"Decision: {summary.get('decision')}\n"
        f"Meaning: {summary.get('reason')}\n"
        f"Report: {summary.get('report_path')}"
    )


def send_telegram(summary_path: Path) -> bool:
    try:
        from _tg_notify import send_review

        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        return bool(send_review(build_telegram_text(payload)))
    except Exception as exc:
        print(f"[multi] telegram skipped: {exc}")
        return False


def parse_seeds(raw: str) -> list[int]:
    seeds = []
    for part in str(raw).split(","):
        part = part.strip()
        if part:
            seeds.append(int(part))
    return seeds or [11]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run rolling OOS multi-seed RKLB strategy validation.")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS, help="Trials per template per seed.")
    parser.add_argument("--seeds", default=DEFAULT_SEEDS, help="Comma-separated seeds.")
    parser.add_argument("--folds", type=int, default=DEFAULT_FOLDS, help="Rolling OOS fold count.")
    parser.add_argument("--oos-days", type=int, default=DEFAULT_OOS_DAYS, help="Trading days per OOS fold.")
    parser.add_argument("--fold-step-days", type=int, default=DEFAULT_FOLD_STEP_DAYS, help="Distance between OOS fold starts.")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--telegram", action="store_true", help="Send personal Telegram summary.")
    parser.add_argument("--scorecard", action="store_true", help="Append summary to docs/STRATEGY_SCORECARD.md.")
    parser.add_argument("--live-relevance-passed", action="store_true", help="Allow shadow promotion only after external live-relevance replay passes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seeds = parse_seeds(args.seeds)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bars = load_market()
    folds = rolling_holdout_folds(bars, args.folds, args.oos_days, args.fold_step_days)
    if len(folds) < args.folds:
        print(f"[multi] warning: requested {args.folds} folds, built {len(folds)} folds")
    all_rows: list[dict] = []
    all_trades: list[dict] = []
    for seed in seeds:
        results, trades = run_seed(seed, args.trials, bars, folds, out_dir / f"seed_{seed}")
        all_rows.extend(result_rows(results))
        all_trades.extend(trades)
    cross_matrix = cross_seed_oos_matrix(all_rows, bars, folds)
    aggregate = aggregate_rows(all_rows, cross_matrix)
    decision, reason, passed, failed = best_decision(aggregate, live_relevance_passed=args.live_relevance_passed)
    report_path = write_report(out_dir, all_rows, aggregate, cross_matrix, decision, reason, passed, failed, folds, seeds, args.trials)
    summary_path = write_summary_json(out_dir, report_path, aggregate, decision, reason, passed, failed)

    write_csv(out_dir / "strategy_miner_multi_run_rows.csv", all_rows, [
        "seed", "rank", "strategy", "rank_score",
        "train_pnl", "train_return_pct", "train_trades", "train_win_rate", "train_profit_factor", "train_max_drawdown",
        "oos_pnl", "oos_return_pct", "oos_trades", "oos_win_rate", "oos_profit_factor", "oos_max_drawdown",
        "oos_positive_folds", "oos_p_value", "oos_trade_sharpe", "oos_signal_density_per_day",
        "full_pnl", "full_return_pct", "full_trades", "full_win_rate", "full_profit_factor", "full_max_drawdown",
        "params", "fold_summaries",
    ])
    write_csv(out_dir / "strategy_miner_multi_run_aggregate.csv", aggregate, [
        "strategy", "runs", "top1_count", "top2_count", "positive_seed_count",
        "median_positive_folds", "mean_oos_pnl", "median_oos_pnl", "worst_seed_oos_pnl",
        "median_oos_trades", "median_profit_factor", "median_p_value", "median_trade_sharpe",
        "median_signal_density", "mean_full_pnl", "cross_positive_cells", "cross_total_cells",
        "cross_median_cell_pnl", "median_param_l2_distance",
    ])
    cross_rows = [cell for matrix in cross_matrix.values() for cell in matrix["cells"]]
    write_csv(out_dir / "strategy_miner_multi_run_cross_seed.csv", cross_rows, ["strategy", "seed", "fold", "pnl", "trades", "positive"])
    trade_fields = [
        "seed", "phase", "fold", "strategy", "direction", "tool", "signal_ts", "signal_et", "entry_ts", "entry_et",
        "entry_price", "qty", "stop", "target", "exit_ts", "exit_et", "exit_price", "exit_reason",
        "hold_minutes", "tool_return_pct", "mae_pct", "mfe_pct", "bars_to_mae", "bars_to_mfe",
        "gross_pnl", "fee", "net_pnl", "equity_after",
    ]
    write_csv(out_dir / "strategy_miner_multi_run_trades.csv", all_trades, trade_fields)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "strategy_miner_multi_run_report_latest.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    (OUT_DIR / "strategy_miner_multi_run_summary_latest.json").write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
    if args.scorecard:
        append_scorecard(report_path, aggregate, decision, reason, seeds, args.trials, folds)
    if args.telegram:
        send_telegram(summary_path)
    print(f"[multi] report: {report_path}")
    print(f"[multi] summary: {summary_path}")
    print(f"[multi] decision: {decision} - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
