"""
MagicQuant Focus - position_followup.py
VERSION : v0.5.36
DATE    : 2026-05-24
DEPENDS : core.focus.context, core.focus.swing_detector target state
CHANGES :
  v0.5.36:
    - [NEW] Position follow-up state machine for held positions.
      [中文] 持仓后的状态跟进,用成本回测/ATR 失效位替代零散止盈止损噪音。
"""

from __future__ import annotations

import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


MANAGED_EXIT_TRIGGERS = {
    "drawdown_from_peak",
    "profit_target_hit",
    "overbought_surge",
    "near_resistance",
    "near_support",
    "large_day_gain",
}


def _position_signature(session, ticker: str, pos: dict):
    fn = getattr(session, "_position_signature_from_pos", None)
    if callable(fn):
        return fn(pos)
    qty = round(float(pos.get("qty") or 0), 4)
    cost = round(float(pos.get("cost_price") or 0), 4)
    return (qty, cost)


def _ensure_state(session):
    if not hasattr(session, "_position_followup_state"):
        session._position_followup_state = {}
    if not hasattr(session, "_position_followup_done"):
        session._position_followup_done = {}
    return session._position_followup_state, session._position_followup_done


def _target_state(session, ticker: str) -> dict:
    return ((getattr(session, "_target_state", {}) or {}).get(ticker) or {})


def _data_untrusted(session) -> Optional[str]:
    quality = getattr(session, "_last_data_quality", None)
    if not isinstance(quality, dict):
        return None
    if quality.get("ok") is False:
        return quality.get("reason") or quality.get("level") or "data_quality_gate"
    return None


def _record_followup(session, hit: dict) -> None:
    """Best-effort audit log for held-position follow-up quality review."""
    try:
        base_dir = Path(__file__).resolve().parents[2]
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = base_dir / "data" / "review" / date_str / "position_followup.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = hit.get("data", {}) or {}
        row = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "ticker": hit.get("ticker"),
            "state": data.get("state"),
            "qty": data.get("qty"),
            "cost": data.get("cost"),
            "current": data.get("current"),
            "pl_val": data.get("pl_val"),
            "pl_pct": data.get("pl_pct"),
            "stop": data.get("stop"),
            "t1": data.get("t1"),
            "reason": data.get("reason"),
            "adverse_pct": data.get("adverse_pct"),
            "rebound_pct": data.get("rebound_pct"),
        }
        rows = []
        if path.exists():
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                rows = []
        if not isinstance(rows, list):
            rows = []
        rows.append(row)
        path.write_text(json.dumps(rows[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _emit(session, hit: dict):
    _record_followup(session, hit)
    return hit


def _price_rebound_from_trough(session, ticker: str, current: float) -> Optional[float]:
    trough = (getattr(session, "trough_price", {}) or {}).get(ticker)
    if not trough or trough <= 0:
        return None
    return (current - trough) / trough * 100.0


def _adverse_from_cost(session, ticker: str, cost: float) -> Optional[float]:
    trough = (getattr(session, "trough_price", {}) or {}).get(ticker)
    if not trough or trough <= 0 or cost <= 0:
        return None
    return (cost - trough) / cost * 100.0


def _recent_top_warning_for(session, ticker: str, window_sec: int = 600) -> Optional[str]:
    """Read whatever swing_detector wrote into session._last_top_warning_ts. / 读顶部风险时间戳。"""
    try:
        state = getattr(session, "_last_top_warning_ts", {}) or {}
        info = state.get(ticker) or {}
        ts = float(info.get("ts") or 0)
        if ts > 0 and (time.time() - ts) < window_sec:
            return info.get("trigger") or "top_warning"
    except Exception:
        pass
    return None


def _top_watch_reasons(session, ticker: str, indicators, target: dict, current: float) -> list:
    """v0.5.36: 持仓后波顶观察的可能原因(任一即可)。规格见 CLAUDE_PLAN holding_followup §P0.2。"""
    reasons = []
    recent = _recent_top_warning_for(session, ticker, window_sec=600)
    if recent:
        reasons.append(f"recent_{recent}")
    if isinstance(indicators, dict):
        try:
            rsi = float(indicators.get("rsi_5m") or 0)
            vwap = float(indicators.get("vwap") or 0)
            atr = float(target.get("atr") or 0) or 0.0
            if rsi >= 70 and vwap > 0 and atr > 0 and current >= vwap + 1.5 * atr:
                reasons.append("rsi_high_and_far_above_vwap")
        except (TypeError, ValueError):
            pass
    # 近 3 根 5m bar 高点不抬升 + 本波涨幅 ≥ 1.5%
    try:
        kl = getattr(session, "_last_kline_cache", None)
        if kl is not None and hasattr(kl, "tail"):
            tail = kl.tail(4)
            if len(tail) >= 4:
                highs = tail["high"].astype(float).tolist()
                closes = tail["close"].astype(float).tolist()
                # 后 3 根 high 不创新高
                if highs[-1] <= highs[-2] and highs[-2] <= highs[-3]:
                    if closes[-1] > 0 and closes[0] > 0 and (closes[-1] - closes[0]) / closes[0] * 100 >= 1.5:
                        reasons.append("lower_highs_after_rally")
    except Exception:
        pass
    return reasons


def _bars_bearish(session, indicators) -> bool:
    bars = []
    if isinstance(indicators, dict):
        bars = indicators.get("bars")
        if bars is None:
            bars = indicators.get("kline_data")
    if bars is None or (hasattr(bars, "__len__") and len(bars) == 0):
        bars = getattr(session, "_last_kline_cache", None)
    if bars is None:
        bars = []
    if hasattr(bars, "tail"):
        try:
            bars = bars.tail(3).to_dict("records")
        except Exception:
            bars = []
    if len(bars) < 3:
        return False
    closes = []
    for bar in bars[-3:]:
        if isinstance(bar, dict):
            closes.append(float(bar.get("close") or 0))
        else:
            close = getattr(bar, "close", None)
            closes.append(float(close or 0))
    closes = [v for v in closes if v > 0]
    if len(closes) < 3:
        return False
    vwap = None
    if isinstance(indicators, dict):
        vwap = indicators.get("vwap")
    if not vwap:
        return closes[-1] < closes[-2] < closes[-3]
    return closes[-1] < vwap and closes[-1] < closes[-2]


def check_position_followup(session, ticker: str, indicators=None, params=None):
    """Return a single held-position follow-up hit. / 返回一个持仓跟进状态。"""
    pos = session.get_position(ticker) if hasattr(session, "get_position") else None
    if not pos or (pos.get("qty", 0) or 0) <= 0:
        return None

    qty = int(pos.get("qty") or 0)
    cost = float(pos.get("cost_price") or 0)
    current = float(session.get_last_price(ticker) or pos.get("current_price") or 0)
    if qty <= 0 or cost <= 0 or current <= 0:
        return None

    state, done = _ensure_state(session)
    sig = _position_signature(session, ticker, pos)
    key = f"{ticker}:{sig}"
    if state.get(ticker) != sig:
        state[ticker] = sig
        for old in list(done.keys()):
            if old.startswith(f"{ticker}:"):
                done.pop(old, None)

    pl_val = float(pos.get("pl_val") or 0)
    pl_pct = float(pos.get("pl_pct") or ((current - cost) / cost * 100.0))
    target = _target_state(session, ticker)
    stop = target.get("stop")
    t1 = target.get("t1")
    adverse_pct = _adverse_from_cost(session, ticker, cost)
    rebound_pct = _price_rebound_from_trough(session, ticker, current)
    cost_gap_pct = abs(current - cost) / cost * 100.0
    hold_sec = session.get_position_age_sec(ticker) if hasattr(session, "get_position_age_sec") else None

    data_reason = _data_untrusted(session)
    if data_reason:
        cool_key = f"position_followup_data_{ticker}"
        if session.can_trigger(cool_key, cooldown_sec=1800):
            session.mark_triggered(cool_key)
            return _emit(session, _hit(
                ticker, "DATA_UNTRUSTED", qty, cost, current, pl_val, pl_pct,
                stop=stop, t1=t1, hold_sec=hold_sec,
                reason=data_reason, adverse_pct=adverse_pct, rebound_pct=rebound_pct,
            ))
        return None

    if stop and current <= float(stop):
        cool_key = f"position_followup_invalidated_{ticker}"
        if session.can_trigger(cool_key, cooldown_sec=600):
            session.mark_triggered(cool_key)
            return _emit(session, _hit(
                ticker, "INVALIDATED", qty, cost, current, pl_val, pl_pct,
                stop=stop, t1=t1, hold_sec=hold_sec,
                reason="price_below_atr_stop", adverse_pct=adverse_pct,
                rebound_pct=rebound_pct,
            ))
        return None

    retest_key = f"{key}:cost_retest"
    if (
        adverse_pct is not None and adverse_pct >= 1.5
        and cost_gap_pct <= 0.5
        and rebound_pct is not None and rebound_pct >= 0.8
        and not done.get(retest_key)
    ):
        done[retest_key] = time.time()
        session.mark_triggered(f"position_followup_cost_retest_{ticker}")
        return _emit(session, _hit(
            ticker, "COST_RETEST", qty, cost, current, pl_val, pl_pct,
            stop=stop, t1=t1, hold_sec=hold_sec, reason="cost_retest_after_adverse_move",
            adverse_pct=adverse_pct, rebound_pct=rebound_pct,
        ))

    # v0.5.36 hotfix: 结构性失效不再硬要求"必须经过 COST_RETEST"。
    # 持仓浮亏且 5m 结构破位即视为失效;先前经过 retest 的标记为 cost_retest_failed,
    # 否则标 structural_breakdown,以便复盘区分。
    if (
        current < cost
        and adverse_pct is not None and adverse_pct >= 1.5
        and _bars_bearish(session, indicators)
    ):
        cool_key = f"position_followup_invalidated_{ticker}"
        if session.can_trigger(cool_key, cooldown_sec=600):
            session.mark_triggered(cool_key)
            reason = "cost_retest_failed" if done.get(retest_key) else "structural_breakdown"
            return _emit(session, _hit(
                ticker, "INVALIDATED", qty, cost, current, pl_val, pl_pct,
                stop=stop, t1=t1, hold_sec=hold_sec,
                reason=reason, adverse_pct=adverse_pct,
                rebound_pct=rebound_pct,
            ))

    # v0.5.36 hotfix: TOP_WATCH —— 持仓接近顶/动能放缓,接管被压制的 near_resistance 等。
    # 每"价格带"最多一次(整数美元做带),30 分钟冷却,只在持仓时工作。
    top_reasons = _top_watch_reasons(session, ticker, indicators, target, current)
    if top_reasons:
        band = int(current)
        cool_key = f"top_watch_{ticker}_{band}"
        if session.can_trigger(cool_key, cooldown_sec=1800):
            session.mark_triggered(cool_key)
            return _emit(session, _hit(
                ticker, "TOP_WATCH", qty, cost, current, pl_val, pl_pct,
                stop=stop, t1=t1, hold_sec=hold_sec,
                reason=";".join(top_reasons), adverse_pct=adverse_pct,
                rebound_pct=rebound_pct,
            ))

    return None


def _hit(ticker, state, qty, cost, current, pl_val, pl_pct, **extra):
    return {
        "trigger": "position_followup",
        "level": "WARN" if state != "INVALIDATED" else "URGENT",
        "style": "A",
        "ticker": ticker,
        "direction": "neutral",
        "strength": "STRONG" if state == "INVALIDATED" else "WEAK",
        "title": f"{ticker.replace('US.', '')} 持仓跟进 · {state}",
        "data": {
            "state": state,
            "qty": qty,
            "cost": cost,
            "current": current,
            "pl_val": pl_val,
            "pl_pct": pl_pct,
            **extra,
        },
    }
