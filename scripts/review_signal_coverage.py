"""
MagicQuant - signal coverage review
VERSION : v0.1.1
DATE    : 2026-05-21
DEPENDS : data/review/YYYY-MM-DD/triggers.json

复盘大波段和信号覆盖。/ Review large price waves and signal coverage.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.focus.swing_labeler import Bar, Wave, label_swings_atr

REVIEW_DIR = ROOT / "data" / "review"
OUT_DIR = ROOT / "data" / "review_reports"

DEFAULT_WAVE_THRESHOLD_PCT = 2.0
DEFAULT_ATR_MULT = 1.0
DEFAULT_TIMELY_MINUTES = 15
DEFAULT_SEGMENT_GAP_MINUTES = 30

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")


def _fmt_et(ts: datetime) -> str:
    return ts.strftime("%m-%d %H:%M ET")


def _fmt_local_from_et(ts: datetime) -> str:
    # K-line bars are ET; local display currently uses ET + 14h.
    # K 线时间为 ET；当前项目展示本地时间暂按 ET + 14 小时换算。
    return (ts + timedelta(hours=14)).strftime("%m-%d %H:%M")


def load_triggers(date_str: str) -> list[dict]:
    path = REVIEW_DIR / date_str / "triggers.json"
    if not path.exists():
        raise FileNotFoundError(f"missing review triggers: {path}")
    return json.loads(path.read_text(encoding="utf-8")) or []


def _bar_from_dict(raw: dict) -> Bar | None:
    if not isinstance(raw, dict):
        return None
    ts_text = raw.get("time") or raw.get("time_key")
    if not ts_text:
        return None
    try:
        return Bar(
            ts=_parse_dt(str(ts_text)),
            open=float(raw["open"]),
            high=float(raw["high"]),
            low=float(raw["low"]),
            close=float(raw["close"]),
            volume=float(raw.get("volume") or 0.0),
        )
    except Exception:
        return None


def collect_bars_from_triggers(records: Iterable[dict]) -> list[Bar]:
    """Collect unique K-line bars embedded in trigger decision_context."""
    by_time: dict[datetime, Bar] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        context = record.get("decision_context") or {}
        kline_data = context.get("kline_data") or {}
        bars = kline_data.get("bars", [])
        for raw_bar in bars:
            bar = _bar_from_dict(raw_bar)
            if bar is not None:
                by_time[bar.ts] = bar
    return [by_time[ts] for ts in sorted(by_time)]


def _review_kline_path(date_str: str, ticker: str = "RKLB") -> Path:
    return REVIEW_DIR / date_str / f"kline_1m_{ticker.replace('US.', '').upper()}.json"


def _bar_to_json(bar: Bar) -> dict:
    return {
        "time_key": bar.ts.strftime("%Y-%m-%d %H:%M:%S"),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def load_review_kline_1m(date_str: str, ticker: str = "RKLB") -> list[Bar]:
    path = _review_kline_path(date_str, ticker)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []
    bars = [_bar_from_dict(item) for item in raw]
    return [bar for bar in bars if bar is not None]


def _filter_bars_for_local_date(bars: list[Bar], date_str: str) -> list[Bar]:
    """Keep ET bars whose ET+14h local date equals review date."""
    out: list[Bar] = []
    for bar in bars:
        local_date = (bar.ts + timedelta(hours=14)).strftime("%Y-%m-%d")
        if local_date == date_str:
            out.append(bar)
    return out


def fetch_futu_kline_1m(date_str: str, ticker: str = "RKLB") -> list[Bar]:
    """
    Fetch 1m bars from Futu for review and persist them locally.
    复盘时按需从 Futu 拉 1m K 线并归档；失败时由上层降级。
    """
    try:
        try:
            from moomoo import OpenQuoteContext, RET_OK, KLType, AuType
        except ImportError:
            from futu import OpenQuoteContext, RET_OK, KLType, AuType
        from config.settings import FUTU_HOST, FUTU_PORT
    except Exception as exc:
        print(f"[review] Futu SDK/config unavailable: {exc}")
        return []

    ticker_full = _normalize_ticker(ticker)
    day = datetime.strptime(date_str, "%Y-%m-%d")
    start = (day - timedelta(days=1)).strftime("%Y-%m-%d")
    end = day.strftime("%Y-%m-%d")
    all_rows = []
    page_key = None
    ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    try:
        while True:
            ret, df, page_key = ctx.request_history_kline(
                ticker_full,
                start=start,
                end=end,
                ktype=KLType.K_1M,
                autype=AuType.QFQ,
                max_count=1000,
                page_req_key=page_key,
                extended_time=True,
            )
            if ret != RET_OK:
                print(f"[review] K_1M fetch failed: {ticker_full} {start}~{end}: {df}")
                return []
            if df is not None and len(df) > 0:
                all_rows.append(df)
            if page_key is None:
                break
    finally:
        ctx.close()

    if not all_rows:
        return []

    bars: list[Bar] = []
    for df in all_rows:
        for _, row in df.iterrows():
            bar = _bar_from_dict({
                "time_key": str(row.get("time_key", "")),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume", 0),
            })
            if bar is not None:
                bars.append(bar)
    bars = _filter_bars_for_local_date(sorted(bars, key=lambda item: item.ts), date_str)
    if not bars:
        return []

    path = _review_kline_path(date_str, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([_bar_to_json(bar) for bar in bars], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[review] saved K_1M {ticker_full}: {len(bars)} bars -> {path}")
    return bars


def load_or_fetch_review_bars(
    date_str: str,
    records: list[dict],
    ticker: str = "RKLB",
    fetch_1m: bool = True,
) -> tuple[list[Bar], str]:
    bars = load_review_kline_1m(date_str, ticker)
    if bars:
        return bars, "K_1M local archive"
    if fetch_1m:
        bars = fetch_futu_kline_1m(date_str, ticker)
        if bars:
            return bars, "K_1M Futu fetched"
    return collect_bars_from_triggers(records), "K_5M trigger snapshots fallback"


def detect_major_waves(
    bars: list[Bar],
    threshold_pct: float = DEFAULT_WAVE_THRESHOLD_PCT,
    atr_mult: float = DEFAULT_ATR_MULT,
) -> list[Wave]:
    """ATR-adaptive zigzag detector for human review, not a trading signal."""
    return label_swings_atr(
        bars,
        atr_mult=atr_mult,
        fallback_pct=threshold_pct,
    )


def _session_name(ts: datetime) -> str:
    minute = ts.hour * 60 + ts.minute
    if 4 * 60 <= minute < 9 * 60 + 30:
        return "premarket"
    if 9 * 60 + 30 <= minute < 16 * 60:
        return "regular"
    if 16 * 60 <= minute <= 20 * 60:
        return "afterhours"
    return "overnight"


def _segment_label(start: datetime, end: datetime) -> str:
    start_label = _session_name(start)
    end_label = _session_name(end)
    if start_label == end_label:
        return start_label
    return f"{start_label}->{end_label}"


def split_bars_by_gap(
    bars: list[Bar],
    gap_minutes: int = DEFAULT_SEGMENT_GAP_MINUTES,
) -> list[dict]:
    """
    Split review bars at large time gaps before running ZigZag.
    先按 K 线时间缺口切段，避免复盘波段跨越隔夜无 K 线空洞。
    """
    if not bars:
        return []
    ordered = sorted(bars, key=lambda item: item.ts)
    segments: list[dict] = []
    current: list[Bar] = [ordered[0]]
    gap_before: float | None = None

    def flush(items: list[Bar], gap_min: float | None) -> None:
        idx = len(segments) + 1
        segments.append({
            "id": f"S{idx}",
            "bars": items,
            "start": items[0].ts,
            "end": items[-1].ts,
            "session": _segment_label(items[0].ts, items[-1].ts),
            "gap_before_min": gap_min,
        })

    for bar in ordered[1:]:
        prev = current[-1]
        gap = (bar.ts - prev.ts).total_seconds() / 60.0
        if gap > gap_minutes:
            flush(current, gap_before)
            current = [bar]
            gap_before = gap
        else:
            current.append(bar)
    flush(current, gap_before)
    return segments


def detect_major_waves_segmented(
    bars: list[Bar],
    threshold_pct: float = DEFAULT_WAVE_THRESHOLD_PCT,
    atr_mult: float = DEFAULT_ATR_MULT,
    gap_minutes: int = DEFAULT_SEGMENT_GAP_MINUTES,
) -> tuple[list[dict], list[dict]]:
    segments = split_bars_by_gap(bars, gap_minutes=gap_minutes)
    waves: list[dict] = []
    for segment in segments:
        for wave in detect_major_waves(segment["bars"], threshold_pct=threshold_pct, atr_mult=atr_mult):
            waves.append({"wave": wave, "segment": segment})
    return waves, segments


def _trigger_ts(record: dict) -> datetime | None:
    text = record.get("ts") or record.get("timestamp")
    if not text:
        return None
    try:
        return _parse_dt(str(text))
    except Exception:
        return None


def _trigger_et(record: dict) -> datetime | None:
    ts = _trigger_ts(record)
    if ts is None:
        return None
    # Review trigger ts is local time. / 触发日志 ts 是本地时间。
    return ts - timedelta(hours=14)


def _normalize_ticker(ticker: str | None) -> str:
    value = (ticker or "").strip().upper()
    if not value:
        return ""
    if not value.startswith("US."):
        value = f"US.{value}"
    return value


def _record_matches_ticker(record: dict, ticker: str) -> bool:
    """Keep legacy records without ticker, but exclude explicit follower records."""
    if not isinstance(record, dict):
        return False
    target = _normalize_ticker(ticker)
    record_ticker = _normalize_ticker(record.get("ticker") or record.get("symbol"))
    return not record_ticker or record_ticker == target


def _filter_records_for_ticker(records: list[dict], ticker: str) -> list[dict]:
    return [
        record for record in records
        if isinstance(record, dict) and _record_matches_ticker(record, ticker)
    ]


def _confidence_value(record: dict) -> int:
    try:
        return int(float(record.get("confidence") or 0))
    except Exception:
        return 0


def _minutes_from_wave_start(record: dict, wave: Wave) -> float | None:
    ts = _trigger_et(record)
    if ts is None:
        return None
    return (ts - wave.start).total_seconds() / 60.0


def _record_in_segment(record: dict, segment: dict) -> bool:
    ts = _trigger_et(record)
    return ts is not None and segment["start"] <= ts <= segment["end"]


def _records_outside_segments(records: list[dict], segments: list[dict]) -> list[dict]:
    out: list[dict] = []
    for record in records:
        ts = _trigger_et(record)
        if ts is None:
            continue
        if not any(segment["start"] <= ts <= segment["end"] for segment in segments):
            out.append(record)
    return out


def _signal_side(record: dict) -> str:
    direction = (record.get("direction") or "").lower()
    trigger = (record.get("trigger") or "").lower()
    text = (record.get("message_text") or "").lower()
    if direction in ("long", "short"):
        return direction
    if "止损" in text or "已破止损" in text:
        return "risk"
    if trigger in ("near_support", "swing_bottom"):
        return "long"
    if trigger in ("near_resistance", "swing_top"):
        return "short"
    return "neutral"


def _is_relevant(record: dict, wave_direction: str) -> bool:
    side = _signal_side(record)
    if wave_direction == "up":
        return side == "long"
    return side in ("short", "risk")


def _is_opposite(record: dict, wave_direction: str) -> bool:
    side = _signal_side(record)
    if wave_direction == "up":
        return side == "short"
    return side == "long"


def evaluate_wave_coverage(
    wave: Wave,
    records: list[dict],
    timely_minutes: int = DEFAULT_TIMELY_MINUTES,
    target_ticker: str | None = None,
) -> dict:
    in_window: list[dict] = []
    relevant: list[dict] = []
    opposite: list[dict] = []
    scan_records = _filter_records_for_ticker(records, target_ticker) if target_ticker else records
    for record in scan_records:
        ts = _trigger_et(record)
        if ts is None or not (wave.start <= ts <= wave.end):
            continue
        in_window.append(record)
        if _is_relevant(record, wave.direction):
            relevant.append(record)
        if _is_opposite(record, wave.direction):
            opposite.append(record)

    timely_cutoff = wave.start + timedelta(minutes=timely_minutes)
    timely = [r for r in relevant if (_trigger_et(r) or wave.end) <= timely_cutoff]
    first_relevant = min((_trigger_et(r) for r in relevant if _trigger_et(r)), default=None)
    status = "MISS"
    if timely:
        status = "TIMELY"
    elif relevant:
        status = "LATE"
    if opposite and not relevant:
        status = "WRONG_SIDE"

    opposite_strong = [
        r for r in opposite
        if str(r.get("strength") or "").upper() == "STRONG"
    ]
    worst_opposite = max(opposite, key=_confidence_value, default=None)

    return {
        "status": status,
        "signals_total": len(in_window),
        "relevant_total": len(relevant),
        "opposite_total": len(opposite),
        "opposite_strong_total": len(opposite_strong),
        "worst_opposite": worst_opposite,
        "worst_opposite_minute": (
            _minutes_from_wave_start(worst_opposite, wave) if worst_opposite else None
        ),
        "first_relevant": first_relevant,
        "records": in_window,
    }


def _record_one_line(record: dict, ticker: str = "RKLB") -> str:
    ts = _trigger_et(record)
    et = _fmt_et(ts) if ts else "?"
    trigger = record.get("trigger", "?")
    direction = record.get("direction", "?")
    strength = record.get("strength", "?")
    confidence = record.get("confidence", "?")
    ticker_key = ticker.replace("US.", "").upper()
    prices = record.get("prices") or {}
    price = prices.get(ticker_key) or (record.get("data") or {}).get("current") or "?"
    return f"{et} {trigger}/{direction}/{strength} conf={confidence} price={price}"


def build_review(
    date_str: str,
    threshold_pct: float = DEFAULT_WAVE_THRESHOLD_PCT,
    atr_mult: float = DEFAULT_ATR_MULT,
    fetch_1m: bool = True,
    ticker: str = "RKLB",
) -> dict:
    all_records = load_triggers(date_str)
    records = _filter_records_for_ticker(all_records, ticker)
    bars, bar_source = load_or_fetch_review_bars(date_str, records, ticker=ticker, fetch_1m=fetch_1m)
    wave_items, segments = detect_major_waves_segmented(bars, threshold_pct=threshold_pct, atr_mult=atr_mult)
    reviews = []
    for wave_item in wave_items:
        wave = wave_item["wave"]
        coverage = evaluate_wave_coverage(wave, records, target_ticker=ticker)
        reviews.append({"wave": wave, "coverage": coverage, "segment": wave_item["segment"]})
    return {
        "date": date_str,
        "ticker": ticker,
        "bar_source": bar_source,
        "threshold_pct": threshold_pct,
        "atr_mult": atr_mult,
        "all_records": all_records,
        "records": records,
        "bars": bars,
        "segments": segments,
        "out_of_session_records": _records_outside_segments(records, segments),
        "waves": reviews,
    }


def _coverage_counts(waves: list[dict]) -> dict[str, int]:
    counts = {"TIMELY": 0, "LATE": 0, "MISS": 0, "WRONG_SIDE": 0}
    for item in waves:
        status = item["coverage"]["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


def _wrong_strong_total(waves: list[dict]) -> int:
    return sum(item["coverage"].get("opposite_strong_total", 0) for item in waves)


def _safe_stat(values: list[float | int | None]) -> str:
    nums = sorted(float(v) for v in values if v is not None)
    if not nums:
        return "-"
    mid = nums[len(nums) // 2]
    return f"{mid:.2f}"


def _feature_for_record(record: dict, segment: dict) -> dict:
    ts = _trigger_et(record)
    data = record.get("data") or {}
    price = data.get("current") or (record.get("prices") or {}).get("RKLB")
    if ts is None or not price:
        return {}
    price = float(price)
    bars = [bar for bar in segment["bars"] if bar.ts <= ts]
    if not bars:
        return {}
    high = max(bar.high for bar in bars)

    def close_before(minutes: int) -> float | None:
        target = ts - timedelta(minutes=minutes)
        prior = [bar for bar in segment["bars"] if bar.ts <= target]
        return prior[-1].close if prior else None

    prev10 = close_before(10)
    prev15 = close_before(15)
    vwap = data.get("vwap")
    return {
        "high_dd": (high - price) / high * 100 if high > 0 else None,
        "move10": (price - prev10) / prev10 * 100 if prev10 else None,
        "move15": (price - prev15) / prev15 * 100 if prev15 else None,
        "above_vwap": price > float(vwap) if isinstance(vwap, (int, float)) else None,
    }


def build_strong_long_calibration(review: dict) -> list[dict]:
    """
    Summarize STRONG long signals after gap segmentation.
    缺口切段后汇总强看多信号，用于判断是否有干净分界。
    """
    buckets: dict[str, dict] = {}
    wave_items = review["waves"]
    for record in review["records"]:
        if (record.get("direction") or "").lower() != "long":
            continue
        if (record.get("strength") or "").upper() != "STRONG":
            continue
        trigger = record.get("trigger") or "?"
        if trigger not in ("direction_trend", "intraday_reversal", "swing_bottom"):
            continue
        ts = _trigger_et(record)
        if ts is None:
            continue
        wave_item = next(
            (item for item in wave_items if item["wave"].start <= ts <= item["wave"].end),
            None,
        )
        if wave_item is None:
            cls = "no_wave"
            segment = next((seg for seg in review["segments"] if seg["start"] <= ts <= seg["end"]), None)
        else:
            cls = "correct_up" if wave_item["wave"].direction == "up" else "wrong_down"
            segment = wave_item.get("segment")
        key = f"{cls}|{trigger}"
        bucket = buckets.setdefault(key, {
            "class": cls,
            "trigger": trigger,
            "n": 0,
            "conf": [],
            "high_dd": [],
            "move10": [],
            "move15": [],
            "above_vwap": 0,
            "with_vwap": 0,
        })
        bucket["n"] += 1
        bucket["conf"].append(_confidence_value(record))
        if segment:
            feat = _feature_for_record(record, segment)
            bucket["high_dd"].append(feat.get("high_dd"))
            bucket["move10"].append(feat.get("move10"))
            bucket["move15"].append(feat.get("move15"))
            if feat.get("above_vwap") is not None:
                bucket["with_vwap"] += 1
                if feat["above_vwap"]:
                    bucket["above_vwap"] += 1
    out: list[dict] = []
    for bucket in buckets.values():
        out.append({
            "class": bucket["class"],
            "trigger": bucket["trigger"],
            "n": bucket["n"],
            "conf_med": _safe_stat(bucket["conf"]),
            "high_dd_med": _safe_stat(bucket["high_dd"]),
            "move10_med": _safe_stat(bucket["move10"]),
            "move15_med": _safe_stat(bucket["move15"]),
            "above_vwap": f"{bucket['above_vwap']}/{bucket['with_vwap']}",
        })
    return sorted(out, key=lambda item: (item["trigger"], item["class"]))


def format_markdown(review: dict) -> str:
    date_str = review["date"]
    bars = review["bars"]
    waves = review["waves"]
    segments = review.get("segments", [])
    out_records = review.get("out_of_session_records", [])
    counts = _coverage_counts(waves)
    wrong_strong_total = _wrong_strong_total(waves)
    excluded = len(review.get("all_records", [])) - len(review["records"])
    lines = [
        f"# Signal Coverage Review - {date_str}",
        "",
        "VERSION : v0.1.1",
        "DEPENDS : data/review/YYYY-MM-DD/triggers.json",
        "",
        "## Summary",
        "",
        f"- Ticker: {review.get('ticker', 'RKLB')}",
        f"- K-line source: {review.get('bar_source', '-')}",
        f"- Swing labeler: ATR ZigZag, atr_mult={review.get('atr_mult', DEFAULT_ATR_MULT)}, fallback={review.get('threshold_pct', DEFAULT_WAVE_THRESHOLD_PCT)}%",
        f"- Trigger records used: {len(review['records'])}",
        f"- Trigger records excluded by ticker filter: {excluded}",
        f"- K-line bars used: {len(bars)}",
        f"- K-line segments detected: {len(segments)}",
        f"- Out-of-session / gap signals: {len(out_records)}",
        f"- Major waves detected: {len(waves)}",
        f"- Coverage: TIMELY {counts.get('TIMELY', 0)} / LATE {counts.get('LATE', 0)} / MISS {counts.get('MISS', 0)} / WRONG_SIDE {counts.get('WRONG_SIDE', 0)}",
        f"- Wrong-side STRONG signals: {wrong_strong_total}",
        "",
        "## K-line Segments",
        "",
    ]
    if segments:
        for segment in segments:
            wave_count = sum(1 for item in waves if item.get("segment", {}).get("id") == segment["id"])
            gap_text = "-" if segment.get("gap_before_min") is None else f"{segment['gap_before_min']:.0f}min"
            lines.append(
                f"- {segment['id']} {segment['session']}: {_fmt_et(segment['start'])} -> {_fmt_et(segment['end'])} "
                f"| bars {len(segment['bars'])} | waves {wave_count} | gap_before {gap_text}"
            )
    else:
        lines.append("- none")
    lines += [
        "",
        "## Out-of-session / Gap Signals",
        "",
    ]
    if out_records:
        lines.append("These signals sit outside available K-line segments and are not counted in wave coverage.")
        for record in out_records[:20]:
            lines.append(f"- {_record_one_line(record, review.get('ticker', 'RKLB'))}")
        if len(out_records) > 20:
            lines.append(f"- ... {len(out_records) - 20} more")
    else:
        lines.append("- none")
    calibration = build_strong_long_calibration(review)
    lines += [
        "",
        "## STRONG Long Calibration",
        "",
        "| Class | Trigger | N | Conf med | High DD med | Move10 med | Move15 med | Above VWAP |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    if calibration:
        for row in calibration:
            lines.append(
                f"| {row['class']} | {row['trigger']} | {row['n']} | {row['conf_med']} | "
                f"{row['high_dd_med']} | {row['move10_med']} | {row['move15_med']} | {row['above_vwap']} |"
            )
    else:
        lines.append("| - | - | 0 | - | - | - | - | - |")
    lines += [
        "",
        "## Major Waves",
        "",
    ]
    if not waves:
        lines.append("No major wave detected.")
    for idx, item in enumerate(waves, 1):
        wave: Wave = item["wave"]
        cov = item["coverage"]
        label = "UP" if wave.direction == "up" else "DOWN"
        segment = item.get("segment") or {}
        first = cov["first_relevant"]
        first_text = _fmt_et(first) if first else "-"
        worst = cov.get("worst_opposite")
        worst_text = "-"
        if worst:
            minute = cov.get("worst_opposite_minute")
            minute_text = f"+{minute:.0f}min" if minute is not None else "?"
            worst_text = f"{_record_one_line(worst, review.get('ticker', 'RKLB'))} ({minute_text})"
        lines += [
            f"### {idx}. {label} {wave.pct:+.2f}%",
            "",
            f"- ET window: {_fmt_et(wave.start)} -> {_fmt_et(wave.end)}",
            f"- Local window: {_fmt_local_from_et(wave.start)} -> {_fmt_local_from_et(wave.end)}",
            f"- Segment: {segment.get('id', '-')} {segment.get('session', '-')}",
            f"- Price: ${wave.start_price:.2f} -> ${wave.end_price:.2f}",
            f"- Duration: {getattr(wave, 'dur_min', 0):.0f} min | threshold: {getattr(wave, 'threshold_pct', 0):.2f}%",
            f"- Status: **{cov['status']}**",
            f"- Signals in wave: {cov['signals_total']} | relevant: {cov['relevant_total']} | opposite: {cov['opposite_total']} | wrong-side STRONG: {cov.get('opposite_strong_total', 0)}",
            f"- First relevant signal: {first_text}",
            f"- Highest-confidence opposite signal: {worst_text}",
            "",
            "Signals:",
        ]
        if cov["records"]:
            for record in cov["records"][:12]:
                lines.append(f"- {_record_one_line(record, review.get('ticker', 'RKLB'))}")
        else:
            lines.append("- none")
        lines.append("")

    lines += [
        "## Findings",
        "",
        "- TIMELY means a same-direction signal appeared within the first 15 minutes of the wave.",
        "- LATE means direction was eventually right but not early enough for intraday execution.",
        "- MISS means the wave had no matching direction/risk signal.",
        "- WRONG_SIDE means the system only produced opposite-side signals in that wave.",
        "- Wrong-side STRONG signals are separated because they are the most likely to mislead live decisions.",
        "- near_support / swing_bottom are currently mapped as long; near_resistance / swing_top are mapped as short.",
        "",
        "## Suggested Next Step",
        "",
        "Any strategy change should be replayed against this report date and recent review logs, then recorded in docs/STRATEGY_SCORECARD.md.",
    ]
    return "\n".join(lines)


def format_telegram_summary(review: dict, max_waves: int = 6) -> str:
    """Readable Telegram summary. / Telegram 可读摘要。"""
    waves = review["waves"]
    counts = _coverage_counts(waves)
    wrong_strong_total = _wrong_strong_total(waves)

    lines = [
        f"📋 信号覆盖复盘 · {review['date']}",
        "━━━━━━━━━━━━━━",
        f"K线: {review.get('bar_source', '-')}",
        f"算法: ATR ZigZag x{review.get('atr_mult', DEFAULT_ATR_MULT)}",
        f"波段: {len(waves)}",
        f"及时 {counts.get('TIMELY', 0)} · 滞后 {counts.get('LATE', 0)} · 漏掉 {counts.get('MISS', 0)} · 反向 {counts.get('WRONG_SIDE', 0)}",
        f"错误 STRONG: {wrong_strong_total}",
        "",
    ]
    for idx, item in enumerate(waves[:max_waves], 1):
        wave: Wave = item["wave"]
        cov = item["coverage"]
        icon = "📈" if wave.direction == "up" else "📉"
        first = cov["first_relevant"]
        first_text = _fmt_et(first) if first else "无"
        worst = cov.get("worst_opposite")
        worst_text = ""
        if worst:
            minute = cov.get("worst_opposite_minute")
            minute_text = f"+{minute:.0f}min" if minute is not None else "?"
            worst_text = f" · 最强反向 {_record_one_line(worst, review.get('ticker', 'RKLB'))} ({minute_text})"
        lines += [
            f"{idx}. {icon} {wave.pct:+.2f}% · {cov['status']}",
            f"   {_fmt_et(wave.start)} -> {_fmt_et(wave.end)}",
            f"   ${wave.start_price:.2f} -> ${wave.end_price:.2f} · {getattr(wave, 'dur_min', 0):.0f}min",
            f"   信号: 相关 {cov['relevant_total']} / 反向 {cov['opposite_total']} / 错误STRONG {cov.get('opposite_strong_total', 0)} · 首次 {first_text}{worst_text}",
        ]
    if len(waves) > max_waves:
        lines.append(f"... 还有 {len(waves) - max_waves} 个波段见 MD 报告")
    lines.append("")
    lines.append("结论: 先看 WRONG_SIDE 和错误 STRONG，再决定是否改策略。")
    return "\n".join(lines)


def save_report(review: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"signal_coverage_{review['date']}.md"
    path.write_text(format_markdown(review), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Review major waves and signal coverage.")
    parser.add_argument("date", help="Review date, e.g. 2026-05-21")
    parser.add_argument("--threshold", type=float, default=DEFAULT_WAVE_THRESHOLD_PCT)
    parser.add_argument("--atr-mult", type=float, default=DEFAULT_ATR_MULT)
    parser.add_argument("--ticker", default="RKLB")
    parser.add_argument("--no-fetch-1m", action="store_true")
    args = parser.parse_args()

    review = build_review(
        args.date,
        threshold_pct=args.threshold,
        atr_mult=args.atr_mult,
        fetch_1m=not args.no_fetch_1m,
        ticker=args.ticker,
    )
    path = save_report(review)
    print(format_telegram_summary(review, max_waves=12))
    print(f"\nReport saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
