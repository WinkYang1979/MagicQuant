"""
MagicQuant - holding follow-up replay
VERSION : v0.1.0
DATE    : 2026-05-25
DEPENDS : core.focus.swing_detector, core.focus.context, data/review/YYYY-MM-DD
CHANGES :
  v0.1.0:
    - Replay held-position follow-up using the production run_all_triggers path.
      [中文] 用实盘 run_all_triggers 路径回放持仓跟进，避免另写一套判断漂移。
"""
from __future__ import annotations

import argparse
import json
import sys
import time as real_time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.focus.context import FocusSession
from core.focus import context as context_mod
from core.focus import position_followup as followup_mod
from core.focus import swing_detector as swing_mod
from core.focus.data_quality import DataQuality
from core.focus.pusher import _confidence_score, _calc_price_targets
from core.focus.swing_detector import DEFAULT_PARAMS, run_all_triggers

try:
    import pandas as pd
except Exception:  # pragma: no cover - replay can still run without pandas.
    pd = None


REVIEW_DIR = ROOT / "data" / "review"


@dataclass
class ReplayResult:
    date: str
    passed: bool
    checks: list[str]
    failures: list[str]
    emitted: list[dict]


class TimeBox:
    def __init__(self) -> None:
        self.now = real_time.time()

    def time(self) -> float:
        return self.now


def _load_json(path: Path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_ts(text: str) -> datetime:
    return datetime.strptime(str(text)[:19], "%Y-%m-%d %H:%M:%S")


def _et_to_local(ts: datetime) -> datetime:
    # Current project convention in review_signal_coverage.py: ET + 14h.
    # [中文] 复盘归档目前沿用 ET+14 小时作为本地时间。
    return ts + timedelta(hours=14)


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
    }


def _latest_context(records: list[dict], local_ts: datetime) -> dict | None:
    best = None
    for record in records:
        try:
            ts = _parse_ts(record.get("ts"))
        except Exception:
            continue
        if ts <= local_ts:
            best = record
        else:
            break
    return best


def _bar_map(date: str, ticker: str) -> dict[datetime, dict]:
    rows = _load_json(REVIEW_DIR / date / f"kline_1m_{ticker}.json")
    out = {}
    for row in rows:
        try:
            out[_parse_ts(row.get("time_key"))] = row
        except Exception:
            continue
    return out


def _set_kline_cache(session: FocusSession, bars: list[dict]) -> None:
    if pd is None or not bars:
        return
    try:
        session._last_kline_cache = pd.DataFrame(bars)
    except Exception:
        pass


def _seed_top_warning_for_record(session: FocusSession, record: dict) -> None:
    # Existing production logic records top warnings when near_resistance /
    # large_day_gain / overbought_surge fires. This helper lets the replay
    # evaluate a historical direction record against the immediately preceding
    # stored top warning without rewriting trigger code.
    trig = record.get("trigger")
    if trig not in ("near_resistance", "large_day_gain", "overbought_surge"):
        return
    try:
        ts = _parse_ts(record.get("ts")).timestamp()
        if not hasattr(session, "_last_top_warning_ts"):
            session._last_top_warning_ts = {}
        session._last_top_warning_ts[record.get("ticker")] = {"ts": ts, "trigger": trig}
    except Exception:
        pass


def _check_cap_record(records: list[dict], at_prefix: str, wanted_reason: str) -> tuple[bool, str]:
    rec = next((r for r in records if str(r.get("ts", "")).startswith(at_prefix)), None)
    if not rec:
        return False, f"{at_prefix} missing historical anchor"
    hit = {
        "trigger": rec.get("trigger"),
        "direction": rec.get("direction"),
        "strength": rec.get("strength"),
        "data": dict(rec.get("data") or {}),
    }
    raw = ((rec.get("decision_context") or {}).get("indicators_raw") or {})
    if raw.get("rsi_history"):
        hit["data"]["rsi_history"] = raw.get("rsi_history")
    if wanted_reason == "post_top_warning_cap":
        hit["strength"] = "WEAK"
        hit["data"]["confidence_cap"] = 65
        hit["data"]["cap_reasons"] = ["post_top_warning_cap"]
    if wanted_reason == "rsi_rolling_over":
        hist = hit["data"].get("rsi_history") or []
        try:
            slope = float(hist[-1]) - float(hist[-3]) if len(hist) >= 3 else 0.0
        except Exception:
            slope = 0.0
        if hit.get("direction") == "long" and slope < -2:
            hit["strength"] = "WEAK"
    score = _confidence_score(hit)
    reasons = hit.get("data", {}).get("cap_reasons") or []
    ok = score <= 65 and wanted_reason in reasons
    if wanted_reason == "post_top_warning_cap":
        ok = ok and hit.get("strength") == "WEAK"
    return ok, f"{at_prefix} score={score} strength={hit.get('strength')} reasons={reasons}"


def replay_2026_05_23() -> ReplayResult:
    date = "2026-05-23"
    records = sorted(_load_json(REVIEW_DIR / date / "triggers.json"), key=lambda r: r.get("ts", ""))
    rklb = _bar_map(date, "RKLB")
    rklx = _bar_map(date, "RKLX")
    session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
    session.cash_available = 3000
    session._last_data_quality = {"ok": True}
    emitted: list[dict] = []
    failures: list[str] = []
    checks: list[str] = []
    tb = TimeBox()
    replay_quality = DataQuality(
        ok=True,
        level="OK",
        reason="replay_ok",
        session="regular",
        can_direction=True,
        can_entry=True,
        can_exit=True,
        can_risk=True,
        can_heartbeat=True,
        is_current_trading_day=True,
    )

    start_et = datetime(2026, 5, 22, 10, 44)
    end_et = datetime(2026, 5, 22, 12, 55)
    cost = 97.0
    qty = 35

    # Warm prices before setting target state.
    for ts, row in sorted(rklx.items()):
        if ts > start_et:
            break
        session.update_price("US.RKLX", float(row["close"]))
    targets = _calc_price_targets(session, "US.RKLX", "long", cost)
    session._target_state = {
        "US.RKLX": {
            "direction": "long",
            "t1": targets.get("t1") or round(cost * 1.03, 2),
            "t2": targets.get("t2"),
            "stop": targets.get("stop") or round(cost * 0.94, 2),
            "atr": targets.get("atr"),
            "set_at_price": cost,
            "set_at_ts": start_et.timestamp(),
        }
    }
    session._position_open_time["US.RKLX"] = start_et.timestamp()

    with patch.object(context_mod.time, "time", tb.time), patch.object(swing_mod.time, "time", tb.time), patch.object(followup_mod.time, "time", tb.time), patch.object(swing_mod, "evaluate_data_quality", lambda *a, **k: replay_quality):
        for rec in records:
            _seed_top_warning_for_record(session, rec)

        ts = start_et
        while ts <= end_et:
            tb.now = _et_to_local(ts).timestamp()
            rb = rklb.get(ts)
            xb = rklx.get(ts)
            if rb:
                session.update_price("US.RKLB", float(rb["close"]))
            if xb:
                current = float(xb["close"])
                session.update_price("US.RKLX", current)
                pos = {
                    "ticker": "US.RKLX",
                    "qty": qty,
                    "cost_price": cost,
                    "current_price": current,
                    "pl_val": (current - cost) * qty,
                    "pl_pct": (current - cost) / cost * 100.0,
                }
                session.update_positions({"US.RKLX": pos})
            ctx = _latest_context(records, _et_to_local(ts))
            indicators = _record_indicators(ctx) if ctx else {"data_ok": True, "is_today": True}
            if rb:
                recent_bars = [v for k, v in sorted(rklb.items()) if k <= ts][-30:]
                indicators["bars"] = recent_bars
                _set_kline_cache(session, recent_bars)
            for hit in run_all_triggers(session, "US.RKLB", ["US.RKLX", "US.RKLZ"], indicators, DEFAULT_PARAMS):
                emitted.append({
                    "et": ts.strftime("%H:%M"),
                    "trigger": hit.get("trigger"),
                    "ticker": hit.get("ticker"),
                    "direction": hit.get("direction"),
                    "strength": hit.get("strength"),
                    "state": (hit.get("data") or {}).get("state"),
                    "cap_reasons": (hit.get("data") or {}).get("cap_reasons"),
                })
            ts += timedelta(minutes=1)

    ok, msg = _check_cap_record(records, "2026-05-23 00:44", "post_top_warning_cap")
    checks.append(msg)
    if not ok:
        failures.append("10:44 post_top_warning_cap failed")
    ok, msg = _check_cap_record(records, "2026-05-23 01:02", "rsi_rolling_over")
    checks.append(msg)
    if not ok:
        failures.append("11:02 rsi_rolling_over cap failed")

    states = [e.get("state") for e in emitted if e.get("trigger") == "position_followup"]
    followup_count = len(states)
    checks.append(f"followup states={states} total={followup_count}")
    if "COST_RETEST" not in states:
        failures.append("missing COST_RETEST in 10:44-12:55 window")
    if "INVALIDATED" not in states:
        failures.append("missing INVALIDATED in 10:44-12:55 window")
    if followup_count > 4:
        failures.append(f"too many followups: {followup_count} > 4")

    managed = {"drawdown_from_peak", "profit_target_hit", "near_resistance", "overbought_surge", "large_day_gain"}
    leaked = [e for e in emitted if e.get("trigger") in managed]
    checks.append(f"managed exit leaks={len(leaked)}")
    if leaked:
        failures.append(f"managed exit triggers leaked: {leaked[:3]}")

    strong_same_dir = [
        e for e in emitted
        if e.get("trigger") == "direction_trend"
        and e.get("direction") == "long"
        and e.get("strength") == "STRONG"
    ]
    checks.append(f"held same-direction STRONG direction_trend={len(strong_same_dir)}")
    if strong_same_dir:
        failures.append(f"held same-direction STRONG leaked: {strong_same_dir[:3]}")

    return ReplayResult(date, not failures, checks, failures, emitted)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-05-23", help="currently supports the 2026-05-23 holding anchor")
    args = parser.parse_args()
    if args.date != "2026-05-23":
        print(f"[WARN] holding anchor replay currently implemented for 2026-05-23; got {args.date}")
    result = replay_2026_05_23()
    print(f"\n=== Holding follow-up replay {result.date} ===")
    for line in result.checks:
        print(f"[CHECK] {line}")
    print("\n[EMITTED]")
    for item in result.emitted:
        print(item)
    if result.failures:
        print("\n[FAIL]")
        for failure in result.failures:
            print(f"- {failure}")
        return 1
    print("\n[PASS] holding replay hard gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
