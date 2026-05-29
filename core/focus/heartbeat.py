"""
MagicQuant — Heartbeat 心跳监控 (v0.5.33)

v0.5.33 (2026-05-16):
  - [NEW] 持仓两行格式: "TKR: N 股 @$cost 现价 $price" + "盈利/亏损 ±$X (±X%)"
          替换原单行 "TKR $price 📉 N股@cost (%)"
  - [NEW] 📍 当前系统判断段: 风险提醒中(冻结/止损/盘前) / 趋势锁定中 / 观望中
          代替单点"触发器距离",给用户系统层面的状态

v0.3.6:

解决"盯盘在跑但看起来完全沉默"的问题.

提供两种使用方式:
  1. 主动查询: /heartbeat 指令,立刻返回系统状态
  2. 定时心跳: /heartbeat_on [分钟],每 N 分钟自动推一次
             /heartbeat_off 关闭

心跳内容:
  - 主标实时价 + 当日区间
  - 5 分钟关键指标(RSI / MACD / 量比 / K线形态)
  - 跟随标的持仓 + 浮盈
  - 7 大触发器"离阈值还差多远"
  - 循环次数 + 运行时长
  - AI 智囊团状态 + 今日累计成本

设计原则:
  - 零 AI 调用,完全免费
  - 只读 FocusSession 内存数据
  - 不影响主循环性能
  - 信息丰富但不啰嗦,单条 TG 消息即可
"""

import time
import threading
from datetime import datetime
from typing import Optional, Callable

from .kline_display import format_kline_source_line, format_subscription_detail


# ══════════════════════════════════════════════════════════════════
#  定时推送状态(模块级单例)
# ══════════════════════════════════════════════════════════════════

_heartbeat_enabled = False
_heartbeat_interval_min = 15
_heartbeat_thread: Optional[threading.Thread] = None
_heartbeat_stop = threading.Event()
_heartbeat_last_push = 0


# ══════════════════════════════════════════════════════════════════
#  v0.5.33: 系统状态推导
# ══════════════════════════════════════════════════════════════════

def _derive_system_state(session, indicators: dict = None) -> list:
    """
    推导"当前系统判断"展示行。
    优先级: 风险提醒(冻结/止损/盘前) > 趋势锁定 > 观望。
    一次最多展示一条状态。

    返回行列表（含标题行），调用方决定是否插入空行分隔。
    """
    # ── 风险提醒：指标冻结中 ──
    try:
        quality = getattr(session, "_last_data_quality", None) or {}
        if quality and quality.get("ok") is False:
            return [
                "📍 当前系统判断: 🚨 风险提醒中",
                f"   原因: 数据质量不可用 ({quality.get('reason', 'unknown')}), 信号已暂停",
            ]
    except Exception:
        pass

    try:
        freeze = getattr(session, "_indicator_freeze", None)
        if freeze is not None and getattr(freeze, "frozen", False):
            mins = freeze.freeze_minutes() if hasattr(freeze, "freeze_minutes") else 0
            return [
                "📍 当前系统判断: 🚨 风险提醒中",
                f"   原因: 指标冻结 (RSI/量比 连续 {mins} 分钟未变, 信号已暂停)",
            ]
    except Exception:
        pass

    # ── 风险提醒：持仓接近止损 (最近一次 stop_loss_warning 30min 内) ──
    try:
        last_times = getattr(session, "last_trigger_time", {}) or {}
        sl_ts = max(
            (ts for k, ts in last_times.items() if k.startswith("stop_loss_")),
            default=0
        )
        if sl_ts and (time.time() - sl_ts) <= 1800:
            mins_ago = int((time.time() - sl_ts) / 60)
            return [
                "📍 当前系统判断: 🚨 风险提醒中",
                f"   原因: 持仓接近止损 ({mins_ago} 分钟前刚推过 stop_loss_warning)",
            ]
    except Exception:
        pass

    # ── 风险提醒：盘前 fallback 模式 ──
    try:
        if indicators and indicators.get("data_ok") and indicators.get("is_today") is False:
            return [
                "📍 当前系统判断: 🚨 风险提醒中",
                "   原因: 盘前 fallback (今日 K 线未出, 用昨日数据兜底, RTH 信号全静默)",
            ]
    except Exception:
        pass

    # ── 趋势锁定中 ──
    try:
        from .swing_detector import _is_strong_trend_locked
        if _is_strong_trend_locked(session):
            lock = getattr(session, "_trend_hold_mode", None) or {}
            dir_word = "看多" if lock.get("direction") == "long" else "看空"
            return [
                "📍 当前系统判断: 🔒 趋势锁定中",
                f"   方向: {dir_word} · 反向信号被静默 (近期连续 STRONG long ≥ 3 次)",
            ]
    except Exception:
        pass

    # ── 观望中 ──
    return ["📍 当前系统判断: ⚪ 观望中 (无强趋势/无风险事件)"]


# ══════════════════════════════════════════════════════════════════
#  核心:格式化心跳消息
# ══════════════════════════════════════════════════════════════════

def format_heartbeat(session, indicators: dict = None) -> str:
    """
    把当前 FocusSession 状态格式化成心跳消息.
    """
    if session is None or not getattr(session, "active", False):
        return (
            "💤 系统空闲\n"
            "当前没有运行中的 Focus 盯盘\n\n"
            "💡 用 /focus 启动盯盘"
        )

    # ── 基本信息 ──
    master = session.master
    master_short = master.replace("US.", "")
    cur_price = session.get_last_price(master)

    sess_high = None
    sess_low = None
    try:
        sess_high = session.session_high.get(master)
        sess_low = session.session_low.get(master)
    except Exception:
        pass

    # 运行时长
    runtime_str = "?"
    try:
        start = getattr(session, "start_time", None)
        if start:
            runtime_sec = int(time.time() - start)
            runtime_min = runtime_sec // 60
            if runtime_min >= 60:
                runtime_str = f"{runtime_min // 60}h{runtime_min % 60}m"
            else:
                runtime_str = f"{runtime_min}m{runtime_sec % 60}s"
    except Exception:
        pass

    loops = getattr(session, "loop_count", 0)
    triggers = getattr(session, "trigger_count", 0)
    if not triggers:
        triggers = getattr(session, "push_count", 0)

    now_str = datetime.now().strftime("%H:%M:%S")

    lines = [
        f"💓 系统心跳  {now_str}",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"⏱️  运行 {runtime_str}  循环 {loops}  触发 {triggers}",
        "",
    ]

    # ── 主标 + 跟随价格 ──
    if cur_price is not None:
        price_line = f"📊 {master_short} ${cur_price:.2f}"
        if sess_high and sess_low and sess_high > 0:
            dist_high = (cur_price - sess_high) / sess_high * 100
            dist_low = (cur_price - sess_low) / sess_low * 100
            price_line += (
                f"  (日 ${sess_low:.2f}~${sess_high:.2f}, "
                f"距高{dist_high:+.2f}% 距低{dist_low:+.2f}%)"
            )
        lines.append(price_line)

    # 跟随标的
    try:
        for tk_full in session.followers:
            tk = tk_full.replace("US.", "")
            tk_price = session.get_last_price(tk_full)

            pos = None
            try:
                if hasattr(session, "get_position"):
                    pos = session.get_position(tk_full)
                elif hasattr(session, "positions_snapshot"):
                    pos = session.positions_snapshot.get(tk_full)
            except Exception:
                pass

            if pos and pos.get("qty", 0) > 0:
                qty = pos.get("qty", 0)
                cost = pos.get("cost_price") or pos.get("cost_basis", 0)
                pl_pct = pos.get("pl_pct", 0)
                pl_val = pos.get("pl_val", 0) or 0
                price_str = f"${tk_price:.2f}" if tk_price is not None else "—"
                lines.append(f"   {tk}: {qty} 股 @${cost:.2f} 现价 {price_str}")
                if pl_val >= 0:
                    lines.append(f"      盈利 +${pl_val:.2f} ({pl_pct:+.2f}%)")
                else:
                    lines.append(f"      亏损 -${abs(pl_val):.2f} ({pl_pct:+.2f}%)")
            else:
                price_str = f"${tk_price:.2f}" if tk_price is not None else "—"
                lines.append(f"   {tk} {price_str}  · 空仓")
    except Exception as e:
        lines.append(f"   (跟随读取失败: {e})")

    lines.append("")

    # ── 5分钟指标 ──
    ind_ok = False
    rsi_val = None
    if indicators and indicators.get("data_ok"):
        ind_ok = True
        try:
            rsi_val = float(indicators.get("rsi_5m", 50))
        except Exception:
            rsi_val = 50

        macd = indicators.get("macd_hist", 0)
        vol = indicators.get("vol_ratio", 1)

        try:
            macd_f = float(macd)
            vol_f = float(vol)
        except Exception:
            macd_f = 0
            vol_f = 1

        if rsi_val >= 70:
            rsi_tag = "🔴 超买"
        elif rsi_val <= 35:
            rsi_tag = "🟢 超卖"
        elif rsi_val >= 65:
            rsi_tag = "🟡 偏高"
        elif rsi_val <= 40:
            rsi_tag = "🟡 偏低"
        else:
            rsi_tag = "⚪ 中性"

        lines.append("📈 5分钟指标:")
        lines.append(f"   RSI {rsi_val:.1f} {rsi_tag}   MACD柱 {macd_f:+.4f}   量比 {vol_f:.2f}x")
        lines.append("   " + format_kline_source_line(session=session, indicators=indicators))
        sub_line = format_subscription_detail()
        if sub_line:
            lines.append("   " + sub_line)

        candle = indicators.get("candle") or {}
        candle_name = candle.get("name") if isinstance(candle, dict) else None
        if candle_name:
            lines.append(f"   最新K线: {candle_name}")
    else:
        lines.append("📈 5分钟指标: K线加载中(30秒内完成)")
        lines.append("   " + format_kline_source_line(session=session, indicators=indicators))
    lines.append("")

    # ── v0.5.33: 📍 当前系统判断 ──
    # 优先级: 风险提醒 > 趋势锁定 > 观望
    data_quality = None
    data_untrusted = False
    try:
        quality_state = getattr(session, "_last_data_quality", None) or {}
        if isinstance(quality_state, dict) and quality_state:
            from types import SimpleNamespace
            data_quality = SimpleNamespace(**quality_state)
            data_untrusted = not bool(quality_state.get("can_direction", True))
        else:
            from .data_quality import evaluate_data_quality
            data_quality = evaluate_data_quality(session, indicators or {}, update_repeat=False)
            data_untrusted = bool(data_quality and not data_quality.can_direction)
    except Exception:
        data_quality = None
        data_untrusted = False

    if data_untrusted:
        lines.append("⚠️ 数据状态: 不可信")
        lines.append(f"   原因: {data_quality.reason}")
        lines.append("   方向信号: 已暂停")
        lines.append("   买入按钮: 已禁用")
        lines.append("   允许推送: 持仓止损 / 账户风险")
        lines.append("")

    sys_state_lines = _derive_system_state(session, indicators)
    if sys_state_lines:
        lines.extend(sys_state_lines)
        lines.append("")

    # ── 触发器距离阈值 ──
    if data_untrusted:
        lines.append("🎯 触发器距离: 已隐藏(数据不可信)")
        lines.append("")
        lines.append("💡 /ai_test 主动问 AI · /status 完整状态")
        return "\n".join(lines)

    try:
        from .swing_detector import DEFAULT_PARAMS as P
        lines.append("🎯 触发器距离:")

        # 持仓类
        has_position = False
        try:
            for tk_full in session.followers:
                pos = None
                try:
                    if hasattr(session, "get_position"):
                        pos = session.get_position(tk_full)
                    elif hasattr(session, "positions_snapshot"):
                        pos = session.positions_snapshot.get(tk_full)
                except Exception:
                    pass

                if pos and pos.get("qty", 0) > 0:
                    has_position = True
                    tk = tk_full.replace("US.", "")
                    pl_pct = pos.get("pl_pct", 0)
                    pl_val = pos.get("pl_val", 0)

                    if pl_pct >= P["profit_target_pct"] or pl_val >= P["profit_target_usd"]:
                        lines.append(f"   💰 {tk} 浮盈达标 ✅!")
                    else:
                        gap_pct = P["profit_target_pct"] - pl_pct
                        lines.append(
                            f"   💰 {tk} 浮盈 {pl_pct:+.2f}%  "
                            f"(差 {gap_pct:.2f}% 到 +{P['profit_target_pct']}%)"
                        )

                    # 回撤
                    try:
                        if hasattr(session, "get_peak_drawdown_pct"):
                            dd = session.get_peak_drawdown_pct(tk_full)
                            if dd is not None:
                                if dd <= -P["drawdown_pct"]:
                                    lines.append(f"   📉 {tk} 回撤 {dd:.2f}% ✅!")
                                else:
                                    gap = P["drawdown_pct"] + dd
                                    lines.append(
                                        f"   📉 {tk} 回撤 {dd:.2f}% (再跌 {gap:.2f}% 触发)"
                                    )
                    except Exception:
                        pass
        except Exception:
            pass

        if not has_position:
            lines.append("   💰 浮盈/回撤: N/A(跟随标的全空仓)")

        # 波段顶/底(RSI) — v0.5.33: P["rsi_overbought"/"rsi_oversold"] 不存在
        # 用真实硬门: swing_top_rsi_floor=70, rsi_oversold_strong=40
        if ind_ok and rsi_val is not None:
            top_th = P.get("swing_top_rsi_floor", 70)
            bot_th = P.get("rsi_oversold_strong", 40)
            if rsi_val >= top_th:
                lines.append(f"   🔴 波段顶 ⚠️ RSI {rsi_val:.1f} ≥ {top_th}(待K线配合)")
            elif rsi_val <= bot_th:
                lines.append(f"   🟢 波段底 ⚠️ RSI {rsi_val:.1f} ≤ {bot_th}(待K线配合)")
            else:
                gap_top = top_th - rsi_val
                gap_bot = rsi_val - bot_th
                if gap_top < gap_bot:
                    lines.append(f"   🔴 波段顶: RSI 还差 {gap_top:.1f} 到 {top_th}")
                else:
                    lines.append(f"   🟢 波段底: RSI 还差 {gap_bot:.1f} 到 {bot_th}")

        # 快速异动
        try:
            if hasattr(session, "get_price_change_pct"):
                chg_2m = session.get_price_change_pct(master, 120)
                if chg_2m is not None:
                    th = P["rapid_move_pct"]
                    if abs(chg_2m) >= th:
                        lines.append(f"   ⚡ 快速异动 ✅ 2分钟 {chg_2m:+.2f}%!")
                    else:
                        gap = th - abs(chg_2m)
                        lines.append(
                            f"   ⚡ 快速异动: 2分钟 {chg_2m:+.2f}% (差 {gap:.2f}% 到 ±{th}%)"
                        )
        except Exception:
            pass

        lines.append("")

    except Exception as e:
        lines.append(f"🎯 触发器: 读取异常 ({e})")
        lines.append("")

    # ── AI 智囊团 ──
    try:
        from .ai_advisor import get_today_cost
        cost = get_today_cost()

        ai_on = False
        try:
            from .focus_manager import is_ai_advise_enabled
            ai_on = is_ai_advise_enabled()
        except Exception:
            pass

        lines.append("🤖 AI 智囊团:")
        lines.append(f"   {'✅ 开启' if ai_on else '⏸️ 关闭'}   "
                     f"今日 ${cost.get('cost', 0):.4f} / {cost.get('calls', 0)} 次")
    except Exception as e:
        pass

    # ── 尾部提示 ──
    lines.append("")
    lines.append("💡 /ai_test 主动问 AI · /status 完整状态")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  定时心跳(后台线程)
# ══════════════════════════════════════════════════════════════════

def start_heartbeat_loop(send_tg_fn: Callable, interval_min: int = 15) -> str:
    """启动定时心跳推送"""
    global _heartbeat_enabled, _heartbeat_interval_min
    global _heartbeat_thread, _heartbeat_stop

    if _heartbeat_enabled:
        return (
            f"⏰ 心跳已在运行(每 {_heartbeat_interval_min} 分钟)\n"
            f"/heartbeat_off 关闭 · /heartbeat 立即查一次"
        )

    # 限制范围: 3 ~ 120 分钟
    interval_min = max(3, min(interval_min, 120))
    _heartbeat_interval_min = interval_min
    _heartbeat_enabled = True
    _heartbeat_stop = threading.Event()

    def _loop():
        # 启动时先推一次,确认心跳链路正常
        _push_heartbeat(send_tg_fn)
        while not _heartbeat_stop.wait(timeout=interval_min * 60):
            if not _heartbeat_enabled:
                break
            _push_heartbeat(send_tg_fn)

    _heartbeat_thread = threading.Thread(
        target=_loop, daemon=True, name="HeartbeatLoop"
    )
    _heartbeat_thread.start()

    return (
        f"✅ 定时心跳已开启 · 每 {interval_min} 分钟\n"
        f"\n"
        f"推送内容: 价格 / 指标 / 触发器距离 / 持仓 / AI 成本\n"
        f"💡 /heartbeat_off 关闭 · /heartbeat 立即查一次"
    )


def stop_heartbeat_loop() -> str:
    global _heartbeat_enabled, _heartbeat_stop
    if not _heartbeat_enabled:
        return "心跳本来就是关的"
    _heartbeat_enabled = False
    _heartbeat_stop.set()
    return "✅ 定时心跳已关闭\n(手动 /heartbeat 随时可用)"


def is_heartbeat_enabled() -> bool:
    return _heartbeat_enabled


def get_heartbeat_interval() -> int:
    return _heartbeat_interval_min


def _push_heartbeat(send_tg_fn: Callable):
    """内部:推一次心跳"""
    global _heartbeat_last_push
    try:
        from .focus_manager import _current_session, _indicators_cache_global
        msg = format_heartbeat(_current_session, _indicators_cache_global)
        if send_tg_fn:
            send_tg_fn(msg)
            _heartbeat_last_push = time.time()
    except Exception as e:
        print(f"  [heartbeat] push err: {e}")


# ══════════════════════════════════════════════════════════════════
#  对外接口
# ══════════════════════════════════════════════════════════════════

def get_heartbeat_text() -> str:
    """/heartbeat 指令调用"""
    try:
        from .focus_manager import _current_session, _indicators_cache_global
        return format_heartbeat(_current_session, _indicators_cache_global)
    except Exception as e:
        return f"❌ 读取状态失败: {e}"
