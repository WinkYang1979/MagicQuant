"""
MagicQuant - Futu 1m historical backfill
VERSION : v0.2.0
DEPENDS : config.settings, Futu/Moomoo OpenAPI, pandas

用途 / Purpose:
  - Backfill US stock 1-minute K-line data from local Futu OpenD.
  - 支持尽量回拉更长历史，用于 ORB/VWAP/direction_trend 回测验证。

Examples:
  python fetch_futu_history_1m.py
  python fetch_futu_history_1m.py --months 6 --backup
  python fetch_futu_history_1m.py --start 2025-11-19 --end 2026-05-19 --tickers RKLB,RKLX,RKLZ --backup
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    from moomoo import OpenQuoteContext, RET_OK, KLType, AuType
except ImportError:
    from futu import OpenQuoteContext, RET_OK, KLType, AuType

try:
    from config.settings import FUTU_HOST, FUTU_PORT
except Exception:
    FUTU_HOST = "127.0.0.1"
    FUTU_PORT = 11111


BASE_DIR = Path(__file__).resolve().parent
HIST_DIR = BASE_DIR / "data" / "historical"
DEFAULT_TICKERS = ["RKLB", "RKLX", "RKLZ"]
FIELDS = ["time_key", "open", "high", "low", "close", "volume"]


def _date_chunks(start: datetime, end: datetime, days: int = 28):
    """Yield inclusive date chunks. / 按日期分段，降低 Futu 单次请求压力。"""
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=days - 1), end)
        yield cur.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        cur = chunk_end + timedelta(days=1)


def fetch_range(ctx, ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch all 1m bars in [start, end] with paging."""
    all_bars = []
    page_key = None
    while True:
        ret, df, page_key = ctx.request_history_kline(
            f"US.{ticker}",
            start=start,
            end=end,
            ktype=KLType.K_1M,
            autype=AuType.QFQ,
            max_count=1000,
            page_req_key=page_key,
            extended_time=True,
        )
        if ret != RET_OK:
            print(f"    [{ticker}] FAIL {start}~{end} ret={ret}: {df}")
            return pd.DataFrame()
        if df is not None and len(df) > 0:
            all_bars.append(df)
        if page_key is None:
            break
    if not all_bars:
        return pd.DataFrame(columns=FIELDS)
    out = pd.concat(all_bars, ignore_index=True)
    missing = [c for c in FIELDS if c not in out.columns]
    if missing:
        print(f"    [{ticker}] missing fields: {missing}")
        return pd.DataFrame(columns=FIELDS)
    return out[FIELDS].copy()


def backup_existing(tickers: list[str]) -> Path | None:
    """Backup current CSVs before overwrite/merge. / 写入前备份当前 CSV。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = HIST_DIR.parent / f"historical_backup_{stamp}"
    copied = 0
    for ticker in tickers:
        src = HIST_DIR / f"{ticker}_1m.csv"
        if not src.exists():
            continue
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, backup_dir / src.name)
        copied += 1
    if copied:
        print(f"[backup] copied {copied} CSV(s) -> {backup_dir}")
        return backup_dir
    return None


def merge_and_save(ticker: str, new_df: pd.DataFrame) -> tuple[int, int, str | None, str | None]:
    """Merge new_df into existing CSV, dedup by time_key."""
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = HIST_DIR / f"{ticker}_1m.csv"
    if csv_path.exists():
        existing = pd.read_csv(csv_path)
        before = len(existing)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        before = 0
        combined = new_df

    if combined.empty:
        return 0, 0, None, None

    combined = (
        combined.drop_duplicates(subset=["time_key"], keep="last")
        .sort_values("time_key")
        .reset_index(drop=True)
    )
    combined.to_csv(csv_path, index=False)
    added = len(combined) - before
    first = str(combined["time_key"].iloc[0])
    last = str(combined["time_key"].iloc[-1])
    return added, len(combined), first, last


def parse_args():
    parser = argparse.ArgumentParser(description="Backfill Futu 1m historical bars.")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS),
                        help="Comma-separated tickers without US. prefix.")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD.")
    parser.add_argument("--months", type=int, default=None,
                        help="If --start is omitted, fetch this many months back. Default: incremental.")
    parser.add_argument("--chunk-days", type=int, default=28,
                        help="Days per request chunk. Default: 28.")
    parser.add_argument("--backup", action="store_true", help="Backup current CSV files first.")
    parser.add_argument("--replace", action="store_true",
                        help="Ignore existing CSV rows by moving them to backup first. Requires --backup.")
    return parser.parse_args()


def main():
    args = parse_args()
    tickers = [t.strip().upper().replace("US.", "") for t in args.tickers.split(",") if t.strip()]
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")

    if args.backup or args.replace:
        backup_existing(tickers)
    if args.replace and not args.backup:
        raise SystemExit("--replace requires --backup")
    if args.replace:
        for ticker in tickers:
            csv_path = HIST_DIR / f"{ticker}_1m.csv"
            if csv_path.exists():
                csv_path.unlink()

    print(f"[connect] Futu OpenD {FUTU_HOST}:{FUTU_PORT}")
    ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)

    try:
        for ticker in tickers:
            csv_path = HIST_DIR / f"{ticker}_1m.csv"
            if args.start:
                start_dt = datetime.strptime(args.start, "%Y-%m-%d")
                reason = "explicit start"
            elif args.months:
                start_dt = end_dt - timedelta(days=max(1, args.months) * 31)
                reason = f"{args.months} months back"
            elif csv_path.exists():
                last_ts = pd.read_csv(csv_path, usecols=["time_key"])["time_key"].iloc[-1]
                start_dt = datetime.strptime(str(last_ts)[:10], "%Y-%m-%d")
                reason = f"incremental from existing last {last_ts}"
            else:
                start_dt = end_dt - timedelta(days=30)
                reason = "default 30 days"

            if start_dt > end_dt:
                print(f"\n[{ticker}] skip: start {start_dt.date()} > end {end_dt.date()}")
                continue

            print(f"\n[{ticker}] fetch {start_dt.date()} -> {end_dt.date()} ({reason})")
            parts = []
            for chunk_start, chunk_end in _date_chunks(start_dt, end_dt, args.chunk_days):
                chunk = fetch_range(ctx, ticker, chunk_start, chunk_end)
                print(f"    {chunk_start} ~ {chunk_end}: {len(chunk)} bars")
                if not chunk.empty:
                    parts.append(chunk)
            if not parts:
                print(f"[{ticker}] no bars returned")
                continue

            new_df = pd.concat(parts, ignore_index=True)
            added, total, first, last = merge_and_save(ticker, new_df)
            print(f"[{ticker}] added {added}, total {total}, range {first} -> {last}")
    finally:
        ctx.close()


if __name__ == "__main__":
    main()
