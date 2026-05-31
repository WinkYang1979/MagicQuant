"""
MagicQuant daily_score.py
VERSION : v0.1.0
DEPENDS : pandas, research.vectorbt_lab.daily_rklb_review

Score daily RKLB signal quality for isolated research review.
为每日 RKLB 复盘计算信号质量评分，仅用于研究报告。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
ET = ZoneInfo("America/New_York")
LOCAL_TZ = datetime.now().astimezone().tzinfo or ZoneInfo("Australia/Sydney")
DIRECTION_TRIGGERS = {"direction_trend", "intraday_reversal", "swing_bottom", "swing_top", "rapid_move"}


@dataclass
class ScoredSignal:
    trigger: str
    direction: str
    strength: str
    confidence: float
    event_et: pd.Timestamp
    price: float
    future_30m_return_pct: float
    outcome: str


def load_trigger_records_for_et_date(review_date: date) -> list[dict]:
    candidates = [
        BASE_DIR / "data" / "review" / review_date.isoformat() / "triggers.json",
        BASE_DIR / "data" / "review" / (review_date + timedelta(days=1)).isoformat() / "triggers.json",
    ]
    output: list[dict] = []
    seen: set[str] = set()
    for path in candidates:
        if not path.exists():
            continue
        for record in _read_records(path):
            event_time = event_time_et(record)
            if event_time is None or event_time.date() != review_date:
                continue
            key = f"{record.get('ts')}|{record.get('trigger')}|{record.get('ticker')}|{record_price(record)}"
            if key in seen:
                continue
            seen.add(key)
            output.append(record)
    return sorted(output, key=lambda item: event_time_et(item) or pd.Timestamp.min.tz_localize(ET))


def _read_records(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        records = payload.get("records") or payload.get("triggers") or []
        return [item for item in records if isinstance(item, dict)]
    return []


def event_time_et(record: dict) -> pd.Timestamp | None:
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    quality = data.get("data_quality") if isinstance(data.get("data_quality"), dict) else {}
    last_bar_time = quality.get("last_bar_time")
    if last_bar_time:
        try:
            return pd.Timestamp(str(last_bar_time)).tz_localize(ET)
        except Exception:
            pass
    ts = record.get("ts") or record.get("timestamp")
    if ts:
        try:
            local_ts = pd.Timestamp(str(ts)).tz_localize(LOCAL_TZ)
            return local_ts.tz_convert(ET)
        except Exception:
            return None
    return None


def record_price(record: dict) -> float | None:
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    context = record.get("decision_context") if isinstance(record.get("decision_context"), dict) else {}
    price_context = context.get("price_context") if isinstance(context.get("price_context"), dict) else {}
    for value in [record.get("price"), record.get("current"), data.get("current"), price_context.get("current")]:
        try:
            if value is not None:
                return float(value)
        except Exception:
            continue
    return None


def trigger_kind(record: dict) -> str:
    return str(record.get("trigger") or record.get("type") or record.get("name") or "unknown")


def trigger_direction(record: dict) -> str:
    raw = str(record.get("direction") or record.get("signal_direction") or record.get("bias") or "").lower()
    if "long" in raw or "bull" in raw or "看多" in raw:
        return "long"
    if "short" in raw or "bear" in raw or "看空" in raw:
        return "short"
    return "neutral"


def bars_after(bars: pd.DataFrame, event_et: pd.Timestamp, minutes: int = 30) -> pd.DataFrame:
    ts_et = bars["timestamp"].dt.tz_convert(ET)
    end = event_et + pd.Timedelta(minutes=minutes)
    return bars.loc[(ts_et >= event_et) & (ts_et <= end)].copy()


def nearest_price(bars: pd.DataFrame, event_et: pd.Timestamp, fallback: float | None) -> float | None:
    if fallback is not None:
        return fallback
    window = bars_after(bars, event_et, minutes=3)
    if window.empty:
        return None
    return float(window.iloc[0]["close"])


def score_signal(record: dict, bars: pd.DataFrame) -> ScoredSignal | None:
    direction = trigger_direction(record)
    kind = trigger_kind(record)
    if direction not in {"long", "short"} or kind not in DIRECTION_TRIGGERS:
        return None
    event_et = event_time_et(record)
    if event_et is None:
        return None
    price = nearest_price(bars, event_et, record_price(record))
    if price is None or price <= 0:
        return None
    future = bars_after(bars, event_et, minutes=30)
    if future.empty:
        return None
    future_close = float(future.iloc[-1]["close"])
    ret = (future_close - price) / price * 100
    if direction == "long":
        outcome = "correct" if ret > 0.25 else "wrong" if ret < -0.50 else "flat"
    else:
        outcome = "correct" if ret < -0.25 else "wrong" if ret > 0.50 else "flat"
    return ScoredSignal(
        trigger=kind,
        direction=direction,
        strength=str(record.get("strength") or "").upper(),
        confidence=float(record.get("confidence") or 0),
        event_et=event_et,
        price=float(price),
        future_30m_return_pct=float(ret),
        outcome=outcome,
    )


def wave_direction(wave) -> str:
    return "long" if getattr(wave, "direction", "") == "UP" else "short"


def evaluate_wave_coverage(waves: list, scored: list[ScoredSignal]) -> list[dict]:
    rows = []
    for wave in waves:
        start = pd.Timestamp(getattr(wave, "start_ts")).tz_convert(ET)
        end = pd.Timestamp(getattr(wave, "end_ts")).tz_convert(ET)
        if end < start:
            start, end = end, start
        direction = wave_direction(wave)
        duration = max((end - start).total_seconds() / 60, 1)
        same = [sig for sig in scored if sig.direction == direction and start <= sig.event_et <= end]
        if not same:
            status = "MISS"
            first_delay = None
        else:
            first = min(same, key=lambda sig: sig.event_et)
            first_delay = (first.event_et - start).total_seconds() / 60
            status = "TIMELY" if first_delay <= min(15, duration * 0.35) else "LATE"
        rows.append({
            "direction": getattr(wave, "direction", ""),
            "move_pct": float(getattr(wave, "move_pct", 0.0)),
            "start_et": start.strftime("%H:%M"),
            "end_et": end.strftime("%H:%M"),
            "status": status,
            "first_delay_min": first_delay,
        })
    return rows


def build_daily_score(review_date: date, bars: pd.DataFrame, waves: list, records: list[dict]) -> dict:
    scored = [item for item in (score_signal(record, bars) for record in records) if item is not None]
    coverage = evaluate_wave_coverage(waves, scored)
    correct = sum(1 for sig in scored if sig.outcome == "correct")
    wrong = sum(1 for sig in scored if sig.outcome == "wrong")
    flat = sum(1 for sig in scored if sig.outcome == "flat")
    strong_wrong = sum(1 for sig in scored if sig.outcome == "wrong" and (sig.strength == "STRONG" or sig.confidence >= 80))
    timely = sum(1 for row in coverage if row["status"] == "TIMELY")
    late = sum(1 for row in coverage if row["status"] == "LATE")
    miss = sum(1 for row in coverage if row["status"] == "MISS")
    score = 70 + timely * 6 - late * 5 - miss * 12 + correct * 2 - wrong * 6 - strong_wrong * 14
    score = max(0, min(100, int(round(score))))
    return {
        "date": review_date.isoformat(),
        "score": score,
        "signals_scored": len(scored),
        "correct": correct,
        "wrong": wrong,
        "flat": flat,
        "strong_wrong": strong_wrong,
        "timely": timely,
        "late": late,
        "miss": miss,
        "coverage": coverage,
        "suggestions": suggestions(coverage, scored),
    }


def suggestions(coverage: list[dict], scored: list[ScoredSignal]) -> list[str]:
    output: list[str] = []
    missed_down = sum(1 for row in coverage if row["status"] == "MISS" and row["direction"] == "DOWN")
    missed_up = sum(1 for row in coverage if row["status"] == "MISS" and row["direction"] == "UP")
    strong_wrong = [sig for sig in scored if sig.outcome == "wrong" and (sig.strength == "STRONG" or sig.confidence >= 80)]
    if missed_down:
        output.append("下跌波段有漏报：优先检查破位/趋势失效提示是否太晚。")
    if missed_up:
        output.append("上涨/反弹波段有漏报：优先检查反弹观察和突破提示是否过严。")
    if strong_wrong:
        output.append("存在错误强信号：优先做置信度封顶，不要直接改方向核心。")
    if len(scored) == 0:
        output.append("没有可评分方向信号：检查 bot 是否运行、日志是否归档、数据日期是否对齐。")
    if not output:
        output.append("暂无明显策略修改建议，继续积累样本。")
    return output


def score_markdown(score: dict) -> str:
    lines = [
        "## Daily Signal Score",
        "",
        f"- Score: {score['score']}/100",
        f"- Scored direction signals: {score['signals_scored']}",
        f"- Correct / Wrong / Flat: {score['correct']} / {score['wrong']} / {score['flat']}",
        f"- Strong wrong signals: {score['strong_wrong']}",
        f"- Wave coverage: timely {score['timely']}, late {score['late']}, miss {score['miss']}",
        "",
        "### Optimization Suggestions",
        "",
    ]
    for item in score["suggestions"]:
        lines.append(f"- {item}")
    return "\n".join(lines)
