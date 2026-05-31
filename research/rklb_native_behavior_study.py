"""
MagicQuant RKLB Native Behavior Study.
VERSION : v1.0.0
DEPENDS : argparse, csv, dataclasses, datetime, json, pathlib, statistics, typing,
          config.settings

Purpose / 用途:
Historically validate RKLB-specific behavior hypotheses before any strategy
promotion. This is research-only: no strategy is added, no parameter is changed,
no optimization is performed, and no trade is sent.
在任何策略晋升前，对 RKLB 专属行为假设做历史验证；本模块仅研究，
不新增策略、不修改参数、不优化、不发送交易。
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, time
import json
from pathlib import Path
from statistics import mean
import sys
from typing import Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RTH_START = time(9, 30)
RTH_END = time(16, 0)
CAPITAL_UNIT = 100.0
WINDOWS = (20, 30, 60)


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class EventResult:
    name: str
    date: str
    signal_time: str
    direction: str
    entry_price: float
    returns: dict
    max_adverse_60m: float
    details: str


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def default_paths() -> dict[str, Path]:
    base = _base_dir()
    return {
        "rklb": base / "data" / "historical" / "RKLB_1m.csv",
        "out": base / "reports" / "research" / "REPORT_RKLB_NATIVE_BEHAVIOR.md",
        "queue": base / "reports" / "research" / "RESEARCH_QUEUE.md",
    }


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")


def _load_daily_bars(path: Path) -> Dict[str, List[Bar]]:
    days: Dict[str, List[Bar]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                ts = _parse_time(row["time_key"])
                if not (RTH_START <= ts.time() < RTH_END):
                    continue
                bar = Bar(
                    ts,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row.get("volume", 0) or 0),
                )
            except (KeyError, ValueError):
                continue
            days.setdefault(ts.strftime("%Y-%m-%d"), []).append(bar)
    return {day: bars for day, bars in days.items() if len(bars) >= 180}


def _pct(entry: float, exit_price: float) -> float:
    return (exit_price - entry) / entry if entry > 0 else 0.0


def _levered_pnl(direction: str, entry: float, exit_price: float) -> float:
    move = _pct(entry, exit_price)
    if direction == "LONG":
        return move * 2.0 * CAPITAL_UNIT
    if direction == "SHORT":
        return -move * 2.0 * CAPITAL_UNIT
    return 0.0


def _vwap(bars: List[Bar]) -> float:
    total_vol = sum(bar.volume for bar in bars)
    if total_vol <= 0:
        return bars[-1].close if bars else 0.0
    return sum(((bar.high + bar.low + bar.close) / 3.0) * bar.volume for bar in bars) / total_vol


def _first_index_at_or_after(bars: List[Bar], hhmm: str) -> Optional[int]:
    target = datetime.strptime(bars[0].ts.strftime("%Y-%m-%d") + " " + hhmm, "%Y-%m-%d %H:%M")
    for idx, bar in enumerate(bars):
        if bar.ts >= target:
            return idx
    return None


def _future_returns(bars: List[Bar], idx: int, direction: str) -> dict:
    entry = bars[idx].close
    output = {}
    for window in WINDOWS:
        target = min(idx + window, len(bars) - 1)
        output[f"{window}m"] = round(_levered_pnl(direction, entry, bars[target].close), 4)
    return output


def _max_adverse(bars: List[Bar], idx: int, direction: str, window: int = 60) -> float:
    entry = bars[idx].close
    sample = bars[idx : min(idx + window + 1, len(bars))]
    if not sample:
        return 0.0
    if direction == "LONG":
        worst = min(bar.low for bar in sample)
        return round(_levered_pnl("LONG", entry, worst), 4)
    worst = max(bar.high for bar in sample)
    return round(_levered_pnl("SHORT", entry, worst), 4)


def _same_time_volume_reference(days: Dict[str, List[Bar]], selected_days: List[str], day_idx: int, minute_idx: int, lookback: int = 5) -> Optional[float]:
    refs = []
    for prev_day in selected_days[max(0, day_idx - lookback) : day_idx]:
        bars = days[prev_day]
        if minute_idx < len(bars):
            refs.append(bars[minute_idx].volume)
    return mean(refs) if refs else None


def _add_event(events: List[EventResult], name: str, bars: List[Bar], idx: int, direction: str, details: str) -> None:
    events.append(
        EventResult(
            name=name,
            date=bars[idx].ts.strftime("%Y-%m-%d"),
            signal_time=bars[idx].ts.strftime("%H:%M"),
            direction=direction,
            entry_price=round(bars[idx].close, 4),
            returns=_future_returns(bars, idx, direction),
            max_adverse_60m=_max_adverse(bars, idx, direction),
            details=details,
        )
    )


def detect_events(days: Dict[str, List[Bar]], max_days: int = 90) -> List[EventResult]:
    selected_days = sorted(days)[-max_days:]
    events: List[EventResult] = []
    for day_idx, day in enumerate(selected_days):
        bars = days[day]
        if len(bars) < 240:
            continue

        # Horse 1: opening volume breakout. / 马1：开盘爆量突破。
        first_30 = bars[:30]
        open_high = max(bar.high for bar in first_30)
        avg_ref = _same_time_volume_reference(days, selected_days, day_idx, 29)
        if avg_ref and sum(bar.volume for bar in first_30) > avg_ref * 30 * 2.0:
            for idx in range(30, min(75, len(bars))):
                if bars[idx].close > open_high:
                    _add_event(events, "Horse 1 Opening Volume Breakout", bars, idx, "LONG", f"30m volume > recent same-time 2x; breakout {open_high:.2f}")
                    break

        # Horse 2: gap-up VWAP breakdown reversal. / 马2：高开低走反转。
        prev_close = days[selected_days[day_idx - 1]][-1].close if day_idx > 0 else None
        idx_1000 = _first_index_at_or_after(bars, "10:00")
        if prev_close and idx_1000 is not None:
            gap = _pct(prev_close, bars[0].open)
            if gap >= 0.03:
                for idx in range(1, idx_1000 + 1):
                    vwap = _vwap(bars[: idx + 1])
                    if bars[idx].close < vwap:
                        _add_event(events, "Horse 2 Gap-Up VWAP Breakdown", bars, idx, "SHORT", f"gap={gap:.2%}; broke VWAP {vwap:.2f} before 10:00")
                        break

        # Horse 3: midday dead-and-revive. / 马3：午盘假死复活。
        idx_1300 = _first_index_at_or_after(bars, "13:00")
        idx_1400 = _first_index_at_or_after(bars, "14:00")
        idx_1200 = _first_index_at_or_after(bars, "12:00")
        if idx_1200 and idx_1300 and idx_1400:
            morning = bars[:idx_1200]
            midday_base = bars[idx_1200:idx_1300]
            morning_high = max(bar.high for bar in morning)
            midday_range = (max(bar.high for bar in midday_base) - min(bar.low for bar in midday_base)) / bars[idx_1200].close
            avg_mid_vol = mean(bar.volume for bar in midday_base) if midday_base else 0.0
            if midday_range <= 0.015:
                for idx in range(idx_1300, idx_1400):
                    if bars[idx].close > morning_high and avg_mid_vol and bars[idx].volume > avg_mid_vol * 1.5:
                        _add_event(events, "Horse 3 Midday Revival", bars, idx, "LONG", f"midday_range={midday_range:.2%}; broke morning high {morning_high:.2f}")
                        break

        # Horse 4: closing charge. / 马4：尾盘冲锋。
        idx_1500 = _first_index_at_or_after(bars, "15:00")
        if idx_1500:
            pre_close_high = max(bar.high for bar in bars[:idx_1500])
            avg_day_vol = mean(bar.volume for bar in bars[:idx_1500])
            for idx in range(idx_1500, len(bars) - 5):
                if bars[idx].close > pre_close_high and bars[idx].volume > avg_day_vol * 1.8:
                    _add_event(events, "Horse 4 Closing Charge", bars, idx, "LONG", f"15:00+ volume spike; broke day high {pre_close_high:.2f}")
                    break
    return events


def _pf(values: List[float]) -> Optional[float]:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _win_rate(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(1 for value in values if value > 0) / len(values)


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if value == float("inf"):
        return "inf"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _summary_rows(events: List[EventResult]) -> List[List[str]]:
    by_name: Dict[str, List[EventResult]] = {}
    for event in events:
        by_name.setdefault(event.name, []).append(event)
    rows = []
    for name in [
        "Horse 1 Opening Volume Breakout",
        "Horse 2 Gap-Up VWAP Breakdown",
        "Horse 3 Midday Revival",
        "Horse 4 Closing Charge",
    ]:
        group = by_name.get(name, [])
        returns_20 = [event.returns["20m"] for event in group]
        returns_30 = [event.returns["30m"] for event in group]
        returns_60 = [event.returns["60m"] for event in group]
        best_window = max(
            [("20m", sum(returns_20)), ("30m", sum(returns_30)), ("60m", sum(returns_60))],
            key=lambda item: item[1],
        )[0] if group else "N/A"
        best_values = {"20m": returns_20, "30m": returns_30, "60m": returns_60}.get(best_window, [])
        rows.append(
            [
                name,
                str(len(group)),
                best_window,
                _fmt(sum(best_values) if best_values else 0.0),
                _fmt((_win_rate(best_values) or 0.0) * 100 if best_values else None) + "%",
                _fmt(_pf(best_values)),
                _fmt(min((event.max_adverse_60m for event in group), default=0.0)),
                _verdict(group, best_values),
            ]
        )
    return rows


def _verdict(group: List[EventResult], values: List[float]) -> str:
    if len(group) < 5:
        return "Insufficient Sample"
    pf = _pf(values) or 0.0
    wr = _win_rate(values) or 0.0
    total = sum(values)
    if total > 0 and pf >= 1.3 and wr >= 0.5:
        return "Promote To Candidate Review"
    if total > 0 and pf >= 1.0:
        return "Watchlist"
    return "Reject For Now"


def _table(headers: List[str], rows: List[List[str]]) -> List[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
        *["| " + " | ".join(row) + " |" for row in rows],
    ]


def render_report(events: List[EventResult]) -> str:
    rows = _summary_rows(events)
    best = [row for row in rows if row[-1] == "Promote To Candidate Review"]
    watch = [row for row in rows if row[-1] == "Watchlist"]
    lines = [
        "# MQ-RESEARCH-011 RKLB Native Behavior Study",
        "",
        "## Executive Summary",
        f"- Tested 4 RKLB-native behavior hypotheses on the latest 90 trading days.",
        f"- Total detected events: {len(events)}.",
        "- This is historical validation only. No strategy was added to Arena.",
        "",
        "## Key Findings",
        f"- Candidate Review: {', '.join(row[0] for row in best) if best else 'None'}",
        f"- Watchlist: {', '.join(row[0] for row in watch) if watch else 'None'}",
        "- Low trigger counts should be treated as weak evidence, not proof.",
        "",
        "## Supporting Data",
        *_table(
            ["Behavior Hypothesis", "Events", "Best Hold", "PnL", "Win Rate", "PF", "Worst 60m Adverse", "Verdict"],
            rows,
        ),
        "",
        "## Event Samples",
    ]
    for event in events[:20]:
        lines.append(
            f"- {event.date} {event.signal_time} | {event.name} | {event.direction} | "
            f"20m {event.returns['20m']:+.2f}, 30m {event.returns['30m']:+.2f}, 60m {event.returns['60m']:+.2f} | {event.details}"
        )
    if len(events) > 20:
        lines.append(f"- ... {len(events) - 20} more events omitted from preview.")
    lines.extend(
        [
            "",
            "## Risks",
            "- This report uses RKLB underlying prices and 2x theoretical direction PnL; ETF execution spread is not modeled here.",
            "- Premarket high is approximated by regular-session opening behavior because this validation uses RTH bars only.",
            "- These hypotheses require human review before becoming Arena candidates.",
            "",
            "## Suggested Follow-up Research",
            "- Re-run with full extended-hours bars to validate true premarket-high breakout logic.",
            "- For any Candidate Review item, compare actual RKLX/RKLZ ETF prices and slippage.",
            "- Add a separate report for gap-up fade versus gap-up continuation.",
            "",
            "Research Queue Status: WAITING_FOR_HUMAN_REVIEW",
            "",
        ]
    )
    return "\n".join(lines)


def update_queue(queue_path: Path, report_name: str) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    if queue_path.exists():
        text = queue_path.read_text(encoding="utf-8")
        if report_name in text:
            return
        text = text.rstrip() + f"\n- {report_name}: WAITING_FOR_HUMAN_REVIEW\n"
    else:
        text = "\n".join(
            [
                "# Research Queue",
                "",
                "Status: WAITING_FOR_HUMAN_REVIEW",
                "",
                "Rules:",
                "- Observation First, Optimization Later.",
                "- No strategy changes are approved by these reports.",
                "- No parameter changes are approved by these reports.",
                "- Human review is required before any experiment proposal.",
                "",
                "Reports:",
                f"- {report_name}: WAITING_FOR_HUMAN_REVIEW",
                "",
            ]
        )
    queue_path.write_text(text, encoding="utf-8")


def generate_report(out_path: Path | None = None) -> tuple[Path, List[EventResult]]:
    paths = default_paths()
    days = _load_daily_bars(paths["rklb"])
    events = detect_events(days)
    out = out_path or paths["out"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(events), encoding="utf-8")
    update_queue(paths["queue"], out.name)
    return out, events


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RKLB native behavior hypotheses.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    out, events = generate_report(Path(args.out) if args.out else None)
    print(f"[rklb_native_behavior] wrote {out}")
    print(f"[rklb_native_behavior] events={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
