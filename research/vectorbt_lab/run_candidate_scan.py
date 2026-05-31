"""
MagicQuant run_candidate_scan.py
VERSION : v0.1.0
DEPENDS : pandas, vectorbt, pyarrow, research.vectorbt_lab.breakout_core

Run breakout_core parameter scan for RKLB-style candidates.
扫描 RKLB 式 breakout_core 参数，仅用于隔离研究。
"""

from __future__ import annotations

import argparse
import itertools
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from breakout_core import BreakoutParams, prepare_bars, run_prepared_backtest
from report import compute_dna, dna_distance, write_markdown_report


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "output"
DEFAULT_TICKERS = ["RKLB", "LUNR", "ASTS", "IONQ"]


def data_path(symbol: str) -> Path:
    sym = symbol.upper().replace("US.", "")
    return DATA_DIR / sym / "1m" / f"{sym}_1m.parquet"


def load_symbol(symbol: str) -> pd.DataFrame:
    path = data_path(symbol)
    if not path.exists():
        raise FileNotFoundError(f"missing parquet for {symbol}: {path}")
    return pd.read_parquet(path)


def param_grid(full: bool = False) -> list[BreakoutParams]:
    if full:
        volume_values = [1.2, 1.5, 2.0]
        atr_values = [0.15, 0.25, 0.40]
        breakout_values = [0.20, 0.35, 0.60]
        stop_values = [1.2, 1.6]
        target_values = [1.5, 2.0, 2.5]
        cooldown_values = [15, 30]
    else:
        # Lightweight default grid for nightly research. / 夜间研究默认轻量网格。
        volume_values = [1.2, 1.5]
        atr_values = [0.15, 0.30]
        breakout_values = [0.20, 0.40]
        stop_values = [1.4]
        target_values = [1.5, 2.0]
        cooldown_values = [15, 30]

    rows = []
    for volume_multiplier, atr_threshold, breakout_pct, stop_atr, take_profit_atr, cooldown_minutes in itertools.product(
        volume_values,
        atr_values,
        breakout_values,
        stop_values,
        target_values,
        cooldown_values,
    ):
        rows.append(BreakoutParams(
            volume_multiplier=volume_multiplier,
            atr_threshold=atr_threshold,
            breakout_pct=breakout_pct,
            stop_atr=stop_atr,
            take_profit_atr=take_profit_atr,
            cooldown_minutes=cooldown_minutes,
        ))
    return rows


def split_train_test(frame: pd.DataFrame, train_frac: float = 0.6) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = frame.sort_values("timestamp").reset_index(drop=True)
    cut = max(1, min(len(data) - 1, int(len(data) * train_frac))) if len(data) > 1 else len(data)
    return data.iloc[:cut].copy(), data.iloc[cut:].copy()


def _result_row(symbol: str, result, segment: str, params: BreakoutParams) -> dict:
    return {
        "symbol": symbol.upper(),
        "segment": segment,
        **asdict(params),
        "net_profit": result.net_profit,
        "fee_adjusted_pnl": result.fee_adjusted_pnl,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "max_drawdown": result.max_drawdown,
        "trade_count": result.trade_count,
        "false_breakout_rate": result.false_breakout_rate,
        "signal_density_per_day": result.signal_density_per_day,
    }


def scan_symbol(symbol: str, frame: pd.DataFrame, full_grid: bool = False) -> list[dict]:
    output = []
    bars = prepare_bars(frame)
    for params in param_grid(full=full_grid):
        result, _trades = run_prepared_backtest(bars, params)
        output.append(_result_row(symbol, result, "full_in_sample", params))
    return output


def pick_rklb_train_params(rklb_frame: pd.DataFrame, full_grid: bool = False) -> tuple[BreakoutParams, pd.DataFrame]:
    train, _test = split_train_test(rklb_frame)
    bars = prepare_bars(train)
    rows = []
    best_params = None
    best_score = None
    for params in param_grid(full=full_grid):
        result, _trades = run_prepared_backtest(bars, params)
        rows.append(_result_row("RKLB", result, "rklb_train_grid", params))
        score = result.fee_adjusted_pnl
        if best_score is None or score > best_score:
            best_score = score
            best_params = params
    return best_params or BreakoutParams(), pd.DataFrame(rows)


def run_oos_shared_params(symbol: str, frame: pd.DataFrame, params: BreakoutParams) -> dict:
    train, test = split_train_test(frame)
    train_result, _ = run_prepared_backtest(prepare_bars(train), params)
    test_result, _ = run_prepared_backtest(prepare_bars(test), params)
    row = _result_row(symbol, test_result, "oos_test_shared_rklb_params", params)
    row["in_sample_pnl"] = train_result.fee_adjusted_pnl
    row["oos_pnl"] = test_result.fee_adjusted_pnl
    row["in_sample_trade_count"] = train_result.trade_count
    row["oos_trade_count"] = test_result.trade_count
    row["in_sample_signal_density_per_day"] = train_result.signal_density_per_day
    row["oos_signal_density_per_day"] = test_result.signal_density_per_day
    return row


def parse_args():
    parser = argparse.ArgumentParser(description="Run breakout_core candidate scan.")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS), help="Comma-separated symbols.")
    parser.add_argument("--full-grid", action="store_true", help="Run the larger research grid.")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Directory for CSV and Markdown outputs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [item.strip().upper().replace("US.", "") for item in args.tickers.split(",") if item.strip()]
    out_dir = Path(args.out_dir)
    frames = {symbol: load_symbol(symbol) for symbol in symbols}

    best_params, train_grid = pick_rklb_train_params(frames["RKLB"], full_grid=args.full_grid)
    print(f"[scan] RKLB train selected params: {asdict(best_params)}")

    rows = []
    for symbol, frame in frames.items():
        print(f"[scan] {symbol}: {len(frame)} rows")
        rows.append(run_oos_shared_params(symbol, frame, best_params))

    out_dir.mkdir(parents=True, exist_ok=True)
    results = pd.DataFrame(rows)
    results_path = out_dir / "candidate_scan.csv"
    results.to_csv(results_path, index=False)
    train_grid_path = out_dir / "rklb_train_grid.csv"
    train_grid.to_csv(train_grid_path, index=False)

    rklb_dna = compute_dna(frames.get("RKLB", pd.DataFrame()))
    dna_rows = []
    for symbol, frame in frames.items():
        current = compute_dna(frame)
        dna_rows.append({
            "symbol": symbol,
            **current,
            "dna_distance": dna_distance(rklb_dna, current),
        })

    report_path = out_dir / "candidate_summary.md"
    write_markdown_report(results, dna_rows, report_path)
    print(f"[done] {results_path}")
    print(f"[done] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
