"""
MagicQuant daily_rklb_review.py
VERSION : v0.1.0
DEPENDS : pandas, pyarrow, research.vectorbt_lab._tg_notify

Generate an isolated RKLB daily review from research parquet data.
生成隔离 RKLB 日复盘：只读研究数据和 review 日志，不改实盘策略。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from _tg_notify import send_review
from daily_score import build_daily_score, load_trigger_records_for_et_date, score_markdown


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1]
DATA_PATH = BASE_DIR / "data" / "RKLB" / "1m" / "RKLB_1m.parquet"
OUT_DIR = BASE_DIR / "output" / "daily"
ET = ZoneInfo("America/New_York")
UTC = timezone.utc


@dataclass
class Wave:
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    direction: str
    start_price: float
    end_price: float
    move_pct: float


def _read_bars() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"missing RKLB parquet: {DATA_PATH}")
    frame = pd.read_parquet(DATA_PATH)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values("timestamp").reset_index(drop=True)


def _et_date_series(frame: pd.DataFrame) -> pd.Series:
    return frame["timestamp"].dt.tz_convert(ET).dt.date


def choose_review_date(frame: pd.DataFrame, requested: str | None) -> date:
    if requested:
        return datetime.strptime(requested, "%Y-%m-%d").date()
    dates = sorted(set(_et_date_series(frame)))
    if not dates:
        raise ValueError("RKLB parquet has no dated bars")
    return dates[-1]


def day_frame(frame: pd.DataFrame, review_date: date) -> pd.DataFrame:
    mask = _et_date_series(frame) == review_date
    return frame.loc[mask].copy().reset_index(drop=True)


def previous_close(frame: pd.DataFrame, review_date: date) -> float | None:
    dates = _et_date_series(frame)
    prev = frame.loc[dates < review_date]
    if prev.empty:
        return None
    return float(prev.iloc[-1]["close"])


def calc_vwap(frame: pd.DataFrame) -> float:
    volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
    close = pd.to_numeric(frame["close"], errors="coerce")
    total_vol = float(volume.sum())
    if total_vol <= 0:
        return float(close.iloc[-1])
    return float((close * volume).sum() / total_vol)


def label_waves(frame: pd.DataFrame, threshold_pct: float = 1.5) -> list[Wave]:
    if frame.empty:
        return []
    closes = pd.to_numeric(frame["close"], errors="coerce").ffill()
    timestamps = frame["timestamp"]
    pivot_idx = 0
    pivot_price = float(closes.iloc[0])
    direction: str | None = None
    extreme_idx = 0
    extreme_price = pivot_price
    waves: list[Wave] = []

    for idx in range(1, len(frame)):
        price = float(closes.iloc[idx])
        move_from_pivot = (price - pivot_price) / pivot_price * 100 if pivot_price else 0.0
        if direction is None:
            if abs(move_from_pivot) >= threshold_pct:
                direction = "UP" if move_from_pivot > 0 else "DOWN"
                extreme_idx = idx
                extreme_price = price
            continue

        if direction == "UP":
            if price > extreme_price:
                extreme_idx = idx
                extreme_price = price
            pullback = (price - extreme_price) / extreme_price * 100 if extreme_price else 0.0
            if pullback <= -threshold_pct:
                waves.append(_wave(timestamps, pivot_idx, extreme_idx, "UP", pivot_price, extreme_price))
                pivot_idx = extreme_idx
                pivot_price = extreme_price
                direction = "DOWN"
                extreme_idx = idx
                extreme_price = price
        else:
            if price < extreme_price:
                extreme_idx = idx
                extreme_price = price
            rebound = (price - extreme_price) / extreme_price * 100 if extreme_price else 0.0
            if rebound >= threshold_pct:
                waves.append(_wave(timestamps, pivot_idx, extreme_idx, "DOWN", pivot_price, extreme_price))
                pivot_idx = extreme_idx
                pivot_price = extreme_price
                direction = "UP"
                extreme_idx = idx
                extreme_price = price

    if direction is not None and extreme_idx != pivot_idx:
        waves.append(_wave(timestamps, pivot_idx, extreme_idx, direction, pivot_price, extreme_price))
    if not waves:
        high_idx = int(pd.to_numeric(frame["high"], errors="coerce").idxmax())
        low_idx = int(pd.to_numeric(frame["low"], errors="coerce").idxmin())
        high_price = float(frame.loc[high_idx, "high"])
        low_price = float(frame.loc[low_idx, "low"])
        if high_price and low_price and abs(high_price - low_price) / min(high_price, low_price) * 100 >= threshold_pct:
            if low_idx < high_idx:
                waves.append(_wave(timestamps, low_idx, high_idx, "UP", low_price, high_price))
            else:
                waves.append(_wave(timestamps, high_idx, low_idx, "DOWN", high_price, low_price))
    return waves


def _wave(timestamps: pd.Series, start_idx: int, end_idx: int, direction: str, start_price: float, end_price: float) -> Wave:
    move_pct = (end_price - start_price) / start_price * 100 if start_price else 0.0
    return Wave(
        start_ts=pd.Timestamp(timestamps.iloc[start_idx]),
        end_ts=pd.Timestamp(timestamps.iloc[end_idx]),
        direction=direction,
        start_price=float(start_price),
        end_price=float(end_price),
        move_pct=float(move_pct),
    )


def load_triggers(review_date: date) -> list[dict]:
    path = PROJECT_ROOT / "data" / "review" / review_date.isoformat() / "triggers.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            records = payload.get("records") or payload.get("triggers") or []
            return [item for item in records if isinstance(item, dict)]
    except Exception as exc:
        print(f"[review] failed to load triggers: {exc}")
    return []


def _trigger_kind(record: dict) -> str:
    return str(record.get("trigger") or record.get("type") or record.get("name") or "unknown")


def _trigger_direction(record: dict) -> str:
    raw = str(record.get("direction") or record.get("signal_direction") or record.get("bias") or "").lower()
    if "long" in raw or "bull" in raw or "看多" in raw:
        return "long"
    if "short" in raw or "bear" in raw or "看空" in raw:
        return "short"
    return "neutral"


def summarize_triggers(records: list[dict]) -> dict:
    counts: dict[str, int] = {}
    dirs = {"long": 0, "short": 0, "neutral": 0}
    for record in records:
        counts[_trigger_kind(record)] = counts.get(_trigger_kind(record), 0) + 1
        direction = _trigger_direction(record)
        dirs[direction] = dirs.get(direction, 0) + 1
    return {"total": len(records), "by_type": counts, "by_direction": dirs}


def _fmt_et(ts: pd.Timestamp) -> str:
    return ts.tz_convert(ET).strftime("%H:%M ET")


def build_report(review_date: date, bars: pd.DataFrame, prev_close: float | None, records: list[dict]) -> tuple[str, str]:
    first = float(bars.iloc[0]["open"])
    last = float(bars.iloc[-1]["close"])
    high = float(bars["high"].max())
    low = float(bars["low"].min())
    volume = int(pd.to_numeric(bars["volume"], errors="coerce").fillna(0).sum())
    vwap = calc_vwap(bars)
    ref = prev_close if prev_close else first
    day_pct = (last - ref) / ref * 100 if ref else 0.0
    intraday_pct = (last - first) / first * 100 if first else 0.0
    waves = sorted(label_waves(bars), key=lambda item: abs(item.move_pct), reverse=True)[:6]
    aligned_records = load_trigger_records_for_et_date(review_date)
    if aligned_records:
        records = aligned_records
    trigger_summary = summarize_triggers(records)
    daily_score = build_daily_score(review_date, bars, waves, records)

    lines = [
        f"# RKLB Daily Review - {review_date.isoformat()}",
        "",
        "## Market Summary",
        "",
        f"- Close: ${last:.2f}",
        f"- Reference close: ${ref:.2f}",
        f"- Change vs reference: {day_pct:+.2f}%",
        f"- Intraday move: {intraday_pct:+.2f}%",
        f"- Range: ${low:.2f} ~ ${high:.2f}",
        f"- VWAP: ${vwap:.2f}",
        f"- Volume: {volume:,}",
        "",
        "## Major Waves",
        "",
    ]
    if waves:
        for idx, wave in enumerate(waves, 1):
            lines.append(
                f"{idx}. {wave.direction} {_fmt_et(wave.start_ts)} -> {_fmt_et(wave.end_ts)}: "
                f"${wave.start_price:.2f} -> ${wave.end_price:.2f} ({wave.move_pct:+.2f}%)"
            )
    else:
        lines.append("No >=1.5% wave detected.")

    lines += [
        "",
        "## Signal Summary",
        "",
        f"- Trigger records: {trigger_summary['total']}",
        f"- Direction count: long {trigger_summary['by_direction'].get('long', 0)}, "
        f"short {trigger_summary['by_direction'].get('short', 0)}, "
        f"neutral {trigger_summary['by_direction'].get('neutral', 0)}",
        "",
        "### Trigger Types",
        "",
    ]
    if trigger_summary["by_type"]:
        for name, count in sorted(trigger_summary["by_type"].items(), key=lambda item: item[1], reverse=True)[:12]:
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No trigger log found for this date.")

    conclusion = _plain_conclusion(day_pct, intraday_pct, waves, trigger_summary)
    lines += ["", "## Plain Conclusion", "", conclusion, ""]

    tg = (
        f"📊 RKLB 日复盘 · {review_date.isoformat()}\n"
        f"收盘 ${last:.2f}，较参考 {day_pct:+.2f}%\n"
        f"区间 ${low:.2f} ~ ${high:.2f}，VWAP ${vwap:.2f}\n"
        f"主要波段 {len(waves)} 段，信号记录 {trigger_summary['total']} 条\n"
        f"结论: {conclusion}"
    )
    return "\n".join(lines), tg


def build_report_v2(review_date: date, bars: pd.DataFrame, prev_close: float | None, records: list[dict]) -> tuple[str, str]:
    """Build review with daily score. / 生成带每日评分的复盘。"""
    first = float(bars.iloc[0]["open"])
    last = float(bars.iloc[-1]["close"])
    high = float(bars["high"].max())
    low = float(bars["low"].min())
    volume = int(pd.to_numeric(bars["volume"], errors="coerce").fillna(0).sum())
    vwap = calc_vwap(bars)
    ref = prev_close if prev_close else first
    day_pct = (last - ref) / ref * 100 if ref else 0.0
    intraday_pct = (last - first) / first * 100 if first else 0.0
    waves = sorted(label_waves(bars), key=lambda item: abs(item.move_pct), reverse=True)[:6]
    aligned_records = load_trigger_records_for_et_date(review_date)
    if aligned_records:
        records = aligned_records
    trigger_summary = summarize_triggers(records)
    daily_score = build_daily_score(review_date, bars, waves, records)

    lines = [
        f"# RKLB Daily Review - {review_date.isoformat()}",
        "",
        "## Market Summary",
        "",
        f"- Close: ${last:.2f}",
        f"- Reference close: ${ref:.2f}",
        f"- Change vs reference: {day_pct:+.2f}%",
        f"- Intraday move: {intraday_pct:+.2f}%",
        f"- Range: ${low:.2f} ~ ${high:.2f}",
        f"- VWAP: ${vwap:.2f}",
        f"- Volume: {volume:,}",
        "",
        "## Major Waves",
        "",
    ]
    if waves:
        for idx, wave in enumerate(waves, 1):
            lines.append(
                f"{idx}. {wave.direction} {_fmt_et(wave.start_ts)} -> {_fmt_et(wave.end_ts)}: "
                f"${wave.start_price:.2f} -> ${wave.end_price:.2f} ({wave.move_pct:+.2f}%)"
            )
    else:
        lines.append("No >=1.5% wave detected.")

    lines += [
        "",
        "## Signal Summary",
        "",
        f"- Trigger records: {trigger_summary['total']}",
        f"- Direction count: long {trigger_summary['by_direction'].get('long', 0)}, "
        f"short {trigger_summary['by_direction'].get('short', 0)}, "
        f"neutral {trigger_summary['by_direction'].get('neutral', 0)}",
        "",
        "### Trigger Types",
        "",
    ]
    if trigger_summary["by_type"]:
        for name, count in sorted(trigger_summary["by_type"].items(), key=lambda item: item[1], reverse=True)[:12]:
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No trigger log found for this date.")

    conclusion = _plain_conclusion(day_pct, intraday_pct, waves, trigger_summary)
    lines += ["", score_markdown(daily_score), "", "## Plain Conclusion", "", conclusion, ""]

    tg = (
        f"📊 RKLB 日复盘 · {review_date.isoformat()}\n"
        f"收盘 ${last:.2f}，较参考 {day_pct:+.2f}%\n"
        f"区间 ${low:.2f} ~ ${high:.2f}，VWAP ${vwap:.2f}\n"
        f"评分 {daily_score['score']}/100 | 及时 {daily_score['timely']} 迟到 {daily_score['late']} 漏报 {daily_score['miss']}\n"
        f"信号 {trigger_summary['total']} 条，强错 {daily_score['strong_wrong']} 条\n"
        f"建议: {daily_score['suggestions'][0]}\n"
        f"结论: {conclusion}"
    )
    return "\n".join(lines), tg


def _plain_conclusion(day_pct: float, intraday_pct: float, waves: list[Wave], summary: dict) -> str:
    if not waves:
        return "当天没有足够大的 1m 波段，策略复盘以数据完整性检查为主。"
    biggest = waves[0]
    signal_count = int(summary.get("total", 0))
    if signal_count == 0:
        return f"最大波段为 {biggest.direction} {biggest.move_pct:+.2f}%，但没有找到触发日志，需检查当天 bot 是否运行或日志是否归档。"
    if biggest.direction == "UP":
        return f"最大机会是上涨波段 {biggest.move_pct:+.2f}%，重点复核看多/反弹信号是否在波段前半段出现。"
    return f"最大风险是下跌波段 {biggest.move_pct:+.2f}%，重点复核看空/趋势失效信号是否及时。"


def write_report(review_date: date, markdown: str) -> Path:
    out_dir = OUT_DIR / review_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "rklb_daily_review.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def parse_args():
    parser = argparse.ArgumentParser(description="Generate RKLB daily review from vectorbt lab data.")
    parser.add_argument("--date", default=None, help="ET date YYYY-MM-DD. Default: latest date in RKLB parquet.")
    parser.add_argument("--telegram", action="store_true", help="Send Telegram summary to TG_REVIEW_CHAT_ID.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_bars = _read_bars()
    review_date = choose_review_date(all_bars, args.date)
    bars = day_frame(all_bars, review_date)
    if bars.empty:
        print(f"[review] no RKLB bars for {review_date}")
        return 1
    records = load_triggers(review_date)
    markdown, telegram_text = build_report_v2(review_date, bars, previous_close(all_bars, review_date), records)
    path = write_report(review_date, markdown)
    print(f"[review] wrote {path}")
    if args.telegram:
        send_review(telegram_text + f"\n报告: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
