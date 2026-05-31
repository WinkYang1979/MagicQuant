"""
MagicQuant report.py
VERSION : v0.2.0
DEPENDS : pandas

Candidate scan report helpers.
候选股扫描报告工具。 / Candidate report helpers.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "output"
DEFAULT_TICKERS = ["RKLB", "LUNR", "ASTS", "IONQ"]


def markdown_table(frame: pd.DataFrame) -> str:
    """Render a compact Markdown table without optional tabulate dependency."""
    if frame.empty:
        return "No rows."
    data = frame.fillna("").astype(str)
    columns = list(data.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in data.iterrows():
        lines.append("| " + " | ".join(str(row[col]) for col in columns) + " |")
    return "\n".join(lines)


def compute_dna(frame: pd.DataFrame) -> dict:
    """Compute rough behavior DNA. / 计算粗略行为特征。"""
    if frame.empty:
        return {"volatility": 0.0, "momentum": 0.0, "volume_cv": 0.0}
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    data["date"] = data["timestamp"].dt.date
    daily = data.groupby("date").agg({
        "high": "max",
        "low": "min",
        "open": "first",
        "close": "last",
        "volume": "sum",
    })
    daily_range = ((daily["high"] - daily["low"]) / daily["open"].replace(0, pd.NA) * 100).dropna()
    daily_momentum = ((daily["close"] - daily["open"]) / daily["open"].replace(0, pd.NA) * 100).dropna().abs()
    volume_cv = daily["volume"].std() / daily["volume"].mean() if daily["volume"].mean() else 0.0
    return {
        "volatility": round(float(daily_range.median() if len(daily_range) else 0.0), 3),
        "momentum": round(float(daily_momentum.median() if len(daily_momentum) else 0.0), 3),
        "volume_cv": round(float(volume_cv or 0.0), 3),
    }


def dna_distance(base: dict, other: dict) -> float:
    """Simple L1 DNA distance. / 简单 L1 行为距离。"""
    keys = ["volatility", "momentum", "volume_cv"]
    return round(sum(abs(float(base.get(key, 0)) - float(other.get(key, 0))) for key in keys), 3)


def _build_conclusion(results: pd.DataFrame) -> str:
    if results.empty:
        return "No conclusion: no results."
    score_col = "oos_pnl" if "oos_pnl" in results.columns else "fee_adjusted_pnl"
    rklb_rows = results[results["symbol"].astype(str).str.upper() == "RKLB"]
    rklb_oos = float(rklb_rows.iloc[0][score_col]) if not rklb_rows.empty else 0.0
    best = results.sort_values(score_col, ascending=False).iloc[0]

    if rklb_oos <= 0:
        return (
            f"当前 v0.2 结论: breakout_core 在 RKLB OOS 上未跑正 ({rklb_oos:.2f})，"
            "本轮无法回答“谁最像 RKLB 且适合复制打法”。候选股结果只可作为研究线索，"
            "不可用于实盘决策。"
        )
    return (
        f"当前 v0.2 结论: RKLB OOS 已跑正 ({rklb_oos:.2f})；同一组 RKLB train "
        f"参数横扫候选股后，{best['symbol']} OOS 扣费表现最好 ({float(best[score_col]):.2f})。"
        "DNA 相似度只作辅证。"
    )


def write_markdown_report(results: pd.DataFrame, dna_rows: list[dict], path: Path) -> None:
    """Write Markdown summary. / 写入 Markdown 汇总。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# MagicQuant VectorBT Lab Candidate Summary",
        "",
        "本报告来自隔离研究模块，不接入实盘、不触发 Telegram。",
        "",
        "## Conclusion",
        "",
        _build_conclusion(results),
        "",
        "## Shared RKLB-Train Parameters: OOS Results",
        "",
    ]

    if results.empty:
        lines.append("No results.")
    else:
        display_cols = [
            col for col in [
                "symbol", "segment", "volume_multiplier", "atr_threshold", "breakout_pct",
                "stop_atr", "take_profit_atr", "cooldown_minutes", "in_sample_pnl",
                "oos_pnl", "fee_adjusted_pnl", "win_rate", "profit_factor",
                "max_drawdown", "trade_count", "signal_density_per_day",
                "false_breakout_rate",
            ] if col in results.columns
        ]
        lines.append(markdown_table(results[display_cols].reset_index(drop=True)))

    lines += ["", "## RKLB DNA Similarity", ""]
    dna_df = pd.DataFrame(dna_rows)
    if dna_df.empty:
        lines.append("No DNA rows.")
    else:
        lines.append(markdown_table(dna_df.sort_values("dna_distance").reset_index(drop=True)))

    lines += [
        "",
        "## Notes",
        "",
        "- `fee_adjusted_pnl` / `oos_pnl` are the primary ranking fields.",
        "- v0.2 uses RKLB train-selected parameters and ranks shared-parameter OOS results.",
        "- Entry fill uses next-bar open with slippage, not signal-bar close.",
        "- `false_breakout_rate` means stopped out within 5 one-minute bars after entry.",
        "- `signal_density_per_day < 0.3` should be treated as too quiet for live usefulness.",
        "- Candidate symbols remain research-only.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _load_data(symbols: list[str]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        sym = symbol.upper().replace("US.", "")
        path = DATA_DIR / sym / "1m" / f"{sym}_1m.parquet"
        if path.exists():
            frames[sym] = pd.read_parquet(path)
        else:
            frames[sym] = pd.DataFrame()
    return frames


def parse_args():
    parser = argparse.ArgumentParser(description="Write VectorBT lab Markdown report.")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Directory containing candidate_scan.csv.")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS), help="Comma-separated symbols for DNA rows.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    results_path = out_dir / "candidate_scan.csv"
    if not results_path.exists():
        print(f"[report] missing {results_path}")
        return 1

    symbols = [item.strip().upper().replace("US.", "") for item in args.tickers.split(",") if item.strip()]
    results = pd.read_csv(results_path)
    frames = _load_data(symbols)
    rklb_dna = compute_dna(frames.get("RKLB", pd.DataFrame()))
    dna_rows = []
    for symbol, frame in frames.items():
        current = compute_dna(frame)
        dna_rows.append({"symbol": symbol, **current, "dna_distance": dna_distance(rklb_dna, current)})

    report_path = out_dir / "candidate_summary.md"
    write_markdown_report(results, dna_rows, report_path)
    print(f"[report] wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
