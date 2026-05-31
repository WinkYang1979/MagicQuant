"""
MagicQuant - breakdown/rebound patch replay
VERSION : v0.1.0
DATE    : 2026-05-29
DEPENDS : core.focus.swing_detector, scripts.review_signal_coverage, data/review/YYYY-MM-DD

Replay the focused v0.5.36 breakdown/rebound patch against saved review
snapshots. / 用已归档复盘快照回放本次破位/反弹补丁。
"""
from __future__ import annotations

import argparse
import json
import sys
import time as real_time
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.focus.context import FocusSession
from core.focus import swing_detector as swing_mod
from core.focus.pusher import _confidence_score
from core.focus.swing_detector import DEFAULT_PARAMS
from scripts import review_signal_coverage as coverage

OUT_DIR = ROOT / "docs"


class TimeBox:
    def __init__(self) -> None:
        self.now = real_time.time()

    def time(self) -> float:
        return self.now


def _parse_ts(text: str) -> datetime:
    return datetime.strptime(str(text)[:19], "%Y-%m-%d %H:%M:%S")


def _record_indicators(record: dict) -> dict:
    ctx = record.get("decision_context") or {}
    raw = ctx.get("indicators_raw") or {}
    price = ctx.get("price_context") or {}
    kline = ctx.get("kline_data") or {}
    return {
        "data_ok": raw.get("data_ok", True),
        "is_today": raw.get("is_today", True),
        "rsi_5m": raw.get("rsi_14") or raw.get("rsi"),
        "rsi_history": raw.get("rsi_history"),
        "vwap": raw.get("vwap"),
        "vol_ratio": raw.get("vol_ratio"),
        "vol_current": raw.get("vol_current"),
        "session_high": raw.get("session_high") or price.get("day_high"),
        "session_low": raw.get("session_low") or price.get("day_low"),
        "dist_high": raw.get("dist_high"),
        "dist_low": raw.get("dist_low"),
        "candle": raw.get("candle") or {},
        "bars": kline.get("bars") or [],
        "indicator_stale": False,
    }


def _current_price(record: dict) -> float | None:
    ctx = record.get("decision_context") or {}
    price = ctx.get("price_context") or {}
    value = price.get("current") or (record.get("prices") or {}).get("RKLB")
    try:
        return float(value)
    except Exception:
        return None


def _day_change(record: dict) -> float | None:
    ctx = record.get("decision_context") or {}
    price = ctx.get("price_context") or {}
    value = price.get("day_change_pct") or (record.get("data") or {}).get("day_change_pct")
    try:
        return float(value)
    except Exception:
        return None


def _synthetic_record(source: dict, hit: dict) -> dict:
    current = (hit.get("data") or {}).get("current") or _current_price(source)
    return {
        "ts": source.get("ts"),
        "trigger": hit.get("trigger"),
        "ticker": hit.get("ticker"),
        "direction": hit.get("direction"),
        "strength": hit.get("strength"),
        "raw_strength": hit.get("strength"),
        "confidence": _confidence_score(hit),
        "profile": "patch_replay",
        "data": hit.get("data") or {},
        "prices": {"RKLB": current},
        "positions": source.get("positions") or {},
        "cash_available": source.get("cash_available"),
        "message_text": "[replay] synthetic patch signal",
        "pusher_version": "replay",
        "swing_version": "replay",
        "decision_context": source.get("decision_context") or {},
    }


def _augment_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
    session.cash_available = 999999
    session._disable_review_log = True
    tb = TimeBox()
    out = list(records)
    added: list[dict] = []
    seen = {(r.get("ts"), r.get("trigger"), r.get("direction")) for r in records}

    with patch.object(swing_mod.time, "time", tb.time):
        for record in sorted(records, key=lambda r: r.get("ts", "")):
            current = _current_price(record)
            if current is None:
                continue
            try:
                tb.now = _parse_ts(record.get("ts")).timestamp()
            except Exception:
                pass
            session.update_price("US.RKLB", current)
            dc = _day_change(record)
            if dc is not None:
                session.quote_snapshot["US.RKLB"] = {"change_pct": dc}
            indicators = _record_indicators(record)
            for fn in (swing_mod.check_breakdown_warning, swing_mod.check_crash_rebound_watch):
                hit = fn(session, "US.RKLB", dict(indicators), DEFAULT_PARAMS)
                if not hit:
                    continue
                key = (record.get("ts"), hit.get("trigger"), hit.get("direction"))
                if key in seen:
                    continue
                seen.add(key)
                synthetic = _synthetic_record(record, hit)
                out.append(synthetic)
                added.append(synthetic)
    out.sort(key=lambda r: r.get("ts", ""))
    return out, added


def _coverage_counts(review: dict) -> Counter:
    counts = Counter()
    for item in review.get("waves") or []:
        counts[item["coverage"]["status"]] += 1
    return counts


def _wrong_strong(review: dict) -> int:
    return sum(item["coverage"].get("opposite_strong_total", 0) for item in review.get("waves") or [])


def _build_review_with_records(date: str, records: list[dict]) -> dict:
    original = coverage.load_triggers
    try:
        coverage.load_triggers = lambda _date: records
        return coverage.build_review(date, fetch_1m=False)
    finally:
        coverage.load_triggers = original


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", default=["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"])
    args = parser.parse_args()

    lines = [
        "# Breakdown/Rebound Patch Replay",
        "",
        "Scope: synthetic replay from saved `triggers.json` snapshots; no live strategy state is modified.",
        "",
        "| Date | Added patch signals | Before T/L/M/W | After T/L/M/W | Wrong STRONG before→after |",
        "|---|---:|---|---|---:|",
    ]
    totals_before = Counter()
    totals_after = Counter()
    added_total = 0
    wrong_before_total = 0
    wrong_after_total = 0

    for date in args.dates:
        records = coverage.load_triggers(date)
        before = coverage.build_review(date, fetch_1m=False)
        augmented, added = _augment_records(records)
        after = _build_review_with_records(date, augmented)
        bc = _coverage_counts(before)
        ac = _coverage_counts(after)
        totals_before.update(bc)
        totals_after.update(ac)
        added_total += len(added)
        wb = _wrong_strong(before)
        wa = _wrong_strong(after)
        wrong_before_total += wb
        wrong_after_total += wa
        before_text = f"{bc['TIMELY']}/{bc['LATE']}/{bc['MISS']}/{bc['WRONG_SIDE']}"
        after_text = f"{ac['TIMELY']}/{ac['LATE']}/{ac['MISS']}/{ac['WRONG_SIDE']}"
        lines.append(f"| {date} | {len(added)} | {before_text} | {after_text} | {wb}→{wa} |")
        if added:
            lines.append("")
            lines.append(f"Added on {date}:")
            for rec in added[:12]:
                lines.append(
                    f"- {rec['ts']} {rec['trigger']}/{rec['direction']}/{rec['strength']} "
                    f"conf={rec['confidence']} price={rec['prices'].get('RKLB')}"
                )
            lines.append("")

    lines += [
        "",
        "## Total",
        "",
        f"- Added patch signals: {added_total}",
        f"- Before TIMELY/LATE/MISS/WRONG_SIDE: {totals_before['TIMELY']}/{totals_before['LATE']}/{totals_before['MISS']}/{totals_before['WRONG_SIDE']}",
        f"- After TIMELY/LATE/MISS/WRONG_SIDE: {totals_after['TIMELY']}/{totals_after['LATE']}/{totals_after['MISS']}/{totals_after['WRONG_SIDE']}",
        f"- Wrong-side STRONG: {wrong_before_total} -> {wrong_after_total}",
        "",
        "Note: this replay can only add signals at archived snapshot times. It is conservative for new early signals between existing pushes.",
    ]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"breakdown_rebound_patch_replay_{stamp}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
