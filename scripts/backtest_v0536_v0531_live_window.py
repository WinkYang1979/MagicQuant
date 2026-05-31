"""
VERSION : v0.5.36-test
DEPENDS : data/review/*/triggers.json, data/historical/RKLB_1m.csv

Replay the v0.5.31 live-good window and compare raw v0.5.31 direction
signals with the current v0.5.36 candidate gate.

回放 v0.5.31 近期实盘表现较好的窗口，对比：
- v0.5.31: 历史方向信号全推
- v0.5.36: 保留 v0.5.31 方向敏感度，但必须通过当前 K_5M 数据门禁
"""

from __future__ import annotations

import json
import argparse
from collections import Counter
from datetime import datetime, timedelta, time as dtime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = ROOT / "data" / "review"
HIST_CSV = ROOT / "data" / "historical" / "RKLB_1m.csv"
OUT_DIR = ROOT / "docs"

DEFAULT_WINDOW_START = "2026-05-13"
DEFAULT_WINDOW_END = "2026-05-15"

FROZEN_VALUE_BLACKLIST = {(43.1, 4.94), (43.1, 5.82)}


def load_kline() -> pd.DataFrame:
    df = pd.read_csv(HIST_CSV)
    df["dt"] = pd.to_datetime(df["time_key"])
    return df.set_index("dt").sort_index()


def market_session(ts: datetime) -> str:
    t = ts.time()
    if t < dtime(3, 50):
        return "overnight"
    if t < dtime(4, 0):
        return "closed"
    if t < dtime(9, 30):
        return "pre"
    if t < dtime(16, 0):
        return "regular"
    if t < dtime(20, 0):
        return "post"
    return "overnight"


def v0536_block_reason(record: dict) -> str | None:
    """Current v0.5.36 freshness gate approximation for historical records."""
    ind = (record.get("decision_context") or {}).get("indicators_raw") or {}
    if not ind.get("data_ok"):
        return "data_ok=False"
    sig_ts = pd.to_datetime(record["ts"])
    if market_session(sig_ts) == "closed":
        return "market closed"
    if ind.get("is_today") is False:
        return "is_today=False"
    rsi = ind.get("rsi_14")
    vol = ind.get("vol_ratio")
    if rsi is not None and vol is not None:
        pair = (round(float(rsi), 1), round(float(vol), 2))
        if pair in FROZEN_VALUE_BLACKLIST:
            return f"known frozen pair {pair}"
    return None


def score_signal(kl: pd.DataFrame, sig_ts: str, direction: str, window_min: int):
    ts = pd.to_datetime(sig_ts)
    fut = kl.loc[ts: ts + timedelta(minutes=window_min)]
    if len(fut) < 2:
        return None
    entry = float(fut["close"].iloc[0])
    later = fut.iloc[1:]
    if entry <= 0 or len(later) == 0:
        return None
    hi = float(later["high"].max())
    lo = float(later["low"].min())
    close = float(later["close"].iloc[-1])
    if direction == "long":
        mfe = (hi - entry) / entry * 100
        mae = (entry - lo) / entry * 100
        ret = (close - entry) / entry * 100
    elif direction == "short":
        mfe = (entry - lo) / entry * 100
        mae = (hi - entry) / entry * 100
        ret = (entry - close) / entry * 100
    else:
        return None
    return {"win": mfe > mae, "mfe": mfe, "mae": mae, "ret": ret}


def collect_direction_records(window_start: str, window_end: str) -> list[dict]:
    rows = []
    for folder in sorted(REVIEW_DIR.glob("2026-*")):
        if not (window_start <= folder.name <= window_end):
            continue
        path = folder / "triggers.json"
        if not path.exists():
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        for rec in records:
            if rec.get("trigger") == "direction_trend" and rec.get("ticker") == "US.RKLB":
                rows.append(rec)
    return rows


def summarize(df: pd.DataFrame, label: str, mask: pd.Series) -> list[str]:
    lines = []
    sub = df[mask].copy()
    lines.append(f"{label}: pushed={len(sub)}")
    if len(sub) == 0:
        return lines
    for window in (5, 10, 15):
        scored = sub[sub[f"win_{window}"].notna()]
        if len(scored) == 0:
            lines.append(f"  {window}min: scored=0")
            continue
        wins = scored[scored[f"win_{window}"] == True]
        lines.append(
            f"  {window}min: scored={len(scored)} win={len(wins)} "
            f"acc={len(wins) / len(scored) * 100:.1f}% "
            f"avgMFE={scored[f'mfe_{window}'].mean():+.2f}% "
            f"avgMAE={scored[f'mae_{window}'].mean():+.2f}% "
            f"avgRet={scored[f'ret_{window}'].mean():+.2f}%"
        )
    by_day = sub.groupby("date").size().to_dict()
    lines.append("  by day: " + ", ".join(f"{k}={v}" for k, v in by_day.items()))
    by_dir = sub.groupby(["direction", "strength"]).size().to_dict()
    lines.append("  by dir/strength: " + ", ".join(f"{k}={v}" for k, v in by_dir.items()))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--end", default=DEFAULT_WINDOW_END)
    args = parser.parse_args()

    kl = load_kline()
    records = collect_direction_records(args.start, args.end)
    rows = []
    for rec in records:
        block = v0536_block_reason(rec)
        row = {
            "date": rec["ts"][:10],
            "ts": rec["ts"],
            "direction": rec.get("direction"),
            "strength": rec.get("strength"),
            "confidence": rec.get("confidence"),
            "rsi": (rec.get("data") or {}).get("rsi"),
            "vol_ratio": (rec.get("data") or {}).get("vol_ratio"),
            "day_change_pct": (rec.get("data") or {}).get("day_change_pct"),
            "v0536_push": block is None,
            "v0536_block_reason": block or "",
        }
        for window in (5, 10, 15):
            score = score_signal(kl, rec["ts"], rec.get("direction"), window)
            row[f"win_{window}"] = score["win"] if score else None
            row[f"mfe_{window}"] = score["mfe"] if score else None
            row[f"mae_{window}"] = score["mae"] if score else None
            row[f"ret_{window}"] = score["ret"] if score else None
        rows.append(row)

    df = pd.DataFrame(rows)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail_path = OUT_DIR / f"v0536_live_window_detail_{stamp}.csv"
    report_path = OUT_DIR / f"v0536_live_window_report_{stamp}.md"
    df.to_csv(detail_path, index=False)

    lines = [
        "# v0.5.36 vs v0.5.31 Live-Window Replay",
        "",
        f"Window: `{args.start}` to `{args.end}`",
        f"Historical data: `{HIST_CSV}`",
        "",
        "Definition:",
        "- `v0.5.31`: historical live direction signals, all pushed.",
        "- `v0.5.36`: same direction sensitivity, but blocked by current K_5M DataQualityGate approximation.",
        "",
        "## Summary",
        "",
    ]
    if len(df) == 0:
        lines.append("No direction_trend records found.")
    else:
        lines += summarize(df, "v0.5.31 all", pd.Series([True] * len(df), index=df.index))
        lines.append("")
        lines += summarize(df, "v0.5.36 gated", df["v0536_push"] == True)
        lines.append("")
        blocked = df[df["v0536_push"] == False]
        lines.append("## Blocked By v0.5.36 Gate")
        lines.append("")
        lines.append(f"blocked={len(blocked)} / {len(df)}")
        for reason, count in Counter(blocked["v0536_block_reason"]).items():
            lines.append(f"- {reason}: {count}")
        lines.append("")
        lines.append("## Decision Notes")
        lines.append("")
        lines.append("- Enough signal count means v0.5.36 should not silence the v0.5.31 good window.")
        lines.append("- Better signal means accuracy/avgRet should be equal or better after K_5M gate.")
        lines.append("- If v0.5.36 blocks many winning signals, the gate is too strict for this live window.")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport saved: {report_path}")
    print(f"Detail saved: {detail_path}")


if __name__ == "__main__":
    main()
