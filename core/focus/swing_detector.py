"""
════════════════════════════════════════════════════════════════════
  MagicQuant Focus — swing_detector.py
  VERSION : v0.5.4
  DATE    : 2026-04-22
  CHANGES :
    - [FIX] 推送频率大幅降低:
          direction_trend:  10分钟 → 20分钟
          rapid_move:        3分钟 → 10分钟
          swing WEAK:       10分钟 → 15分钟
          swing STRONG:      7分钟 → 10分钟
    - [NEW] 全局互斥 60 秒:任何信号推过后,60s 内不再推任何信号
    - [FIX] 所有触发器冷却 key 立刻 mark_triggered,防止同秒双推
  DEPENDS :
    context.py ≥ v0.5.2  (last_any_trigger_ts 字段)
    pairs.py   any
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

import time
from typing import Optional


DEFAULT_PARAMS = {
    "profit_target_pct":    1.5,
    "profit_target_usd":    30.0,
    "drawdown_pct":         0.8,

    # 快速异动:冷却从 3 分钟 → 10 分钟
    "rapid_move_pct":       0.4,
    "rapid_move_window":    120,
    "rapid_move_cooldown":  600,     # ← 10 分钟

    "rsi_overbought_strong": 65,
    "rsi_oversold_strong":   40,
    "rsi_overbought_weak":   58,
    "rsi_oversold_weak":     48,

    "near_high_pct_strong": -0.8,
    "near_high_pct_weak":   -1.5,
    "near_low_pct_strong":   0.8,
    "near_low_pct_weak":     1.5,

    # 方向信号:10 分钟 → 20 分钟
    "trend_day_change_pct":  0.8,
    "trend_rsi_long":        52,
    "trend_rsi_short":       48,
    "trend_cooldown_sec":    1200,   # ← 20 分钟

    # 波段信号:WEAK 15 分钟,STRONG 10 分钟
    "swing_cooldown_weak":   900,    # ← 15 分钟
    "swing_cooldown_strong": 600,    # ← 10 分钟

    # v0.5.4 新增:全局互斥(session 级别)
    "global_mutex_sec":      60,     # 任何推送后 60s 内不再推
}


# ══════════════════════════════════════════════════════════════════
#  全局互斥 — v0.5.4 新增
# ══════════════════════════════════════════════════════════════════
def _global_mutex_ok(session, mutex_sec: int = 60) -> bool:
    """
    检查距离上次推送是否超过 mutex_sec 秒
    每次任何信号触发成功(调 mark_triggered)时,session.trigger_count 加 1
    我们用 session.last_any_trigger_ts 作为全局闸门
    """
    last_ts = getattr(session, "last_any_trigger_ts", 0) or 0
    return (time.time() - last_ts) >= mutex_sec


def _mark_global_triggered(session):
    """任何一条信号推送后调用,启动全局互斥计时"""
    session.last_any_trigger_ts = time.time()


# ══════════════════════════════════════════════════════════════════
#  触发器
# ══════════════════════════════════════════════════════════════════
def check_profit_target(session, ticker, params=None):
    params = params or DEFAULT_PARAMS
    pos = session.get_position(ticker)
    if not pos or pos.get("qty", 0) <= 0:
        return None

    pl_pct = pos.get("pl_pct", 0) or 0
    pl_val = pos.get("pl_val", 0) or 0

    if pl_val >= params["profit_target_usd"] or pl_pct >= params["profit_target_pct"]:
        cool_key = f"profit_target_{ticker}"
        if not session.can_trigger(cool_key, cooldown_sec=300):
            return None
        session.mark_triggered(cool_key)

        qty = pos.get("qty", 0)
        cost = pos.get("cost_price", 0)
        current = session.get_last_price(ticker) or pos.get("current_price", 0)
        sell_price = round(current * 1.003, 2)

        return {
            "trigger": "profit_target_hit", "level": "URGENT", "style": "A",
            "ticker": ticker, "direction": "neutral",
            "strength": "STRONG" if pl_val >= 100 else "WEAK",
            "data": {
                "qty": qty, "cost": cost, "current": current,
                "pl_val": pl_val, "pl_pct": pl_pct,
                "sell_half_qty": int(qty / 2),
                "sell_price_half": sell_price,
                "stop_upgrade_to": round(cost * 1.002, 2),
            },
            "title": f"💰 {ticker.replace('US.','')} 浮盈达标",
        }
    return None


def check_drawdown_from_peak(session, ticker, params=None):
    params = params or DEFAULT_PARAMS
    drawdown = session.get_peak_drawdown_pct(ticker)
    if drawdown is None:
        return None

    if drawdown <= -params["drawdown_pct"]:
        cool_key = f"drawdown_{ticker}"
        if not session.can_trigger(cool_key, cooldown_sec=300):
            return None
        session.mark_triggered(cool_key)

        return {
            "trigger": "drawdown_from_peak", "level": "WARN", "style": "B",
            "ticker": ticker, "direction": "neutral", "strength": "STRONG",
            "data": {
                "current": session.get_last_price(ticker),
                "peak": session.peak_price.get(ticker),
                "drawdown_pct": drawdown,
                "position": session.get_position(ticker),
            },
            "title": f"🚨 {ticker.replace('US.','')} 高位回撤 {drawdown:.2f}%",
        }
    return None


def check_swing_top(session, ticker, indicators, params=None):
    params = params or DEFAULT_PARAMS
    if not indicators.get("data_ok"):
        return None

    rsi = indicators.get("rsi_5m", 50) or 50
    candle = indicators.get("candle") or {}
    vol_ratio = indicators.get("vol_ratio", 1) or 1
    dist_high = indicators.get("dist_high", 0) or 0

    cond_rsi_strong  = rsi >= params["rsi_overbought_strong"]
    cond_rsi_weak    = rsi >= params["rsi_overbought_weak"]
    cond_candle      = candle.get("type") == "bearish"
    cond_near_high_s = dist_high >= params["near_high_pct_strong"]
    cond_near_high_w = dist_high >= params["near_high_pct_weak"]

    if cond_rsi_strong and cond_candle and cond_near_high_s:
        strength, level, cd = "STRONG", "URGENT", params["swing_cooldown_strong"]
    elif sum([cond_rsi_weak, cond_candle, cond_near_high_w]) >= 2:
        strength, level, cd = "WEAK", "WARN", params["swing_cooldown_weak"]
    else:
        return None

    cool_key = f"swing_top_{ticker}_{strength}"
    if not session.can_trigger(cool_key, cooldown_sec=cd):
        return None
    session.mark_triggered(cool_key)

    return {
        "trigger": "swing_top", "level": level, "style": "B", "ticker": ticker,
        "direction": "short", "strength": strength,
        "data": {
            "rsi": rsi, "candle": candle, "vol_ratio": vol_ratio, "dist_high": dist_high,
            "session_high": indicators.get("session_high"),
            "current": session.get_last_price(ticker),
            "day_change_pct": _get_day_change(session, ticker),
            "cond_rsi": cond_rsi_weak, "cond_candle": cond_candle, "cond_near": cond_near_high_w,
        },
        "title": f"🔴 {ticker.replace('US.','')} 波段顶信号 [{strength}]",
    }


def check_swing_bottom(session, ticker, indicators, params=None):
    params = params or DEFAULT_PARAMS
    if not indicators.get("data_ok"):
        return None

    rsi = indicators.get("rsi_5m", 50) or 50
    candle = indicators.get("candle") or {}
    vol_ratio = indicators.get("vol_ratio", 1) or 1
    dist_low = indicators.get("dist_low", 0) or 0

    cond_rsi_strong = rsi <= params["rsi_oversold_strong"]
    cond_rsi_weak   = rsi <= params["rsi_oversold_weak"]
    cond_candle     = candle.get("type") == "bullish"
    cond_near_low_s = dist_low <= params["near_low_pct_strong"]
    cond_near_low_w = dist_low <= params["near_low_pct_weak"]

    if cond_rsi_strong and cond_candle and cond_near_low_s:
        strength, level, cd = "STRONG", "URGENT", params["swing_cooldown_strong"]
    elif sum([cond_rsi_weak, cond_candle, cond_near_low_w]) >= 2:
        strength, level, cd = "WEAK", "WARN", params["swing_cooldown_weak"]
    else:
        return None

    cool_key = f"swing_bottom_{ticker}_{strength}"
    if not session.can_trigger(cool_key, cooldown_sec=cd):
        return None
    session.mark_triggered(cool_key)

    return {
        "trigger": "swing_bottom", "level": level, "style": "B", "ticker": ticker,
        "direction": "long", "strength": strength,
        "data": {
            "rsi": rsi, "candle": candle, "vol_ratio": vol_ratio, "dist_low": dist_low,
            "session_low": indicators.get("session_low"),
            "current": session.get_last_price(ticker),
            "day_change_pct": _get_day_change(session, ticker),
            "cond_rsi": cond_rsi_weak, "cond_candle": cond_candle, "cond_near": cond_near_low_w,
        },
        "title": f"🟢 {ticker.replace('US.','')} 波段底信号 [{strength}]",
    }


def check_direction_trend(session, ticker, indicators, params=None):
    params = params or DEFAULT_PARAMS

    day_chg = _get_day_change(session, ticker)
    if day_chg is None:
        return None

    has_indicators = bool(indicators and indicators.get("data_ok"))
    rsi = indicators.get("rsi_5m", 50) if has_indicators else 50

    if day_chg >= params["trend_day_change_pct"]:
        if has_indicators and rsi < params["trend_rsi_long"]:
            return None
        direction, emoji, word = "long", "🚀", "看多"
    elif day_chg <= -params["trend_day_change_pct"]:
        if has_indicators and rsi > params["trend_rsi_short"]:
            return None
        direction, emoji, word = "short", "📉", "看空"
    else:
        return None

    strength = "STRONG" if abs(day_chg) >= 1.5 else "WEAK"

    cool_key = f"trend_{direction}_{ticker}"
    if not session.can_trigger(cool_key, cooldown_sec=params["trend_cooldown_sec"]):
        return None
    session.mark_triggered(cool_key)

    return {
        "trigger": "direction_trend",
        "level": "WARN" if strength == "STRONG" else "INFO",
        "style": "B", "ticker": ticker,
        "direction": direction, "strength": strength,
        "data": {
            "day_change_pct": day_chg, "rsi": rsi,
            "vol_ratio": indicators.get("vol_ratio", 1) if has_indicators else 1,
            "vwap": indicators.get("vwap", 0) if has_indicators else 0,
            "current": session.get_last_price(ticker),
            "session_high": indicators.get("session_high") if has_indicators else None,
            "session_low":  indicators.get("session_low")  if has_indicators else None,
            "has_indicators": has_indicators,
        },
        "title": f"{emoji} {ticker.replace('US.','')} 方向信号({word} {day_chg:+.2f}%)",
    }


def check_rapid_move(session, ticker, params=None):
    params = params or DEFAULT_PARAMS
    chg = session.get_price_change_pct(ticker, params["rapid_move_window"])
    if chg is None:
        return None

    if abs(chg) >= params["rapid_move_pct"]:
        direction_key = "up" if chg > 0 else "down"
        cool_key = f"rapid_{ticker}_{direction_key}"
        if not session.can_trigger(cool_key, cooldown_sec=params["rapid_move_cooldown"]):
            return None
        session.mark_triggered(cool_key)

        direction_word = "急涨" if chg > 0 else "急跌"
        return {
            "trigger": "rapid_move", "level": "INFO", "style": "C",
            "ticker": ticker,
            "direction": "long" if chg > 0 else "short",
            "strength": "WEAK",
            "data": {
                "change_pct": chg,
                "window_sec": params["rapid_move_window"],
                "current": session.get_last_price(ticker),
                "direction": direction_word,
            },
            "title": f"⚡ {ticker.replace('US.','')} {direction_word} {chg:+.2f}%",
        }
    return None


def _get_day_change(session, ticker):
    if hasattr(session, "get_day_change_pct"):
        return session.get_day_change_pct(ticker)
    q = getattr(session, "quote_snapshot", {}).get(ticker)
    return q.get("change_pct") if q else None


def diagnose_distance(session, ticker, indicators, params=None):
    params = params or DEFAULT_PARAMS
    day_chg = _get_day_change(session, ticker)

    has_ind = bool(indicators and indicators.get("data_ok"))
    rsi = indicators.get("rsi_5m", 50) if has_ind else None

    distances = []
    if day_chg is not None:
        if day_chg > 0:
            gap = params["trend_day_change_pct"] - day_chg
            if gap <= 0:
                distances.append(f"🚀 看多已满足 (日内 {day_chg:+.2f}%)")
            elif gap <= 0.3:
                distances.append(f"⏳ 看多差 {gap:.2f}% (日内 {day_chg:+.2f}%)")
        else:
            gap = params["trend_day_change_pct"] - abs(day_chg)
            if gap <= 0:
                distances.append(f"📉 看空已满足 (日内 {day_chg:+.2f}%)")
            elif gap <= 0.3:
                distances.append(f"⏳ 看空差 {gap:.2f}% (日内 {day_chg:+.2f}%)")

    if rsi is not None:
        gap_top = params["rsi_overbought_weak"] - rsi
        if 0 < gap_top <= 3:
            distances.append(f"RSI 差 {gap_top:.1f} 到超买")
        gap_bot = rsi - params["rsi_oversold_weak"]
        if 0 < gap_bot <= 3:
            distances.append(f"RSI 差 {gap_bot:.1f} 到超卖")

    return {
        "ready": True, "rsi": rsi, "day_chg": day_chg,
        "dist_high": indicators.get("dist_high") if has_ind else None,
        "dist_low":  indicators.get("dist_low")  if has_ind else None,
        "distances": distances, "has_indicators": has_ind,
    }


# ══════════════════════════════════════════════════════════════════
#  主调度 — v0.5.4 加全局互斥
# ══════════════════════════════════════════════════════════════════
def run_all_triggers(session, master_ticker, followers, indicators, params=None):
    params = params or DEFAULT_PARAMS

    # ── v0.5.4 全局互斥 — 60 秒内任何信号推过就静默 ──
    if not _global_mutex_ok(session, params["global_mutex_sec"]):
        return []

    hits = []

    trend_hit = check_direction_trend(session, master_ticker, indicators, params)
    if trend_hit:
        hits.append(trend_hit)

    if indicators.get("data_ok"):
        for fn in (check_swing_top, check_swing_bottom):
            h = fn(session, master_ticker, indicators, params)
            if h:
                hits.append(h)

    master_rapid = check_rapid_move(session, master_ticker, params)
    if master_rapid:
        hits.append(master_rapid)

    master_dir = None
    if master_rapid:
        master_dir = master_rapid["direction"]
    elif trend_hit:
        master_dir = trend_hit["direction"]

    for tk in followers:
        fh = check_rapid_move(session, tk, params)
        if fh:
            if master_dir and _is_linked(tk, fh["direction"], master_ticker, master_dir):
                continue
            hits.append(fh)

    for tk in followers:
        for fn in (check_profit_target, check_drawdown_from_peak):
            h = fn(session, tk, params)
            if h:
                hits.append(h)

    level_order    = {"URGENT": 0, "WARN": 1, "INFO": 2}
    strength_order = {"STRONG": 0, "WEAK": 1}
    hits.sort(key=lambda h: (
        level_order.get(h.get("level"), 3),
        strength_order.get(h.get("strength"), 2),
    ))

    # ── 关键!只推第一条,其他压后 ──
    # 这样配合全局互斥 = 每 60 秒最多推 1 条
    if hits:
        _mark_global_triggered(session)
        return [hits[0]]   # ← 只推最优先那条

    return []


def _is_linked(follower, follower_dir, master, master_dir):
    try:
        from .pairs import classify_follower
        role = classify_follower(master, follower)
        if role == "long":
            return follower_dir == master_dir
        if role == "short":
            return follower_dir != master_dir
    except Exception:
        pass
    return False
