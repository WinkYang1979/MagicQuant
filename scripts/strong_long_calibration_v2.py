"""
MagicQuant - STRONG long calibration v2
VERSION : v0.1.0
DATE    : 2026-05-21
DEPENDS : scripts/review_signal_coverage.py

只读标定 STRONG long 信号，不修改策略。
Read-only calibration for STRONG long signals; no strategy changes.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.review_signal_coverage import (  # noqa: E402
    DEFAULT_ATR_MULT,
    DEFAULT_SEGMENT_GAP_MINUTES,
    DEFAULT_WAVE_THRESHOLD_PCT,
    OUT_DIR,
    REVIEW_DIR,
    Wave,
    _coverage_counts,
    _filter_records_for_ticker,
    _fmt_et,
    _record_matches_ticker,
    _session_name,
    _trigger_et,
    build_review,
    evaluate_wave_coverage,
)

DOCS_DIR = ROOT / "docs"
REPORT_NAME = "discussion_2026-05-21_strong_long_calibration_v2.md"
TARGET_TRIGGERS = ("direction_trend", "intraday_reversal", "swing_bottom")


@dataclass(frozen=True)
class Sample:
    date: str
    trigger: str
    record: dict
    segment: dict
    wave_item: dict | None
    cls: str
    session: str
    features: dict


@dataclass(frozen=True)
class Rule:
    name: str
    func: Callable[[Sample], bool]


def _available_dates(start: str) -> list[str]:
    dates = []
    for item in REVIEW_DIR.iterdir():
        if item.is_dir() and item.name >= start and (item / "triggers.json").exists():
            dates.append(item.name)
    return sorted(dates)


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def _pct(num: int, den: int) -> str:
    if den <= 0:
        return "-"
    return f"{num / den * 100:.1f}%"


def _num(values: list[float | None]) -> list[float]:
    return sorted(v for v in (_safe_float(x) for x in values) if v is not None)


def _iqr(values: list[float | None]) -> str:
    nums = _num(values)
    if not nums:
        return "-"
    q1 = nums[len(nums) // 4]
    q3 = nums[(len(nums) * 3) // 4]
    return f"{q1:.2f}..{q3:.2f}"


def _med(values: list[float | None]) -> str:
    nums = _num(values)
    return "-" if not nums else f"{median(nums):.2f}"


def _minmax(values: list[float | None]) -> str:
    nums = _num(values)
    return "-" if not nums else f"{nums[0]:.2f}..{nums[-1]:.2f}"


def _rsi_slope(rsi_history: list) -> tuple[float | None, str]:
    raw = rsi_history[-5:] if isinstance(rsi_history, list) else []
    nums = [v for v in (_safe_float(item) for item in raw) if v is not None]
    if len(nums) < 2:
        return None, "unknown"
    slope = nums[-1] - nums[0]
    if slope > 1.0:
        return slope, "up"
    if slope < -1.0:
        return slope, "down"
    return slope, "flat"


def _lower_highs_from_record(record: dict) -> bool | None:
    bars = (((record.get("decision_context") or {}).get("kline_data") or {}).get("bars") or [])
    highs: list[float] = []
    for raw in bars[-3:]:
        high = _safe_float(raw.get("high") if isinstance(raw, dict) else None)
        if high is not None:
            highs.append(high)
    if len(highs) < 3:
        return None
    return highs[0] > highs[1] > highs[2]


def _close_before(segment: dict, ts: datetime, minutes: int) -> float | None:
    target = ts.timestamp() - minutes * 60
    prior = [bar for bar in segment["bars"] if bar.ts.timestamp() <= target]
    return prior[-1].close if prior else None


def _segment_high_before(segment: dict, ts: datetime) -> float | None:
    bars = [bar for bar in segment["bars"] if bar.ts <= ts]
    if not bars:
        return None
    return max(bar.high for bar in bars)


def _features(record: dict, segment: dict) -> dict:
    dc = record.get("decision_context") or {}
    price_context = dc.get("price_context") or {}
    indicators = dc.get("indicators_raw") or {}
    data = record.get("data") or {}
    ts = _trigger_et(record)
    price = (
        _safe_float(price_context.get("current"))
        or _safe_float(data.get("current"))
        or _safe_float((record.get("prices") or {}).get("RKLB"))
    )
    vwap = _safe_float(indicators.get("vwap")) or _safe_float(data.get("vwap"))
    rsi = _safe_float(indicators.get("rsi_14")) or _safe_float(data.get("rsi"))
    vol_ratio = _safe_float(indicators.get("vol_ratio")) or _safe_float(data.get("vol_ratio"))
    day_chg = _safe_float(price_context.get("day_change_pct")) or _safe_float(data.get("day_change_pct"))
    prev10 = _close_before(segment, ts, 10) if ts else None
    prev15 = _close_before(segment, ts, 15) if ts else None
    high = _segment_high_before(segment, ts) if ts else None
    rsi_slope_value, rsi_slope_label = _rsi_slope(indicators.get("rsi_history") or [])
    price_vs_vwap = ((price - vwap) / vwap * 100) if price is not None and vwap else None
    move10 = ((price - prev10) / prev10 * 100) if price is not None and prev10 else None
    move15 = ((price - prev15) / prev15 * 100) if price is not None and prev15 else None
    high_dd = ((high - price) / high * 100) if price is not None and high else None
    lower_highs = _lower_highs_from_record(record)
    weakness_count = sum(
        1
        for flag in (
            price_vs_vwap is not None and price_vs_vwap < 0,
            move10 is not None and move10 < 0,
            move15 is not None and move15 < 0,
            rsi_slope_label == "down",
            lower_highs is True,
        )
        if flag
    )
    above_vwap = None if price_vs_vwap is None else price_vs_vwap >= 0
    return {
        "price": price,
        "price_vs_vwap": price_vs_vwap,
        "above_vwap": above_vwap,
        "rsi": rsi,
        "rsi_slope": rsi_slope_value,
        "rsi_slope_label": rsi_slope_label,
        "high_dd": high_dd,
        "move10": move10,
        "move15": move15,
        "lower_highs": lower_highs,
        "day_chg": day_chg,
        "vol_ratio": vol_ratio,
        "weakness_count": weakness_count,
    }


def _find_segment(segments: list[dict], ts: datetime) -> dict | None:
    return next((seg for seg in segments if seg["start"] <= ts <= seg["end"]), None)


def _find_wave_item(wave_items: list[dict], ts: datetime) -> dict | None:
    return next((item for item in wave_items if item["wave"].start <= ts <= item["wave"].end), None)


def collect_samples(reviews: list[dict], ticker: str) -> list[Sample]:
    samples: list[Sample] = []
    for review in reviews:
        for record in review["records"]:
            if not _record_matches_ticker(record, ticker):
                continue
            if (record.get("trigger") or "") not in TARGET_TRIGGERS:
                continue
            if (record.get("direction") or "").lower() != "long":
                continue
            if (record.get("strength") or "").upper() != "STRONG":
                continue
            ts = _trigger_et(record)
            if ts is None:
                continue
            segment = _find_segment(review["segments"], ts)
            if not segment:
                continue
            wave_item = _find_wave_item(review["waves"], ts)
            if wave_item is None:
                cls = "no_wave"
            elif wave_item["wave"].direction == "up":
                cls = "correct_up"
            else:
                cls = "wrong_down"
            samples.append(Sample(
                date=review["date"],
                trigger=record.get("trigger") or "?",
                record=record,
                segment=segment,
                wave_item=wave_item,
                cls=cls,
                session=_session_name(ts),
                features=_features(record, segment),
            ))
    return samples


def _sample_rows(samples: list[Sample], trigger: str, session: str) -> list[Sample]:
    return [s for s in samples if s.trigger == trigger and s.session == session and s.cls in ("correct_up", "wrong_down")]


def _feature_stats(samples: list[Sample]) -> list[str]:
    cols = [
        ("price_vs_vwap", "price_vs_vwap%"),
        ("high_dd", "high_dd%"),
        ("move10", "move10%"),
        ("move15", "move15%"),
        ("rsi", "rsi"),
        ("rsi_slope", "rsi_slope"),
        ("day_chg", "day_chg%"),
        ("vol_ratio", "vol_ratio"),
    ]
    lines = [
        "| Feature | Correct N | Correct med | Correct IQR | Correct min..max | Wrong N | Wrong med | Wrong IQR | Wrong min..max |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    correct = [s for s in samples if s.cls == "correct_up"]
    wrong = [s for s in samples if s.cls == "wrong_down"]
    for key, label in cols:
        c_vals = [s.features.get(key) for s in correct]
        w_vals = [s.features.get(key) for s in wrong]
        lines.append(
            f"| {label} | {len(_num(c_vals))} | {_med(c_vals)} | {_iqr(c_vals)} | {_minmax(c_vals)} | "
            f"{len(_num(w_vals))} | {_med(w_vals)} | {_iqr(w_vals)} | {_minmax(w_vals)} |"
        )
    for key, label in (("above_vwap", "above_vwap"), ("lower_highs", "lower_highs"), ("rsi_slope_label", "rsi_down")):
        if key == "rsi_slope_label":
            c_avail = [s for s in correct if s.features.get(key) != "unknown"]
            w_avail = [s for s in wrong if s.features.get(key) != "unknown"]
            c_true = sum(1 for s in c_avail if s.features.get(key) == "down")
            w_true = sum(1 for s in w_avail if s.features.get(key) == "down")
        else:
            c_avail = [s for s in correct if s.features.get(key) is not None]
            w_avail = [s for s in wrong if s.features.get(key) is not None]
            c_true = sum(1 for s in c_avail if s.features.get(key) is True)
            w_true = sum(1 for s in w_avail if s.features.get(key) is True)
        lines.append(f"| {label} | {len(c_avail)} | {c_true}/{len(c_avail)} | {_pct(c_true, len(c_avail))} | - | {len(w_avail)} | {w_true}/{len(w_avail)} | {_pct(w_true, len(w_avail))} | - |")
    return lines


def _candidate_rules() -> list[Rule]:
    rules: list[Rule] = []
    for threshold in (0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5):
        rules.append(Rule(f"high_dd >= {threshold:.1f}%", lambda s, t=threshold: (s.features.get("high_dd") or -999) >= t))
    for threshold in (-1.0, -0.7, -0.5, -0.3, 0.0):
        rules.append(Rule(f"move10 <= {threshold:.1f}%", lambda s, t=threshold: (s.features.get("move10") or 999) <= t))
        rules.append(Rule(f"move15 <= {threshold:.1f}%", lambda s, t=threshold: (s.features.get("move15") or 999) <= t))
    for threshold in (-0.5, 0.0, 0.3, 0.5):
        rules.append(Rule(f"price_vs_vwap <= {threshold:.1f}%", lambda s, t=threshold: (s.features.get("price_vs_vwap") or 999) <= t))
    rules.append(Rule("lower_highs == True", lambda s: s.features.get("lower_highs") is True))
    rules.append(Rule("RSI slope == down", lambda s: s.features.get("rsi_slope_label") == "down"))
    for day_threshold in (2.0, 3.0, 5.0):
        for weakness in (1, 2, 3):
            rules.append(Rule(
                f"day_chg >= {day_threshold:.0f}% and weakness_count >= {weakness}",
                lambda s, d=day_threshold, w=weakness: (s.features.get("day_chg") or -999) >= d and (s.features.get("weakness_count") or 0) >= w,
            ))
    return rules


def _remaining_space_pct(sample: Sample, replacement: Sample) -> float | None:
    if not sample.wave_item or not replacement.features.get("price"):
        return None
    wave: Wave = sample.wave_item["wave"]
    if wave.direction != "up" or wave.end_price <= wave.start_price:
        return None
    return max(0.0, (wave.end_price - replacement.features["price"]) / (wave.end_price - wave.start_price) * 100)


def _recovery_stats(rule: Rule, correct_samples: list[Sample]) -> dict:
    suppressed = [s for s in correct_samples if rule.func(s)]
    recovered = 0
    executable = 0
    remaining_values = []
    delays = []
    for sample in suppressed:
        if not sample.wave_item:
            continue
        wave: Wave = sample.wave_item["wave"]
        ts = _trigger_et(sample.record)
        if ts is None:
            continue
        later = [
            s for s in correct_samples
            if s.wave_item is sample.wave_item
            and _trigger_et(s.record) is not None
            and _trigger_et(s.record) > ts
            and not rule.func(s)
        ]
        if not later:
            continue
        repl = min(later, key=lambda item: _trigger_et(item.record) or wave.end)
        recovered += 1
        delay = (_trigger_et(repl.record) - wave.start).total_seconds() / 60.0
        remaining = _remaining_space_pct(sample, repl)
        delays.append(delay)
        remaining_values.append(remaining)
        if remaining is not None and remaining >= 50.0:
            executable += 1
    return {
        "suppressed": len(suppressed),
        "recovered": recovered,
        "executable": executable,
        "delay_med": _med(delays),
        "remain_med": _med(remaining_values),
    }


def _rule_eval(rule: Rule, samples: list[Sample]) -> dict:
    correct = [s for s in samples if s.cls == "correct_up"]
    wrong = [s for s in samples if s.cls == "wrong_down"]
    hit_correct = [s for s in correct if rule.func(s)]
    hit_wrong = [s for s in wrong if rule.func(s)]
    recovery = _recovery_stats(rule, correct)
    return {
        "rule": rule.name,
        "wrong_total": len(wrong),
        "correct_total": len(correct),
        "wrong_hit": len(hit_wrong),
        "correct_hit": len(hit_correct),
        "wrong_pct": (len(hit_wrong) / len(wrong) * 100) if wrong else 0.0,
        "correct_pct": (len(hit_correct) / len(correct) * 100) if correct else 0.0,
        "recovery": recovery,
    }


def _candidate_table(samples: list[Sample]) -> list[str]:
    evals = [_rule_eval(rule, samples) for rule in _candidate_rules()]
    evals = [item for item in evals if item["wrong_total"] > 0 and item["correct_total"] > 0]
    evals.sort(key=lambda item: (-item["wrong_pct"], item["correct_pct"], item["rule"]))
    lines = [
        "| Candidate rule | Wrong hit | Correct killed | Recovered | Executable recovery | Median refill delay | Median space left |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in evals[:18]:
        rec = item["recovery"]
        lines.append(
            f"| {item['rule']} | {item['wrong_hit']}/{item['wrong_total']} ({item['wrong_pct']:.1f}%) | "
            f"{item['correct_hit']}/{item['correct_total']} ({item['correct_pct']:.1f}%) | "
            f"{rec['recovered']}/{rec['suppressed']} | {rec['executable']}/{rec['suppressed']} | "
            f"{rec['delay_med']} min | {rec['remain_med']}% |"
        )
    return lines


def _candidate_passes(samples: list[Sample]) -> list[dict]:
    rows = []
    for rule in _candidate_rules():
        item = _rule_eval(rule, samples)
        if item["wrong_total"] <= 0 or item["correct_total"] <= 0:
            continue
        if item["wrong_pct"] >= 70.0 and item["correct_pct"] < 15.0:
            rows.append(item)
    return rows


def _simulate_after_counts(review: dict, rule: Rule, trigger: str, session: str) -> dict:
    suppressed_ids: set[int] = set()
    review_samples = collect_samples([review], review.get("ticker", "RKLB"))
    for sample in review_samples:
        if sample.trigger == trigger and sample.session == session and rule.func(sample):
            suppressed_ids.add(id(sample.record))
    before = _coverage_counts(review["waves"])
    after_waves = []
    for item in review["waves"]:
        wave = item["wave"]
        records = [r for r in review["records"] if id(r) not in suppressed_ids]
        cov = evaluate_wave_coverage(wave, records, target_ticker=review.get("ticker", "RKLB"))
        after_waves.append({"wave": wave, "coverage": cov})
    after = _coverage_counts(after_waves)
    return {
        "before_miss": before.get("MISS", 0),
        "after_miss": after.get("MISS", 0),
        "before_wrong": before.get("WRONG_SIDE", 0),
        "after_wrong": after.get("WRONG_SIDE", 0),
        "suppressed": len(suppressed_ids),
    }


def _redline_0519(samples: list[Sample], reviews: list[dict]) -> list[str]:
    dt_regular = _sample_rows(samples, "direction_trend", "regular")
    candidates = _candidate_passes(dt_regular)
    review_0519 = next((r for r in reviews if r["date"] == "2026-05-19"), None)
    lines = [
        "| Rule | Suppressed on 05-19 | MISS before -> after | WRONG before -> after | Verdict |",
        "|---|---:|---:|---:|---|",
    ]
    if not review_0519:
        lines.append("| - | - | - | - | 2026-05-19 review unavailable |")
        return lines
    if not candidates:
        lines.append("| - | 0 | - | - | No rule passed the preset gate, so 05-19 redline is not triggered. |")
        return lines
    for item in candidates[:8]:
        rule = next(rule for rule in _candidate_rules() if rule.name == item["rule"])
        counts = _simulate_after_counts(review_0519, rule, "direction_trend", "regular")
        verdict = "REJECT" if counts["after_miss"] > counts["before_miss"] else "OK"
        lines.append(
            f"| {item['rule']} | {counts['suppressed']} | {counts['before_miss']} -> {counts['after_miss']} | "
            f"{counts['before_wrong']} -> {counts['after_wrong']} | {verdict} |"
        )
    return lines


def _daily_counts(samples: list[Sample]) -> list[str]:
    by_date: dict[str, dict[str, int]] = {}
    for sample in samples:
        row = by_date.setdefault(sample.date, {"all": 0, "regular": 0, "premarket": 0, "gap_excluded": 0})
        row["all"] += 1
        row[sample.session] = row.get(sample.session, 0) + 1
    lines = [
        "| Date | In-session STRONG long samples | Regular | Premarket |",
        "|---|---:|---:|---:|",
    ]
    for date in sorted(by_date):
        row = by_date[date]
        lines.append(f"| {date} | {row['all']} | {row.get('regular', 0)} | {row.get('premarket', 0)} |")
    return lines


def _verdict_for_trigger(samples: list[Sample], trigger: str, session: str) -> str:
    rows = _sample_rows(samples, trigger, session)
    wrong = sum(1 for s in rows if s.cls == "wrong_down")
    correct = sum(1 for s in rows if s.cls == "correct_up")
    if trigger != "direction_trend" and wrong < 5:
        return f"In-session wrong sample is {wrong}, below the ~5 evidence floor. Verdict: do not design a gate for {trigger} yet."
    passes = _candidate_passes(rows)
    if trigger == "direction_trend" and not passes:
        return (
            "No measured feature/combination reached the preset gate "
            "(catch >=70% wrong_down and kill <15% correct_up). Verdict: structure gate is not supported; prefer confidence/STRONG cap."
        )
    if passes:
        names = ", ".join(item["rule"] for item in passes[:3])
        return f"Candidate separation exists under preset gate: {names}. Must still pass 05-19 redline before strategy use."
    return f"Samples: correct_up={correct}, wrong_down={wrong}. Verdict: no actionable separation."


def build_report(reviews: list[dict], samples: list[Sample], dates: list[str]) -> str:
    lines = [
        "# STRONG Long Calibration v2",
        "",
        "VERSION : v0.1.0",
        "DATE    : 2026-05-21",
        "DEPENDS : scripts/review_signal_coverage.py, data/review/YYYY-MM-DD/triggers.json",
        "",
        "## Scope",
        "",
        "- Read-only analysis only. No strategy code, trigger, DEFAULT_PARAMS, or dispatch changes.",
        "- Uses gap-segmented review waves; gap/out-of-session signals are excluded from calibration.",
        "- Premarket samples are reported separately and are not mixed into RTH calibration.",
        "- Main question: can RTH direction_trend STRONG-long wrong_down signals be separated from correct_up at firing time?",
        "",
        "## Preset Decision Gate",
        "",
        "- direction_trend: a structure rule must catch >=70% of wrong_down while killing <15% of correct_up. Otherwise prefer confidence/STRONG cap.",
        "- intraday_reversal / swing_bottom: if in-session wrong sample is below ~5, do not design a gate in this round.",
        "- 05-19 redline: any candidate that increases MISS on 2026-05-19 is rejected.",
        "",
        "## Available Review Dates",
        "",
        f"- Dates scanned: {len(dates)}",
        f"- Range: {dates[0] if dates else '-'} -> {dates[-1] if dates else '-'}",
        "",
    ]
    lines += _daily_counts(samples)
    lines += [
        "",
        "## Trigger-Level Calibration",
        "",
    ]
    for trigger in TARGET_TRIGGERS:
        for session in ("regular", "premarket"):
            rows = _sample_rows(samples, trigger, session)
            correct = sum(1 for s in rows if s.cls == "correct_up")
            wrong = sum(1 for s in rows if s.cls == "wrong_down")
            no_wave = sum(1 for s in samples if s.trigger == trigger and s.session == session and s.cls == "no_wave")
            lines += [
                f"### {trigger} / {session}",
                "",
                f"- correct_up: {correct}",
                f"- wrong_down: {wrong}",
                f"- no_wave: {no_wave}",
                f"- 判定: {_verdict_for_trigger(samples, trigger, session)}",
                "",
                "Feature overlap:",
                "",
            ]
            if rows:
                lines += _feature_stats(rows)
                lines += ["", "Candidate sweep:", ""]
                lines += _candidate_table(rows)
            else:
                lines.append("- No in-session sample.")
            lines.append("")
    lines += [
        "## 05-19 Redline",
        "",
        "If a candidate rule makes 2026-05-19 more silent, reject it even if it helps 2026-05-21.",
        "",
    ]
    lines += _redline_0519(samples, reviews)
    direction_regular = _sample_rows(samples, "direction_trend", "regular")
    passes = _candidate_passes(direction_regular)
    recommendation = (
        "Structure gate"
        if passes
        else "Confidence/STRONG cap"
    )
    reason = (
        "At least one measured rule passed the preset separation gate; still verify 05-19 redline before coding."
        if passes
        else "No RTH direction_trend feature/combination passed the preset separation gate. Do not add a hard structure gate from this sample."
    )
    lines += [
        "",
        "## Final Recommendation",
        "",
        f"- Recommendation: **{recommendation}**",
        f"- Reason: {reason}",
        "- Practical implication: if confidence cap is chosen later, cap the label/score without muting the directional signal, so 05-19-style silence does not get worse.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build STRONG-long calibration v2 report.")
    parser.add_argument("--start", default="2026-04-24")
    parser.add_argument("--ticker", default="RKLB")
    parser.add_argument("--no-fetch-1m", action="store_true", default=True)
    parser.add_argument("--output", default=str(DOCS_DIR / REPORT_NAME))
    args = parser.parse_args()

    dates = _available_dates(args.start)
    reviews = []
    for date in dates:
        try:
            reviews.append(build_review(
                date,
                threshold_pct=DEFAULT_WAVE_THRESHOLD_PCT,
                atr_mult=DEFAULT_ATR_MULT,
                fetch_1m=False,
                ticker=args.ticker,
            ))
        except Exception as exc:
            print(f"[calibration] skip {date}: {exc}")
    samples = collect_samples(reviews, args.ticker)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(reviews, samples, dates), encoding="utf-8")
    print(f"[calibration] dates={len(dates)} reviews={len(reviews)} samples={len(samples)}")
    print(f"[calibration] report={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
