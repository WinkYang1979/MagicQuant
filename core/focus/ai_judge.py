"""
MagicQuant Focus - ai_judge.py
VERSION : v0.1.0
DATE    : 2026-05-20
DEPENDS : core.agents.providers, core.focus.context
OWNER   : laoyang

One-shot AI tape reading for manual intervention.
手动 AI 临时判盘：只拉一次行情快照，把同一份数据喂给多个 AI。
"""

from __future__ import annotations

import json
import math
import re
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Optional

try:
    from moomoo import KLType, SubType, AuType, Session
except ImportError:
    from futu import KLType, SubType, AuType, Session

from core.agents.providers import build_all_providers


VERSION = "v0.1.0"
K1_CACHE_TTL_SEC = 45
K1_BAR_COUNT = 90
AI_TIMEOUT_SEC = 35
AI_MAX_TOKENS = 650

_K1_CACHE: dict[str, dict[str, Any]] = {}


def run_ai_judge(
    session,
    indicators_cache: dict,
    client,
    ticker: str = "RKLB",
    reason: str = "AI 临时判盘",
    send_tg_fn: Optional[Callable] = None,
) -> dict:
    """Run one-shot AI judgment and optionally push Telegram. / 运行一次手动 AI 判盘。"""
    ticker_full = _normalize_ticker(ticker)
    snapshot = build_one_shot_snapshot(session, indicators_cache or {}, client, ticker_full)
    snapshot["reason"] = reason

    result = consult_three_ai(snapshot)
    text = format_ai_judge_message(snapshot, result)
    result["summary_text"] = text
    result["snapshot"] = snapshot

    if send_tg_fn:
        send_tg_fn(text)
    return result


def build_one_shot_snapshot(session, indicators_cache: dict, client, ticker_full: str) -> dict:
    """Build one market snapshot for all AIs. / 为所有 AI 构建同一份行情快照。"""
    master = getattr(session, "master", ticker_full) if session else ticker_full
    followers = list(getattr(session, "followers", []) or []) if session else []
    symbols = [master] + [tk for tk in followers if tk != master]
    if ticker_full not in symbols:
        symbols.insert(0, ticker_full)

    prices = {}
    for tk in symbols:
        prices[_short(tk)] = _quote_from_session(session, tk)

    k5_bars = _bars_from_any(getattr(session, "_last_kline_cache", None), limit=60) if session else []
    k1_bars, k1_error = fetch_k1m_bars_once(client, ticker_full, K1_BAR_COUNT)

    current = _safe_float(prices.get(_short(ticker_full), {}).get("price"))
    if current is None and k1_bars:
        current = _safe_float(k1_bars[-1].get("close"))
    if current is None and k5_bars:
        current = _safe_float(k5_bars[-1].get("close"))

    levels = compute_key_levels(
        current=current,
        indicators=indicators_cache,
        session=session,
        ticker_full=ticker_full,
        k1_bars=k1_bars,
        k5_bars=k5_bars,
    )

    positions = _positions_from_session(session)
    cash = _safe_float(getattr(session, "cash_available", None)) if session else None

    return {
        "ticker": _short(ticker_full),
        "ticker_full": ticker_full,
        "snapshot_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prices": prices,
        "current_price": current,
        "indicators": _compact_indicators(indicators_cache),
        "levels": levels,
        "k1m": {
            "last": _bar_time(k1_bars),
            "bars": k1_bars[-30:],
            "error": k1_error,
            "source": "Futu get_cur_kline K_1M once",
        },
        "k5m": {
            "last": _bar_time(k5_bars),
            "bars": k5_bars[-24:],
            "source": "Focus session _last_kline_cache",
        },
        "portfolio": {
            "cash": cash,
            "positions": positions,
        },
    }


def fetch_k1m_bars_once(client, ticker_full: str, num: int = K1_BAR_COUNT) -> tuple[list[dict], Optional[str]]:
    """Fetch K_1M once with a short cache. / 只拉一次 K_1M，并做短缓存。"""
    now = time.time()
    cached = _K1_CACHE.get(ticker_full)
    if cached and now - cached.get("ts", 0) <= K1_CACHE_TTL_SEC:
        return list(cached.get("bars", [])), cached.get("error")

    if client is None:
        return [], "quote client unavailable"

    try:
        if hasattr(client, "_ensure_quote") and not client._ensure_quote():
            return [], "quote context unavailable"

        subtype = getattr(SubType, "K_1M", None)
        ktype = getattr(KLType, "K_1M", None)
        if subtype is None or ktype is None:
            return [], "SDK has no K_1M enum"

        # Keep this isolated from the strategy K_5M subscription.
        # 这里独立按需订阅 K_1M，不改主策略 K_5M 订阅状态。
        with client._quote_lock:
            try:
                client._quote_ctx.subscribe(
                    [ticker_full], [subtype], subscribe_push=False,
                    extended_time=True, session=Session.ALL,
                )
            except TypeError:
                client._quote_ctx.subscribe([ticker_full], [subtype])
            try:
                ret, data = client._quote_ctx.get_cur_kline(ticker_full, num, ktype, AuType.QFQ)
            except TypeError:
                ret, data = client._quote_ctx.get_cur_kline(ticker_full, num, ktype)

        if ret != 0:
            err = str(data)[:160]
            _K1_CACHE[ticker_full] = {"ts": now, "bars": [], "error": err}
            return [], err

        bars = _bars_from_any(data, limit=num)
        _K1_CACHE[ticker_full] = {"ts": now, "bars": bars, "error": None}
        return bars, None
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:160]}"
        _K1_CACHE[ticker_full] = {"ts": now, "bars": [], "error": err}
        return [], err


def consult_three_ai(snapshot: dict) -> dict:
    """Call up to three configured AIs with the same snapshot. / 同一份快照并行喂给最多三个 AI。"""
    try:
        providers = build_all_providers()
    except Exception as e:
        return {"error": f"AI provider 初始化失败: {e}", "advisors": {}, "combined": {}}

    preferred = ["claude_sonnet", "gpt_5", "deepseek", "kimi", "claude_opus", "claude_haiku"]
    names = [name for name in preferred if name in providers][:3]
    if not names:
        return {"error": "没有可用 AI provider，请检查 API key", "advisors": {}, "combined": {}}

    system_prompt = (
        "你是短线交易判盘助手。只基于用户给出的同一份行情快照判断，不要编造外部数据。"
        "重点输出方向、支撑、压力、均线/VWAP位置、失效条件。不要给仓位建议。"
    )
    user_prompt = _build_ai_prompt(snapshot)
    advisors = {}
    total_cost = 0.0

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        tasks = {
            pool.submit(
                providers[name].call,
                system_prompt,
                user_prompt,
                AI_MAX_TOKENS,
                AI_TIMEOUT_SEC,
            ): name
            for name in names
        }
        for future in as_completed(tasks):
            name = tasks[future]
            provider = providers[name]
            try:
                raw = future.result()
            except Exception as e:
                raw = {"text": "", "error": f"{type(e).__name__}: {str(e)[:120]}", "cost_usd": 0}

            total_cost += float(raw.get("cost_usd") or 0)
            text = (raw.get("text") or "").strip()
            advisors[name] = {
                "display_name": getattr(provider, "display_name", name),
                "text": text,
                "error": raw.get("error"),
                "direction": _extract_direction(text),
                "confidence": _extract_confidence(text),
                "duration_ms": raw.get("duration_ms", 0),
            }

    return {
        "advisors": advisors,
        "combined": _combine_advisors(advisors),
        "total_cost_usd": round(total_cost, 5),
    }


def compute_key_levels(
    current: Optional[float],
    indicators: dict,
    session,
    ticker_full: str,
    k1_bars: list[dict],
    k5_bars: list[dict],
) -> dict:
    """Compute support/resistance and moving averages. / 计算支撑、压力与均线。"""
    vwap = _safe_float(indicators.get("vwap"))
    day_low = _safe_float(getattr(session, "session_low", {}).get(ticker_full)) if session else None
    day_high = _safe_float(getattr(session, "session_high", {}).get(ticker_full)) if session else None
    recent_1m_low = _recent_extreme(k1_bars, "low", min)
    recent_1m_high = _recent_extreme(k1_bars, "high", max)
    recent_5m_low = _recent_extreme(k5_bars, "low", min)
    recent_5m_high = _recent_extreme(k5_bars, "high", max)

    ma1 = _ma_pack(k1_bars)
    ma5 = _ma_pack(k5_bars)

    supports = _unique_prices([recent_1m_low, recent_5m_low, day_low, vwap if current and vwap and vwap < current else None])
    resistances = _unique_prices([recent_1m_high, recent_5m_high, day_high, vwap if current and vwap and vwap > current else None])

    return {
        "support": supports[:4],
        "resistance": resistances[:4],
        "vwap": _round_price(vwap),
        "ma_1m": ma1,
        "ma_5m": ma5,
        "day_low": _round_price(day_low),
        "day_high": _round_price(day_high),
        "recent_1m_low": _round_price(recent_1m_low),
        "recent_1m_high": _round_price(recent_1m_high),
        "recent_5m_low": _round_price(recent_5m_low),
        "recent_5m_high": _round_price(recent_5m_high),
    }


def format_ai_judge_message(snapshot: dict, result: dict) -> str:
    """Format Telegram message. / 格式化 Telegram 输出。"""
    ticker = snapshot.get("ticker", "RKLB")
    levels = snapshot.get("levels", {})
    ind = snapshot.get("indicators", {})
    combined = result.get("combined") or {}
    advisors = result.get("advisors") or {}

    current = _fmt_price(snapshot.get("current_price"))
    support = _fmt_levels(levels.get("support"))
    resistance = _fmt_levels(levels.get("resistance"))
    ma1 = _fmt_ma(levels.get("ma_1m"))
    ma5 = _fmt_ma(levels.get("ma_5m"))

    lines = [
        f"🧠 AI 临时判盘 · {ticker}",
        "━━━━━━━━━━━━━━",
        f"现价 {current} · RSI {ind.get('rsi_5m', '—')} · VWAP {_fmt_price(levels.get('vwap'))} · 量比 {ind.get('vol_ratio', '—')}x",
        f"🕐 K_1M last: {snapshot.get('k1m', {}).get('last') or '—'}",
        f"🕐 K_5M last: {snapshot.get('k5m', {}).get('last') or '—'}",
    ]
    if snapshot.get("k1m", {}).get("error"):
        lines.append(f"⚠️ K_1M 获取失败: {snapshot['k1m']['error']}")

    lines += [
        "",
        "📍 关键价位",
        f"支撑: {support}",
        f"压力: {resistance}",
        f"均线: 1m {ma1} · 5m {ma5}",
        "",
        f"🧭 综合: {combined.get('direction_label', '分歧/不明')} · 信心 {combined.get('confidence_label', '—')}",
    ]
    if combined.get("reason"):
        lines.append(f"理由: {combined['reason']}")

    lines.append("")
    lines.append("🤖 三路 AI")
    lines.append("━━━━━━━━━━━━━━")
    for name, item in _ordered_advisors(advisors):
        lines.extend(_format_advisor_block(name, item))
        lines.append("")

    lines += [
        "",
        f"成本约 ${result.get('total_cost_usd', 0):.4f} · ai_judge {VERSION}",
    ]
    return "\n".join(lines)


def _build_ai_prompt(snapshot: dict) -> str:
    compact = json.dumps(snapshot, ensure_ascii=False, default=str)
    return (
        "请对下面这份同一时刻快照做短线判盘。必须按这个格式输出，依据请分条换行：\n"
        "方向: 看多/看空/震荡/反弹观察/底部观察\n"
        "信心: 0-100\n"
        "依据:\n"
        "1. 2-4条，必须引用具体价格\n"
        "2. 每条单独一行，不要堆成长句\n"
        "支撑: $xx / $xx\n"
        "压力: $xx / $xx\n"
        "失效: 如果价格怎样就说明判断错了\n"
        "下一步: 盯哪个价位或形态\n\n"
        f"行情快照 JSON:\n{compact}"
    )


def _quote_from_session(session, ticker_full: str) -> dict:
    q = {}
    if session is not None and hasattr(session, "get_quote"):
        q = session.get_quote(ticker_full) or {}
    price = _safe_float(q.get("price")) if q else None
    if price is None and session is not None:
        price = _safe_float(session.get_last_price(ticker_full))
    return {
        "price": _round_price(price),
        "change_pct": _safe_float(q.get("change_pct")) if q else None,
        "high": _round_price(getattr(session, "session_high", {}).get(ticker_full) if session else None),
        "low": _round_price(getattr(session, "session_low", {}).get(ticker_full) if session else None),
        "update_time": q.get("update_time") if q else None,
    }


def _positions_from_session(session) -> dict:
    out = {}
    positions = getattr(session, "positions_snapshot", {}) if session else {}
    if not isinstance(positions, dict):
        return out
    for tk, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        qty = _safe_float(pos.get("qty") or pos.get("qty_held") or pos.get("position_qty"))
        if not qty or qty <= 0:
            continue
        out[_short(tk)] = {
            "qty": qty,
            "cost": _safe_float(pos.get("cost_price") or pos.get("average_cost") or pos.get("avg_cost")),
            "pl_val": _safe_float(pos.get("pl_val") or pos.get("pl")),
            "pl_pct": _safe_float(pos.get("pl_ratio") or pos.get("pl_pct")),
        }
    return out


def _compact_indicators(indicators: dict) -> dict:
    keep = [
        "data_ok", "rsi_5m", "vwap", "vol_ratio", "day_chg_pct",
        "dist_to_vwap_pct", "session_high", "session_low", "kline_last_time",
        "kline_age_sec", "market_session", "candle_dir",
    ]
    return {k: indicators.get(k) for k in keep if k in indicators}


def _bars_from_any(data: Any, limit: int = 60) -> list[dict]:
    if data is None:
        return []
    try:
        if hasattr(data, "tail") and hasattr(data, "iterrows"):
            rows = []
            for _, row in data.tail(limit).iterrows():
                rows.append(_row_to_bar(row))
            return [b for b in rows if b]
        if isinstance(data, list):
            return [_row_to_bar(row) for row in data[-limit:] if _row_to_bar(row)]
    except Exception:
        return []
    return []


def _row_to_bar(row: Any) -> dict:
    def get(name):
        if isinstance(row, dict):
            return row.get(name)
        try:
            return row[name]
        except Exception:
            return None

    bar = {
        "time": str(get("time_key") or get("time") or get("datetime") or ""),
        "open": _round_price(get("open")),
        "high": _round_price(get("high")),
        "low": _round_price(get("low")),
        "close": _round_price(get("close")),
        "volume": _safe_float(get("volume")),
    }
    if bar["close"] is None:
        return {}
    return bar


def _ma_pack(bars: list[dict]) -> dict:
    closes = [_safe_float(b.get("close")) for b in bars]
    closes = [x for x in closes if x is not None]
    return {
        "ma5": _round_price(_mean_tail(closes, 5)),
        "ma10": _round_price(_mean_tail(closes, 10)),
        "ma20": _round_price(_mean_tail(closes, 20)),
    }


def _mean_tail(values: list[float], n: int) -> Optional[float]:
    if len(values) < n:
        return None
    tail = values[-n:]
    return sum(tail) / n


def _recent_extreme(bars: list[dict], key: str, fn) -> Optional[float]:
    vals = [_safe_float(b.get(key)) for b in bars[-24:]]
    vals = [v for v in vals if v is not None]
    return fn(vals) if vals else None


def _combine_advisors(advisors: dict) -> dict:
    votes = {"bullish": 0, "bearish": 0, "neutral": 0}
    confs = []
    for item in advisors.values():
        direction = item.get("direction") or "neutral"
        votes[direction] = votes.get(direction, 0) + 1
        if item.get("confidence") is not None:
            confs.append(item["confidence"])

    direction = max(votes, key=votes.get) if votes else "neutral"
    avg_conf = int(round(sum(confs) / len(confs))) if confs else None
    label_map = {"bullish": "偏多", "bearish": "偏空", "neutral": "分歧/震荡"}
    agree = votes.get(direction, 0)
    return {
        "direction": direction,
        "direction_label": label_map.get(direction, "分歧/震荡"),
        "confidence": avg_conf,
        "confidence_label": f"{avg_conf}% ({agree}/{len(advisors)} 同向)" if avg_conf is not None else f"{agree}/{len(advisors)} 同向",
        "reason": "按三路 AI 多数方向汇总；若分歧明显，以关键价位突破/跌破确认。",
    }


def _extract_direction(text: str) -> str:
    if re.search(r"看空|偏空|下跌|破位|bear", text, re.I):
        return "bearish"
    if re.search(r"看多|偏多|反弹|上行|bull", text, re.I):
        return "bullish"
    return "neutral"


def _extract_confidence(text: str) -> Optional[int]:
    m = re.search(r"(?:信心|confidence)[：:\s]*(\d{1,3})", text, re.I)
    if not m:
        m = re.search(r"(\d{1,3})\s*%", text)
    if not m:
        return None
    val = int(m.group(1))
    return max(0, min(100, val))


def _ordered_advisors(advisors: dict) -> list[tuple[str, dict]]:
    """Stable display order. / 固定展示顺序，方便肉眼对比。"""
    preferred = ["claude_sonnet", "gpt_5", "deepseek", "kimi", "claude_opus", "claude_haiku"]
    ordered = [(name, advisors[name]) for name in preferred if name in advisors]
    ordered.extend((name, item) for name, item in advisors.items() if name not in preferred)
    return ordered


def _format_advisor_block(name: str, item: dict) -> list[str]:
    display = item.get("display_name") or name
    if item.get("error"):
        return [f"🧩 {display}", f"  ❌ 调用失败: {item['error']}"]
    if not (item.get("text") or "").strip():
        return [f"🧩 {display}", "  ❌ 空响应: 未返回可解析文本"]

    parsed = _parse_advisor_text(item.get("text", ""))
    direction = parsed.get("方向") or _direction_label(item.get("direction"))
    confidence = parsed.get("信心") or item.get("confidence") or "—"
    if isinstance(confidence, int) or str(confidence).isdigit():
        confidence = f"{confidence}%"
    support = parsed.get("支撑") or "—"
    resistance = parsed.get("压力") or "—"

    lines = [
        f"🧩 {display}",
        f"  🧭 方向: {direction}",
        f"  🔥 信心: {confidence}",
    ]

    reason_lines = parsed.get("依据") or []
    if reason_lines:
        lines.append("  📌 依据:")
        for idx, reason in enumerate(reason_lines[:4], 1):
            for part_idx, wrapped in enumerate(_wrap(reason, width=32)):
                prefix = f"    {idx}. " if part_idx == 0 else "       "
                lines.append(prefix + wrapped)
    else:
        raw_lines = _fallback_advisor_lines(item.get("text", ""))
        if raw_lines:
            lines.append("  📌 原始要点:")
            for raw in raw_lines[:5]:
                for wrapped in _wrap(raw, width=34):
                    lines.append(f"    {wrapped}")

    lines.append("  🟩 支撑:")
    lines.extend(_format_level_lines(support, "    "))
    lines.append("  🟥 压力:")
    lines.extend(_format_level_lines(resistance, "    "))

    if parsed.get("失效"):
        lines.append("  ⚠️ 失效:")
        lines.extend(f"    {line}" for line in _wrap(parsed["失效"], width=34))
    if parsed.get("下一步"):
        lines.append("  👀 下一步:")
        lines.extend(f"    {line}" for line in _wrap(parsed["下一步"], width=34))
    return lines


def _parse_advisor_text(text: str) -> dict:
    out = {"依据": []}
    current_key = None
    for raw in [line.strip() for line in text.splitlines() if line.strip()]:
        line = _clean_ai_line(raw)
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(方向|信心|依据|支撑|压力|失效|下一步)\s*[：:]\s*(.*)$", line)
        if m:
            current_key = m.group(1)
            value = m.group(2).strip()
            if current_key == "依据":
                if value:
                    out["依据"].extend(_split_reason_items(value))
            else:
                out[current_key] = value
            continue

        if current_key == "依据":
            out["依据"].extend(_split_reason_items(line))
        elif current_key in ("支撑", "压力") and current_key in out:
            out[current_key] += " / " + line
        elif current_key in ("失效", "下一步") and current_key in out:
            out[current_key] += " " + line
    return out


def _fallback_advisor_lines(text: str) -> list[str]:
    parsed_keys = ("方向", "信心", "支撑", "压力", "失效", "下一步")
    out = []
    for raw in [line.strip() for line in text.splitlines() if line.strip()]:
        line = _clean_ai_line(raw)
        if not line or line.startswith("#"):
            continue
        if re.match(rf"^({'|'.join(parsed_keys)})\s*[：:]", line):
            continue
        if line == "依据:":
            continue
        out.extend(_split_reason_items(line))
    return [line for line in out if line]


def _clean_ai_line(line: str) -> str:
    line = line.strip().lstrip("·-• ").strip()
    line = re.sub(r"^\d+[\.、)]\s*", "", line)
    line = re.sub(r"\*\*(方向|信心|依据|支撑|压力|失效|下一步)\s*[：:]\*\*", r"\1:", line)
    line = re.sub(r"\*\*(方向|信心|依据|支撑|压力|失效|下一步)\*\*\s*[：:]", r"\1:", line)
    line = line.replace("**", "").strip()
    return line


def _split_reason_items(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    parts = re.split(r"(?:^|\s+)(?:\d+[\.、)]\s*)|[；;]", value)
    parts = [p.strip("；;。 ") for p in parts if p.strip("；;。 ")]
    return parts if parts else [value]


def _format_level_lines(value: str, indent: str) -> list[str]:
    prices = re.findall(r"\$?\d+(?:\.\d+)?", str(value or ""))
    if prices:
        shown = []
        for price in prices[:4]:
            val = _safe_float(price.replace("$", ""))
            shown.append(_fmt_price(val) if val is not None else price)
        return [indent + " / ".join(shown)]
    return [indent + (str(value).strip() or "—")]


def _direction_label(direction: Optional[str]) -> str:
    return {"bullish": "偏多", "bearish": "偏空", "neutral": "震荡"}.get(direction or "", "—")


def _wrap(text: str, width: int = 34) -> list[str]:
    text = re.sub(r"\s+", " ", str(text)).strip()
    return textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or ["—"]


def _first_lines(text: str, max_lines: int = 5) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[:max_lines] if lines else ["无有效文本"]


def _unique_prices(values: list[Optional[float]]) -> list[float]:
    out = []
    for val in values:
        val = _round_price(val)
        if val is None:
            continue
        if all(abs(val - old) > 0.03 for old in out):
            out.append(val)
    return out


def _bar_time(bars: list[dict]) -> Optional[str]:
    if not bars:
        return None
    return bars[-1].get("time")


def _fmt_levels(values: Any) -> str:
    if not values:
        return "—"
    return " / ".join(_fmt_price(v) for v in values if v is not None)


def _fmt_ma(pack: Any) -> str:
    if not isinstance(pack, dict):
        return "—"
    return f"MA5 {_fmt_price(pack.get('ma5'))} / MA20 {_fmt_price(pack.get('ma20'))}"


def _fmt_price(value: Any) -> str:
    val = _safe_float(value)
    if val is None:
        return "—"
    return f"${val:.2f}"


def _round_price(value: Any) -> Optional[float]:
    val = _safe_float(value)
    return round(val, 4) if val is not None else None


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except (TypeError, ValueError):
        return None


def _normalize_ticker(ticker: str) -> str:
    ticker = (ticker or "RKLB").upper().strip()
    return ticker if ticker.startswith("US.") else f"US.{ticker}"


def _short(ticker: str) -> str:
    return (ticker or "").replace("US.", "")
