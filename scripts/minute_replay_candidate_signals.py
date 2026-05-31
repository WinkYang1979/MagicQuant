"""
MagicQuant - minute-level candidate signal replay
VERSION : v0.1.0
DATE    : 2026-05-29
DEPENDS : core.focus.swing_detector, core.focus.micro_indicators, scripts.review_signal_coverage

Replay production triggers minute-by-minute from 1m bars, then overlay a
candidate breakdown/rebound timing strategy. / 用 1m K 线逐分钟回放实盘触发器，
再叠加候选破位/反弹策略，供合入前决策。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time as real_time
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.focus.context import FocusSession
from core.focus import context as context_mod
from core.focus import swing_detector as swing_mod
from core.focus.data_quality import DataQuality
from core.focus.micro_indicators import calc_all_micro
from core.focus.pusher import _confidence_score
from core.focus.swing_detector import DEFAULT_PARAMS, run_all_triggers
from scripts import review_signal_coverage as coverage

OUT_DIR = ROOT / "docs"


CANDIDATE_PROFILES = {
    "A_STRICT": {
        "breakdown_day": -2.0,
        "breakdown_vwap": True,
        "breakdown_high_dd": 1.8,
        "breakdown_rsi_max": 48,
        "breakdown_vol_min": 0.75,
        "breakdown_move5": -0.55,
        "breakdown_move15": -1.10,
        "breakdown_cooldown": 12,
        "breakdown_strong_vol": 1.00,
        "breakdown_strong_dd": 2.50,
        "rebound_day": -3.0,
        "rebound_low": 1.0,
        "rebound_rsi_min": 35,
        "rebound_rsi_max": 68,
        "rebound_vol_min": 0.30,
        "rebound_move5": 0.45,
        "rebound_cooldown": 12,
        "rebound_strong_low": 2.0,
        "rebound_strong_needs_vwap": True,
    },
    "B_BALANCED": {
        "breakdown_day": -1.5,
        "breakdown_vwap": True,
        "breakdown_high_dd": 1.2,
        "breakdown_rsi_max": 52,
        "breakdown_vol_min": 0.45,
        "breakdown_move5": -0.35,
        "breakdown_move15": -0.75,
        "breakdown_cooldown": 15,
        "breakdown_strong_vol": 0.90,
        "breakdown_strong_dd": 2.0,
        "rebound_day": -2.5,
        "rebound_low": 0.8,
        "rebound_rsi_min": 33,
        "rebound_rsi_max": 70,
        "rebound_vol_min": 0.25,
        "rebound_move5": 0.25,
        "rebound_cooldown": 15,
        "rebound_strong_low": 1.6,
        "rebound_strong_needs_vwap": False,
    },
    "C_AGGRESSIVE_WATCH": {
        "breakdown_day": -1.0,
        "breakdown_vwap": False,
        "breakdown_high_dd": 0.8,
        "breakdown_rsi_max": 55,
        "breakdown_vol_min": 0.25,
        "breakdown_move5": -0.20,
        "breakdown_move15": -0.60,
        "breakdown_cooldown": 20,
        "breakdown_strong_vol": 99.0,
        "breakdown_strong_dd": 99.0,
        "rebound_day": -2.0,
        "rebound_low": 0.6,
        "rebound_rsi_min": 30,
        "rebound_rsi_max": 72,
        "rebound_vol_min": 0.20,
        "rebound_move5": 0.20,
        "rebound_cooldown": 20,
        "rebound_strong_low": 99.0,
        "rebound_strong_needs_vwap": False,
    },
    "D_TARGETED_BREAKDOWN": {
        "breakdown_day": -1.0,
        "breakdown_vwap": False,
        "breakdown_high_dd": 0.8,
        "breakdown_rsi_max": 55,
        "breakdown_vol_min": 0.25,
        "breakdown_move5": -0.20,
        "breakdown_move15": -0.60,
        "breakdown_cooldown": 20,
        "breakdown_strong_vol": 99.0,
        "breakdown_strong_dd": 99.0,
        "rebound_day": -3.0,
        "rebound_low": 1.0,
        "rebound_rsi_min": 35,
        "rebound_rsi_max": 68,
        "rebound_vol_min": 0.30,
        "rebound_move5": 0.45,
        "rebound_cooldown": 20,
        "rebound_strong_low": 99.0,
        "rebound_strong_needs_vwap": False,
    },
}


class TimeBox:
    def __init__(self) -> None:
        self.now = real_time.time()

    def time(self) -> float:
        return self.now


def _parse_ts(text: str) -> datetime:
    return datetime.strptime(str(text)[:19], "%Y-%m-%d %H:%M:%S")


def _first_prev_close(records: list[dict], fallback: float) -> float:
    for rec in records:
        ctx = rec.get("decision_context") or {}
        price = ctx.get("price_context") or {}
        try:
            prev = float(price.get("prev_close"))
            if prev > 0:
                return prev
        except Exception:
            pass
    return fallback


def _bars_to_frame(bars: list[coverage.Bar]) -> pd.DataFrame:
    rows = []
    for b in bars:
        rows.append({
            "time_key": b.ts.strftime("%Y-%m-%d %H:%M:%S"),
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        })
    return pd.DataFrame(rows)


def _resample_5m(bars_1m: list[coverage.Bar], et_today: str) -> pd.DataFrame:
    frame = _bars_to_frame(bars_1m)
    if frame.empty:
        return frame
    dt = pd.to_datetime(frame["time_key"])
    frame = frame.set_index(dt)
    out = frame.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"]).reset_index(drop=False)
    out.rename(columns={"index": "time_key"}, inplace=True)
    out["time_key"] = pd.to_datetime(out["time_key"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    out.attrs["et_today"] = et_today
    out.attrs["has_today_data"] = True
    return out


def _synthetic_record(ts: datetime, hit: dict, price: float, prev_close: float, label: str) -> dict:
    data = hit.get("data") or {}
    # Review trigger `ts` is stored in local time; coverage converts it back to ET.
    # 复盘触发日志 ts 使用本地时间；coverage 会再换算回 ET。
    local_ts = ts + timedelta(hours=14)
    return {
        "ts": local_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "et_ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "trigger": hit.get("trigger"),
        "ticker": hit.get("ticker", "US.RKLB"),
        "direction": hit.get("direction"),
        "strength": hit.get("strength"),
        "raw_strength": hit.get("strength"),
        "confidence": _confidence_score(hit) if not hit.get("confidence") else hit.get("confidence"),
        "profile": label,
        "data": data,
        "prices": {"RKLB": data.get("current") or price},
        "positions": {},
        "cash_available": 999999,
        "message_text": f"[{label}] synthetic replay signal",
        "pusher_version": "minute_replay",
        "swing_version": "minute_replay",
        "decision_context": {
            "price_context": {
                "current": price,
                "prev_close": prev_close,
                "day_change_pct": (price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0,
            },
            "indicators_raw": data,
            "kline_data": {},
            "session_state": {},
        },
    }


def _move_pct(bars: list[coverage.Bar], minutes: int) -> float | None:
    if len(bars) <= minutes:
        return None
    start = bars[-minutes - 1].close
    end = bars[-1].close
    if start <= 0:
        return None
    return (end - start) / start * 100.0


def _candidate_hits(
    ts: datetime,
    session: FocusSession,
    bars_1m: list[coverage.Bar],
    indicators: dict,
    prev_close: float,
    cooldown: dict[str, datetime],
    profile_name: str,
    profile: dict,
) -> list[dict]:
    """Candidate timing layer; research-only. / 候选及时性层，仅供研究回放。"""
    if len(bars_1m) < 20 or prev_close <= 0:
        return []
    current = bars_1m[-1].close
    day_chg = (current - prev_close) / prev_close * 100.0
    vwap = indicators.get("vwap") or 0
    rsi = indicators.get("rsi_5m") or 50
    vol_ratio = indicators.get("vol_ratio") or 1
    session_high = max(b.high for b in bars_1m)
    session_low = min(b.low for b in bars_1m)
    high_dd = (session_high - current) / session_high * 100 if session_high > 0 else 0.0
    low_rebound = (current - session_low) / session_low * 100 if session_low > 0 else 0.0
    move5 = _move_pct(bars_1m, 5)
    move15 = _move_pct(bars_1m, 15)
    hits: list[dict] = []

    def cool_ok(key: str, minutes: int) -> bool:
        last = cooldown.get(key)
        if last and (ts - last).total_seconds() < minutes * 60:
            return False
        cooldown[key] = ts
        return True

    vwap_ok = current < vwap if profile.get("breakdown_vwap") else (not vwap or current < vwap or (move15 is not None and move15 <= profile["breakdown_move15"]))
    breakdown = (
        day_chg <= profile["breakdown_day"]
        and vwap_ok
        and high_dd >= profile["breakdown_high_dd"]
        and rsi <= profile["breakdown_rsi_max"]
        and vol_ratio >= profile["breakdown_vol_min"]
        and ((move5 is not None and move5 <= profile["breakdown_move5"]) or (move15 is not None and move15 <= profile["breakdown_move15"]))
    )
    if breakdown and cool_ok(f"{profile_name}:candidate_breakdown_follow", profile["breakdown_cooldown"]):
        hits.append({
            "trigger": "candidate_breakdown_follow",
            "level": "WARN",
            "style": "B",
            "ticker": "US.RKLB",
            "direction": "short",
            "strength": "STRONG" if vol_ratio >= profile["breakdown_strong_vol"] and high_dd >= profile["breakdown_strong_dd"] else "WEAK",
            "data": {
                "current": current,
                "day_change_pct": day_chg,
                "vwap": vwap,
                "rsi": rsi,
                "vol_ratio": vol_ratio,
                "high_drawdown_pct": high_dd,
                "move5_pct": move5,
                "move15_pct": move15,
            },
        })

    rebound = (
        day_chg <= profile["rebound_day"]
        and low_rebound >= profile["rebound_low"]
        and rsi >= profile["rebound_rsi_min"]
        and rsi <= profile["rebound_rsi_max"]
        and vol_ratio >= profile["rebound_vol_min"]
        and (
            (move5 is not None and move5 >= profile["rebound_move5"])
            or (len(bars_1m) >= 3 and bars_1m[-1].close > bars_1m[-2].close > bars_1m[-3].close)
        )
    )
    if rebound and cool_ok(f"{profile_name}:candidate_rebound_entry_watch", profile["rebound_cooldown"]):
        vwap_confirmed = bool(vwap and current >= vwap)
        can_strong = low_rebound >= profile["rebound_strong_low"] and (
            not profile.get("rebound_strong_needs_vwap") or vwap_confirmed
        )
        strength = "STRONG" if can_strong else "WEAK"
        hits.append({
            "trigger": "candidate_rebound_entry_watch",
            "level": "WARN" if strength == "STRONG" else "INFO",
            "style": "B" if strength == "STRONG" else "C",
            "ticker": "US.RKLB",
            "direction": "long",
            "strength": strength,
            "data": {
                "current": current,
                "day_change_pct": day_chg,
                "vwap": vwap,
                "rsi": rsi,
                "vol_ratio": vol_ratio,
                "low_rebound_pct": low_rebound,
                "move5_pct": move5,
                "move15_pct": move15,
            },
        })
    return hits


def _replay_date(date: str, fetch_1m: bool) -> tuple[dict, dict[str, dict], list[dict], dict[str, list[dict]], str]:
    original_records = coverage.load_triggers(date)
    bars, source = coverage.load_or_fetch_review_bars(date, original_records, ticker="RKLB", fetch_1m=fetch_1m)
    if not bars:
        raise RuntimeError(f"no bars for {date}")
    prev_close = _first_prev_close(original_records, bars[0].open)
    session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
    session.cash_available = 999999
    session._disable_review_log = True
    replay_quality = DataQuality(
        ok=True,
        level="OK",
        reason="minute_replay",
        session="regular",
        can_direction=True,
        can_entry=True,
        can_exit=True,
        can_risk=True,
        can_heartbeat=True,
        is_current_trading_day=True,
    )
    tb = TimeBox()
    production_records: list[dict] = []
    candidate_records_by_profile: dict[str, list[dict]] = {name: [] for name in CANDIDATE_PROFILES}
    cooldown_by_profile: dict[str, dict[str, datetime]] = {name: {} for name in CANDIDATE_PROFILES}

    seen_prod = set()
    seen_cand: dict[str, set] = {name: set() for name in CANDIDATE_PROFILES}
    with (
        patch.object(context_mod.time, "time", tb.time),
        patch.object(swing_mod.time, "time", tb.time),
        patch.object(swing_mod, "evaluate_data_quality", lambda *a, **k: replay_quality),
        patch.object(swing_mod, "_log_direction_skip", lambda *a, **k: None),
        patch.object(swing_mod, "_log_rebound_delay", lambda *a, **k: None),
    ):
        for idx, bar in enumerate(bars):
            ts = bar.ts
            tb.now = ts.timestamp()
            session.update_price("US.RKLB", bar.close)
            session.quote_snapshot["US.RKLB"] = {
                "change_pct": (bar.close - prev_close) / prev_close * 100 if prev_close > 0 else 0.0,
                "prev_close": prev_close,
            }
            partial_1m = bars[:idx + 1]
            kl5 = _resample_5m(partial_1m, ts.strftime("%Y-%m-%d"))
            session._last_kline_cache = kl5
            indicators = calc_all_micro(kl5, bar.close)
            with redirect_stdout(io.StringIO()):
                prod_hits = run_all_triggers(session, "US.RKLB", ["US.RKLX", "US.RKLZ"], dict(indicators), DEFAULT_PARAMS)
            for hit in prod_hits:
                key = (ts, hit.get("trigger"), hit.get("direction"))
                if key in seen_prod:
                    continue
                seen_prod.add(key)
                production_records.append(_synthetic_record(ts, hit, bar.close, prev_close, "production_minute_replay"))
            for profile_name, profile in CANDIDATE_PROFILES.items():
                for hit in _candidate_hits(
                    ts, session, partial_1m, indicators, prev_close,
                    cooldown_by_profile[profile_name], profile_name, profile,
                ):
                    key = (ts, hit.get("trigger"), hit.get("direction"))
                    if key in seen_cand[profile_name]:
                        continue
                    seen_cand[profile_name].add(key)
                    candidate_records_by_profile[profile_name].append(
                        _synthetic_record(ts, hit, bar.close, prev_close, profile_name)
                    )

    original_review = _build_review_from_records(date, original_records)
    candidate_reviews: dict[str, dict] = {}
    for profile_name, candidate_records in candidate_records_by_profile.items():
        # Candidate score is original historical pushes + candidate overlay only.
        # 评分只比较"历史原始推送 + 候选补充",避免生产分钟回放信号污染候选结果。
        candidate_reviews[profile_name] = _build_review_from_records(date, original_records + candidate_records)
    return original_review, candidate_reviews, production_records, candidate_records_by_profile, source


def _build_review_from_records(date: str, records: list[dict]) -> dict:
    original = coverage.load_triggers
    try:
        coverage.load_triggers = lambda _date: records
        return coverage.build_review(date, fetch_1m=False)
    finally:
        coverage.load_triggers = original


def _counts(review: dict) -> Counter:
    out = Counter()
    for item in review.get("waves") or []:
        out[item["coverage"]["status"]] += 1
    return out


def _wrong_strong(review: dict) -> int:
    return sum(item["coverage"].get("opposite_strong_total", 0) for item in review.get("waves") or [])


def _fmt_counts(counts: Counter) -> str:
    return f"{counts['TIMELY']}/{counts['LATE']}/{counts['MISS']}/{counts['WRONG_SIDE']}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", default=["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"])
    parser.add_argument("--no-fetch-1m", action="store_true")
    args = parser.parse_args()

    lines = [
        "# Minute Replay Candidate Strategy Variants",
        "",
        "Purpose: compare several minute-level breakdown/rebound candidates before any live strategy update.",
        "",
    ]
    total_before = Counter()
    wrong_before = 0
    prod_total = 0
    totals_by_profile = {name: Counter() for name in CANDIDATE_PROFILES}
    wrong_by_profile = {name: 0 for name in CANDIDATE_PROFILES}
    cand_total_by_profile = {name: 0 for name in CANDIDATE_PROFILES}
    detail_by_profile: dict[str, list[str]] = {name: [] for name in CANDIDATE_PROFILES}
    date_rows: list[str] = [
        "| Date | K source | Prod replay | Profile | Candidate added | Before T/L/M/W | Candidate T/L/M/W | Wrong STRONG before→candidate |",
        "|---|---|---:|---|---:|---|---|---:|",
    ]

    for date in args.dates:
        before, candidates, prod_records, candidate_records_by_profile, source = _replay_date(
            date, fetch_1m=not args.no_fetch_1m
        )
        bc = _counts(before)
        total_before.update(bc)
        wb = _wrong_strong(before)
        wrong_before += wb
        prod_total += len(prod_records)
        for profile_name, after in candidates.items():
            ac = _counts(after)
            wa = _wrong_strong(after)
            cand_records = candidate_records_by_profile[profile_name]
            totals_by_profile[profile_name].update(ac)
            wrong_by_profile[profile_name] += wa
            cand_total_by_profile[profile_name] += len(cand_records)
            date_rows.append(
                f"| {date} | {source} | {len(prod_records)} | {profile_name} | {len(cand_records)} | "
                f"{_fmt_counts(bc)} | {_fmt_counts(ac)} | {wb}→{wa} |"
            )
            if cand_records:
                detail_by_profile[profile_name].append(f"### {date}")
                detail_by_profile[profile_name].append("")
                for rec in cand_records[:20]:
                    detail_by_profile[profile_name].append(
                        f"- {rec['ts']} {rec['trigger']}/{rec['direction']}/{rec['strength']} "
                        f"conf={rec['confidence']} price={rec['prices'].get('RKLB')}"
                    )
                detail_by_profile[profile_name].append("")

    lines += [
        "## Daily Results",
        "",
        *date_rows,
        "",
        "## Summary",
        "",
        f"- Production minute replay signals: {prod_total}",
        f"- Baseline TIMELY/LATE/MISS/WRONG_SIDE: {_fmt_counts(total_before)}",
        f"- Baseline wrong-side STRONG: {wrong_before}",
        "",
        "| Profile | Added | T/L/M/W | TIMELY Δ | MISS Δ | Wrong STRONG Δ | Useful Δ | Added/useful | Decision |",
        "|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]

    ranked: list[tuple[int, int, int, str]] = []
    for profile_name in CANDIDATE_PROFILES:
        counts = totals_by_profile[profile_name]
        timely_delta = counts["TIMELY"] - total_before["TIMELY"]
        miss_delta = counts["MISS"] - total_before["MISS"]
        wrong_delta = wrong_by_profile[profile_name] - wrong_before
        useful_delta = timely_delta + max(0, -miss_delta)
        added = cand_total_by_profile[profile_name]
        added_per_useful = added / useful_delta if useful_delta > 0 else 999.0
        decision = "DISCUSS" if useful_delta > 0 and wrong_delta <= 0 and added_per_useful <= 8 else "REJECT"
        ranked.append((useful_delta, -int(added_per_useful * 100), -wrong_delta, profile_name))
        lines.append(
            f"| {profile_name} | {cand_total_by_profile[profile_name]} | {_fmt_counts(counts)} | "
            f"{timely_delta:+d} | {miss_delta:+d} | {wrong_delta:+d} | {useful_delta:+d} | "
            f"{added_per_useful:.1f} | {decision} |"
        )

    ranked.sort(reverse=True)
    best_profile = ranked[0][3] if ranked else ""
    best_counts = totals_by_profile[best_profile] if best_profile else Counter()
    best_timely_delta = best_counts["TIMELY"] - total_before["TIMELY"] if best_profile else 0
    best_miss_delta = best_counts["MISS"] - total_before["MISS"] if best_profile else 0
    best_wrong_delta = wrong_by_profile[best_profile] - wrong_before if best_profile else 0
    best_useful_delta = best_timely_delta + max(0, -best_miss_delta)
    best_added = cand_total_by_profile[best_profile] if best_profile else 0
    best_added_per_useful = best_added / best_useful_delta if best_useful_delta > 0 else 999.0
    if best_profile and best_useful_delta > 0 and best_wrong_delta <= 0 and best_added_per_useful <= 8:
        final_decision = (
            f"DISCUSS {best_profile}: improved timing with acceptable alert cost "
            f"({best_added_per_useful:.1f} added/useful)."
        )
    else:
        final_decision = "REJECT ALL: no variant improved TIMELY/MISS enough to justify live alerts."

    lines += [
        "",
        "## Decision",
        "",
        final_decision,
        "",
        "## Decision Notes",
        "",
        "- A variant must raise TIMELY or reduce MISS without increasing wrong-side STRONG.",
        "- If a variant only adds weak alerts without coverage improvement, keep it in research.",
        "- This report tests direction timing only; VectorBT/QuantStats should test trade PnL next.",
        "",
    ]
    for profile_name, detail_lines in detail_by_profile.items():
        if not detail_lines:
            continue
        lines.append(f"## Candidate Signals - {profile_name}")
        lines.append("")
        lines += detail_lines
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"minute_replay_candidate_{stamp}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
