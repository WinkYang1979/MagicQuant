"""
MagicQuant - direction cap variant replay
VERSION : v0.1.0
DATE    : 2026-05-30
DEPENDS : scripts.review_signal_coverage, data/review/YYYY-MM-DD/triggers.json

Pure offline replay for direction_trend STRONG-long downgrade candidates.
纯离线回放 direction_trend 强多降级候选；不修改实盘策略。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_signal_coverage as cov

OUT_PATH = ROOT / "docs" / "discussion_2026-05-30_direction_cap_variant_replay.md"


def _price(record: dict) -> float | None:
    data = record.get("data") or {}
    value = data.get("current") or (record.get("prices") or {}).get("RKLB")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vwap(record: dict) -> float | None:
    try:
        return float((record.get("data") or {}).get("vwap"))
    except (TypeError, ValueError):
        return None


def _day_chg(record: dict) -> float | None:
    try:
        return float((record.get("data") or {}).get("day_change_pct"))
    except (TypeError, ValueError):
        return None


def _rth_open(segment: dict) -> float | None:
    bars = segment.get("bars") or []
    rth = [
        bar for bar in bars
        if (bar.ts.hour, bar.ts.minute) >= (9, 30) and (bar.ts.hour, bar.ts.minute) <= (16, 0)
    ]
    rows = rth or bars
    if not rows:
        return None
    try:
        return float(rows[0].open)
    except (TypeError, ValueError):
        return None


def _bars_before(segment: dict, ts: datetime):
    return [bar for bar in (segment.get("bars") or []) if bar.ts <= ts]


def _lower_highs(segment: dict, ts: datetime) -> bool:
    bars = _bars_before(segment, ts)
    if len(bars) < 3:
        return False
    highs = [float(bar.high) for bar in bars[-3:]]
    return highs[-1] <= highs[-2] <= highs[-3]


def _remaining_adverse_pct(wave, segment: dict, ts: datetime, entry: float) -> float | None:
    """Estimate adverse move after a wrong long. / 估算错误做多后的后续最大不利波动。"""
    if entry <= 0:
        return None
    future = [bar for bar in (segment.get("bars") or []) if ts <= bar.ts <= wave.end]
    if not future:
        return None
    low = min(float(bar.low) for bar in future)
    return (low - entry) / entry * 100.0


def _feature_row(record: dict, wave_item: dict) -> dict:
    wave = wave_item["wave"]
    segment = wave_item["segment"]
    ts = cov._trigger_et(record)
    price = _price(record)
    vwap = _vwap(record)
    day_chg = _day_chg(record)
    feat = cov._feature_for_record(record, segment) if segment else {}
    intraday_open = _rth_open(segment)
    intraday_chg = None
    if price is not None and intraday_open and intraday_open > 0:
        intraday_chg = (price - intraday_open) / intraday_open * 100.0

    price_below_vwap = price is not None and vwap is not None and price < vwap
    move10 = feat.get("move10")
    move15 = feat.get("move15")
    high_dd = feat.get("high_dd")
    lower_highs = _lower_highs(segment, ts) if ts else False

    # Variant A: gap up but RTH intraday action does not confirm.
    # 方案甲：较昨收强，但 RTH 盘中未确认。
    cap_a = (
        day_chg is not None and day_chg > 0
        and intraday_chg is not None and intraday_chg <= 0
        and price_below_vwap
    )

    # Variant B: structural rollover candidate; deliberately measured, not live.
    # 方案乙：结构转弱候选，只做测量，不直接上线。使用 OR 口径观察误伤率。
    cap_b = bool(
        price_below_vwap
        or (move10 is not None and move10 < 0)
        or (move15 is not None and move15 < 0)
        or lower_highs
        or (high_dd is not None and high_dd >= 1.0)
    )

    adverse = None
    if wave.direction == "down" and price is not None and ts is not None:
        adverse = _remaining_adverse_pct(wave, segment, ts, price)

    return {
        "date": None,
        "ts": ts,
        "trigger": record.get("trigger"),
        "confidence": cov._confidence_value(record),
        "class": "correct_up" if wave.direction == "up" else "wrong_down",
        "price": price,
        "day_chg": day_chg,
        "intraday_chg": intraday_chg,
        "price_below_vwap": price_below_vwap,
        "move10": move10,
        "move15": move15,
        "high_dd": high_dd,
        "lower_highs": lower_highs,
        "cap_a": cap_a,
        "cap_b": cap_b,
        "cap_a_or_b": cap_a or cap_b,
        "adverse_pct": adverse,
    }


def _strong_direction_rows(date_str: str) -> tuple[list[dict], dict]:
    review = cov.build_review(date_str, fetch_1m=False, ticker="RKLB")
    rows: list[dict] = []
    for record in review["records"]:
        if record.get("trigger") != "direction_trend":
            continue
        if (record.get("direction") or "").lower() != "long":
            continue
        if (record.get("strength") or "").upper() != "STRONG":
            continue
        ts = cov._trigger_et(record)
        if ts is None:
            continue
        wave_item = next(
            (item for item in review["waves"] if item["wave"].start <= ts <= item["wave"].end),
            None,
        )
        if wave_item is None:
            continue
        row = _feature_row(record, wave_item)
        row["date"] = date_str
        rows.append(row)
    return rows, review


def _variant_stats(rows: list[dict], flag: str) -> dict:
    wrong = [row for row in rows if row["class"] == "wrong_down"]
    correct = [row for row in rows if row["class"] == "correct_up"]
    caught_wrong = [row for row in wrong if row[flag]]
    killed_correct = [row for row in correct if row[flag]]
    adverse = [row["adverse_pct"] for row in caught_wrong if row.get("adverse_pct") is not None]
    avg_adverse = sum(adverse) / len(adverse) if adverse else None
    return {
        "wrong_total": len(wrong),
        "correct_total": len(correct),
        "wrong_caught": len(caught_wrong),
        "correct_downgraded": len(killed_correct),
        "wrong_caught_pct": (len(caught_wrong) / len(wrong) * 100.0) if wrong else 0.0,
        "correct_downgraded_pct": (len(killed_correct) / len(correct) * 100.0) if correct else 0.0,
        "avg_caught_adverse_pct": avg_adverse,
    }


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def build_report(dates: list[str]) -> str:
    all_rows: list[dict] = []
    review_counts = {}
    for date_str in dates:
        rows, review = _strong_direction_rows(date_str)
        all_rows.extend(rows)
        counts = cov._coverage_counts(review["waves"])
        review_counts[date_str] = {
            "waves": len(review["waves"]),
            "miss": counts.get("MISS", 0),
            "wrong_strong": cov._wrong_strong_total(review["waves"]),
            "rows": len(rows),
        }

    variants = [
        ("A_gap_intraday", "cap_a", "方案甲: gap 强但盘中未确认"),
        ("B_structure_rollover", "cap_b", "方案乙: VWAP/动能/低高点结构转弱"),
        ("A_or_B", "cap_a_or_b", "甲或乙: 任一命中即降级"),
    ]

    lines = [
        "# Direction Trend STRONG-long Cap Replay",
        "",
        "VERSION : v0.1.0",
        "SCOPE   : offline analysis only; no live strategy changed",
        "",
        "## Summary",
        "",
        f"- Dates: {', '.join(dates)}",
        f"- Samples: direction_trend / long / STRONG / in-wave = {len(all_rows)}",
        "- Candidate action: downgrade STRONG to WEAK only; do not silence the signal.",
        "",
        "## Daily Baseline",
        "",
        "| Date | Waves | MISS | Wrong STRONG | STRONG-long samples |",
        "|---|---:|---:|---:|---:|",
    ]
    for date_str in dates:
        item = review_counts[date_str]
        lines.append(
            f"| {date_str} | {item['waves']} | {item['miss']} | "
            f"{item['wrong_strong']} | {item['rows']} |"
        )

    lines += [
        "",
        "## Variant Results",
        "",
        "| Variant | Wrong caught | Correct downgraded | Avg caught adverse | Readout |",
        "|---|---:|---:|---:|---|",
    ]
    for name, flag, note in variants:
        stats = _variant_stats(all_rows, flag)
        lines.append(
            f"| {name} | {stats['wrong_caught']}/{stats['wrong_total']} "
            f"({_fmt_pct(stats['wrong_caught_pct'])}) | "
            f"{stats['correct_downgraded']}/{stats['correct_total']} "
            f"({_fmt_pct(stats['correct_downgraded_pct'])}) | "
            f"{_fmt_pct(stats['avg_caught_adverse_pct'])} | {note} |"
        )

    lines += [
        "",
        "## Sample Rows",
        "",
        "| Date | ET | Class | Conf | Price | Day% | Intra% | <VWAP | m10 | m15 | highDD | LH | A | B |",
        "|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|---|---|",
    ]
    for row in all_rows[:80]:
        et = row["ts"].strftime("%m-%d %H:%M") if row.get("ts") else "?"
        lines.append(
            f"| {row['date']} | {et} | {row['class']} | {row['confidence']} | "
            f"{row['price']:.2f} | {_fmt_pct(row['day_chg'])} | {_fmt_pct(row['intraday_chg'])} | "
            f"{'Y' if row['price_below_vwap'] else 'N'} | {_fmt_pct(row['move10'])} | "
            f"{_fmt_pct(row['move15'])} | {_fmt_pct(row['high_dd'])} | "
            f"{'Y' if row['lower_highs'] else 'N'} | {'Y' if row['cap_a'] else 'N'} | "
            f"{'Y' if row['cap_b'] else 'N'} |"
        )
    if len(all_rows) > 80:
        lines.append(f"| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |")

    lines += [
        "",
        "## Decision Rule",
        "",
        "- Promotion gate: wrong STRONG decreases materially, while correct STRONG downgrade stays low.",
        "- This report does not judge fast-wave MISS fixes; it only evaluates direction_trend confidence honesty.",
        "- If B or A_or_B downgrades too many correct_up samples, keep live logic at A only.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay direction_trend cap variants.")
    parser.add_argument("dates", nargs="*", default=["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30"])
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    report = build_report(args.dates)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"saved {out}")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
