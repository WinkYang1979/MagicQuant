"""
════════════════════════════════════════════════════════════════════
  MagicQuant Focus — focus_manager.py
  VERSION : v0.5.27
  DATE    : 2026-05-12
  CHANGES :
    v0.5.27 (2026-05-12):
      - [FIX] 开盘后 50 min has_indicators=False 黄金时段失明根治:
              根因: v0.5.18 ET 当日过滤 + micro_indicators >=10 根门槛 互锁
                    开盘头 50 min 当日 K < 10 根 → 所有指标走 default 兜底
                    RSI/vol_ratio 本是滚动 N 周期统计,跨日反而稳,被错杀
              修复 _fetch_5m_kline: 不再缩减 DataFrame, 只写 attrs.et_today
                    + attrs.has_today_data, 由 calc_all_micro 分指标过滤
              配套修改 micro_indicators.calc_all_micro:
                · RSI/vol_ratio/candle 用全量 K (含昨日尾盘,≥15 根即可用)
                · VWAP/session_high/low 用当日子集 (<3 根回退 current_price)
                · 新增 vwap_ok 字段,is_today 语义保留
              效果: 09:30 开盘瞬间 RSI/vol_ratio 立刻可用, no_indicators
                    告警不再因开盘 50 min 空窗误推
    v0.5.22 (2026-05-12):
      - [NEW] 关键错误 Telegram 告警（不推普通 kline fetch error）:
              · Futu 连接失败（含 "128" / "Context status bad"）
              · K 线订阅失败（subscribe ret != 0）
              · has_indicators 持续 10 分钟 False
              · 连续 5 次 loop error（consecutive_errors 计数，成功即重置）
              格式: ⚠️ 系统警告 / [类型] 详情 / 时间: HH:MM
              同类告警 15 min 内不重复推（_tg_warn_last 节流）
              _push_system_warning() 函数 + _send_tg_ref 模块级引用
    v0.5.21 (2026-05-11):
      - [NEW] 共享市场快照输出: _write_shared_market_snapshot()
              每轮主循环按市场时段节流写入 data/shared/market_snapshot.json
              先写 .tmp 再原子替换(os.replace),防止读到半截 JSON
              包含 quotes / account / positions / indicators / last_signal / focus 状态
              写失败只打 warning,不影响盯盘主循环
      - [NEW] _snapshot_throttle_sec(): PEAK=5s/HIGH=10s/MEDIUM=15s/LOW=30s/CLOSED=60s
      - [NEW] _build_last_signal(): hit dict → last_signal schema 字段
    v0.5.20 (2026-05-09):
      - [NEW] 趋势锁定机制 (TrendLock):
              direction_trend STRONG 同向连续 3 次 → 锁定
              锁定推送"趋势锁定"消息: 方向/日内涨幅/目标价
              目标价: 整十关口 + ATR×1.5/2.0/3.0 三档
              日内涨幅从峰值回落 >3% → 解锁推送解除消息
              锁定期间:
                trend_lock=long  → swing_top + direction_trend short 静默
                trend_lock=short → swing_bottom + direction_trend long  静默
              helper: _calc_atr / _calc_trend_targets /
                      _fmt_trend_lock_msg / _fmt_trend_unlock_msg
    v0.5.19 (2026-05-09):
      - [FIX] K 线冻结第三次根治：
              根因 D: vol_sum 冻结检测有误报——两次轮询落在同一根 5m 柱内时
                      vol_sum 天然不变，误触重订阅，若重订阅失败则陷入死循环
              根因 E: 重订阅只清 _kl_subscribed 但不重建 _quote_ctx，
                      TCP 层推送流静默冻结时重订阅同一连接完全无效
              修复 D: 用 last_bar_time_key 取代 vol_sum 做冻结判断；
                      仅当 "最后一根柱的 time_key 连续 3 次不变
                      且市场处于交易时段" 才判定为冻结（消除误报）
              修复 E: 冻结确认后调用 client.reconnect_quote() 强制重建
                      OpenQuoteContext，而不仅仅是重订阅
              新增 F: 尝试注册 RealTimeKlineHandlerBase push 回调；
                      回调触发时更新 _kl_push_ts，用于辅助活跃检测；
                      SDK 不支持时静默降级，不影响轮询
              新增 G: _fetch_5m_kline 每次成功必打印诊断行：
                      bars/last_time_key/last_vol，便于日志追溯冻结起点
    v0.5.18 (2026-05-08):
      - [FIX] VWAP 跨日污染: _fetch_5m_kline 增加 ET 日期过滤
              根因: get_cur_kline(num=30) 取最近 30 根 K 线不区分日期,
                    重启时 kline_cache 横跨昨天+今天, VWAP 混入昨日数据
              修复: num 从 30→200 (覆盖完整交易日), 按 time_key 的 ET 日期
                    过滤只保留今天; 若今日无数据则回退全量(盘前兜底)
    v0.5.17 (2026-05-08):
      - [FIX] kline_cache 冻结根治:
              根因 A: subscribe_push=False → get_cur_kline 只拿订阅瞬间快照,
                      Futu Gateway 不再推新 K 线, RSI/VWAP/量比 10 分钟不变
              根因 B: _kl_subscribed 是 set, 只订阅一次永不刷新,
                      连接重置后订阅流已死但不重连
              修复 A: subscribe_push=False → subscribe_push=True
                      让 Futu Gateway 持续推 5M K 线实时更新
              修复 B: _kl_subscribed 改为 dict{(ticker,type): last_sub_ts},
                      每 KLINE_RESUB_INTERVAL(25 min) 强制重订阅
              修复 C: _focus_loop 增加 volume 冻结检测
                      连续 4 次(≈2 min) vol_sum 不变 → 判定订阅流已死
                      → 清掉订阅时间戳, 下次 fetch 强制重订阅 + 打印告警
    v0.5.16 (2026-04-28):
      - [FIX] kline freeze: _fetch_5m_kline 返回 None 时不再覆盖 kline_cache
              原问题: fetch 失败 → kline_cache=None → indicators_cache 不更新
                      → RSI/vol_ratio 永远冻结在上一次成功的值
              修复: 只有 fetch 成功才更新 kline_cache，失败时保留上次好的 cache
      - [FIX] 方向互斥: direction_trend 触发后 15 min 内压制反向 swing 信号
              原问题: direction_trend 看多 与 swing_top 看空 同批推送，矛盾
              修复: _focus_loop 里对 hits 二次过滤
                    direction_trend long  → 15min 内 swing_top(short) 不推
                    direction_trend short → 15min 内 swing_bottom(long) 不推
                    压制时打印 "[focus] swing_xxx suppressed: ... fired Xs ago"
    v0.5.15 (2026-04-27):
      - [FIX] _fetch_5m_kline: 在 get_cur_kline 前先调用 subscribe(K_5M)
              未订阅时 Futu 返回空/错误数据，是 has_indicators 永远 False 的根因
              使用模块级 _kl_subscribed set 去重，每个 ticker 只订阅一次
              新增 first_indicators_sent 验证日志：成功后打印 RSI/vol_ratio/vwap
              SubType 加入 moomoo/futu import
    v0.5.14 (2026-04-27):
      - [FIX] _fetch_5m_kline: "DataFrame constructor not properly called!" 根因修复
              原问题: 对非 None/str/DataFrame 的类型（int/bytes/自定义对象等）
                      统一走 pd.DataFrame(kl) 兜底，遇到标量或不可解析对象就崩
              修复: 每种类型独立处理分支，不用 pd.DataFrame() 作通配兜底
                    - str   → 打印 Futu 错误信息，return None
                    - Series → to_frame().T 转 DataFrame
                    - list/dict → pd.DataFrame()，失败则 return None
                    - 其他所有类型 → 打印 type 名称，return None
              新增: 非 DataFrame 时先打印 type / repr / 前3条 item
                    (KLINE-DIAG 日志)，帮助定位 Futu 实际返回内容
    v0.5.13 (2026-04-27):
      - [FIX] _fetch_5m_kline: Futu 失败时返回 str(错误信息) 而非 DataFrame/list/dict
              pd.DataFrame(str) 抛 "DataFrame constructor not properly called!"
              修复: isinstance(kl, str) 时记录错误并直接 return None
              非预期类型时打印 type 名称辅助诊断
    v0.5.12 (2026-04-25):
      - [FIX] _fetch_5m_kline: 반환값이 DataFrame 이 아닌 경우(list/dict) 방어 처리
              TypeError: string indices must be integers 오류 수정
              DataFrame 으로 변환 시도 + 필수 컬럼 확인
      - [FIX] positions refresh: list 반환 시 dict 로 변환
              'list' object has no attribute 'items' 오류 수정
    v0.5.11 (2026-04-25):
      - [FIX] _fetch_5m_kline: ret=-1 是 Moomoo AU 的已知行为
              原来判断 ret==0 才用数据,导致 kline_cache 永远是 None
              indicators_cache 永远是 {},has_indicators 永远 False
              RSI/VWAP/量比 全部用默认值,信号质量极差
              修复:只要 kl 有数据就使用,不依赖 ret 值
    v0.5.10 (2026-04-23):
      - [NEW] _archive_daily_klines() 盘后自动归档当日 1 分钟 K 线
              + session summary 到 data/review/YYYY-MM-DD/
              触发时机:市场从 regular/post/overnight → closed
              供第二天自动复盘使用
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
    from moomoo import KLType, AuType, SubType
except ImportError:
    from futu import KLType, AuType, SubType

# v0.5.19: 尝试导入推送回调基类；SDK 不支持时降级为轮询
_HAS_KLINE_HANDLER = False
try:
    try:
        from moomoo import RealTimeKlineHandlerBase as _KLHandlerBase
    except ImportError:
        from futu import RealTimeKlineHandlerBase as _KLHandlerBase
    _HAS_KLINE_HANDLER = True
except ImportError:
    _KLHandlerBase = object   # 哑占位，让 class 定义不报错

from core.realtime_quote import get_client as get_quote_client

from .context import FocusSession
from .micro_indicators import calc_all_micro
from .swing_detector import run_all_triggers, diagnose_distance, DEFAULT_PARAMS as SWING_DEFAULT_PARAMS
from .pusher import format_trigger_message
from .market_clock import (
    ET,
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


FOCUS_MGR_VERSION = "v0.5.22"
FOCUS_MGR_DATE    = "2026-05-12"

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
KLINE_RESUB_INTERVAL    = 25 * 60   # 每 25 min 强制重订阅 K_5M，防止推送流静默老化
POSITION_FETCH_INTERVAL = 15
CASH_FETCH_INTERVAL     = 30
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
#  v0.5.10 复盘数据归档(每天收盘后触发一次)
# ══════════════════════════════════════════════════════════════════
_kline_archive_done_date = None   # 避免同一天重复归档
_kl_subscribed: dict = {}         # {(ticker, subtype): last_subscribed_ts}，定期强制刷新
_snapshot_last_write: float = 0.0  # v0.5.21 共享快照节流时间戳

# v0.5.22 关键错误 TG 推送
_send_tg_ref = None               # _focus_loop 启动时写入，供工具函数调用
_tg_warn_last: dict = {}          # {warn_key: last_push_epoch}，同类告警节流
_TG_WARN_INTERVAL = 15 * 60      # 同类告警最短间隔 15 min


def _push_system_warning(warn_key: str, error_type: str, detail: str):
    """推送关键系统警告到 Telegram；同类警告 15 min 内不重复推，避免刷屏。"""
    global _tg_warn_last
    now = time.time()
    if now - _tg_warn_last.get(warn_key, 0) < _TG_WARN_INTERVAL:
        return
    _tg_warn_last[warn_key] = now

    ts  = datetime.now().strftime("%H:%M")
    msg = f"⚠️ 系统警告\n[{error_type}] {detail}\n时间: {ts}"
    print(f"  [focus] SYS_WARN [{error_type}]: {detail}")

    if _send_tg_ref:
        try:
            _send_tg_ref(msg)
        except Exception as _e:
            print(f"  [focus] _push_system_warning send failed: {_e}")

# v0.5.19: push 回调时间戳 —— 每次 SDK 推送 K 线时更新，用于冻结检测
_kl_push_ts: dict = {}           # {ticker: last_push_epoch}
_kl_push_lock = threading.Lock()


class _KLinePushHandler(_KLHandlerBase):
    """
    v0.5.19: 注册到 OpenQuoteContext 的 K 线推送回调。
    SDK 每次推送 K 线更新时自动调用 on_recv_rsp。
    只更新时间戳用于冻结检测；实际 kline_cache 仍由轮询写入，
    避免复杂的跨线程 DataFrame 合并。
    若 SDK 不支持 RealTimeKlineHandlerBase，此类退化为空对象。
    """
    def on_recv_rsp(self, rsp_pb):
        if not _HAS_KLINE_HANDLER:
            return
        try:
            ret, df = super().on_recv_rsp(rsp_pb)
            if ret == 0 and df is not None:
                # 从 DataFrame 中提取 ticker（列名因版本而异）
                import pandas as pd
                if isinstance(df, pd.DataFrame) and len(df) > 0:
                    for col in ("code", "stock_code", "ticker"):
                        if col in df.columns:
                            ticker = str(df[col].iloc[0])
                            if not ticker.startswith("US."):
                                ticker = "US." + ticker
                            with _kl_push_lock:
                                _kl_push_ts[ticker] = time.time()
                            break
            return ret, df
        except Exception:
            pass

def _archive_daily_klines(session, client):
    """
    v0.5.10: 盘后归档当日 1 分钟 K 线到 data/review/YYYY-MM-DD/
    供第二天自动复盘使用。失败不影响主流程。

    每天只归档一次(通过 _kline_archive_done_date 去重)。
    """
    global _kline_archive_done_date
    try:
        import os
        import json
        from datetime import datetime as _dt

        today_str = _dt.now().strftime("%Y-%m-%d")
        if _kline_archive_done_date == today_str:
            return  # 今天已经归档过

        # 路径:项目根/data/review/YYYY-MM-DD/
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        archive_dir = os.path.join(base_dir, "data", "review", today_str)
        os.makedirs(archive_dir, exist_ok=True)

        tickers = [session.master] + list(session.followers or [])
        success_count = 0

        # v0.5.26: 同时归档 1m + 5m
        kline_specs = [
            ("1m", KLType.K_1M, 500),
            ("5m", KLType.K_5M, 200),
        ]

        for ticker in tickers:
            for period_tag, ktype, n_bars in kline_specs:
                try:
                    if not client._ensure_quote():
                        continue
                    with client._quote_lock:
                        ret, kl = client._quote_ctx.get_cur_kline(
                            ticker, n_bars, ktype, AuType.QFQ
                        )
                    if ret != 0 or kl is None or len(kl) == 0:
                        continue

                    # DataFrame → dict list 存 JSON
                    records = []
                    for _, row in kl.iterrows():
                        records.append({
                            "time_key": str(row.get("time_key", "")),
                            "open":    float(row.get("open", 0)),
                            "close":   float(row.get("close", 0)),
                            "high":    float(row.get("high", 0)),
                            "low":     float(row.get("low", 0)),
                            "volume":  int(row.get("volume", 0)),
                            "turnover": float(row.get("turnover", 0)),
                        })

                    short_name = ticker.replace("US.", "")
                    out_path = os.path.join(archive_dir, f"kline_{period_tag}_{short_name}.json")
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(records, f, ensure_ascii=False, indent=2)
                    success_count += 1
                    print(f"  [archive] saved {ticker} {period_tag} klines ({len(records)} bars) → {out_path}")
                except Exception as e:
                    print(f"  [archive] {ticker} {period_tag} failed: {e}")

        # 顺便存一份 session 快照(session 总结)
        try:
            summary = {
                "date": today_str,
                "master": session.master,
                "followers": list(session.followers or []),
                "loop_count": session.loop_count,
                "trigger_count": session.trigger_count,
                "push_count": session.push_count,
                "error_count": session.error_count,
                "cash_available_final": session.cash_available,
                "session_high": {k.replace("US.", ""): v for k, v in (session.session_high or {}).items()},
                "session_low":  {k.replace("US.", ""): v for k, v in (session.session_low  or {}).items()},
                "positions_final": {
                    k.replace("US.", ""): {
                        "qty": v.get("qty"),
                        "cost": v.get("cost_price"),
                        "pl_val": v.get("pl_val"),
                        "pl_pct": v.get("pl_pct"),
                    }
                    for k, v in (session.positions_snapshot or {}).items()
                    if v and v.get("qty", 0) > 0
                },
                "archive_time": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(os.path.join(archive_dir, "session_summary.json"), "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"  [archive] session summary failed: {e}")

        _kline_archive_done_date = today_str
        print(f"  [archive] ✅ {success_count}/{len(tickers)} klines archived to {archive_dir}")

    except Exception as e:
        print(f"  [_archive_daily_klines] failed: {e}")


# ══════════════════════════════════════════════════════════════════
#  v0.5.20 趋势锁定 — 工具函数
# ══════════════════════════════════════════════════════════════════

def _calc_atr(kline_cache, period: int = 14) -> float:
    """简单 ATR：最近 period 根 5m 柱的 (high-low) 均值。"""
    try:
        if kline_cache is None or len(kline_cache) < period:
            return 0.0
        import pandas as pd
        recent = kline_cache.tail(period)
        tr = (recent["high"] - recent["low"]).abs()
        return float(tr.mean())
    except Exception:
        return 0.0


def _calc_trend_targets(price: float, atr: float, direction: str) -> dict:
    """
    趋势锁定目标价：
    - 整十关口（long 取上方最近整十，short 取下方最近整十）
    - ATR × 1.5 / 2.0 / 3.0
    """
    import math
    sign = 1 if direction == "long" else -1
    if direction == "long":
        round_ten = math.ceil(price / 10) * 10
        if round_ten == price:          # 恰好在整十位则取上一级
            round_ten += 10
    else:
        round_ten = math.floor(price / 10) * 10
        if round_ten == price:
            round_ten -= 10

    return {
        "round_ten": round(round_ten, 2),
        "atr_1_5":   round(price + sign * atr * 1.5, 2) if atr else None,
        "atr_2_0":   round(price + sign * atr * 2.0, 2) if atr else None,
        "atr_3_0":   round(price + sign * atr * 3.0, 2) if atr else None,
    }


def _fmt_trend_lock_msg(ticker_short: str, direction: str,
                        day_chg: float, price: float, targets: dict) -> str:
    emoji = "🚀" if direction == "long" else "📉"
    word  = "看多" if direction == "long" else "看空"
    chg_sign = "+" if day_chg >= 0 else ""
    suppress = ("swing_top + direction_trend 看空"
                if direction == "long"
                else "swing_bottom + direction_trend 看多")
    lines = [
        f"🔒 <b>趋势锁定 · {ticker_short} {emoji}{word}</b>",
        f"━━━━━━━━━━━━━━",
        f"连续 3 次 STRONG {word}  日内 {chg_sign}{day_chg:.2f}%  现价 ${price:.2f}",
        f"🔕 锁定期间静默: {suppress}",
        f"🔓 解锁条件: 日内涨幅从峰值回落 >3%",
        f"",
        f"📐 <b>目标价参考</b>",
        f"🔢 整十关口: ${targets['round_ten']:.2f}",
    ]
    if targets.get("atr_1_5") is not None:
        lines += [
            f"📊 ATR×1.5: ${targets['atr_1_5']:.2f}",
            f"📊 ATR×2.0: ${targets['atr_2_0']:.2f}",
            f"📊 ATR×3.0: ${targets['atr_3_0']:.2f}",
        ]
    else:
        lines.append("📊 ATR: K 线数据不足，暂无计算")
    return "\n".join(lines)


def _fmt_trend_unlock_msg(ticker_short: str, direction: str,
                          peak_chg: float, cur_chg: float, duration_min: int) -> str:
    word = "看多" if direction == "long" else "看空"
    drawdown = peak_chg - cur_chg if direction == "long" else cur_chg - peak_chg
    peak_sign = "+" if peak_chg >= 0 else ""
    cur_sign  = "+" if cur_chg  >= 0 else ""
    return (
        f"🔓 <b>趋势锁定解除 · {ticker_short} {word}</b>\n"
        f"日内涨幅从 {peak_sign}{peak_chg:.2f}% 回落至 {cur_sign}{cur_chg:.2f}%"
        f"（回撤 {drawdown:.2f}%）\n"
        f"锁定持续 {duration_min} 分钟"
    )


# ══════════════════════════════════════════════════════════════════
#  v0.5.21 共享市场快照
# ══════════════════════════════════════════════════════════════════

def _snapshot_throttle_sec(profile: dict, market_status: str) -> int:
    """按行情密度等级决定快照写入最小间隔（秒）"""
    level = (profile.get("level") or "").upper()
    if "PEAK" in level:
        return 5
    if "HIGH" in level:
        return 10
    if "MEDIUM" in level:
        return 15
    if market_status == "closed":
        return 60
    return 30  # LOW / MINIMAL / unknown


def _build_last_signal(hit: dict) -> dict:
    """hit dict → last_signal 快照字段"""
    trigger   = hit.get("trigger", "")
    direction = hit.get("direction", "")
    strength  = hit.get("strength", "WEAK")

    bias = {"long": "bullish", "short": "bearish"}.get(direction, "neutral")

    RISK_TRIGGERS  = {"near_resistance", "near_support", "overbought_surge",
                      "large_day_gain", "profit_target_hit", "drawdown_from_peak"}
    ENTRY_TRIGGERS = {"direction_trend", "swing_top", "swing_bottom"}
    is_risk  = trigger in RISK_TRIGGERS
    is_entry = trigger in ENTRY_TRIGGERS

    confidence = 75 if strength == "STRONG" else 55

    if is_risk:
        intent = ("reduce_risk"
                  if trigger in ("overbought_surge", "large_day_gain",
                                 "near_resistance", "profit_target_hit")
                  else "watch_breakout")
    elif strength == "STRONG" and is_entry:
        intent = "light_long" if direction == "long" else "light_short"
    elif strength == "WEAK" and is_entry:
        intent = "watch_pullback" if direction == "long" else "watch_breakout"
    else:
        intent = "wait"

    return {
        "trigger":         trigger,
        "direction":       direction,
        "strength":        strength,
        "confidence":      confidence,
        "bias":            bias,
        "action_intent":   intent,
        "is_trade_entry":  is_entry,
        "is_risk_warning": is_risk,
        "ts":              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _write_shared_market_snapshot(session, indicators_cache: dict, profile: dict,
                                   market_status: str, last_signal: dict = None,
                                   trend_lock_dir=None, trend_lock_ts: float = 0.0):
    """
    v0.5.21: 写入共享市场快照 data/shared/market_snapshot.json
    供其他系统读取，只读输出，不下单。
    先写 .tmp 再 os.replace() 原子替换，防止读到半截 JSON。
    写失败只打 warning，不影响盯盘主循环。
    """
    global _snapshot_last_write
    import json, os

    now_ts   = time.time()
    interval = _snapshot_throttle_sec(profile, market_status)
    if now_ts - _snapshot_last_write < interval:
        return

    try:
        base_dir  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        share_dir = os.path.join(base_dir, "data", "shared")
        os.makedirs(share_dir, exist_ok=True)
        out_path  = os.path.join(share_dir, "market_snapshot.json")
        tmp_path  = os.path.join(share_dir, "market_snapshot.tmp")

        # ── quotes ──────────────────────────────────────────────
        quotes = {}
        for tk in [session.master] + list(session.followers or []):
            q = session.quote_snapshot.get(tk) or {}
            quotes[tk] = {
                "price":       session.get_last_price(tk),
                "change":      q.get("change"),
                "change_pct":  q.get("change_pct") or session.get_day_change_pct(tk),
                "high":        session.session_high.get(tk),
                "low":         session.session_low.get(tk),
                "volume":      q.get("volume"),
                "update_time": session.get_quote_update_time(tk) or "",
            }

        # ── positions (qty > 0 only) ─────────────────────────────
        positions = {}
        for tk in [session.master] + list(session.followers or []):
            pos = session.get_position(tk)
            if pos and pos.get("qty", 0) > 0:
                positions[tk] = {
                    "qty":           pos.get("qty"),
                    "cost_price":    pos.get("cost_price"),
                    "current_price": session.get_last_price(tk),
                    "market_val":    pos.get("market_val"),
                    "pl_val":        pos.get("pl_val"),
                    "pl_pct":        pos.get("pl_pct"),
                }

        # ── indicators ──────────────────────────────────────────
        ind = indicators_cache or {}
        indicators = {
            "rsi_5m":       ind.get("rsi_5m"),
            "vwap":         ind.get("vwap"),
            "vol_ratio":    ind.get("vol_ratio"),
            "session_high": ind.get("session_high"),
            "session_low":  ind.get("session_low"),
            "dist_high":    ind.get("dist_high"),
            "dist_low":     ind.get("dist_low"),
            "data_ok":      bool(ind.get("data_ok")),
        }

        # ── account ─────────────────────────────────────────────
        fetched_at_str = (datetime.fromtimestamp(session.cash_fetched_at)
                          .strftime("%Y-%m-%d %H:%M:%S")
                          if session.cash_fetched_at else "")
        account = {
            "cash":         session.cash_available,
            "power":        session.cash_power,
            "total_assets": None,
            "market_val":   None,
            "currency":     "USD",
            "fetched_at":   fetched_at_str,
        }

        # ── focus state ─────────────────────────────────────────
        focus = {
            "loop_count":           session.loop_count,
            "push_count":           session.push_count,
            "error_count":          session.error_count,
            "trend_lock":           trend_lock_dir is not None,
            "trend_lock_direction": trend_lock_dir,
            "trend_lock_since":     (datetime.fromtimestamp(trend_lock_ts)
                                     .strftime("%Y-%m-%d %H:%M:%S")
                                     if trend_lock_ts else None),
            "heartbeat_enabled":    _heartbeat_enabled,
        }

        snapshot = {
            "schema_version":   "1.1",
            "source":           "claude_focus",
            "updated_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "market_status":    market_status,
            "activity_profile": {
                "level":    profile.get("level", ""),
                "poll_sec": profile.get("poll_sec"),
                "scale":    profile.get("scale"),
                "reason":   profile.get("reason", ""),
            },
            "master":     session.master,
            "followers":  list(session.followers or []),
            "quotes":     quotes,
            "account":    account,
            "positions":  positions,
            "indicators": indicators,
            "last_signal": last_signal or {},
            "focus":      focus,
            "producer": {
                "system":  "claude",
                "module":  "focus_manager",
                "version": FOCUS_MGR_VERSION,
            },
            "notes": [
                "This file is read-only for other systems.",
                "No order placement is performed by this export.",
                "If updated_at is older than 120s during CLOSED session, "
                "or 15s during active session, consider fallback to direct Futu query.",
            ],
        }

        payload = json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, out_path)
        _snapshot_last_write = now_ts

    except Exception as e:
        print(f"  [snapshot] ⚠️ write failed: {e}")


# ══════════════════════════════════════════════════════════════════
#  主循环
# ══════════════════════════════════════════════════════════════════
def _focus_loop(session: FocusSession, send_tg_fn: Callable, stop_event: threading.Event):
    print(f"  [focus] loop started for {session.master} "
          f"(manual={getattr(session, 'manual_mode', False)})")

    last_kline_fetch      = 0
    last_position_fetch   = 0
    last_cash_fetch       = 0
    last_heartbeat        = time.time()
    kline_cache           = None
    indicators_cache      = {}
    first_indicators_sent = False
    last_market_status    = None
    last_trend_fire: dict = {}        # {"long": float, "short": float} 方向互斥时间戳
    last_bar_time_key     = None      # v0.5.19 冻结检测：上次最后一根柱的 time_key
    kline_freeze_count    = 0         # v0.5.19 冻结检测：连续 time_key 未变次数

    # v0.5.20 趋势锁定状态
    trend_lock_dir        = None      # "long" / "short" / None
    trend_lock_ts         = 0.0       # 锁定时刻 (epoch)
    trend_lock_peak_chg   = 0.0       # 锁定后日内涨幅峰值（动态更新）
    strong_count: dict    = {"long": 0, "short": 0}  # 同向 STRONG 连续次数

    # v0.5.21 共享快照：跨迭代保留最后一次推送信号
    snapshot_last_signal: dict = {}

    # v0.5.22 关键错误告警计数器
    consecutive_errors    = 0
    last_has_indicators_ts = time.time()   # 初始化为启动时，给足 10 min 预热

    # ── v0.5.6 关键:读 manual_mode ──
    manual_mode = getattr(session, "manual_mode", False)

    client = get_quote_client()

    # v0.5.22: 保存 send_tg_fn 引用，供 _push_system_warning 使用
    global _send_tg_ref
    _send_tg_ref = send_tg_fn

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
                # v0.5.10: 从 post/regular/overnight 切到 closed 时归档当日 K 线
                if (market_status == "closed" and
                    last_market_status in ("regular", "post", "overnight")):
                    _archive_daily_klines(session, client)
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
                fetched = _fetch_5m_kline(client, session.master)
                if fetched is not None:
                    kline_cache = fetched          # 只有成功才覆盖

                    # v0.5.19 冻结检测：比较最后一根柱的 time_key（取代 vol_sum）
                    # vol_sum 误报原因：两次轮询落在同一根 5m 柱内时 vol_sum 天然不变
                    cur_bar_tk = (str(fetched["time_key"].iloc[-1])
                                  if "time_key" in fetched.columns else None)

                    if cur_bar_tk and cur_bar_tk == last_bar_time_key:
                        kline_freeze_count += 1
                        # 仅在交易时段（pre/regular/post/overnight）才判定为冻结
                        # closed 状态下 time_key 不变是正常的
                        trading_now = (get_market_status() != "closed")
                        if trading_now and kline_freeze_count >= 3:   # 3×30s = 90s
                            print(f"  [focus] ⚠️ kline frozen {kline_freeze_count}x "
                                  f"(last_bar={cur_bar_tk} unchanged) "
                                  f"— hard reconnecting quote context")
                            # 清空订阅缓存，强制重建连接（不只是重订阅）
                            _kl_subscribed.clear()
                            client.reconnect_quote()
                            kline_freeze_count = 0
                    else:
                        kline_freeze_count = 0
                        last_bar_time_key = cur_bar_tk
                else:
                    print("  [focus] kline fetch returned None, retaining last cache")
                last_kline_fetch = now

            current_master_price = session.get_last_price(session.master)
            if kline_cache is not None and current_master_price:
                indicators_cache = calc_all_micro(kline_cache, current_master_price)
                # v0.5.9: 同步到全局,供 /ai_test 使用
                global _indicators_cache_global
                _indicators_cache_global = indicators_cache or {}
                # v0.5.26: 挂到 session,供 pusher._log_trigger 写决策上下文
                session._last_kline_cache = kline_cache
                session._last_indicators_cache = indicators_cache

            # v0.5.22: has_indicators 连续 10 min False → 系统警告
            if indicators_cache.get("data_ok"):
                last_has_indicators_ts = now
            elif now - last_has_indicators_ts > 600:
                _push_system_warning(
                    "no_indicators", "指标长时间不可用",
                    f"has_indicators 已持续 {int((now - last_has_indicators_ts) / 60)} 分钟为 False，"
                    f"RSI/VWAP/量比 均使用默认值，信号质量差"
                )

            if now - last_position_fetch >= POSITION_FETCH_INTERVAL:
                positions = client.fetch_positions()
                if positions is not None:
                    # v0.5.12: fetch_positions 가 list 를 반환하는 경우 방어 처리
                    if isinstance(positions, list):
                        print(f"  [focus] positions was list, converting to dict")
                        positions = {p["ticker"]: p for p in positions if "ticker" in p}
                    session.update_positions(positions)

                    # v0.5.24: 拉一次当日成交,刷新还没缓存 open_time 的持仓
                    missing = [tk for tk in positions
                               if tk not in session._position_open_time]
                    if missing:
                        try:
                            deals = client.fetch_today_deals()
                            if deals:
                                for tk, ts in deals.items():
                                    session.set_position_open_time(tk, ts)
                        except Exception as e:
                            print(f"  [focus] fetch_today_deals failed: {e}")
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

            # ── v0.5.20 趋势锁定：解锁检测（每轮执行，不依赖 hits）──
            if trend_lock_dir:
                cur_day_chg = (session.get_day_change_pct(session.master)
                               if hasattr(session, "get_day_change_pct") else None)
                if cur_day_chg is not None:
                    # 更新峰值
                    if trend_lock_dir == "long":
                        trend_lock_peak_chg = max(trend_lock_peak_chg, cur_day_chg)
                        drawdown = trend_lock_peak_chg - cur_day_chg
                    else:
                        trend_lock_peak_chg = min(trend_lock_peak_chg, cur_day_chg)
                        drawdown = cur_day_chg - trend_lock_peak_chg
                    # 回落 >3% → 解锁
                    if drawdown >= 3.0:
                        dur_min = int((now - trend_lock_ts) / 60)
                        ticker_s = session.master.replace("US.", "")
                        unlock_msg = _fmt_trend_unlock_msg(
                            ticker_s, trend_lock_dir,
                            trend_lock_peak_chg, cur_day_chg, dur_min
                        )
                        print(f"  [focus] 🔓 trend_lock {trend_lock_dir} released "
                              f"(drawdown={drawdown:.2f}% after {dur_min}min)")
                        try:
                            send_tg_fn(unlock_msg)
                        except Exception:
                            pass
                        trend_lock_dir      = None
                        trend_lock_ts       = 0.0
                        trend_lock_peak_chg = 0.0
                        strong_count        = {"long": 0, "short": 0}

            # ── 方向互斥过滤：direction_trend 触发后压制反向 swing ──
            # WEAK  看多/空 → 15 min 内压制反向 swing
            # STRONG 看多   → 30 min 内压制 swing_top 看空（用户要求：强趋势不逆势）
            DIRECTION_MUTEX_SEC        = 15 * 60   # WEAK 互斥窗口
            DIRECTION_MUTEX_STRONG_SEC = 30 * 60   # STRONG 互斥窗口
            TREND_LOCK_COUNT           = 3          # 触发锁定所需同向 STRONG 次数
            filtered_hits = []
            for hit in hits:
                trig = hit.get("trigger")
                dirn = hit.get("direction")

                # ── v0.5.20 趋势锁定压制：锁定期间静默反向信号 ──────────────
                if trend_lock_dir == "long":
                    if trig == "swing_top" and dirn == "short":
                        print(f"  [focus] swing_top suppressed: trend_lock=long active")
                        continue
                    if trig == "direction_trend" and dirn == "short":
                        print(f"  [focus] direction_trend short suppressed: trend_lock=long active")
                        continue
                elif trend_lock_dir == "short":
                    if trig == "swing_bottom" and dirn == "long":
                        print(f"  [focus] swing_bottom suppressed: trend_lock=short active")
                        continue
                    if trig == "direction_trend" and dirn == "long":
                        print(f"  [focus] direction_trend long suppressed: trend_lock=short active")
                        continue

                # ── direction_trend：方向互斥记录 + 趋势锁定计数 ─────────────
                if trig == "direction_trend":
                    last_trend_fire[dirn] = now           # 任意强度都记录
                    if hit.get("strength") == "STRONG":
                        last_trend_fire[dirn + "_strong"] = now   # STRONG 单独记录
                        # v0.5.20: 同向 STRONG 计数，反向重置
                        opp = "short" if dirn == "long" else "long"
                        strong_count[dirn] = strong_count.get(dirn, 0) + 1
                        strong_count[opp]  = 0
                        # 连续 3 次 → 触发锁定
                        if strong_count[dirn] >= TREND_LOCK_COUNT and trend_lock_dir != dirn:
                            cur_day_chg = (session.get_day_change_pct(session.master)
                                           if hasattr(session, "get_day_change_pct") else 0.0) or 0.0
                            cur_price   = session.get_last_price(session.master) or 0.0
                            atr         = _calc_atr(kline_cache)
                            targets     = _calc_trend_targets(cur_price, atr, dirn)
                            trend_lock_dir      = dirn
                            trend_lock_ts       = now
                            trend_lock_peak_chg = cur_day_chg
                            ticker_s = session.master.replace("US.", "")
                            lock_msg = _fmt_trend_lock_msg(
                                ticker_s, dirn, cur_day_chg, cur_price, targets
                            )
                            print(f"  [focus] 🔒 trend_lock={dirn} activated "
                                  f"(STRONG×{strong_count[dirn]}, day_chg={cur_day_chg:+.2f}%)")
                            try:
                                send_tg_fn(lock_msg)
                            except Exception:
                                pass
                    else:
                        # WEAK signal 重置计数（趋势不够强则从头累积）
                        strong_count[dirn] = 0
                    filtered_hits.append(hit)

                elif trig == "swing_top" and dirn == "short":
                    # direction_trend STRONG 看多 30 min 内 → 压制
                    strong_elapsed = now - last_trend_fire.get("long_strong", 0)
                    any_elapsed    = now - last_trend_fire.get("long", 0)
                    if strong_elapsed < DIRECTION_MUTEX_STRONG_SEC:
                        print(f"  [focus] swing_top suppressed: "
                              f"direction_trend STRONG long fired {int(strong_elapsed)}s ago")
                        continue
                    elif any_elapsed < DIRECTION_MUTEX_SEC:
                        print(f"  [focus] swing_top suppressed: "
                              f"direction_trend long fired {int(any_elapsed)}s ago")
                        continue
                    filtered_hits.append(hit)

                elif trig == "swing_bottom" and dirn == "long":
                    # direction_trend 看空 15 min 内 → 压制 swing_bottom 看多（不变）
                    elapsed = now - last_trend_fire.get("short", 0)
                    if elapsed < DIRECTION_MUTEX_SEC:
                        print(f"  [focus] swing_bottom suppressed: "
                              f"direction_trend short fired {int(elapsed)}s ago")
                        continue
                    filtered_hits.append(hit)

                else:
                    filtered_hits.append(hit)

            for hit in filtered_hits:
                try:
                    msg = format_trigger_message(hit, session)
                    if send_tg_fn:
                        send_tg_fn(msg["text"], buttons=msg.get("buttons"))
                        session.push_count += 1
                        snapshot_last_signal = _build_last_signal(hit)  # v0.5.21
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
                print(f"  [focus] ✅ has_indicators=True — RSI={indicators_cache.get('rsi_5m','?')} "
                      f"vol_ratio={indicators_cache.get('vol_ratio','?')} "
                      f"vwap={indicators_cache.get('vwap','?')}")
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

            # v0.5.21: 写共享快照(节流控制,失败不影响主循环)
            _write_shared_market_snapshot(
                session,
                indicators_cache,
                getattr(session, "activity_profile", None) or {},
                market_status,
                last_signal=snapshot_last_signal,
                trend_lock_dir=trend_lock_dir,
                trend_lock_ts=trend_lock_ts,
            )

            consecutive_errors = 0  # v0.5.22: 成功完成一轮，重置连续错误计数

        except Exception as e:
            session.error_count += 1
            consecutive_errors += 1
            print(f"  [focus] loop error: {e}")
            traceback.print_exc()
            err_str = str(e).lower()
            # v0.5.22: Futu 连接失败检测（连接数超128 / Context status bad）
            if any(kw in err_str for kw in
                   ("128", "context status", "status bad", "connection failed", "connect error")):
                _push_system_warning("futu_conn", "Futu 连接失败", str(e)[:120])
            # v0.5.22: 连续 5 次 loop error → 系统警告
            if consecutive_errors >= 5:
                _push_system_warning(
                    "loop_errors", "连续循环错误",
                    f"连续 {consecutive_errors} 次 loop error，最近: {str(e)[:80]}"
                )
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


def _fetch_5m_kline(client, ticker: str, num: int = 200):
    try:
        if not client._ensure_quote():
            return None

        # v0.5.17: subscribe_push=True 确保 Futu Gateway 持续推 K 线实时数据；
        #          _kl_subscribed 改为 {key: ts} dict，每 KLINE_RESUB_INTERVAL 强制刷新，
        #          防止连接重置后订阅流静默老化（v0.5.15 用 subscribe_push=False 是冻结根因）
        global _kl_subscribed
        sub_key = (ticker, "K_5M")
        now_ts = time.time()
        if now_ts - _kl_subscribed.get(sub_key, 0) >= KLINE_RESUB_INTERVAL:
            with client._quote_lock:
                ret_sub, err_sub = client._quote_ctx.subscribe(
                    [ticker], [SubType.K_5M], subscribe_push=True
                )
            if ret_sub == 0:
                _kl_subscribed[sub_key] = now_ts
                print(f"  [focus] (re)subscribed {ticker} K_5M push=True ✅")
                # v0.5.19: 注册 push 回调（SDK 支持时），更新 _kl_push_ts 用于冻结检测
                if _HAS_KLINE_HANDLER:
                    try:
                        client._quote_ctx.set_handler(_KLinePushHandler())
                    except Exception as _he:
                        print(f"  [focus] set_handler failed (non-fatal): {_he}")
            else:
                print(f"  [focus] subscribe {ticker} K_5M failed (ret={ret_sub}): {err_sub}")
                # v0.5.22: 订阅失败推系统警告
                _push_system_warning("kline_sub", "K线订阅失败",
                    f"{ticker} K_5M ret={ret_sub}: {str(err_sub)[:80]}")
                # 订阅失败仍继续尝试 get_cur_kline（可能已在别处订阅）

        with client._quote_lock:
            ret, kl = client._quote_ctx.get_cur_kline(
                ticker, num, KLType.K_5M, AuType.QFQ
            )

        import pandas as pd

        # ── 诊断：非 DataFrame 时打印实际类型和内容，帮助定位根因 ──
        if not isinstance(kl, pd.DataFrame):
            kl_type = type(kl).__name__
            kl_repr = repr(kl)
            print(f"  [KLINE-DIAG] ret={ret}  type={kl_type}")
            print(f"  [KLINE-DIAG] repr={kl_repr[:300]}")
            if hasattr(kl, "__len__"):
                print(f"  [KLINE-DIAG] len={len(kl)}")
            if hasattr(kl, "__iter__") and not isinstance(kl, (str, bytes)):
                try:
                    for i, item in enumerate(list(kl)[:3]):
                        print(f"  [KLINE-DIAG] item[{i}] "
                              f"type={type(item).__name__}  {repr(item)[:150]}")
                except Exception:
                    pass

        # ── 类型分支：每种情况独立处理，不用 pd.DataFrame() 兜底 ──
        if kl is None:
            return None

        if isinstance(kl, str):
            # Futu 失败时返回错误字符串（已知场景）
            print(f"  [focus] kline error str from Futu (ret={ret}): {kl[:120]}")
            return None

        if isinstance(kl, pd.DataFrame):
            pass  # 正常路径，直接往下走

        elif isinstance(kl, pd.Series):
            # 极少数情况：单行数据以 Series 返回
            kl = kl.to_frame().T.reset_index(drop=True)

        elif isinstance(kl, (list, dict)):
            try:
                kl = pd.DataFrame(kl)
            except Exception as e2:
                print(f"  [focus] kline {type(kl).__name__}→DataFrame failed: {e2}")
                return None

        else:
            # int / float / bytes / 自定义 Futu 对象等——无法转换，放弃
            print(f"  [focus] kline unhandled type={type(kl).__name__}, dropping")
            return None

        if len(kl) == 0:
            return None

        # 必要列检查
        required = {"close", "high", "low", "open", "volume"}
        if not required.issubset(set(kl.columns)):
            print(f"  [focus] kline missing columns: {kl.columns.tolist()}")
            return None

        # v0.5.27: 不再缩减 DataFrame, 改为只写 attrs, 由 calc_all_micro 分指标过滤
        #          根因: v0.5.18 一刀切过滤导致开盘头 50 min has_indicators=False
        #                (当日 K < 10 根,RSI/vol_ratio 都走兜底,黄金时段错失信号)
        #          解法: RSI/vol_ratio 用全量 K (跨日反而稳),VWAP 仍按当日子集
        et_today       = datetime.now(ET).strftime("%Y-%m-%d")
        has_today_data = True
        n_today        = len(kl)
        if "time_key" in kl.columns:
            today_mask = kl["time_key"].astype(str).str.startswith(et_today)
            n_today    = int(today_mask.sum())
            has_today_data = n_today > 0
        kl.attrs["et_today"]       = et_today
        kl.attrs["has_today_data"] = has_today_data
        if has_today_data:
            print(f"  [focus] kline {len(kl)} bars total, today subset {n_today} bars (ET {et_today})")
        else:
            print(f"  [focus] kline {len(kl)} bars total, no today bars yet for {et_today} ET (pre-market/early open)")

        # v0.5.19: 每次成功必打印诊断行 —— bars / last_time_key / last_vol
        last_tk  = str(kl["time_key"].iloc[-1])  if "time_key" in kl.columns else "?"
        last_vol = int(kl["volume"].iloc[-1])     if "volume"   in kl.columns else 0
        last_cls = float(kl["close"].iloc[-1])    if "close"    in kl.columns else 0.0
        with _kl_push_lock:
            last_push = _kl_push_ts.get(ticker, 0)
        push_age = int(time.time() - last_push) if last_push else -1
        print(f"  [KLINE] bars={len(kl)}  last={last_tk}  "
              f"vol={last_vol}  close={last_cls:.2f}  "
              f"push_age={push_age}s")

        return kl

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
