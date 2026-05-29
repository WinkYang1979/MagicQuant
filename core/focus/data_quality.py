"""
MagicQuant Focus - data_quality.py
VERSION : v0.5.36
DEPENDS : core.focus.market_clock

Session-aware data quality gate.
数据质量门禁：先证明指标新鲜可信，再允许方向/买入类信号。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo


ENTRY_TRIGGERS = {
    "direction_trend",
    "intraday_reversal",
    "breakdown_warning",
    "capitulation_bottom_watch",
    "swing_bottom",
    "near_support",
    "rapid_move",
}

EXIT_TRIGGERS = {
    "target_advance",
    "profit_target_hit",
    "overbought_surge",
    "near_resistance",
    "large_day_gain",
    "drawdown_from_peak",
}

RISK_TRIGGERS = {
    "stop_loss_warning",
}

SESSION_KLINE_MAX_AGE_SEC = {
    "regular": 360,
    "pre": 600,
    "post": 600,
    "overnight": 1200,
    "closed": 0,
    "unknown": 600,
}

FROZEN_VALUE_BLACKLIST = {
    (43.1, 4.94),
    (43.1, 5.82),
}


@dataclass
class DataQuality:
    ok: bool
    level: str
    reason: str
    session: str = "unknown"
    can_direction: bool = False
    can_entry: bool = False
    can_exit: bool = False
    can_risk: bool = True
    can_heartbeat: bool = True
    last_bar_time: Optional[str] = None
    last_bar_age_sec: Optional[float] = None
    is_current_trading_day: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "level": self.level,
            "reason": self.reason,
            "session": self.session,
            "can_direction": self.can_direction,
            "can_entry": self.can_entry,
            "can_exit": self.can_exit,
            "can_risk": self.can_risk,
            "can_heartbeat": self.can_heartbeat,
            "last_bar_time": self.last_bar_time,
            "last_bar_age_sec": self.last_bar_age_sec,
            "is_current_trading_day": self.is_current_trading_day,
        }


def _market_session(now: Optional[datetime] = None) -> str:
    try:
        from .market_clock import get_market_status
        if now is not None:
            return str(get_market_status(now.replace(tzinfo=ZoneInfo("America/New_York"))) or "unknown")
        return str(get_market_status() or "unknown")
    except Exception:
        return "unknown"


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text[:19])
    except ValueError:
        return None


def _last_bar_from_indicators(indicators: Optional[dict]) -> Optional[datetime]:
    if not indicators:
        return None
    for key in ("last_bar_time", "kline_last_time", "last_time_key"):
        dt = _parse_dt(indicators.get(key))
        if dt:
            return dt
    bars = indicators.get("kline_bars")
    if bars is None:
        bars = indicators.get("bars")
    if hasattr(bars, "empty"):
        try:
            bars = [] if bars.empty else bars.to_dict("records")
        except Exception:
            bars = []
    if bars is not None and len(bars) > 0:
        last = bars[-1]
        if isinstance(last, dict):
            for key in ("time", "time_key", "datetime", "ts"):
                dt = _parse_dt(last.get(key))
                if dt:
                    return dt
    return None


def _last_bar_from_session(session: Any) -> Optional[datetime]:
    kl = getattr(session, "_last_kline_cache", None)
    if kl is None:
        return None
    try:
        if len(kl) == 0:
            return None
        row = kl.iloc[-1]
        for key in ("time_key", "time", "datetime"):
            if key in row:
                dt = _parse_dt(row[key])
                if dt:
                    return dt
    except Exception:
        return None
    return None


def _same_trading_day(now: datetime, last_bar: datetime) -> bool:
    # Overnight session can cross midnight ET; allow previous calendar day after 20:00.
    # 夜盘可能跨 ET 午夜；20:00 后允许上一自然日的 K 线归属同一夜盘。
    if now.date() == last_bar.date():
        return True
    if now.hour < 4 and last_bar.date() == (now - timedelta(days=1)).date():
        return True
    return False


def _update_repeat_state(session: Any, indicators: Optional[dict], threshold: int,
                         last_bar: Optional[datetime] = None) -> bool:
    if session is None or not indicators:
        return False
    rsi = indicators.get("rsi_5m")
    if rsi is None:
        rsi = indicators.get("rsi_14")
    vol = indicators.get("vol_ratio")
    if rsi is None or vol is None:
        return False
    try:
        key = (round(float(rsi), 4), round(float(vol), 4))
    except (TypeError, ValueError):
        return False

    bar_key = last_bar.strftime("%Y-%m-%d %H:%M:%S") if last_bar else None
    state = getattr(session, "_data_quality_repeat_state", None) or {
        "last": None,
        "last_bar": None,
        "count": 0,
    }
    if bar_key and state.get("last_bar") == bar_key:
        # 同一根 5m K 线内重复不代表冻结。Same 5m bar repeats are expected.
        session._data_quality_repeat_state = state
        return state["count"] >= threshold
    if state.get("last") == key:
        state["count"] = int(state.get("count", 0)) + 1
    else:
        state = {"last": key, "last_bar": bar_key, "count": 1}
    state["last_bar"] = bar_key
    session._data_quality_repeat_state = state
    return state["count"] >= threshold


def _hits_frozen_blacklist(indicators: Optional[dict]) -> tuple[bool, Optional[tuple[float, float]]]:
    if not indicators:
        return False, None
    try:
        rsi = indicators.get("rsi_5m")
        if rsi is None:
            rsi = indicators.get("rsi_14")
        vol = indicators.get("vol_ratio")
        if rsi is None or vol is None:
            return False, None
        pair = (round(float(rsi), 1), round(float(vol), 2))
        return pair in FROZEN_VALUE_BLACKLIST, pair
    except (TypeError, ValueError):
        return False, None


def _block(reason: str, session: str, last_bar: Optional[datetime],
           age: Optional[float], is_current: bool) -> DataQuality:
    return DataQuality(
        ok=False,
        level="BLOCK",
        reason=reason,
        session=session,
        can_direction=False,
        can_entry=False,
        can_exit=False,
        can_risk=True,
        can_heartbeat=True,
        last_bar_time=last_bar.strftime("%Y-%m-%d %H:%M:%S") if last_bar else None,
        last_bar_age_sec=age,
        is_current_trading_day=is_current,
    )


def _max_age_for_session(session: str, fallback: int) -> int:
    return SESSION_KLINE_MAX_AGE_SEC.get(session, fallback)


def evaluate_data_quality(session: Any = None, indicators: Optional[dict] = None,
                          now: Optional[datetime] = None,
                          max_kline_age_sec: int = 600,
                          repeat_threshold: int = 30,
                          update_repeat: bool = True) -> DataQuality:
    """Evaluate if indicators are safe for trading signals.

    判断指标是否足够新鲜可信，可用于方向/买入/止盈信号。
    """
    now = (now or datetime.now(ZoneInfo("America/New_York"))).replace(tzinfo=None)
    market_session = _market_session(now)
    max_kline_age_sec = _max_age_for_session(market_session, max_kline_age_sec)
    last_bar = _last_bar_from_indicators(indicators) or _last_bar_from_session(session)
    age = (now - last_bar).total_seconds() if last_bar else None
    is_current = bool(last_bar and _same_trading_day(now, last_bar))

    if not indicators or not indicators.get("data_ok"):
        return _block("indicators data_ok is false", market_session, last_bar, age, is_current)

    if market_session == "closed":
        return _block("market session is closed", market_session, last_bar, age, is_current)

    if indicators.get("is_today") is False:
        return _block("indicators are not from current trading day", market_session, last_bar, age, is_current)

    blacklisted, pair = _hits_frozen_blacklist(indicators)
    if blacklisted:
        return _block(f"known frozen RSI/vol_ratio pair: {pair}", market_session, last_bar, age, is_current)

    if last_bar is not None:
        if not is_current:
            return _block("last K_5M bar is not in current trading day/session",
                          market_session, last_bar, age, is_current)
        if age is not None and age > max_kline_age_sec:
            return _block(f"last K_5M bar is stale: {int(age)}s",
                          market_session, last_bar, age, is_current)

    if update_repeat and _update_repeat_state(session, indicators, repeat_threshold, last_bar):
        return _block(f"RSI and vol_ratio repeated {repeat_threshold} times", market_session, last_bar, age, is_current)

    return DataQuality(
        ok=True,
        level="OK",
        reason="OK",
        session=market_session,
        can_direction=True,
        can_entry=True,
        can_exit=True,
        can_risk=True,
        can_heartbeat=True,
        last_bar_time=last_bar.strftime("%Y-%m-%d %H:%M:%S") if last_bar else None,
        last_bar_age_sec=age,
        is_current_trading_day=is_current if last_bar else True,
    )


def trigger_requires_fresh_data(trigger: str) -> bool:
    return trigger in ENTRY_TRIGGERS or trigger in EXIT_TRIGGERS


def trigger_allows_bad_data(trigger: str) -> bool:
    return trigger in RISK_TRIGGERS


def attach_quality(hit: dict, quality: DataQuality) -> dict:
    data = hit.setdefault("data", {})
    data["data_quality"] = quality.to_dict()
    return hit


def log_blocked_signal(session: Any, hit_or_trigger: Any, quality: DataQuality,
                       source: str = "gate", would_have_pushed: Optional[str] = None) -> None:
    """Persist blocked signal for review. / 落盘记录被拦截信号，便于复盘。"""
    try:
        if isinstance(hit_or_trigger, dict):
            hit = hit_or_trigger
            trigger = hit.get("trigger")
            ticker = hit.get("ticker")
            direction = hit.get("direction")
            strength = hit.get("strength")
            title = hit.get("title")
        else:
            trigger = str(hit_or_trigger)
            ticker = None
            direction = None
            strength = None
            title = None

        now_et = datetime.now(ZoneInfo("America/New_York"))
        project_root = Path(__file__).resolve().parents[2]
        out_dir = project_root / "data" / "review" / now_et.strftime("%Y-%m-%d")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "blocked_signals.json"

        records = []
        if out_file.exists():
            try:
                records = json.loads(out_file.read_text(encoding="utf-8"))
            except Exception:
                records = []

        record = {
            "ts": now_et.strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "ticker": ticker,
            "trigger": trigger,
            "direction": direction,
            "strength": strength,
            "reason": quality.reason,
            "last_bar_time": quality.last_bar_time,
            "would_have_pushed": would_have_pushed or title,
            "data_quality": quality.to_dict(),
        }
        records.append(record)
        out_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

        if session is not None:
            blocked = getattr(session, "_blocked_signals", None)
            if blocked is None:
                blocked = []
                session._blocked_signals = blocked
            blocked.append(record)
            if len(blocked) > 200:
                del blocked[:-200]
    except Exception as e:
        print(f"  [data_quality] blocked signal log failed: {e}")
