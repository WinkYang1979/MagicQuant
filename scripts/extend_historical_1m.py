"""增量补齐 data/historical/{TKR}_1m.csv 到最新(含隔夜全时段),按 time_key 去重。

用 Futu request_history_kline(extended_time=True, session=ALL) 拉 1m,
追加到现有 CSV(time_key,open,high,low,close,volume)。只补"最后一根之后"的新 bar。

用法: python scripts/extend_historical_1m.py [END_DATE]   # 默认到今天
"""
from __future__ import annotations
import csv, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HIST = ROOT / "data" / "historical"
TICKERS = ["RKLB", "RKLX", "RKLZ"]

from config.settings import FUTU_HOST, FUTU_PORT
try:
    import moomoo as mm
    from moomoo import OpenQuoteContext, KLType, AuType, RET_OK
except ImportError:
    import futu as mm
    from futu import OpenQuoteContext, KLType, AuType, RET_OK

FIELDS = ["time_key", "open", "high", "low", "close", "volume"]


def _last_ts(path: Path) -> str | None:
    if not path.exists():
        return None
    last = None
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            tk = (row.get("time_key") or "").strip()
            if tk:
                last = tk
    return last


def fetch_1m(ctx, code, start, end):
    rows, page_key = [], None
    while True:
        ret, data, page_key = ctx.request_history_kline(
            code, start, end, KLType.K_1M, AuType.QFQ,
            fields=[mm.KL_FIELD.DATE_TIME, mm.KL_FIELD.OPEN, mm.KL_FIELD.HIGH,
                    mm.KL_FIELD.LOW, mm.KL_FIELD.CLOSE, mm.KL_FIELD.TRADE_VOL],
            max_count=1000, page_req_key=page_key,
            extended_time=True, session=mm.Session.ALL)
        if ret != RET_OK:
            print(f"  [FAIL] {code}: {data}")
            return None
        for _, r in data.iterrows():
            rows.append({
                "time_key": str(r["time_key"]),
                "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": float(r["volume"]),
            })
        if not page_key:
            break
    return rows


def main():
    end = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    try:
        for tkr in TICKERS:
            path = HIST / f"{tkr}_1m.csv"
            last = _last_ts(path)
            start = (last[:10] if last else "2026-05-18")
            code = f"US.{tkr}"
            print(f"[{tkr}] CSV 最后 {last} → 拉 {start}..{end}")
            rows = fetch_1m(ctx, code, start, end)
            if not rows:
                continue
            # 只保留严格晚于 last 的新 bar
            new = [r for r in rows if (last is None or r["time_key"] > last)]
            if not new:
                print(f"  [{tkr}] 无新增 bar(已最新)")
                continue
            exists = path.exists()
            with open(path, "a", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if not exists:
                    w.writeheader()
                for r in new:
                    w.writerow(r)
            print(f"  [{tkr}] 追加 {len(new)} 根 → {new[0]['time_key']} .. {new[-1]['time_key']}")
    finally:
        ctx.close()


if __name__ == "__main__":
    main()
