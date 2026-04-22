"""
════════════════════════════════════════════════════════════════════
  MagicQuant Focus — focus_manager.py
  VERSION : v0.5.9
  DATE    : 2026-04-22
  CHANGES :
    v0.5.9 (2026-04-22):
      - [FIX] 新增模块级 _indicators_cache_global,修复 /ai_test 指令
              "❌ 无法读取 Focus session 状态" 错误
              (bot_controller 需要从本模块 import 这个变量)
    v0.5.8 (2026-04-22):
      - [NEW] 接入 activity_profile v0.1.0 动态频率 + 阈值缩放
              PEAK+ 时段(巫时刻/周一开盘)0.5 秒轮询 + 阈值×0.6
              MINIMAL 时段(夜盘) 30 秒轮询 + 阈值×1.8
      - [NEW] 接入 proactive_reminder v0.1.0 黄金时段主动提醒
              开盘前 15m / 收盘前 30m / 周一前 45m / 巫日 / 巫时刻
      - [NEW] 接入 event_calendar v0.1.0 三重巫日/月度 Opex 识别
    v0.5.7 (2026-04-22):
      - [NEW] 接入 market_clock v0.2.0 的 "overnight" 状态
      - 夜盘 10 秒低频轮询,不再静默
    v0.5.6:
      - [FIX] manual_mode 参数,手动 /focus 不受休市静默影响
  DEPENDS :
    context.py            ≥ v0.5.2
    market_clock.py       ≥ v0.2.0
    event_calendar.py     ≥ v0.1.0
    activity_profile.py   ≥ v0.1.0
    proactive_reminder.py ≥ v0.1.0
    swing_detector.py     ≥ v0.5.4
    pusher.py             ≥ v0.5.11
    realtime_quote.py     ≥ v0.5.3
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

import time
import threading
import traceback
from datetime import datetime
from typing import Callable, Optional

try:
    from moomoo import KLType, AuType
except ImportError:
    from futu import KLType, AuType

from core.realtime_quote import get_client as get_quote_client

from .context import FocusSession
from .micro_indicators import calc_all_micro
from .swing_detector import run_all_triggers, diagnose_distance, DEFAULT_PARAMS as SWING_DEFAULT_PARAMS
from .pusher import format_trigger_message
from .market_clock import (
    get_market_status,
    is_market_open,
    format_market_status,
    time_until_open,
    format_time_delta,
)
from .activity_profile import (
    get_current_profile,
    scale_params,
    format_profile_line,
)
from .proactive_reminder import check_and_fire_reminders
from .event_calendar import format_event_line


FOCUS_MGR_VERSION = "v0.5.9"
FOCUS_MGR_DATE    = "2026-04-22"

# ── 全局单例 ─────────────────────────────────────────────
_current_session: Optional[FocusSession] = None
_manager_thread:  Optional[threading.Thread] = None
_stop_event = threading.Event()
_session_lock = threading.Lock()

_heartbeat_enabled = True

# v0.5.9: 模块级 indicators 缓存,供 bot_controller /ai_test 读取
_indicators_cache_global: dict = {}

# ── 参数 ─────────────────────────────────────────────────
POLL_INTERVAL_REGULAR   = 2
POLL_INTERVAL_EXTENDED  = 10
POLL_INTERVAL_CLOSED    = 60

KLINE_FETCH_INTERVAL    = 30
POSITION_FETCH_INTERVAL = 60
CASH_FETCH_INTERVAL     = 60
HEARTBEAT_INTERVAL      = 600


def set_heartbeat(on: bool) -> str:
    global _heartbeat_enabled
    _heartbeat_enabled = bool(on)
    return f"心跳已{'开启' if on else '关闭'}(每 {HEARTBEAT_INTERVAL//60} 分钟一条)"


def start_focus(master: str = "US.RKLB",
                followers: list = None,
                send_tg_fn: Callable = None,
                auto_attach_positions: bool = True,
                manual_mode: bool = False) -> str:
    """
    manual_mode=True  → 用户手动 /focus,不受休市静默影响
    manual_mode=False → 系统自动启动,休市时静默
    """
    global _current_session, _manager_thread, _stop_event

    with _session_lock:
        if _current_session is not None and _current_session.active:
            return f"⚠️ 已有盯盘运行中({_current_session.master}),请先 /unfocus"

        if followers is None:
            followers = []

        try:
            from .pairs import get_all_followers
            default_followers = get_all_followers(master)
            for tk in default_followers:
                if tk not in followers:
                    followers.append(tk)
        except Exception as e:
            print(f"  [focus] default followers load failed: {e}")

        if auto_attach_positions:
            try:
                positions = get_quote_client().fetch_positions() or {}
                for pair_candidate in ["US.RKLZ", "US.RKLX"]:
                    if pair_candidate in positions and pair_candidate not in followers:
                        followers.append(pair_candidate)
            except Exception as e:
                print(f"  [focus] auto-attach failed: {e}")

        _current_session = FocusSession(master, followers)
        _current_session.manual_mode = manual_mode   # ← 写到 session
        _stop_event = threading.Event()

        _manager_thread = threading.Thread(
            target=_focus_loop,
            args=(_current_session, send_tg_fn, _stop_event),
            daemon=True,
            name="FocusLoop"
        )
        _manager_thread.start()

    followers_str = ", ".join(f.replace("US.", "") for f in followers) or "(无跟随)"
    hb_str = f"{HEARTBEAT_INTERVAL//60}分钟" if _heartbeat_enabled else "关闭"
    mkt = format_market_status()
    manual_hint = "⚡ 手动启动模式(休市也推信号)" if manual_mode else "💡 休市时自动进入静默,开盘自动恢复"

    return (
        f"🎯 <b>已进入盯盘模式 {FOCUS_MGR_VERSION}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"主标的:  {master.replace('US.', '')}\n"
        f"跟随:    {followers_str}\n"
        f"市场:    {mkt}\n"
        f"心跳:    {hb_str}\n"
        f"\n"
        f"{manual_hint}\n"
        f"/status 查看状态  /unfocus 退出"
    )


def stop_focus() -> str:
    global _current_session, _manager_thread, _stop_event

    with _session_lock:
        if _current_session is None or not _current_session.active:
            return "当前没有运行中的盯盘"

        _stop_event.set()
        _current_session.active = False
        summary = _current_session.summary()

    if _manager_thread:
        _manager_thread.join(timeout=5)

    return f"✅ 盯盘已停止\n\n{summary}"


def get_focus_status() -> str:
    global _current_session
    mkt = format_market_status()
    prof = format_profile_line()
    ev = format_event_line()

    if _current_session is None or not _current_session.active:
        parts = ["当前没有运行中的盯盘", "", mkt, prof]
        if ev:
            parts.append(ev)
        parts += ["", "💡 /focus 启动"]
        return "\n".join(parts)

    summary = _current_session.summary()
    parts = [summary, "", mkt, prof]
    if ev:
        parts.append(ev)
    return "\n".join(parts)


def is_focused() -> bool:
    return _current_session is not None and _current_session.active


def get_current_session() -> Optional[FocusSession]:
    return _current_session


def get_version_info() -> dict:
    try:
        from .pusher import VERSION as PUSHER_V
    except ImportError:
        PUSHER_V = "?"
    try:
        from .activity_profile import __name__ as _ap  # 仅作探测
        ACTIVITY_V = "v0.1.0"
    except ImportError:
        ACTIVITY_V = "?"
    try:
        from .event_calendar import __name__ as _ec
        EVENT_V = "v0.1.0"
    except ImportError:
        EVENT_V = "?"
    try:
        from .proactive_reminder import VERSION as REMINDER_V
    except ImportError:
        REMINDER_V = "?"
    return {
        "focus_manager":       FOCUS_MGR_VERSION,
        "focus_manager_date":  FOCUS_MGR_DATE,
        "pusher":              PUSHER_V,
        "market_clock":        "v0.2.0",
        "activity_profile":    ACTIVITY_V,
        "event_calendar":      EVENT_V,
        "proactive_reminder":  REMINDER_V,
    }


def _fetch_and_update_cash(session: FocusSession, client) -> bool:
    try:
        if not hasattr(client, "fetch_account"):
            return False
        acc = client.fetch_account()
        if not acc:
            return False
        cash = power = None
        if isinstance(acc, dict):
            cash  = acc.get("cash")
            power = acc.get("power") or acc.get("buy_power") or acc.get("max_power_short")
            if cash is None and "account" in acc:
                inner = acc["account"] or {}
                cash  = inner.get("cash")
                power = power or inner.get("power") or inner.get("buy_power")
        if cash is not None:
            session.update_cash(float(cash), float(power) if power else None)
            return True
    except Exception as e:
        print(f"  [focus] fetch_cash error: {e}")
    return False


def _notify_market_change(send_tg_fn, old_status, new_status):
    if old_status == new_status:
        return
    mkt_line = format_market_status()

    if new_status == "closed":
        tu = time_until_open()
        eta = format_time_delta(tu) if tu else "?"
        msg = (
            f"🌙 <b>美股休市</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"盯盘进入静默模式(不推信号,不推心跳)\n"
            f"下次开盘约 {eta}后,届时自动恢复\n\n"
            f"{mkt_line}"
        )
    elif new_status == "regular":
        msg = (
            f"🔔 <b>美股开盘 · 恢复实时盯盘</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"{mkt_line}\n"
            f"轮询频率:2秒/次"
        )
    elif new_status == "pre":
        msg = (
            f"🟡 <b>美股盘前</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"{mkt_line}\n"
            f"低频盯盘(10秒/次),等盘中 9:30 ET"
        )
    elif new_status == "post":
        msg = (
            f"🟠 <b>美股盘后</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"{mkt_line}\n"
            f"低频盯盘(10秒/次)"
        )
    elif new_status == "overnight":
        msg = (
            f"🌃 <b>美股夜盘</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"{mkt_line}\n"
            f"低频盯盘(10秒/次)  ·  流动性差注意假信号"
        )
    else:
        return

    try:
        send_tg_fn(msg)
    except Exception as e:
        print(f"  [focus] market notify failed: {e}")


def _build_heartbeat(session: FocusSession, indicators: dict) -> str:
    master_short = session.master.replace("US.", "")
    price        = session.get_last_price(session.master)
    day_chg      = session.get_day_change_pct(session.master)
    high         = session.session_high.get(session.master)
    low          = session.session_low.get(session.master)
    quote_time   = session.get_quote_update_time(session.master) or "—"
    push_time    = datetime.now().strftime("%H:%M:%S")

    lines = [
        f"🟦 <b>盯盘心跳 · {master_short}</b>",
        f"📡 推送 {push_time}  ·  📈 行情 {quote_time[-8:] if quote_time != '—' else '—'}",
        format_market_status(),
    ]
    if price:
        line = f"现价 ${price:.2f}"
        if day_chg is not None:
            line += f"  日内 {day_chg:+.2f}%"
        lines.append(line)
    if high and low:
        lines.append(f"今日区间 ${low:.2f} ~ ${high:.2f}")

    if indicators.get("data_ok"):
        rsi  = indicators.get("rsi_5m", 50) or 50
        vwap = indicators.get("vwap",    0)  or 0
        vr   = indicators.get("vol_ratio",1) or 1
        lines.append(f"RSI {rsi:.1f}  VWAP ${vwap:.2f}  量比 {vr:.2f}x")

    diag = diagnose_distance(session, session.master, indicators)
    if diag.get("ready"):
        ds = diag.get("distances") or []
        if ds:
            lines.append("")
            lines.append("🔍 近触发:")
            for d in ds[:3]:
                lines.append(f"  · {d}")

    if session.cash_available is not None:
        lines += ["", f"💵 可用现金 ${session.cash_available:,.0f}"]

    pos_lines = []
    for tk in session.followers:
        pos = session.get_position(tk)
        if pos and pos.get("qty", 0) > 0:
            pl   = pos.get("pl_val", 0) or 0
            sign = "+" if pl >= 0 else ""
            pos_lines.append(
                f"  · {tk.replace('US.','')}: {pos['qty']:.0f}股 "
                f"{sign}${pl:.2f} ({sign}{pos.get('pl_pct',0):.2f}%)"
            )
    if pos_lines:
        lines += ["💼 持仓:"] + pos_lines

    manual_tag = "⚡手动" if getattr(session, "manual_mode", False) else ""
    runtime_min = int((time.time() - (session.first_data_ts or time.time())) / 60)
    lines.append("")
    lines.append(f"运行 {runtime_min}分 · 循环 {session.loop_count} · "
                 f"推送 {session.push_count} · 错误 {session.error_count} {manual_tag}")
    lines.append(f"\n⚙️ focus {FOCUS_MGR_VERSION}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  主循环
# ══════════════════════════════════════════════════════════════════
def _focus_loop(session: FocusSession, send_tg_fn: Callable, stop_event: threading.Event):
    print(f"  [focus] loop started for {session.master} "
          f"(manual={getattr(session, 'manual_mode', False)})")

    last_kline_fetch     = 0
    last_position_fetch  = 0
    last_cash_fetch      = 0
    last_heartbeat       = time.time()
    kline_cache          = None
    indicators_cache     = {}
    first_indicators_sent = False
    last_market_status   = None

    # ── v0.5.6 关键:读 manual_mode ──
    manual_mode = getattr(session, "manual_mode", False)

    client = get_quote_client()

    try:
        send_tg_fn(f"🎯 盯盘循环已启动 · {session.master.replace('US.','')}\n"
                   f"{format_market_status()}")
    except:
        pass

    while not stop_event.is_set():
        t_loop_start = time.time()
        session.loop_count += 1

        market_status = get_market_status()
        if market_status != last_market_status:
            if last_market_status is not None:
                _notify_market_change(send_tg_fn, last_market_status, market_status)
            last_market_status = market_status
            session.market_status = market_status

        # ── v0.5.6 静默逻辑:manual_mode 下绕过 ──
        if market_status == "closed" and not manual_mode:
            sleep_for = POLL_INTERVAL_CLOSED
            if stop_event.wait(timeout=sleep_for):
                break
            continue

        try:
            all_tickers = [session.master] + session.followers
            quotes = client.fetch_many(all_tickers)
            for tk, q in quotes.items():
                if q:
                    session.update_price(tk, q["price"])
                    session.update_quote(tk, q)

            now = time.time()

            if now - last_kline_fetch >= KLINE_FETCH_INTERVAL:
                kline_cache = _fetch_5m_kline(client, session.master)
                last_kline_fetch = now

            current_master_price = session.get_last_price(session.master)
            if kline_cache is not None and current_master_price:
                indicators_cache = calc_all_micro(kline_cache, current_master_price)
                # v0.5.9: 同步到全局,供 /ai_test 使用
                global _indicators_cache_global
                _indicators_cache_global = indicators_cache or {}

            if now - last_position_fetch >= POSITION_FETCH_INTERVAL:
                positions = client.fetch_positions()
                if positions is not None:
                    session.update_positions(positions)
                last_position_fetch = now

            if now - last_cash_fetch >= CASH_FETCH_INTERVAL:
                _fetch_and_update_cash(session, client)
                last_cash_fetch = now

            # ── v0.5.8: 获取当前机会密度画像 ──────────────────
            profile = get_current_profile()
            session.activity_profile = profile   # 让 pusher/status 能读到

            # 按 profile.scale 缩放触发器参数
            scaled_params = scale_params(SWING_DEFAULT_PARAMS, profile["scale"]) \
                            if profile["scale"] is not None else SWING_DEFAULT_PARAMS

            hits = run_all_triggers(
                session, session.master, session.followers,
                indicators_cache or {},
                params=scaled_params,
            )

            for hit in hits:
                try:
                    msg = format_trigger_message(hit, session)
                    if send_tg_fn:
                        send_tg_fn(msg["text"], buttons=msg.get("buttons"))
                        session.push_count += 1
                except Exception as e:
                    print(f"  [focus] push error: {e}")
                    session.error_count += 1

            # ── v0.5.8: 主动提醒(每天每个提醒点仅推一次) ──
            try:
                check_and_fire_reminders(session, send_tg_fn)
            except Exception as e:
                print(f"  [focus] reminder error: {e}")

            if (not first_indicators_sent
                    and indicators_cache
                    and indicators_cache.get("data_ok")):
                first_indicators_sent = True
                try:
                    send_tg_fn(_build_heartbeat(session, indicators_cache))
                    last_heartbeat = now
                except:
                    pass

            if _heartbeat_enabled and (now - last_heartbeat) >= HEARTBEAT_INTERVAL:
                try:
                    send_tg_fn(_build_heartbeat(session, indicators_cache or {}))
                    last_heartbeat = now
                except Exception as e:
                    print(f"  [focus] heartbeat error: {e}")

        except Exception as e:
            session.error_count += 1
            print(f"  [focus] loop error: {e}")
            traceback.print_exc()
            if session.error_count % 5 == 0:
                time.sleep(5)

        # ── v0.5.8: 轮询频率由 profile 决定 ──
        # profile.poll_sec 已综合时段 + 事件日 + 周一加速
        try:
            interval = profile["poll_sec"]
        except (NameError, KeyError, TypeError):
            # profile 异常时的兜底(第一轮或出错)
            if market_status == "regular":
                interval = POLL_INTERVAL_REGULAR
            elif market_status in ("pre", "post", "overnight"):
                interval = POLL_INTERVAL_EXTENDED
            else:
                interval = POLL_INTERVAL_EXTENDED

        elapsed   = time.time() - t_loop_start
        sleep_for = max(0.5, interval - elapsed)
        if stop_event.wait(timeout=sleep_for):
            break

    print(f"  [focus] loop stopped")
    try:
        send_tg_fn(f"✅ 盯盘循环已停止 · 共运行 {session.loop_count} 轮")
    except:
        pass


def _fetch_5m_kline(client, ticker: str, num: int = 30):
    try:
        if not client._ensure_quote():
            return None
        with client._quote_lock:
            ret, kl = client._quote_ctx.get_cur_kline(
                ticker, num, KLType.K_5M, AuType.QFQ
            )
        if ret == 0 and kl is not None and len(kl) > 0:
            return kl
        return None
    except Exception as e:
        print(f"  [focus] kline fetch error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
#  v0.3 / v0.4 兼容 stub
# ══════════════════════════════════════════════════════════════════
HAS_AI_ADVISOR     = False
HAS_MANUAL_CONSULT = False
HAS_HEARTBEAT      = True

def set_ai_advise(on: bool = True):
    return "ℹ️ AI Advisor 在 v0.5 已被手动触发取代"

def is_ai_advise_enabled():
    return False

def manual_consult(*args, **kwargs):
    return "ℹ️ Manual Consult 在 v0.5 未启用,请用 /detail"

def get_heartbeat_text():
    global _current_session
    if _current_session is None or not _current_session.active:
        return "🟦 当前没有运行中的盯盘,用 /focus 启动"
    return _current_session.summary()

def start_heartbeat_loop(send_tg_fn=None, interval_min: int = 10):
    global HEARTBEAT_INTERVAL
    HEARTBEAT_INTERVAL = max(60, int(interval_min) * 60)
    set_heartbeat(True)
    return f"✅ 盯盘心跳已开启,每 {interval_min} 分钟"

def stop_heartbeat_loop():
    set_heartbeat(False)
    return "✅ 盯盘心跳已关闭(信号触发仍推送)"

def is_heartbeat_enabled():
    return _heartbeat_enabled

def get_heartbeat_interval():
    return HEARTBEAT_INTERVAL // 60

def verify_trigger(trigger_id, send_tg_fn=None, auto_retry_sec: int = 30):
    return "ℹ️ Trigger 验证在 v0.5 已改用 focus_order_ 按钮体系"

def mark_ignored(trigger_id):
    return "👌 已忽略"

def recompute_price(trigger_id):
    return "ℹ️ 重算价格在 v0.5 自动完成"

def is_us_market_open() -> bool:
    return is_market_open(strict=False)
