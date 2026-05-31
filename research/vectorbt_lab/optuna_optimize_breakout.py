"""
MagicQuant optuna_optimize_breakout.py
VERSION : v0.1.0
DEPENDS : optuna(optional), pandas, research.vectorbt_lab.breakout_core

Optional Optuna optimizer for isolated RKLB breakout_core research.
可选 Optuna 参数优化器，仅用于隔离 RKLB 研究，不接入实盘。
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from breakout_core import BreakoutParams, prepare_bars, run_prepared_backtest
from run_candidate_scan import load_symbol, split_train_test


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "output" / "optuna"


def _load_optuna():
    try:
        import optuna

        return optuna
    except Exception as exc:
        raise RuntimeError("Optuna is not installed. Install with: python -m pip install optuna") from exc


def objective_factory(train_bars: pd.DataFrame):
    def objective(trial):
        params = BreakoutParams(
            volume_multiplier=trial.suggest_float("volume_multiplier", 1.0, 2.5, step=0.1),
            atr_threshold=trial.suggest_float("atr_threshold", 0.10, 0.60, step=0.05),
            breakout_pct=trial.suggest_float("breakout_pct", 0.10, 0.80, step=0.05),
            stop_atr=trial.suggest_float("stop_atr", 1.0, 2.4, step=0.1),
            take_profit_atr=trial.suggest_float("take_profit_atr", 1.2, 3.2, step=0.1),
            cooldown_minutes=trial.suggest_int("cooldown_minutes", 10, 45, step=5),
        )
        result, _ = run_prepared_backtest(train_bars, params)
        if result.trade_count < 3:
            return -10_000.0
        density_penalty = max(0.0, 0.30 - result.signal_density_per_day) * 100.0
        return float(result.fee_adjusted_pnl - abs(result.max_drawdown) * 8.0 - density_penalty)

    return objective


def optimize(symbol: str, trials: int, out_dir: Path) -> Path:
    optuna = _load_optuna()
    frame = load_symbol(symbol)
    train, test = split_train_test(frame)
    train_bars = prepare_bars(train)
    test_bars = prepare_bars(test)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective_factory(train_bars), n_trials=trials, show_progress_bar=False)
    best = BreakoutParams(**study.best_params)
    train_result, _ = run_prepared_backtest(train_bars, best)
    test_result, _ = run_prepared_backtest(test_bars, best)

    out_dir.mkdir(parents=True, exist_ok=True)
    trials_path = out_dir / f"{symbol.upper()}_optuna_trials.csv"
    study.trials_dataframe().to_csv(trials_path, index=False)
    report_path = out_dir / f"{symbol.upper()}_optuna_summary.md"
    lines = [
        f"# Optuna Breakout Optimization - {symbol.upper()}",
        "",
        "This is research-only. Do not promote to live strategy without replay and scorecard review.",
        "",
        "## Best Parameters",
        "",
    ]
    for key, value in asdict(best).items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Walk-Forward Check",
        "",
        f"- Train fee-adjusted PnL: {train_result.fee_adjusted_pnl:.2f}",
        f"- Train trades: {train_result.trade_count}",
        f"- Test fee-adjusted PnL: {test_result.fee_adjusted_pnl:.2f}",
        f"- Test trades: {test_result.trade_count}",
        f"- Test max drawdown: {test_result.max_drawdown:.2f}",
        f"- Test false breakout rate: {test_result.false_breakout_rate:.2f}",
        "",
        "## Interpretation",
        "",
        "If train improves but test stays weak, treat this as overfit and do not change live rules.",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def parse_args():
    parser = argparse.ArgumentParser(description="Optional Optuna optimizer for breakout_core.")
    parser.add_argument("--symbol", default="RKLB", help="Symbol to optimize.")
    parser.add_argument("--trials", type=int, default=40, help="Number of Optuna trials.")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        path = optimize(args.symbol.upper().replace("US.", ""), args.trials, Path(args.out_dir))
    except RuntimeError as exc:
        print(f"[optuna] skipped: {exc}")
        return 2
    print(f"[optuna] wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
