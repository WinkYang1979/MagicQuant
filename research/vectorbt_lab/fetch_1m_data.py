"""
MagicQuant fetch_1m_data.py
VERSION : v0.1.0
DEPENDS : config.settings, pandas, pyarrow, Futu/Moomoo OpenAPI

Fetch isolated 1-minute research bars from Futu.
从 Futu 拉取隔离研究用 1分钟K，不影响实盘主系统。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
DATA_DIR = BASE_DIR / "data"
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
DEFAULT_TICKERS = ["RKLB", "LUNR", "ASTS", "IONQ"]
SCHEMA = ["timestamp", "open", "high", "low", "close", "volume", "symbol"]


@dataclass
class FetchResult:
    symbol: str
    rows: int
    rows_added: int
    trading_days: int
    first_timestamp: str | None
    last_timestamp: str | None
    output_path: str | None
    errors: list[str]


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("US.", "")


def to_futu_symbol(symbol: str) -> str:
    return f"US.{normalize_symbol(symbol)}"


def et_to_utc(value: str) -> pd.Timestamp:
    raw = str(value).replace("T", " ")[:19]
    local_dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
    return pd.Timestamp(local_dt.astimezone(UTC))


def date_chunks(start: datetime, end: datetime, days: int = 28):
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=days - 1), end)
        yield cur.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        cur = chunk_end + timedelta(days=1)


def fetch_range(ctx, symbol: str, start: str, end: str) -> tuple[pd.DataFrame, list[str]]:
    rows = []
    errors: list[str] = []
    page_key = None
    futu_symbol = to_futu_symbol(symbol)

    while True:
        ret, frame, page_key = ctx.request_history_kline(
            futu_symbol,
            start=start,
            end=end,
            ktype=KLType.K_1M,
            autype=AuType.QFQ,
            max_count=1000,
            page_req_key=page_key,
            extended_time=True,
        )
        if ret != RET_OK:
            msg = f"{symbol} {start}~{end} ret={ret}: {frame}"
            print(f"[fetch] FAIL {msg}")
            errors.append(msg)
            break
        if frame is not None and len(frame) > 0:
            rows.append(frame)
        if page_key is None:
            break

    if not rows:
        return pd.DataFrame(), errors
    return pd.concat(rows, ignore_index=True), errors


def normalize_frame(symbol: str, raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=SCHEMA)
    missing = [col for col in ["time_key", "open", "high", "low", "close", "volume"] if col not in raw.columns]
    if missing:
        raise ValueError(f"{symbol} missing columns: {missing}")

    out = pd.DataFrame({
        "timestamp": raw["time_key"].map(et_to_utc),
        "open": pd.to_numeric(raw["open"], errors="coerce"),
        "high": pd.to_numeric(raw["high"], errors="coerce"),
        "low": pd.to_numeric(raw["low"], errors="coerce"),
        "close": pd.to_numeric(raw["close"], errors="coerce"),
        "volume": pd.to_numeric(raw["volume"], errors="coerce").fillna(0),
        "symbol": normalize_symbol(symbol),
    })
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    out = out.drop_duplicates(subset=["timestamp"], keep="last")
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out[SCHEMA]


def trading_day_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    et_dates = frame["timestamp"].dt.tz_convert(ET).dt.date
    return int(et_dates.nunique())


def output_path(symbol: str) -> Path:
    sym = normalize_symbol(symbol)
    return DATA_DIR / sym / "1m" / f"{sym}_1m.parquet"


def save_symbol(symbol: str, frame: pd.DataFrame) -> Path:
    path = output_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def load_existing(symbol: str) -> pd.DataFrame:
    path = output_path(symbol)
    if not path.exists():
        return pd.DataFrame(columns=SCHEMA)
    frame = pd.read_parquet(path)
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame[SCHEMA].drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)


def merge_existing(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return fresh[SCHEMA].copy()
    if fresh.empty:
        return existing[SCHEMA].copy()
    merged = pd.concat([existing[SCHEMA], fresh[SCHEMA]], ignore_index=True)
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
    return merged.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)


def incremental_start(symbol: str, requested_start: datetime) -> tuple[datetime, pd.DataFrame]:
    existing = load_existing(symbol)
    if existing.empty:
        return requested_start, existing
    last_ts = pd.to_datetime(existing["timestamp"].iloc[-1], utc=True)
    last_et_date = last_ts.tz_convert(ET).date()
    overlap_start = datetime.combine(last_et_date - timedelta(days=2), datetime.min.time())
    return max(requested_start, overlap_start), existing


def fetch_symbol(ctx, symbol: str, start_dt: datetime, end_dt: datetime, chunk_days: int, incremental: bool = False) -> FetchResult:
    sym = normalize_symbol(symbol)
    parts = []
    errors: list[str] = []
    existing = pd.DataFrame(columns=SCHEMA)
    original_rows = 0

    if incremental:
        start_dt, existing = incremental_start(sym, start_dt)
        original_rows = len(existing)

    mode = "incremental" if incremental else "full"
    print(f"[fetch] {sym}: {start_dt.date()} -> {end_dt.date()} ({mode})")
    for chunk_start, chunk_end in date_chunks(start_dt, end_dt, chunk_days):
        raw, chunk_errors = fetch_range(ctx, sym, chunk_start, chunk_end)
        errors.extend(chunk_errors)
        print(f"  {chunk_start} ~ {chunk_end}: {len(raw)} rows")
        if not raw.empty:
            parts.append(raw)

    if not parts:
        if incremental and not existing.empty:
            path = save_symbol(sym, existing)
            days = trading_day_count(existing)
            first = existing["timestamp"].iloc[0].isoformat()
            last = existing["timestamp"].iloc[-1].isoformat()
            return FetchResult(sym, len(existing), 0, days, first, last, str(path), errors)
        return FetchResult(sym, 0, 0, 0, None, None, None, errors or ["no rows returned"])

    frame = normalize_frame(sym, pd.concat(parts, ignore_index=True))
    frame = merge_existing(existing, frame) if incremental else frame
    path = save_symbol(sym, frame)
    rows_added = max(0, len(frame) - original_rows) if incremental else len(frame)
    days = trading_day_count(frame)
    first = frame["timestamp"].iloc[0].isoformat() if not frame.empty else None
    last = frame["timestamp"].iloc[-1].isoformat() if not frame.empty else None
    return FetchResult(sym, len(frame), rows_added, days, first, last, str(path), errors)


def write_manifest(results: list[FetchResult]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "manifest.json"
    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "schema": SCHEMA,
        "results": [result.__dict__ for result in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch isolated 1m research bars from Futu.")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS), help="Comma-separated tickers.")
    parser.add_argument("--trading-days", type=int, default=60, help="Target trading days. Default: 60.")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD. Overrides --trading-days.")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"), help="End date YYYY-MM-DD.")
    parser.add_argument("--chunk-days", type=int, default=28, help="Futu request chunk size.")
    parser.add_argument("--incremental", action="store_true", help="Merge only recent bars into existing parquet files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [normalize_symbol(item) for item in args.tickers.split(",") if item.strip()]
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")
    if args.start:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        calendar_days = max(30, int(args.trading_days * 1.65) + 10)
        start_dt = end_dt - timedelta(days=calendar_days)

    print(f"[connect] Futu OpenD {FUTU_HOST}:{FUTU_PORT}")
    ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    results: list[FetchResult] = []
    try:
        for sym in symbols:
            results.append(fetch_symbol(ctx, sym, start_dt, end_dt, args.chunk_days, incremental=args.incremental))
    finally:
        ctx.close()

    manifest = write_manifest(results)
    print(f"[manifest] {manifest}")
    for result in results:
        status = "OK" if result.trading_days >= min(args.trading_days, 30) else "SHORT"
        print(f"[{status}] {result.symbol}: rows={result.rows}, added={result.rows_added}, days={result.trading_days}, path={result.output_path}")
        for err in result.errors:
            print(f"  error: {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
