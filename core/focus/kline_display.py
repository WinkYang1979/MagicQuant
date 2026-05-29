"""
VERSION : v0.5.35
DEPENDS : core.focus.market_clock

K_5M data-source display helpers.
K_5M 数据源透明展示工具，只负责文案，不参与交易判断。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from .market_clock import ET, get_market_status
except Exception:
    ET = ZoneInfo("America/New_York")

    def get_market_status():
        return "unknown"


def _parse_kline_time(value):
    """Parse Futu/Moomoo K-line time as ET. / 按 ET 解析 K 线时间。"""
    if not value:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        raw = raw.replace("T", " ")
        if "." in raw:
            raw = raw.split(".", 1)[0]
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(raw[:len(fmt)], fmt)
                    break
                except Exception:
                    dt = None
            if dt is None:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


def _last_bar_from_bars(bars):
    if bars is None:
        return None
    try:
        if hasattr(bars, "empty"):
            if bars.empty:
                return None
            row = bars.iloc[-1]
            if hasattr(row, "get"):
                return row.get("time_key") or row.get("time") or row.get("datetime")
            return None
        if len(bars) == 0:
            return None
        last = bars[-1]
        if isinstance(last, dict):
            return last.get("time_key") or last.get("time") or last.get("datetime")
        return getattr(last, "time_key", None) or getattr(last, "time", None)
    except Exception:
        return None


def find_kline_last_time(session=None, indicators=None, hit=None, quality=None):
    """Find latest K_5M timestamp from available context. / 从上下文提取最新 K_5M 时间。"""
    sources = []
    if quality is not None:
        sources.append(getattr(quality, "last_bar_time", None))
    if hit:
        data = hit.get("data") or {}
        q = data.get("data_quality") or hit.get("data_quality") or {}
        if isinstance(q, dict):
            sources.append(q.get("last_bar_time"))
        sources += [data.get("last_bar_time"), data.get("kline_last_time")]
    if indicators:
        sources += [
            indicators.get("last_bar_time"),
            indicators.get("kline_last_time"),
            indicators.get("indicator_at"),
            _last_bar_from_bars(
                indicators.get("kline_bars")
                if indicators.get("kline_bars") is not None
                else indicators.get("bars")
            ),
        ]
        q = indicators.get("data_quality") or {}
        if isinstance(q, dict):
            sources.append(q.get("last_bar_time"))
    if session is not None:
        q = getattr(session, "_last_data_quality", None) or {}
        if isinstance(q, dict):
            sources.append(q.get("last_bar_time"))
        cache = getattr(session, "_last_indicators_cache", None) or {}
        if isinstance(cache, dict):
            sources += [
                cache.get("last_bar_time"),
                cache.get("kline_last_time"),
                _last_bar_from_bars(
                    cache.get("kline_bars")
                    if cache.get("kline_bars") is not None
                    else cache.get("bars")
                ),
            ]
        kl = getattr(session, "_last_kline_cache", None)
        if kl is not None:
            try:
                if hasattr(kl, "iloc") and len(kl) > 0:
                    row = kl.iloc[-1]
                    sources.append(row.get("time_key") if hasattr(row, "get") else None)
                elif isinstance(kl, list):
                    sources.append(_last_bar_from_bars(kl))
            except Exception:
                pass

    for src in sources:
        dt = _parse_kline_time(src)
        if dt is not None:
            return dt
    return None


def _format_age(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}min"
    hours = minutes // 60
    rem = minutes % 60
    return f"{hours}h" if rem == 0 else f"{hours}h {rem}min"


def format_kline_source_line(session=None, indicators=None, hit=None, quality=None) -> str:
    """Render K_5M last line. / 渲染 K_5M 最新时间与 age。"""
    dt = find_kline_last_time(session=session, indicators=indicators, hit=hit, quality=quality)
    if dt is None:
        return "🕐 K_5M last: —"
    now = datetime.now(ET)
    age_raw = (now - dt).total_seconds()
    age_sec = max(0, age_raw)
    try:
        session_name = get_market_status()
    except Exception:
        session_name = "unknown"
    stale_limit = 600 if session_name == "regular" else 1800
    stamp = dt.strftime("%Y-%m-%d %H:%M")
    if age_raw < -30:
        ahead = _format_age(abs(age_raw))
        return f"🕐 K_5M last: {stamp} (当前5m柱, 时间戳领先 {ahead})"
    age = _format_age(age_sec)
    if age_sec > stale_limit:
        return f"🕐 K_5M last: {stamp} ⚠️ (age {age}, 数据过期)"
    return f"🕐 K_5M last: {stamp} (age {age})"


def should_show_subscription_detail() -> bool:
    try:
        from config.settings import SHOW_SUBSCRIPTION_DETAIL
        return bool(SHOW_SUBSCRIPTION_DETAIL)
    except Exception:
        return False


def format_subscription_detail(detail=None) -> str | None:
    """Render optional subscription params. / 可选显示订阅参数。"""
    if not should_show_subscription_detail():
        return None
    detail = detail or {}
    extended = detail.get("extended_time", detail.get("extended", "?"))
    session = detail.get("session", "?")
    return f"🔌 订阅: K_5M | extended={extended} | session={session}"


def inject_kline_source_line(text: str, session=None, indicators=None, hit=None, quality=None) -> str:
    """Insert K_5M source line below indicator-like lines. / 在指标行下插入 K_5M 数据源。"""
    if not text or "K_5M last:" in text:
        return text
    line = format_kline_source_line(session=session, indicators=indicators, hit=hit, quality=quality)
    # 仅在 K 线异常(数据过期 / 缺失)时显示, 供信号冻结诊断;
    # 正常时不显示——首行状态灯已表明信号正常。Show only when stale/missing.
    if "⚠️" not in line and "K_5M last: —" not in line:
        return text
    lines = text.splitlines()
    for idx, existing in enumerate(lines):
        if any(token in existing for token in ("📊 指标", "5分钟指标", "RSI", "VWAP", "量比")):
            lines.insert(idx + 1, line)
            return "\n".join(lines)
    for idx, existing in enumerate(lines):
        if not existing.strip() and idx > 0:
            lines.insert(idx, line)
            return "\n".join(lines)
    return text + "\n" + line
