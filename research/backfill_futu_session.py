# -*- coding: utf-8 -*-
"""
Futu 全时段补足 — 解决 review 快照截断导致回放无前向数据的问题
─────────────────────────────────────────────────────────────
关键: 隔夜/盘前柱必须用 extended_time=True + session=Session.ALL,
      否则 request_history_kline 默认只回常规时段(RTH),漏掉 00:00-04:00。

用法: python research/backfill_futu_session.py
输出: data/historical/{TKR}_5m_{start}_{end}_full.json  (含隔夜全时段)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import moomoo as mm
from moomoo import OpenQuoteContext, RET_OK, KLType, AuType
try:
    from config.settings import FUTU_HOST, FUTU_PORT
except Exception:
    FUTU_HOST, FUTU_PORT = "127.0.0.1", 11111

OUT = ROOT / "data" / "historical"
TICKERS = ["US.RKLB", "US.RKLX"]
START, END = "2026-05-28", "2026-05-29"
FIELDS = ["time_key", "open", "high", "low", "close", "volume"]


def fetch_full(ctx, code, ktype):
    """分页拉全时段(含隔夜)历史 K 线。"""
    rows, page_key = [], None
    while True:
        ret, data, page_key = ctx.request_history_kline(
            code, START, END, ktype, AuType.QFQ,
            fields=[mm.KL_FIELD.DATE_TIME, mm.KL_FIELD.OPEN, mm.KL_FIELD.HIGH,
                    mm.KL_FIELD.LOW, mm.KL_FIELD.CLOSE, mm.KL_FIELD.TRADE_VOL],
            max_count=1000, page_req_key=page_key,
            extended_time=True, session=mm.Session.ALL)   # ← 隔夜关键
        if ret != RET_OK:
            print(f"  [FAIL] {code} {ktype}: {data}")
            return None
        for _, r in data.iterrows():
            rows.append({k: (float(r[k]) if k != "time_key" else r["time_key"]) for k in FIELDS})
        if not page_key:
            break
    return rows


def main():
    ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    try:
        for code in TICKERS:
            rows = fetch_full(ctx, code, KLType.K_5M)
            if not rows:
                continue
            tkr = code.split(".")[-1]
            path = OUT / f"{tkr}_5m_{START}_{END}_full.json"
            json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False)
            on = [r for r in rows if "00:00" <= r["time_key"][11:16] < "09:30"]
            print(f"  [OK] {tkr} 5m: {len(rows)} 根 ({rows[0]['time_key']} → {rows[-1]['time_key']}), "
                  f"隔夜/盘前 {len(on)} 根 → {path.name}")
    finally:
        ctx.close()


if __name__ == "__main__":
    main()
