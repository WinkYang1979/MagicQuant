"""
════════════════════════════════════════════════════════════════════
  MagicQuant Focus — pusher.py
  VERSION : v0.5.37
  DATE    : 2026-05-13
  CHANGES :
    v0.5.30 (2026-05-13):
      - [SYNC] 与 swing_detector v0.5.30 / focus_manager v0.5.30 一并发布
              本次 pusher 无功能改动, 只刷 VERSION 常量与 SWING_VERSION
              便于 triggers.json 复盘按统一版本标识对齐
              | version bump only; aligns recorded swing_version/pusher_version
    v0.5.29 (2026-05-13):
      - [NEW] _fmt_stop_loss_warning: 亏损持仓专用文案模板
              · 标题:🛑 已破止损位 / 📉 接近止损位
              · 关键指标行明示"原止损 $X 已击穿 N%" 或 "距现价 N%"
              · leftover 兜底 hard_stop = stop if stop<current else current×0.98
                解决"止损价高于现价"的逻辑矛盾
              · 大白话解读:符合 CLAUDE.md 推送规范
              | dedicated formatter for stop_loss_warning trigger
              配合 swing_detector v0.5.27 — 亏损持仓走专用通道
      - [CHG] format_trigger_message 路由新增 stop_loss_warning 分支
    v0.5.28 (2026-05-13):
      - [FIX] _fmt_profit_target: 亏损版文案
              · 标题 emoji: near_stop→🛑 / 其他亏损→📉 / 盈利→💰
              · "目前盈利/实际盈利" 按 pl_val 符号换成"亏损"
              · drawdown 在亏损时 leftover 提示从"上移成本+0.2%保本"
                改为"跌破 $stop 全清止损"(成本之上的止损在亏损时立刻触发,无意义)
              · LAST_PLAN_CACHE.reason 同步分支盈/亏
              配合 swing_detector v0.5.26 — 亏损放行 near_stop/drawdown
      - [FIX-CRITICAL] _fmt_signal_with_conflict: targets 错配 bug
              · 之前用 master(RKLB) entry_price 算 T1/T2/stop,
                显示时却拼成 "RKLX 目标 T1 $XX" — 拿 RKLB 价位
                标注 follower 入场价旁,导致止损 $119.26 出现在
                RKLX 买入价 $75.72 上方 +57.5%,永远不会触发。
              · 修法:同时计算 follower 域 targets(以 follower 现价
                为入场价),传给 _build_action_plan 显示;master 域
                targets 仍存 _target_state[master] 供 target_advance
                检测使用,follower 域同步存 _target_state[follower]
                供 profit_target/target_advance 查 follower 持仓时使用。
    v0.5.26 (2026-05-12):
      - [NEW] _build_decision_context(): 推送时写入完整原始决策数据
              · kline_data: 最近 30 根 5m K 线 (含 is_today 标记)
              · indicators_raw: 完整指标 + RSI 最近 5 个历史值
              · price_context: 现价/day OHLC/prev_close/day_chg%
              · session_state: loop_count/cash/持仓数/master/followers
              写入 triggers.json 的 decision_context 字段
              供 verify_signals.py 精准复盘:数据/逻辑/时机三类问题分类
    v0.5.24 (2026-05-12):
      - [REWRITE] _fmt_profit_target 跟随 swing_detector v0.5.24:
                  按 sub_reason 写标题(near_target/broke_target/overbought_surge
                  /drawdown/near_stop)
                  按 tier (1/3, 1/2, 3/4, 全仓) 计算 sell_qty
                  文案必须包含"为什么 + 做什么 + 剩余怎么处理"
                  保留扣费后实际盈利行
    v0.5.22 (2026-05-12):
      - [FIX] 强度标签中文化: STRONG→强烈 / WEAK→一般，删除英文标签
              新增 _strength_cn() 辅助函数
      - [FIX] 持仓盈亏改为"目前盈利 $XX / 目前亏损 $XX"，加上成本价 @$XX
              _ticker_line / Scenario B / Scenario C / _fmt_profit_target / _fmt_drawdown
      - [FIX] 目标价/止损前加股票名: "{ticker} 目标 T1 $XX" / "{ticker} 止损 $XX"
              _fmt_price_targets 新增 ticker 参数，Scenario A/B/C 均传入
      - [FIX] 删除所有免责声明: "这是方向参考，不是下单指令" 等五处
    v0.5.21 (2026-05-12):
      - [FIX] _log_trigger(): record 新增 confidence 字段
              调用 _confidence_score(hit) 计算并写入，解决 triggers.json confidence=None 问题
    v0.5.20 (2026-05-11):
      - [FIX] 删除 ACCOUNT_SIZE_USD=20000 硬编码兜底;
              get_available_cash(None) 改为返回 0 + 打 ERROR 日志
      - [FIX] 仓位建议语言去除"买入/卖出"直接指令;
              Scenario A/B 改为"可考虑介入"/"可考虑顺势建" + "仓位由你决定"
      - [NEW] 信号推送加三行: 行情类型 / 方向偏向 / 免责声明"这是方向参考，不是下单指令"
      - [NEW] 风险提醒推送末尾加"这是风险提醒，不是卖出信号"声明
      - [NEW] _market_regime_label() / _action_intent_label() 辅助函数
    v0.5.19 (2026-05-11):
      - [NEW] 信号推送全面重设计 — "明确操作指令 + 利润最大化":
              信号强度进度条 _strength_bar() [████████░░] 85%
              仓位比例按信心分级: 90%+ → 九成仓 / 80-90% → 七成仓
                                  60-80% → 四成仓 / <60% → 三成仓
              _pct_by_conf() / _pct_label() 替代固定 STRONG/WEAK 仓位
      - [NEW] 目标价 T1/T2 重算:
              候选: 近20点最高(低)点 / 最近$5整数关口 / 当前价±ATR×2.0
              取距入场价最近的作 T1,次近的作 T2
              止损: 当前价 ± ATR×1.5
      - [NEW] _fmt_price_targets() 完整重写 — T1/T2/止损/盈亏比一行展示
      - [NEW] _calc_price_targets() 重写 — ATR估算 + 多候选价位去重
      - [NEW] 仓位方案 Scenario A/B 使用新信心-仓位体系
      - [NEW] 新触发器推送格式: near_resistance / near_support /
              overbought_surge / large_day_gain
    v0.5.14 (2026-05-06):
      - [NEW] _calc_price_targets(): 波峰/波谷预测
    v0.5.13 (2026-04-23):
      - [NEW] _log_trigger() 自动日志
    v0.5.12 (2026-04-23):
      - [NEW] 往返手续费估算 / 信心指数 / scenario B Step 2 重写
    v0.5.11 (2026-04-22):
      - [NEW] activity_profile tag
  DEPENDS :
    context.py           ≥ v0.5.2
    swing_detector.py    ≥ v0.5.21
    market_clock.py      ≥ v0.2.0
    activity_profile.py  ≥ v0.1.0
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

import csv
import math
import os
import time
from datetime import datetime
from typing import Optional

try:
    from .data_quality import (
        evaluate_data_quality,
        log_blocked_signal,
        trigger_allows_bad_data,
        trigger_requires_fresh_data,
    )
    from .kline_display import inject_kline_source_line
except ImportError:
    import importlib.util
    import sys
    from pathlib import Path
    _dq_path = Path(__file__).resolve().parent / "data_quality.py"
    _dq_spec = importlib.util.spec_from_file_location("mq_focus_data_quality", _dq_path)
    _dq_mod = importlib.util.module_from_spec(_dq_spec)
    sys.modules["mq_focus_data_quality"] = _dq_mod
    _dq_spec.loader.exec_module(_dq_mod)
    evaluate_data_quality = _dq_mod.evaluate_data_quality
    log_blocked_signal = _dq_mod.log_blocked_signal
    trigger_allows_bad_data = _dq_mod.trigger_allows_bad_data
    trigger_requires_fresh_data = _dq_mod.trigger_requires_fresh_data
    _kd_path = Path(__file__).resolve().parent / "kline_display.py"
    _kd_spec = importlib.util.spec_from_file_location("mq_focus_kline_display", _kd_path)
    _kd_mod = importlib.util.module_from_spec(_kd_spec)
    sys.modules["mq_focus_kline_display"] = _kd_mod
    _kd_spec.loader.exec_module(_kd_mod)
    inject_kline_source_line = _kd_mod.inject_kline_source_line

VERSION = "v0.5.37"
SWING_VERSION = "v0.5.37"

_DAILY_ATR_CACHE = {}

try:
    from .pairs import get_long_tools, get_short_tools, classify_follower
except ImportError:
    def get_long_tools(m): return []
    def get_short_tools(m): return []
    def classify_follower(m, f): return "unknown"


def _strength_cn(strength: str) -> str:
    """v0.5.22: STRONG/WEAK → 强烈/一般"""
    return "强烈" if strength == "STRONG" else "一般"


# ══════════════════════════════════════════════════════════════════
#  v0.5.12 Moomoo AU 手续费估算
# ══════════════════════════════════════════════════════════════════
def _estimate_roundtrip_fee(qty: int, price: float) -> float:
    """
    估算 Moomoo AU 往返手续费(美元)
    基于 2026-04 交割单实测:
        买入固定: Platform $0.99 + Settlement $0.30 = $1.29
        卖出浮动: Platform $0.99 + Settlement $0.30 + SEC + TAF
                 SEC = 成交额 × 0.0000278
                 TAF = min(max(0.01, qty × 0.000166), 8.30)
    """
    if qty <= 0 or price <= 0:
        return 0.0
    buy = 1.29
    notional = price * qty
    sec = notional * 0.0000278
    taf = max(0.01, min(8.30, qty * 0.000166))
    sell = 0.99 + 0.30 + sec + taf
    return round(buy + sell, 2)


def _estimate_single_side_fee(qty: int, price: float, side: str = "sell") -> float:
    """估算单边手续费(买或卖)"""
    if qty <= 0 or price <= 0:
        return 0.0
    if side == "buy":
        return 1.29
    # sell
    notional = price * qty
    sec = notional * 0.0000278
    taf = max(0.01, min(8.30, qty * 0.000166))
    return round(0.99 + 0.30 + sec + taf, 2)


# ══════════════════════════════════════════════════════════════════
#  v0.5.12 信心指数
# ══════════════════════════════════════════════════════════════════
def _confidence_score(hit) -> int:
    """
    基于 hit["data"] 已有字段打分 0-100。
    不引入新数据源。
    """
    score = 50  # 基准

    strength = hit.get("strength", "WEAK")
    if strength == "STRONG":
        score += 20

    data = hit.get("data", {}) or {}
    rsi = data.get("rsi")
    direction = hit.get("direction", "")

    cap_reasons = data.get("cap_reasons")
    if not isinstance(cap_reasons, list):
        cap_reasons = []
        data["cap_reasons"] = cap_reasons

    def _add_cap_reason(reason: str) -> None:
        if reason not in cap_reasons:
            cap_reasons.append(reason)

    def _rsi_slope() -> float | None:
        try:
            hist = data.get("rsi_history") or []
            if len(hist) < 3:
                return None
            recent = [float(v) for v in hist[-3:]]
            return recent[-1] - recent[0]
        except Exception:
            return None

    rsi_slope = _rsi_slope()

    if rsi is not None:
        try:
            r = float(rsi)
            if direction == "long":
                if 50 < r < 65:
                    # v0.5.36 hotfix: r >= 55 → r >= 50,抓住"刚滚到 55 下方"的失速
                    # (97 案例 11:02 RSI 54.5 在旧阈值下漏掉)。
                    if rsi_slope is not None and rsi_slope < -2 and r >= 50:
                        _add_cap_reason("rsi_rolling_over")
                    else:
                        score += 15
                elif 45 < r <= 50: score += 10
                elif r >= 75:      score -= 20
                elif r >= 70:      score -= 10
            elif direction == "short":
                if 35 < r < 50:
                    # v0.5.36 hotfix: r <= 45 → r <= 50,对称放宽到整个 short-friendly 区。
                    if rsi_slope is not None and rsi_slope > 2 and r <= 50:
                        _add_cap_reason("rsi_rebounding")
                    else:
                        score += 15
                elif 50 <= r < 55: score += 10
                elif r <= 25:      score -= 20
                elif r <= 30:      score -= 10
        except (TypeError, ValueError):
            pass

    vol_ratio = data.get("vol_ratio", 1)
    if vol_ratio is not None:
        try:
            vr = float(vol_ratio)
            if vr >= 1.5:    score += 10
            elif vr >= 1.2:  score += 5
            elif vr < 0.8:   score -= 5
        except (TypeError, ValueError):
            pass

    try:
        cap = data.get("confidence_cap")
        if cap is not None and score > float(cap):
            score = int(float(cap))
            _add_cap_reason("post_top_warning_cap")
    except (TypeError, ValueError):
        pass

    return max(0, min(100, score))


def _signal_market_session(session=None, hit=None) -> str:
    """Return market session for signal display. / 获取信号时段。"""
    if session is not None:
        status = getattr(session, "market_status", None)
        if status:
            return str(status)
    data = (hit or {}).get("data", {}) or {}
    status = data.get("market_session")
    if status:
        return str(status)
    try:
        from .market_clock import get_market_status
        return str(get_market_status() or "unknown")
    except Exception:
        return "unknown"


def _premarket_low_volume_downgrade(hit, session, direction: str, conf: int) -> tuple[int, bool]:
    """Cap pre-market low-volume long signals. / 盘前低量看多降级。"""
    data = (hit or {}).get("data", {}) or {}
    try:
        vol_ratio = float(data.get("vol_ratio", 1) or 1)
    except (TypeError, ValueError):
        vol_ratio = 1
    market_session = _signal_market_session(session, hit)
    should_downgrade = (
        market_session == "pre"
        and direction == "long"
        and vol_ratio < 0.8
        and conf > 65
    )
    if should_downgrade:
        return 65, True
    return conf, False


def _confidence_emoji(score: int) -> str:
    """给信心指数配表情"""
    if score >= 85:   return "🔥"
    if score >= 70:   return "💪"
    if score >= 55:   return "👍"
    if score >= 40:   return "🤔"
    return "⚠️"


# ══════════════════════════════════════════════════════════════════
#  v0.5.19 信号强度进度条 / 信心→仓位映射
# ══════════════════════════════════════════════════════════════════
def _strength_bar(pct: int, width: int = 10) -> str:
    """生成更易读的信心展示 / Render readable confidence."""
    filled = max(0, min(width, round(pct / 100 * width)))
    empty = width - filled
    if pct >= 85:
        label = "高"
    elif pct >= 65:
        label = "中"
    else:
        label = "低"
    return f"{pct}%｜{label}｜{'█' * filled}{'░' * empty}"


def _pct_by_conf(conf: int) -> float:
    """信心指数 → 仓位比例 (占可用现金)"""
    if conf >= 90: return 0.90
    if conf >= 80: return 0.70
    if conf >= 60: return 0.40
    return 0.30


def _pct_label(conf: int) -> str:
    """信心标签 / Confidence label."""
    if conf >= 90: return "高信心参考"
    if conf >= 80: return "中高信心参考"
    if conf >= 60: return "中等信心参考"
    return "低信心观察"


def _market_regime_label(hit: dict) -> str:
    """从 hit data 推断行情类型 / Infer market regime."""
    d = hit.get("data", {}) or {}
    has_ind = d.get("has_indicators", False) or any(
        d.get(k) is not None for k in ("rsi", "rsi_5m", "vol_ratio", "vwap")
    )
    if not has_ind:
        return "数据不足"
    vol_ratio = d.get("vol_ratio", 1) or 1
    rsi       = d.get("rsi", d.get("rsi_5m", 50)) or 50
    if vol_ratio >= 1.5 and 40 < rsi < 70:
        return "趋势偏强"
    if vol_ratio < 0.8:
        return "量能偏弱"
    return "震荡观察"


def _action_intent_label(conf: int, direction: str) -> str:
    """信心 + 方向 -> 保守动作提示 / Conservative action intent."""
    if direction == "long":
        if conf >= 80: return "偏多条件较强"
        if conf >= 60: return "偏多条件出现"
        return "低信号"
    if direction == "short":
        if conf >= 80: return "偏空条件较强"
        if conf >= 60: return "偏空条件出现"
        return "低信号"
    return "低信号"


# ══════════════════════════════════════════════════════════════════
#  交易参数
# ══════════════════════════════════════════════════════════════════
STRONG_POSITION_PCT = 0.70
WEAK_POSITION_PCT   = 0.50
MAX_BUDGET_USD      = 15000
MIN_BUDGET_USD      = 2000      # 开新仓最低资金
MIN_ADD_BUDGET_USD  = 500       # v0.5.9:加仓最低资金(低很多,能买几股就行)
LEVERAGED_FOLLOWERS = {"RKLX", "RKLZ", "TSLL"}
MIN_INVALID_GAP_PCT = 1.20      # 2x 工具方向信号最小失效距离 / min invalidation gap for leveraged tools
NEAR_INVALID_GAP_PCT = 0.80     # 贴近失效价时不再提示追入 / no chase when close to invalidation

STRONG_TARGET_USD = 100
STRONG_STOP_USD   = 50
WEAK_TARGET_USD   = 50
WEAK_STOP_USD     = 30

PROFIT_SMALL_USD  = 30
PROFIT_BIG_USD    = 100

LAST_PLAN_CACHE = {}


# ══════════════════════════════════════════════════════════════════
#  None 安全格式化
# ══════════════════════════════════════════════════════════════════
def _money(x, fmt=".2f", default="—"):
    if x is None:
        return default
    try:
        return f"${float(x):{fmt}}"
    except (ValueError, TypeError):
        return default

def _format_hold_duration(hold_sec) -> str:
    """格式化持仓时长,不隐藏小时/分钟余量。 / Keep hour/min remainder visible."""
    try:
        hold_sec = max(0, int(hold_sec or 0))
    except (TypeError, ValueError):
        hold_sec = 0
    hold_min = hold_sec // 60
    if hold_min < 60:
        return f"{hold_min} 分钟"
    hours = hold_min // 60
    mins = hold_min % 60
    if hours < 24:
        return f"{hours} 小时{mins} 分"
    days = hours // 24
    rem_hours = hours % 24
    if rem_hours:
        return f"{days} 天{rem_hours} 小时"
    return f"{days} 天"

def _num(x, fmt=".2f", default="—"):
    if x is None:
        return default
    try:
        return f"{float(x):{fmt}}"
    except (ValueError, TypeError):
        return default

def _pct(x, fmt="+.2f", default="—"):
    if x is None:
        return default
    try:
        return f"{float(x):{fmt}}%"
    except (ValueError, TypeError):
        return default


# ══════════════════════════════════════════════════════════════════
#  时间戳 / footer
# ══════════════════════════════════════════════════════════════════
def _market_tag():
    """返回当前市场时段标签,如 '🌃夜盘',失败返回空串"""
    try:
        from .market_clock import get_market_status, market_status_tag
        return market_status_tag(get_market_status())
    except Exception:
        return ""

def _profile_tag():
    """
    返回当前机会密度标签(含事件/周一加速)
    形如:'🔥黄金 🧙 ⚡周一',失败返回空串
    """
    try:
        from .activity_profile import get_current_profile
        p = get_current_profile()
        return p.get("tag", "") or ""
    except Exception:
        return ""

def _timestamp_line(session, ticker=None):
    """
    第一行抬头:
      📡 23:14:22  ·  📈 23:14:20  ·  🔥黄金 🧙 ⚡周一

    v0.5.11: profile tag 已包含市场时段 emoji,所以不再重复显示 market_tag
    """
    push_time = datetime.now().strftime("%H:%M:%S")
    quote_time = "—"
    if session and ticker and hasattr(session, "get_quote_update_time"):
        qt = session.get_quote_update_time(ticker)
        if qt:
            quote_time = qt[-8:]
    # 优先用 profile tag(包含 🔥/🌃 + 事件 + 周一)
    # 若 activity_profile 不可用,回落到 market tag
    tag = _profile_tag() or _market_tag()
    tag_part = f"  ·  {tag}" if tag else ""
    return f"📡 {push_time}  ·  📈 {quote_time}{tag_part}"

def _footer():
    """
    v0.5.11: footer 加入 profile 简要信息,便于诊断
    例:"⚙️ swing v0.5.4 · pusher v0.5.12 · 轮询 1.0s · 阈值×0.75"
    """
    try:
        from .activity_profile import get_current_profile
        p = get_current_profile()
        poll = p.get("poll_sec", 0)
        scale = p.get("scale")
        extra = f" · 轮询 {poll}s"
        if scale is not None:
            extra += f" · 阈值×{scale:.2f}"
    except Exception:
        extra = ""
    return f"⚙️ swing {SWING_VERSION} · pusher {VERSION}{extra}"

def _manual_cmd_line(hit, session=None):
    trigger = hit.get("trigger")
    ticker_short = hit.get("ticker", "").replace("US.", "")
    direction = hit.get("direction")
    cmds = []
    if trigger in ("direction_trend", "intraday_reversal", "swing_top", "swing_bottom"):
        etf = "RKLZ" if direction == "short" else "RKLX" if direction == "long" else None
        if etf:
            cmds.append(f"/order {etf}")
    elif trigger in ("profit_target_hit", "drawdown_from_peak"):
        cmds.append(f"/order {ticker_short}")
    cmds.append(f"/detail {ticker_short}")
    return "💬 手动:  " + "  ·  ".join(cmds) if cmds else None

def _ticker_line(session, ticker, with_position=True):
    if not session:
        return ticker.replace("US.", "")
    short = ticker.replace("US.", "")
    price = session.get_last_price(ticker)
    day_chg = None
    if hasattr(session, "get_day_change_pct"):
        day_chg = session.get_day_change_pct(ticker)
    line = f"{short:5s} {_money(price)}"
    if day_chg is not None:
        line += f" ({day_chg:+.2f}%)"
    if with_position:
        pos = session.get_position(ticker)
        if pos and pos.get("qty", 0) > 0:
            qty  = pos["qty"]
            pl   = pos.get("pl_val", 0) or 0
            cost = pos.get("cost_price", 0) or 0
            pl_word = "目前盈利" if pl >= 0 else "目前亏损"
            # v0.5.22: 显示成本价 + 中文盈亏 + 扣费后真实盈亏
            if price and cost > 0:
                fee = _estimate_roundtrip_fee(qty, price)
                true_pl = pl - fee
                true_word = "盈利" if true_pl >= 0 else "亏损"
                line += (f"  💼 {qty:.0f}股 @{_money(cost)}"
                         f"  {pl_word} ${abs(pl):.0f}"
                         f" (扣费后{true_word} ${abs(true_pl):.0f})")
            else:
                line += f"  💼 {qty:.0f}股 @{_money(cost)}  {pl_word} ${abs(pl):.0f}"
    return line

def _safe_float(value):
    """Best-effort float parse. / 尽量把输入转成 float。"""
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta_word(delta: float) -> str:
    """Display direction word. / 价格变化方向文字。"""
    if delta > 0:
        return "提升"
    if delta < 0:
        return "下降"
    return "持平"


def _quote_prev_close(session, ticker, current=None):
    """Read previous close from quote snapshot, with day-change fallback. / 读取昨收价。"""
    if not session:
        return None
    quote = (getattr(session, "quote_snapshot", {}) or {}).get(ticker, {}) or {}
    prev_close = _safe_float(quote.get("prev_close"))
    if prev_close and prev_close > 0:
        return prev_close

    # Fallback: derive prev_close from current price and day change when Futu snapshot lacks it.
    # 兜底: 快照没有昨收时, 用现价和日内涨跌幅反推。
    day_chg = None
    try:
        if hasattr(session, "get_day_change_pct"):
            day_chg = _safe_float(session.get_day_change_pct(ticker))
    except Exception:
        day_chg = None
    current = _safe_float(current)
    if current and day_chg is not None:
        denom = 1.0 + day_chg / 100.0
        if denom > 0:
            return current / denom
    return None


def _delta_ticker_label(ticker: str) -> str:
    """Short ticker label for delta display. / 价格变化展示用短代码。"""
    return (ticker or "").replace("US.", "")


def build_price_delta_lines(
    session,
    ticker,
    current=None,
    include_last_signal=True,
    label=None,
    include_prev_close=True,
    include_accuracy=False,
):
    """
    Build price-change lines for signal/heartbeat display.
    生成“较昨收 / 较上次信号价”的展示行, 只用于复盘辅助, 不参与策略判断。
    """
    if not session or not ticker:
        return []
    current = _safe_float(current)
    if current is None:
        try:
            current = _safe_float(session.get_last_price(ticker))
        except Exception:
            current = None
    if current is None or current <= 0:
        return []

    lines = []
    prefix = f"{label or _delta_ticker_label(ticker)}: "
    if include_prev_close:
        prev_close = _quote_prev_close(session, ticker, current=current)
    else:
        prev_close = None
    if include_prev_close and prev_close and prev_close > 0:
        delta = current - prev_close
        pct = delta / prev_close * 100.0
        lines.append(
            f"{prefix}现价 {_money(current)}  较昨收 {_money(prev_close)}  "
            f"{_delta_word(delta)} {_money(abs(delta))} ({pct:+.2f}%)"
        )
    else:
        day_chg = None
        if include_prev_close:
            try:
                if hasattr(session, "get_day_change_pct"):
                    day_chg = _safe_float(session.get_day_change_pct(ticker))
            except Exception:
                day_chg = None
        if include_prev_close and day_chg is not None:
            lines.append(f"{prefix}现价 {_money(current)}  较昨收 {day_chg:+.2f}%")
        else:
            lines.append(f"{prefix}现价 {_money(current)}")

    if include_last_signal:
        state = getattr(session, "_last_signal_price", {}) or {}
        last = state.get(ticker)
        if isinstance(last, dict):
            last_price = _safe_float(last.get("price"))
        else:
            last_price = _safe_float(last)
        if last_price and last_price > 0:
            delta = current - last_price
            pct = delta / last_price * 100.0
            lines.append(
                f"{prefix}上次信号价 {_money(last_price)}  "
                f"{_delta_word(delta)} {_money(abs(delta))} ({pct:+.2f}%)"
            )
            if include_accuracy and isinstance(last, dict):
                direction = last.get("direction")
                is_related = bool(last.get("related_to"))
                if direction in ("long", "short"):
                    expected_up = is_related or direction == "long"
                    ok = delta >= 0 if expected_up else delta <= 0
                    verdict = "✅ 信号有效" if ok else "⚠️ 信号偏离"
                    expected = "应上涨" if expected_up else "应下跌"
                    lines.append(f"{prefix}信号跟踪: {verdict}（{expected}，当前 {pct:+.2f}%）")
    return lines


def _related_delta_tickers(session, ticker, direction=None):
    """Return master + relevant tool tickers for delta display. / 返回主标和相关操作工具。"""
    if not session or not ticker:
        return []
    tickers = [ticker]
    followers = list(getattr(session, "followers", []) or [])
    target = None
    if direction in ("long", "short"):
        try:
            target = pick_target_follower(session, direction)
        except Exception:
            target = None
    elif ticker == getattr(session, "master", None) and "US.RKLX" in followers:
        target = "US.RKLX"
    if target and target not in tickers:
        tickers.append(target)
    return tickers


def build_related_price_delta_lines(
    session,
    ticker,
    current=None,
    direction=None,
    include_prev_close=True,
    include_accuracy=False,
):
    """Build delta lines for RKLB plus the traded tool. / 生成 RKLB + 操作工具的价格变化行。"""
    lines = []
    for tk in _related_delta_tickers(session, ticker, direction=direction):
        tk_current = current if tk == ticker else None
        lines.extend(
            build_price_delta_lines(
                session,
                tk,
                current=tk_current,
                include_prev_close=include_prev_close,
                include_accuracy=include_accuracy,
            )
        )
    return lines


def inject_price_delta_lines(text, session=None, ticker=None, current=None, direction=None):
    """Insert price delta lines near the top of a pushed message. / 在推送顶部插入价格变化行。"""
    if not text or not session or not ticker:
        return text
    if "上次信号价:" in text:
        return text
    delta_lines = build_related_price_delta_lines(session, ticker, current=current, direction=direction)
    if not delta_lines:
        return text

    lines = text.splitlines()
    insert_at = None
    for idx, line in enumerate(lines):
        if "━━━━━━━━" in line:
            insert_at = idx + 1
            break
    if insert_at is None:
        insert_at = min(2, len(lines))
    return "\n".join(lines[:insert_at] + delta_lines + lines[insert_at:])


def remember_signal_price(session, hit):
    """
    Remember sent signal price for later delta display.
    发送成功后记录信号价, 下一条信号/心跳展示“较上次信号价”。
    """
    if not session or not hit:
        return
    ticker = hit.get("ticker") or getattr(session, "master", None)
    if not ticker:
        return
    data = hit.get("data", {}) or {}
    price = _safe_float(data.get("current") or data.get("price"))
    if price is None:
        try:
            price = _safe_float(session.get_last_price(ticker))
        except Exception:
            price = None
    if price is None or price <= 0:
        return
    try:
        state = getattr(session, "_last_signal_price", None)
        if not isinstance(state, dict):
            state = {}
            session._last_signal_price = state
        now = time.time()
        payload = {
            "price": price,
            "ts": now,
            "trigger": hit.get("trigger"),
            "direction": hit.get("direction"),
        }
        state[ticker] = payload
        for related in _related_delta_tickers(session, ticker, direction=hit.get("direction")):
            if related == ticker:
                continue
            try:
                related_price = _safe_float(session.get_last_price(related))
            except Exception:
                related_price = None
            if related_price and related_price > 0:
                state[related] = {
                    **payload,
                    "price": related_price,
                    "related_to": ticker,
                }
    except Exception:
        pass

def _trio_block(session):
    if not session:
        return []
    lines = [_ticker_line(session, session.master, with_position=False)]
    for f in session.followers:
        lines.append(_ticker_line(session, f, with_position=True))
    return lines

def get_available_cash(session) -> float:
    if session is not None:
        cash = getattr(session, "cash_available", None)
        if cash is not None and cash >= 0:
            return float(cash)
    # v0.5.20: 禁止硬编码金额兜底，返回 0 强制手动确认
    print("  [pusher] ❌ session.cash_available=None, 返回 0 — 仓位建议不可用，请手动确认")
    return 0.0


# ══════════════════════════════════════════════════════════════════
#  交易计划
# ══════════════════════════════════════════════════════════════════
def calc_trade_plan(entry_price, budget_usd, target_profit_usd, stop_loss_usd,
                   min_budget=None):
    if entry_price is None or entry_price <= 0:
        return None
    min_b = min_budget if min_budget is not None else MIN_BUDGET_USD
    if budget_usd < min_b:
        return {
            "insufficient_cash": True,
            "budget_usd": budget_usd,
            "min_required": min_b,
        }
    qty = max(1, int(budget_usd / entry_price))
    notional = round(qty * entry_price, 2)
    target = round(entry_price + target_profit_usd / qty, 2)
    stop   = round(entry_price - stop_loss_usd / qty, 2)
    tgt_pct  = round((target - entry_price) / entry_price * 100, 2)
    stop_pct = round((entry_price - stop)   / entry_price * 100, 2)
    rr = round(target_profit_usd / stop_loss_usd, 2) if stop_loss_usd > 0 else 0
    return {
        "insufficient_cash": False,
        "entry": round(entry_price, 2), "qty": qty, "notional": notional,
        "target": target, "stop": stop,
        "target_usd": target_profit_usd, "stop_usd": stop_loss_usd,
        "target_pct": tgt_pct, "stop_pct": stop_pct,
        "rr": rr, "budget_usd": budget_usd,
    }

def plan_by_strength(entry_price, strength, session=None):
    cash = get_available_cash(session)
    if strength == "STRONG":
        budget = min(cash * STRONG_POSITION_PCT, MAX_BUDGET_USD)
        return calc_trade_plan(entry_price, budget, STRONG_TARGET_USD, STRONG_STOP_USD)
    budget = min(cash * WEAK_POSITION_PCT, MAX_BUDGET_USD)
    return calc_trade_plan(entry_price, budget, WEAK_TARGET_USD, WEAK_STOP_USD)

def pick_target_follower(session, direction):
    if session is None or direction not in ("long", "short"):
        return None
    candidates = {
        "long":  get_long_tools(session.master),
        "short": get_short_tools(session.master),
    }[direction]
    for tk in candidates:
        if tk in session.followers:
            return tk
    for tk in session.followers:
        if classify_follower(session.master, tk) == direction:
            return tk
    return candidates[0] if candidates else None


# ══════════════════════════════════════════════════════════════════
#  仓位冲突分析
# ══════════════════════════════════════════════════════════════════
def analyze_position_conflict(session, signal_direction: str) -> dict:
    same_etf    = pick_target_follower(session, signal_direction)
    reverse_dir = "short" if signal_direction == "long" else "long"
    reverse_etf = pick_target_follower(session, reverse_dir)

    same_pos = session.get_position(same_etf) if (session and same_etf) else None
    rev_pos  = session.get_position(reverse_etf) if (session and reverse_etf) else None

    has_same = bool(same_pos and same_pos.get("qty", 0) > 0)
    has_rev  = bool(rev_pos and rev_pos.get("qty", 0) > 0)

    if has_same and has_rev:
        scenario = "D"
    elif has_rev:
        scenario = "B"
    elif has_same:
        scenario = "C"
    else:
        scenario = "A"

    return {
        "scenario":    scenario,
        "same_etf":    same_etf,
        "reverse_etf": reverse_etf,
        "same_pos":    same_pos if has_same else None,
        "reverse_pos": rev_pos  if has_rev  else None,
    }


def _build_action_plan(session, signal_direction, strength, conflict,
                       conf: int = 70, targets: dict = None):
    """
    v0.5.19: 加入 conf(信心指数) 和 targets(T1/T2/止损)
    Scenario A: 空仓时使用信心→仓位比例 + T1/T2/止损展示
    Scenario B: 反向持仓时 Step 2 也使用信心→仓位比例
    """
    scenario   = conflict["scenario"]
    same_etf   = conflict["same_etf"]
    rev_etf    = conflict["reverse_etf"]
    same_short = (same_etf or "").replace("US.", "")
    rev_short  = (rev_etf  or "").replace("US.", "")
    targets    = targets or {}

    lines = []
    buttons = []
    caches = []

    same_price = session.get_last_price(same_etf) if (session and same_etf) else None

    def _reference_lines(ticker_short: str, price: float | None, target_data: dict) -> list[str]:
        """Direction signal copy: entry/invalid price only, no sizing noise."""
        if not price:
            return [f"📍 参考入场: {ticker_short} 报价失败,请手动确认"]
        stop = target_data.get("stop") if target_data else None
        invalid_gap_pct = None
        if stop:
            try:
                invalid_gap_pct = abs(float(price) - float(stop)) / float(price) * 100
            except (TypeError, ValueError, ZeroDivisionError):
                invalid_gap_pct = None

        if invalid_gap_pct is not None and invalid_gap_pct <= NEAR_INVALID_GAP_PCT:
            out = [
                f"📍 <b>入场状态</b>: {ticker_short} {_money(price)} 已贴近失效价",
                f"⚠️ <b>失效价</b>: 跌破 {_money(stop)}（仅差 {invalid_gap_pct:.1f}%）",
                "   方向仍在，但这里不追；等重新站稳或回踩不破。",
            ]
        else:
            out = [f"📍 <b>参考入场</b>: {ticker_short} {_money(price)} 附近"]
            if stop:
                gap_txt = f"（距离 {invalid_gap_pct:.1f}%）" if invalid_gap_pct is not None else ""
                out.append(f"🧭 <b>失效价</b>: {ticker_short} 跌破 {_money(stop)}{gap_txt}")
        tgt_str = _fmt_price_targets(target_data, signal_direction, price, ticker_short)
        if tgt_str:
            out.append(tgt_str)
        return out

    # ── A 空仓 ────────────────────────────────────────────
    if scenario == "A":
        if not same_price:
            lines.append(f"📋 {same_short}(报价失败,请手动确认)")
            return {"scenario": "A", "lines": lines, "buttons": [], "caches": []}

        lines += _reference_lines(same_short, same_price, targets)

    # ── B 反向持仓 ──(v0.5.12 重写:双路建议 + 释放现金重算)──
    elif scenario == "B":
        rev_pos    = conflict["reverse_pos"]
        rev_qty    = rev_pos["qty"]
        rev_pl     = rev_pos.get("pl_val", 0) or 0
        rev_cost   = rev_pos.get("cost_price", 0) or 0
        rev_cur    = session.get_last_price(rev_etf) or rev_pos.get("current_price", 0)
        sell_price = round(rev_cur * 0.998, 2)

        # v0.5.12: 算释放现金 + 手续费 + 真实亏损
        sell_fee = _estimate_single_side_fee(rev_qty, sell_price, "sell")
        buy_fee_historical = _estimate_single_side_fee(rev_qty, rev_cost, "buy")
        roundtrip_fee = round(buy_fee_historical + sell_fee, 2)
        true_loss = rev_pl - roundtrip_fee
        released_cash_gross = rev_qty * sell_price
        released_cash_net = round(released_cash_gross - sell_fee, 2)

        current_cash = get_available_cash(session)
        total_after_sell = round(current_cash + released_cash_net, 2)

        # Step 1 详细展示
        rev_pl_word   = "目前盈利" if rev_pl >= 0 else "目前亏损"
        true_loss_word = "实际盈利" if true_loss >= 0 else "实际亏损"
        lines += [
            f"⚠️ <b>方向冲突!持有反向头寸 {rev_short}</b>",
            f"{rev_short}: {rev_qty:.0f}股 @{_money(rev_cost)}  "
            f"{rev_pl_word} ${abs(rev_pl):.0f}",
            f"         手续费 ~${roundtrip_fee:.2f}  →  {true_loss_word} ${abs(true_loss):.0f}",
            f"",
            f"🅰️ <b>Step 1 — 先平 {rev_short}</b>",
            f"卖 {rev_qty:.0f} 股 @{_money(sell_price)}",
            f"释放净现金 ~${released_cash_net:,.0f}",
        ]
        caches.append((rev_short, {
            "action": "SELL", "ticker": rev_short,
            "qty": rev_qty, "price": sell_price,
            "reason": f"先平反向,准备买 {same_short}",
        }))

        # Step 2: 用 total_after_sell 重新算建仓预算 (v0.5.19: 改用信心→仓位比例)
        if same_price and same_price > 0:
            pct = _pct_by_conf(conf)
            pct_lbl = _pct_label(conf)
            budget = min(total_after_sell * pct, MAX_BUDGET_USD)
            t1_price   = targets.get("t1")
            stop_price = targets.get("stop")
            if budget >= MIN_BUDGET_USD:
                qty2 = max(1, int(budget / same_price))
                notional2 = round(qty2 * same_price, 2)
                rest_after_buy = total_after_sell - notional2
                lines += [
                    f"",
                    f"🅱️ <b>Step 2 — 可考虑顺势建 {same_short}</b>",
                    f"总现金: ${current_cash:,.0f}(现)+ ${released_cash_net:,.0f}(释放)= ${total_after_sell:,.0f}",
                    f"📋 {same_short} × {qty2} 股 @{_money(same_price)}  ({pct_lbl} ${notional2:,.0f})",
                    f"   仓位由你决定",
                ]
                tgt_str2 = _fmt_price_targets(targets, signal_direction, same_price, same_short)
                if tgt_str2:
                    lines.append(tgt_str2)
                lines.append(f"剩余 ~${rest_after_buy:,.0f}")
                caches.append((same_short, {
                    "action": "BUY", "ticker": same_short,
                    "price": same_price, "qty": qty2,
                    "entry": same_price, "notional": notional2,
                    "target": t1_price, "stop": stop_price,
                }))
                buttons += [
                    [{"text": f"1️⃣ 卖 {rev_qty:.0f}股 {rev_short}",
                      "callback_data": f"focus_order_{rev_short}"}],
                    [{"text": f"2️⃣ 买 {qty2}股 {same_short}",
                      "callback_data": f"focus_order_{same_short}"}],
                ]
            else:
                # 资金不足
                lines += [
                    f"",
                    f"🅱️ <b>Step 2 — 资金不足,平仓后观望</b>",
                    f"平仓后总现金 ${total_after_sell:,.0f} < ${MIN_BUDGET_USD:,.0f} 最低建仓门槛",
                    f"建议:先平 Step 1 保留子弹,等下一个更强信号",
                ]
                buttons.append([{"text": f"1️⃣ 卖 {rev_qty:.0f}股 {rev_short}",
                                 "callback_data": f"focus_order_{rev_short}"}])
        else:
            # same_price 缺失(报价失败)
            lines += [
                f"",
                f"🅱️ <b>Step 2 — {same_short} 报价异常</b>",
                f"平仓后有 ${total_after_sell:,.0f} 现金可用",
                f"请手动查 {same_short} 现价决定仓位",
            ]
            buttons.append([{"text": f"1️⃣ 卖 {rev_qty:.0f}股 {rev_short}",
                             "callback_data": f"focus_order_{rev_short}"}])

    # ── C 顺势持仓 — A+B 并列 ────────────────────────────
    elif scenario == "C":
        same_pos = conflict["same_pos"]
        cur_qty  = same_pos["qty"]
        cur_cost = same_pos.get("cost_price", 0)
        cur_pl   = same_pos.get("pl_val", 0) or 0

        cur_pl_word = "目前盈利" if cur_pl >= 0 else "目前亏损"
        lines += [
            f"✅ <b>你已顺势持仓 {same_short}</b>",
            f"现仓 {cur_qty:.0f}股 @{_money(cur_cost)}  "
            f"{cur_pl_word} ${abs(cur_pl):.0f}",
            f"",
            f"<b>🅰️ 继续持有</b>",
        ]

        # 目标/止损: 优先用 ATR targets,回退固定美元
        t1_price   = targets.get("t1")
        stop_price = targets.get("stop")
        if t1_price and stop_price:
            gap = t1_price - (same_price or cur_cost)
            lines += [
                f"  {same_short} 目标 T1 {_money(t1_price)}  (还差 {gap:+.2f})",
                f"  {same_short} 止损 {_money(stop_price)}  [ATR×1.5]",
            ]
        else:
            tgt_usd  = STRONG_TARGET_USD if strength == "STRONG" else WEAK_TARGET_USD
            stop_usd = STRONG_STOP_USD   if strength == "STRONG" else WEAK_STOP_USD
            target_price = round(cur_cost + tgt_usd  / max(cur_qty, 1), 2)
            stop_price_c = round(cur_cost - stop_usd / max(cur_qty, 1), 2)
            gap = target_price - (same_price or cur_cost)
            lines += [
                f"  {same_short} 目标 {_money(target_price)}  (还差 {gap:+.2f})",
                f"  {same_short} 止损 {_money(stop_price_c)}",
            ]

        # ── v0.5.9 加仓:用 MIN_ADD_BUDGET_USD($500),不再用 $2000 ──
        cash       = get_available_cash(session)
        add_budget = min(cash * 0.4, MAX_BUDGET_USD / 2)
        lines += ["", f"<b>🅱️ 加仓</b>"]

        if same_price and add_budget >= MIN_ADD_BUDGET_USD:
            add_qty = max(1, int(add_budget / same_price))
            add_cost = round(add_qty * same_price, 2)
            avg_cost = round(
                (cur_cost * cur_qty + same_price * add_qty) / (cur_qty + add_qty), 2
            )
            lines += [
                f"  再买 {add_qty} 股 @{_money(same_price)}  (${add_cost:,.0f})",
                f"  合并后 {cur_qty + add_qty:.0f} 股  平均成本 {_money(avg_cost)}",
                f"  可用余 ${cash - add_cost:,.0f}",
            ]
            caches.append((same_short, {
                "action": "BUY", "ticker": same_short,
                "qty": add_qty, "price": same_price,
                "reason": f"顺势加仓(原 {cur_qty:.0f} 股)",
                "entry": same_price,
            }))
            buttons.append([
                {"text": f"🅱️ 加仓 {add_qty}股 {same_short}",
                 "callback_data": f"focus_order_{same_short}"},
            ])
        else:
            if same_price and add_budget < MIN_ADD_BUDGET_USD:
                # 显示到底有多少,哪怕少也给明确数字
                min_qty = max(1, int(cash * 0.1 / same_price)) if same_price else 0
                if min_qty >= 1:
                    lines.append(
                        f"  资金偏少(可用 ${cash:,.0f})\n"
                        f"  最多可加 {min_qty} 股 (${min_qty*same_price:,.0f})\n"
                        f"  建议持有,等信号更强时再加"
                    )
                else:
                    lines.append(f"  资金不足(可用 ${cash:,.0f}),仅能持有")
            else:
                lines.append(f"  资金不足(可用 ${cash:,.0f}),仅能持有")

    # ── D 双向持仓 — 红警 ─────────────────────────────────
    elif scenario == "D":
        same_pos = conflict["same_pos"]
        rev_pos  = conflict["reverse_pos"]
        lines += [
            f"🚨 <b>严重警告 — 双向持仓!</b>",
            f"{same_short}: {same_pos['qty']:.0f}股  "
            f"{'+'if (same_pos.get('pl_val',0) or 0)>=0 else ''}${(same_pos.get('pl_val',0) or 0):.0f}",
            f"{rev_short}: {rev_pos['qty']:.0f}股  "
            f"{'+'if (rev_pos.get('pl_val',0) or 0)>=0 else ''}${(rev_pos.get('pl_val',0) or 0):.0f}",
            f"",
            f"💡 多空对冲浪费资金,建议先平 {rev_short}",
        ]
        rev_qty    = rev_pos["qty"]
        rev_cur    = session.get_last_price(rev_etf) or rev_pos.get("current_price", 0)
        sell_price = round(rev_cur * 0.998, 2)
        caches.append((rev_short, {
            "action": "SELL", "ticker": rev_short,
            "qty": rev_qty, "price": sell_price,
            "reason": "清理双向持仓冲突",
        }))
        buttons.append([
            {"text": f"⚠️ 平 {rev_qty:.0f}股 {rev_short}",
             "callback_data": f"focus_order_{rev_short}"},
        ])

    return {"scenario": scenario, "lines": lines, "buttons": buttons, "caches": caches}


def _cache_all(plans, signal_info):
    for short, plan in plans:
        if plan.get("insufficient_cash"):
            continue
        LAST_PLAN_CACHE[short] = {**plan, "signal": signal_info}


# ══════════════════════════════════════════════════════════════════
#  v0.5.13 自动日志(复盘数据源)
# ══════════════════════════════════════════════════════════════════
def _build_decision_context(session, hit):
    """
    v0.5.26: 收集推送时实际使用的原始决策数据 —— 供 verify_signals.py 精准复盘。

    返回 dict:
      kline_data:  {period, bars_count, bars: [{time,open,high,low,close,volume}], is_today}
      indicators_raw: {rsi_14, rsi_history, vwap, vol_ratio, vol_current, vol_ma_base, ...}
      price_context:  {current, day_open, day_high, day_low, prev_close, day_change_pct}
      session_state:  {loop_count, cash_available, positions_count, master, followers}

    任一子项失败时该字段返回 None,不影响主日志写入。
    """
    ctx = {"kline_data": None, "indicators_raw": None,
           "price_context": None, "session_state": None}
    if session is None:
        return ctx

    # ── kline_data: 取 session._last_kline_cache 最近 30 根 ──
    try:
        kl = getattr(session, "_last_kline_cache", None)
        if kl is not None and hasattr(kl, "tail"):
            tail = kl.tail(30)
            bars = []
            for _, row in tail.iterrows():
                bars.append({
                    "time":   str(row.get("time_key", "")),
                    "open":   round(float(row.get("open", 0)), 4),
                    "high":   round(float(row.get("high", 0)), 4),
                    "low":    round(float(row.get("low", 0)), 4),
                    "close":  round(float(row.get("close", 0)), 4),
                    "volume": int(row.get("volume", 0)),
                })
            attrs = getattr(kl, "attrs", {}) or {}
            ctx["kline_data"] = {
                "period":     "5m",
                "bars_count": len(bars),
                "bars":       bars,
                "is_today":   bool(attrs.get("has_today_data", True)),
            }
    except Exception as e:
        print(f"  [decision_context] kline_data failed: {e}")

    # ── indicators_raw: 完整指标 + RSI 最近 5 个值 ──
    try:
        ind = getattr(session, "_last_indicators_cache", {}) or {}
        rsi_history = []
        # 计算 RSI 历史:对 kline.close 滚动算最近 5 个 RSI 值
        try:
            from .micro_indicators import calc_rsi_fast
            kl = getattr(session, "_last_kline_cache", None)
            if kl is not None and "close" in kl.columns and len(kl) >= 20:
                closes = kl["close"].astype(float)
                # 末尾 5 个时间点上分别算一次 RSI
                for offset in range(4, -1, -1):
                    end_idx = len(closes) - offset
                    if end_idx >= 15:
                        rsi_history.append(calc_rsi_fast(closes.iloc[:end_idx], 14))
        except Exception:
            pass

        # vol_ma_base = 量比的基准值 (3 根均量基准)
        vol_current = None
        try:
            kl = getattr(session, "_last_kline_cache", None)
            if kl is not None and "volume" in kl.columns and len(kl) >= 1:
                vol_current = int(kl["volume"].iloc[-1])
        except Exception:
            pass

        ctx["indicators_raw"] = {
            "rsi_14":       ind.get("rsi_5m"),
            "rsi_history":  rsi_history if rsi_history else None,
            "vwap":         ind.get("vwap"),
            "vol_ratio":    ind.get("vol_ratio"),
            "vol_current":  vol_current,
            "session_high": ind.get("session_high"),
            "session_low":  ind.get("session_low"),
            "dist_high":    ind.get("dist_high"),
            "dist_low":     ind.get("dist_low"),
            "candle":       ind.get("candle"),
            "data_ok":      ind.get("data_ok"),
            "is_today":     ind.get("is_today"),
        }
    except Exception as e:
        print(f"  [decision_context] indicators_raw failed: {e}")

    # ── price_context ──
    try:
        tk = hit.get("ticker") or session.master
        current = session.get_last_price(tk)
        q = (getattr(session, "quote_snapshot", {}) or {}).get(tk) or {}
        ind = getattr(session, "_last_indicators_cache", {}) or {}
        # day_open / day_high / day_low 优先从 K 线第一根/极值取
        day_open = day_high = day_low = None
        try:
            kl = getattr(session, "_last_kline_cache", None)
            if kl is not None and len(kl) > 0:
                day_open = round(float(kl["open"].iloc[0]), 4)
                day_high = round(float(kl["high"].max()), 4)
                day_low  = round(float(kl["low"].min()),  4)
        except Exception:
            pass
        ctx["price_context"] = {
            "current":        round(float(current), 4) if current else None,
            "day_open":       day_open,
            "day_high":       day_high,
            "day_low":        day_low,
            "prev_close":     q.get("prev_close"),
            "day_change_pct": q.get("change_pct"),
        }
    except Exception as e:
        print(f"  [decision_context] price_context failed: {e}")

    # ── session_state ──
    try:
        ctx["session_state"] = {
            "loop_count":     getattr(session, "loop_count", 0),
            "cash_available": getattr(session, "cash_available", None),
            "positions_count": len([p for p in (session.positions_snapshot or {}).values()
                                    if p and p.get("qty", 0) > 0]),
            "master":         getattr(session, "master", None),
            "followers":      list(getattr(session, "followers", []) or []),
        }
    except Exception as e:
        print(f"  [decision_context] session_state failed: {e}")

    return ctx


def _log_trigger(hit, result, session=None):
    """
    v0.5.13: 每次推送触发,写入 data/review/YYYY-MM-DD/triggers.json
    便于第二天自动复盘,不需要再截图 Telegram
    写失败不影响主流程(静默失败)

    v0.5.26: 新增 decision_context 字段,保存推送时实际使用的所有原始数据
    """
    try:
        import os
        import json
        import sys
        from datetime import datetime as _dt

        if getattr(session, "_disable_review_log", False) or "unittest" in sys.modules:
            return

        # 路径:项目根/data/review/YYYY-MM-DD/triggers.json
        # 用 __file__ 反推项目根,避免依赖 config
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        today_str = _dt.now().strftime("%Y-%m-%d")
        log_dir = os.path.join(base_dir, "data", "review", today_str)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "triggers.json")

        # 读已有记录
        records = []
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    records = json.load(f)
                if not isinstance(records, list):
                    records = []
            except Exception:
                records = []

        # 当前 profile(用于复盘理解当时等级)
        try:
            from .activity_profile import get_current_profile
            p = get_current_profile() or {}
            profile_info = {
                "tag": p.get("tag", ""),
                "level": p.get("level", ""),
                "poll_sec": p.get("poll_sec"),
                "scale": p.get("scale"),
            }
        except Exception:
            profile_info = {}

        # 当前价格快照(master + followers)
        prices_snapshot = {}
        positions_snapshot = {}
        if session:
            try:
                tickers = [session.master] + list(session.followers or [])
                for tk in tickers:
                    p = session.get_last_price(tk)
                    if p is not None:
                        prices_snapshot[tk.replace("US.", "")] = round(float(p), 4)
                    pos = session.get_position(tk)
                    if pos and pos.get("qty", 0) > 0:
                        positions_snapshot[tk.replace("US.", "")] = {
                            "qty": pos.get("qty"),
                            "cost": pos.get("cost_price"),
                            "pl_val": pos.get("pl_val"),
                            "pl_pct": pos.get("pl_pct"),
                        }
            except Exception:
                pass

        # v0.5.26: 决策上下文 — 完整还原推送时的原始数据
        decision_context = _build_decision_context(session, hit)

        confidence = _confidence_score(hit)
        raw_strength = hit.get("strength")
        effective_strength = raw_strength
        if raw_strength == "STRONG" and confidence < 65:
            effective_strength = "WEAK"

        # 组装记录
        record = {
            "ts": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger": hit.get("trigger"),
            "ticker": hit.get("ticker"),
            "direction": hit.get("direction"),
            "strength": effective_strength,
            "raw_strength": raw_strength,
            "confidence": confidence,   # v0.5.21: 信心指数写入日志
            "profile": profile_info,
            "data": hit.get("data", {}),
            "prices": prices_snapshot,
            "positions": positions_snapshot,
            "cash_available": getattr(session, "cash_available", None) if session else None,
            "message_text": result.get("text", "") if isinstance(result, dict) else "",
            "pusher_version": VERSION,
            "swing_version": SWING_VERSION,
            "decision_context": decision_context,   # v0.5.26
        }

        records.append(record)

        # 写回
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        # 日志失败不影响推送主流程
        print(f"  [pusher._log_trigger] failed: {e}")


# ══════════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════════
def _quality_for_push(hit, session=None):
    """Return data quality when live indicators are available. / 有实时指标时返回质量门禁。"""
    if session is None:
        return None
    indicators = getattr(session, "_last_indicators_cache", None)
    if not indicators:
        return None
    try:
        return evaluate_data_quality(session, indicators, update_repeat=False)
    except Exception as e:
        print(f"  [pusher] data quality gate error: {e}")
        return None


def _record_push_block(session, hit, quality):
    """Record final pusher blocks. / 记录 pusher 最终门禁拦截。"""
    try:
        blocked = getattr(session, "_blocked_signals", None)
        if blocked is None:
            blocked = []
            session._blocked_signals = blocked
        blocked.append({
            "ts": time.time(),
            "source": "pusher",
            "trigger": hit.get("trigger"),
            "ticker": hit.get("ticker"),
            "reason": quality.reason,
            "last_bar_time": quality.last_bar_time,
        })
        if len(blocked) > 200:
            del blocked[:-200]
    except Exception:
        pass
    try:
        log_blocked_signal(session, hit, quality, source="pusher", would_have_pushed=hit.get("title"))
    except Exception:
        pass


def _data_untrusted_note(quality):
    reason = getattr(quality, "reason", "unknown")
    return (
        "\n\n⚠️ 技术指标数据不可用\n"
        f"原因: {reason}\n"
        "本提醒仅基于实时价格/持仓盈亏，不代表方向判断。"
    )


def _order_buttons_allowed(session, quality=None) -> tuple[bool, str]:
    """One-click button warmup gate. / 启动初期禁用一键按钮。"""
    try:
        from config.settings import ALLOW_ONE_CLICK_BUTTONS, ONE_CLICK_BUTTON_WARMUP_SEC
    except Exception:
        ALLOW_ONE_CLICK_BUTTONS = True
        ONE_CLICK_BUTTON_WARMUP_SEC = 0
    if not ALLOW_ONE_CLICK_BUTTONS:
        return False, "config disabled"
    if quality is not None and not quality.ok:
        return False, "data quality blocked"
    start = getattr(session, "start_time", None) if session else None
    if start is None and session is not None:
        start = getattr(session, "started_at", None)
    if start:
        try:
            if hasattr(start, "timestamp"):
                start = start.timestamp()
            elapsed = time.time() - float(start)
            if elapsed < ONE_CLICK_BUTTON_WARMUP_SEC:
                return False, f"warmup {int(ONE_CLICK_BUTTON_WARMUP_SEC - elapsed)}s remaining"
        except Exception:
            pass
    return True, "OK"


def _strip_order_buttons(buttons):
    if not buttons:
        return buttons
    kept_rows = []
    for row in buttons:
        kept = []
        for btn in row:
            data = btn.get("callback_data", "") if isinstance(btn, dict) else ""
            if data.startswith("focus_order_"):
                continue
            kept.append(btn)
        if kept:
            kept_rows.append(kept)
    return kept_rows


def format_trigger_message(hit, session=None):
    trigger = hit["trigger"]
    quality = _quality_for_push(hit, session)
    bad_quality = bool(quality and not quality.ok)
    if bad_quality and trigger_requires_fresh_data(trigger):
        _record_push_block(session, hit, quality)
        print(
            f"  [pusher] blocked {trigger} {hit.get('ticker')}: "
            f"{quality.reason}"
        )
        return None

    if trigger == "profit_target_hit":
        result = _fmt_profit_target(hit, session)
    elif trigger == "position_followup":
        result = _fmt_position_followup(hit, session)
    elif trigger == "stop_loss_warning":
        result = _fmt_stop_loss_warning(hit, session)
    elif trigger == "drawdown_from_peak":
        result = _fmt_drawdown(hit, session)
    elif trigger == "swing_top":
        result = _fmt_swing_top(hit, session)
    elif trigger == "swing_bottom":
        result = _fmt_swing_bottom(hit, session)
    elif trigger == "direction_trend":
        result = _fmt_direction_trend(hit, session)
    elif trigger == "intraday_reversal":
        result = _fmt_intraday_reversal(hit, session)
    elif trigger == "breakdown_warning":
        result = _fmt_breakdown_warning(hit, session)
    elif trigger == "capitulation_bottom_watch":
        result = _fmt_capitulation_bottom_watch(hit, session)
    elif trigger == "panic_rebound":
        result = _fmt_panic_rebound(hit, session)
    elif trigger == "crash_rebound_watch":
        result = _fmt_crash_rebound_watch(hit, session)
    elif trigger in ("wave_trough_rebound", "wave_peak_rollover"):
        result = _fmt_wave_moment(hit, session)
    elif trigger == "rapid_move":
        result = _fmt_rapid_move(hit, session)
    elif trigger == "near_resistance":
        result = _fmt_near_resistance(hit, session)
    elif trigger == "near_support":
        result = _fmt_near_support(hit, session)
    elif trigger == "overbought_surge":
        result = _fmt_overbought_surge(hit, session)
    elif trigger == "large_day_gain":
        result = _fmt_large_day_gain(hit, session)
    elif trigger == "target_advance":
        result = _fmt_target_advance(hit, session)
    else:
        result = {"text": hit.get("title", "未知"), "buttons": None, "style": hit.get("style", "C")}

    if result is None:
        return None

    data = hit.get("data", {}) or {}
    result["text"] = inject_price_delta_lines(
        result.get("text") or "",
        session=session,
        ticker=hit.get("ticker"),
        current=data.get("current") or data.get("price"),
        direction=hit.get("direction"),
    )

    if bad_quality and trigger_allows_bad_data(trigger):
        result["buttons"] = []
        result["text"] = (result.get("text") or "") + _data_untrusted_note(quality)

    result["text"] = inject_kline_source_line(
        result.get("text") or "",
        session=session,
        indicators=getattr(session, "_last_indicators_cache", None) if session else None,
        hit=hit,
        quality=quality,
    )

    buttons_allowed, button_reason = _order_buttons_allowed(session, quality)
    if not buttons_allowed:
        result["buttons"] = _strip_order_buttons(result.get("buttons"))
        if trigger_requires_fresh_data(trigger):
            # Avoid stale /order plans during the warmup gate.
            LAST_PLAN_CACHE.clear()
        if trigger_requires_fresh_data(trigger) and "一键按钮" not in (result.get("text") or ""):
            result["text"] = (
                (result.get("text") or "")
                + f"\n\n⏱️ 防御模式: 一键按钮已禁用 ({button_reason})"
            )

    manual = None if (bad_quality or not buttons_allowed) else _manual_cmd_line(hit, session)
    result["text"] = _wrap_message(result["text"], session, hit.get("ticker"), manual)

    # v0.5.13: 自动日志(复盘数据源),静默失败
    _log_trigger(hit, result, session)

    return result

def _wrap_message(text, session, ticker, manual_cmd=None):
    if not text:
        return text
    ts    = _timestamp_line(session, ticker)
    lines = text.split("\n", 1)
    wrapped = lines[0] + "\n" + ts + ("\n" + lines[1] if len(lines) > 1 else "")
    wrapped += "\n"
    if manual_cmd:
        wrapped += f"\n{manual_cmd}"
    wrapped += f"\n{_footer()}"
    return wrapped


# ══════════════════════════════════════════════════════════════════
#  v0.5.19 新触发类型推送格式
# ══════════════════════════════════════════════════════════════════
def _fmt_target_advance(hit, session=None):
    """
    v0.5.23: T1 突破后推新一档目标价。
    自动用当前价重算 T1/T2/stop，并写回 session._target_state
    """
    d = hit["data"]
    ticker = hit["ticker"]
    m = ticker.replace("US.", "")
    direction = hit.get("direction", "long")
    cur_px = d.get("current", 0) or 0
    old_t1 = d.get("old_t1", 0) or 0

    # 用当前价重算
    new_targets = _calc_price_targets(session, ticker, direction, cur_px) if session else {}
    new_t1   = new_targets.get("t1")
    new_t2   = new_targets.get("t2")
    new_stop = new_targets.get("stop")

    # v0.5.36: target_advance must roll the state forward even when the
    # normal target calculator returns the current/old level. Otherwise
    # follow-up logic keeps reading a stale T1/stop after a breakout.
    if cur_px > 0:
        atr = new_targets.get("atr") or 0
        min_gap = max(cur_px * 0.008, float(atr or 0) * 0.5)
        level, level_label = _next_target_level(cur_px, direction)
        if direction == "short":
            anchor = min(cur_px, old_t1) if old_t1 else cur_px
            if not new_t1 or new_t1 >= anchor:
                new_t1 = round(min(level, anchor - min_gap), 2)
                new_targets["t1"] = new_t1
                new_targets["t1_label"] = f"{level_label}/滚动目标"
            if not new_t2 or new_t2 >= new_t1:
                new_t2 = round(new_t1 - max(min_gap, cur_px * 0.01), 2)
                new_targets["t2"] = new_t2
                new_targets["t2_label"] = "滚动目标"
        else:
            anchor = max(cur_px, old_t1) if old_t1 else cur_px
            if not new_t1 or new_t1 <= anchor:
                new_t1 = round(max(level, anchor + min_gap), 2)
                new_targets["t1"] = new_t1
                new_targets["t1_label"] = f"{level_label}/滚动目标"
            if not new_t2 or new_t2 <= new_t1:
                new_t2 = round(new_t1 + max(min_gap, cur_px * 0.01), 2)
                new_targets["t2"] = new_t2
                new_targets["t2_label"] = "滚动目标"

    # 写回新状态（关键：下一次突破以新 T1 为准）
    if session and new_t1:
        if not hasattr(session, '_target_state'):
            session._target_state = {}
        session._target_state[ticker] = {
            "direction":    direction,
            "t1":           new_t1,
            "t2":           new_t2,
            "stop":         new_stop,
            "set_at_price": cur_px,
            "set_at_ts":    time.time(),
        }

    if d.get("trend_hold") and direction == "long":
        lines = [
            f"🚀 <b>{m} 趋势继续</b>",
            f"━━━━━━━━━━━━━━",
            f"目标上移: {_money(old_t1)} → {_money(new_t1) if new_t1 else '计算中'}",
        ]
        if new_stop:
            lines.append(f"建议: 继续持有，止损上移至 {_money(new_stop)} 保护利润")
        lines.append("不建议此时止盈")
        return {"text": "\n".join(lines), "buttons": [], "style": "B"}

    arrow = "✅ 突破" if direction == "long" else "✅ 跌破"
    lines = [
        f"📐 <b>目标升级 · {m}</b>",
        f"━━━━━━━━━━━━━━",
        f"{arrow} 原 T1 {_money(old_t1)}  ·  现价 <b>{_money(cur_px)}</b>",
    ]
    if new_t1 and cur_px > 0:
        nt1_pct = (new_t1 - cur_px) / cur_px * 100
        lbl = new_targets.get("t1_label", "")
        lines.append(f"新 T1 → <b>{_money(new_t1)}</b>  ({nt1_pct:+.1f}%)  [{lbl}]")
    if new_t2 and cur_px > 0:
        nt2_pct = (new_t2 - cur_px) / cur_px * 100
        lbl = new_targets.get("t2_label", "")
        lines.append(f"新 T2 → {_money(new_t2)}  ({nt2_pct:+.1f}%)  [{lbl}]")
    if new_stop and cur_px > 0:
        stop_pct = (new_stop - cur_px) / cur_px * 100
        lines.append(f"新止损 → {_money(new_stop)}  ({stop_pct:+.1f}%)  [ATR×1.5]")

    return {"text": "\n".join(lines), "buttons": [], "style": "B"}


def _fmt_near_resistance(hit, session=None):
    d            = hit["data"]
    ticker_short = hit["ticker"].replace("US.", "")
    current      = d.get("current", 0)
    resistance   = d.get("resistance", 0)
    dist_pct     = d.get("dist_pct", 0)
    lines = [
        f"⚠️ <b>{ticker_short} 准备卖出预警</b>",
        f"━━━━━━━━━━━━━━",
        f"现价 {_money(current)}  /  阻力 {_money(resistance)}",
        f"还有 <b>{dist_pct:.1f}%</b> 到目标阻力位",
        f"",
        f"💡 持有 RKLX 建议准备分批止盈，不要等到顶",
    ]
    lines += _trio_block(session)
    return {"text": "\n".join(lines), "buttons": [], "style": "C"}


def _fmt_near_support(hit, session=None):
    d            = hit["data"]
    ticker_short = hit["ticker"].replace("US.", "")
    current      = d.get("current", 0)
    support      = d.get("support", 0)
    dist_pct     = d.get("dist_pct", 0)
    if d.get("weak_market"):
        lines = [
            f"🟡 <b>{ticker_short} 支撑观察，等确认</b>",
            f"━━━━━━━━━━━━━━",
            f"现价 {_money(current)}  /  支撑 {_money(support)}",
            f"距离支撑 <b>{dist_pct:.1f}%</b>",
            f"",
            f"支撑观察，不建议提前接。",
            f"等重新站回 VWAP / 放量反弹再考虑。",
        ]
        lines += _trio_block(session)
        return {"text": "\n".join(lines), "buttons": [], "style": "C"}
    lines = [
        f"💡 <b>{ticker_short} 接近支撑位预警</b>",
        f"━━━━━━━━━━━━━━",
        f"现价 {_money(current)}  /  支撑 {_money(support)}",
        f"还有 <b>{dist_pct:.1f}%</b> 到支撑位",
        f"",
        f"💡 看多 RKLX 布局机会临近，等确认再进",
    ]
    lines += _trio_block(session)
    return {"text": "\n".join(lines), "buttons": [], "style": "C"}


def _fmt_overbought_surge(hit, session=None):
    d            = hit["data"]
    ticker_short = hit["ticker"].replace("US.", "")
    rsi          = d.get("rsi", 80)
    vol_ratio    = d.get("vol_ratio", 3)
    day_chg      = d.get("day_change_pct", 0) or 0
    lines = [
        f"🔥 <b>{ticker_short} 超买放量</b>",
        f"━━━━━━━━━━━━━━",
        f"RSI <b>{rsi:.1f}</b>  量比 <b>{vol_ratio:.1f}x</b>  日内 {day_chg:+.2f}%",
        f"",
        f"⚠️ RSI 过热 + 放量 = 顶部风险，持有 RKLX 考虑逐步锁定利润",
    ]
    lines += _trio_block(session)
    buttons = [[{"text": "🧠 AI", "callback_data": f"focus_ai_{ticker_short}"}]]
    return {"text": "\n".join(lines), "buttons": buttons, "style": "B"}


def _fmt_large_day_gain(hit, session=None):
    d            = hit["data"]
    ticker_short = hit["ticker"].replace("US.", "")
    day_chg      = d.get("day_change_pct", 0) or 0
    current      = d.get("current", 0)
    lines = [
        f"🚀 <b>{ticker_short} 大幅上涨 {day_chg:+.1f}%</b>",
        f"━━━━━━━━━━━━━━",
        f"现价 {_money(current)}  日内 {day_chg:+.2f}%",
        f"",
        f"⚠️ 大涨后回调风险增加，建议逐步锁定利润，不建议此时追加买入",
    ]
    lines += _trio_block(session)
    buttons = [[{"text": "🧠 AI", "callback_data": f"focus_ai_{ticker_short}"}]]
    return {"text": "\n".join(lines), "buttons": buttons, "style": "B"}


# ── 浮盈达标 v0.5.24 重写 ─────────────────────────────────
_PROFIT_SUB_REASON_HEADER = {
    "near_target":      "接近目标位",
    "broke_target":     "突破目标位",
    "overbought_surge": "超买放量",
    "drawdown":         "高点回落",
    "near_stop":        "接近止损",
}
_PROFIT_SUB_REASON_WHY = {
    "near_target":      "目标位就在眼前,先锁部分盈利,剩余仓位等更高目标",
    "broke_target":     "已突破第一目标,建议止盈+上移止损至成本上方,锁定利润",
    "overbought_surge": "RSI + 放量过热,顶部风险大,先收一波利润再说",
    "volume_dry":       "趋势量能明显枯竭,先保护利润,不要把浮盈还回去",
    "drawdown":         "高点回吐,趋势可能转弱,保住浮盈优先",
    "near_stop":        "止损位近在咫尺,无论如何先收回成本",
}


def _fmt_profit_target(hit, session=None):
    d            = hit["data"]
    ticker_short = hit["ticker"].replace("US.", "")
    qty          = int(d.get("qty") or 0)
    pl_val       = d.get("pl_val") or 0
    pl_pct       = d.get("pl_pct") or 0
    current      = d.get("current") or 0
    cost         = d.get("cost") or 0
    sub_reason   = d.get("sub_reason", "near_target")
    tier         = int(d.get("tier") or 2)
    tier_text    = d.get("tier_text", "")
    sell_qty     = int(d.get("sell_qty") or max(1, qty // 2))
    sell_price   = d.get("sell_price") or round(current * 1.003, 2)
    t1           = d.get("t1")
    stop         = d.get("stop")
    hold_sec     = int(d.get("hold_seconds") or 0)
    short_hold   = bool(d.get("short_hold"))
    bad_data_mode = bool(d.get("bad_data_mode"))

    # 实际手续费用 pusher 精确估算覆盖 swing_detector 粗估
    fee     = _estimate_roundtrip_fee(qty, current) if (qty and current) else 0
    true_pl = pl_val - fee

    header_word = _PROFIT_SUB_REASON_HEADER.get(sub_reason, "止盈提醒")
    why         = _PROFIT_SUB_REASON_WHY.get(sub_reason, "")

    # v0.5.28: 盈/亏文案区分
    is_loss = pl_val < 0
    if is_loss:
        # 亏损版 why 覆盖 (盈利版的"浮盈优先"/"收回成本"在亏损语境下不通)
        _LOSS_WHY = {
            "drawdown":  "已从高点回吐进入亏损,趋势走弱风险加大,先减仓控制损失",
            "near_stop": "止损位近在咫尺,严守纪律先减仓,避免被打穿后扩大损失",
        }
        why = _LOSS_WHY.get(sub_reason, why)
        # 亏损时 tier_text "止盈" 改 "减仓"
        if tier_text:
            tier_text = (tier_text
                         .replace("考虑部分止盈", "考虑部分减仓控损")
                         .replace("分批止盈半仓", "分批减仓半仓")
                         .replace("止盈大部分", "减仓大部分")
                         .replace("强烈建议全部止盈", "强烈建议立即清仓"))
    sign = "+" if pl_pct >= 0 else ""
    if is_loss and sub_reason == "near_stop":
        title_emoji = "🛑"
    elif is_loss:
        title_emoji = "📉"
    else:
        title_emoji = "💰"
    title = f"{title_emoji} <b>{ticker_short} {sign}{pl_pct:.1f}% · {header_word}</b>"

    # 持仓时长描述
    hold_str = _format_hold_duration(hold_sec)

    # 详细参数行 (因为 sub_reason 是关键决策点,把各档位置具体数字摆出来)
    detail = []
    if sub_reason in ("near_target", "broke_target") and t1:
        gap_pct = (t1 - current) / current * 100
        if sub_reason == "broke_target":
            detail.append(f"目标 T1 ${t1:.2f} 已突破 · 现价 {_money(current)}")
        else:
            detail.append(f"目标 T1 ${t1:.2f} · 距现价 {gap_pct:+.2f}%")
    elif sub_reason == "overbought_surge":
        detail.append(f"现价 {_money(current)} · 浮盈 +{pl_pct:.1f}%")
    elif sub_reason == "drawdown":
        peak = getattr(session, "peak_price", {}).get(hit["ticker"]) if session else None
        if peak:
            dd = (current - peak) / peak * 100
            detail.append(f"峰值 ${peak:.2f} → 现价 {_money(current)} (回撤 {dd:.2f}%)")
    elif sub_reason == "near_stop" and stop:
        gap_pct = (current - stop) / current * 100
        detail.append(f"止损 ${stop:.2f} · 距现价 {gap_pct:+.2f}%")

    # v0.5.28: 盈/亏措辞
    pl_word      = "目前亏损" if is_loss else "目前盈利"
    true_pl_word = "实际亏损" if true_pl < 0 else "实际盈利"
    lines = [
        title,
        "━━━━━━━━━━━━━━",
        f"{qty} 股 @{_money(cost)} → 现价 {_money(current)}",
        f"{pl_word} ${abs(pl_val):.2f} ({sign}{pl_pct:.2f}%) · 持仓 {hold_str}",
        f"手续费 ~${fee:.2f}  →  {true_pl_word} ${abs(true_pl):.2f}",
    ]
    if detail:
        lines.extend(detail)
    lines.append("")

    # 动作建议 — sell_qty 已按 tier 算好,这里给"为什么 + 剩余怎么处理"
    if bad_data_mode:
        action_line = f"🎯 <b>{tier_text}</b>: 请人工判断是否处理 {sell_qty} 股"
        leftover_line = None
    elif sell_qty >= qty:
        verb = "全仓清仓止损" if is_loss else "全仓兑现"
        action_line = f"🎯 <b>{verb}</b>:卖 {sell_qty} 股 @{_money(sell_price)}"
        leftover_line = None
    else:
        action_line = f"🎯 <b>{tier_text}</b>:卖 {sell_qty} 股 @{_money(sell_price)}"
        leftover_qty = qty - sell_qty
        if sub_reason == "broke_target":
            leftover_line = f"剩 {leftover_qty} 股 · 止损上移到 {_money(round(cost * 1.005, 2))} (成本+0.5%)"
        elif sub_reason == "near_stop":
            leftover_line = f"剩 {leftover_qty} 股 · 若跌破 ${stop:.2f} 立即清仓"
        elif sub_reason in ("overbought_surge", "drawdown"):
            # v0.5.28: 亏损时"上移到成本"会立刻触发,改用 stop 价或现价×0.98
            if is_loss:
                hard_stop = stop or round(current * 0.98, 2)
                leftover_line = f"剩 {leftover_qty} 股 · 若跌破 {_money(hard_stop)} 全清止损"
            else:
                leftover_line = f"剩 {leftover_qty} 股 · 止损上移到 {_money(round(cost * 1.002, 2))} 保本"
        else:
            leftover_line = f"剩 {leftover_qty} 股 · 等更高目标"

    if stop:
        action_line = f"🎯 <b>方向风险</b>: 关注 {ticker_short} {_money(stop)} 是否失守"
    else:
        action_line = f"🎯 <b>方向风险</b>: 结构走弱时再处理"
    if stop and stop > 0:
        action_line = f"🛑 <b>止损参考</b>: {ticker_short} {_money(stop)}"
    else:
        action_line = "🛑 <b>止损参考</b>: 真实浮亏扩大时处理"
    lines.append(action_line)
    if leftover_line:
        lines.append(leftover_line)
    if why:
        lines.append(f"💡 {why}")
    if short_hold:
        lines.append(f"⚠️ 注意:持仓仅 {hold_str},短线翻动大,确认条件再下手")

    buttons = [
        [{"text": "🧠 AI", "callback_data": f"focus_ai_{ticker_short}"},
         {"text": "⏳ 忽略", "callback_data": "focus_ignore"}],
    ]
    return {"text": "\n".join(lines), "buttons": buttons, "style": "A"}


# ══════════════════════════════════════════════════════════════════
#  v0.5.29 stop_loss_warning — 亏损持仓专用文案
#  | dedicated copy for stop_loss_warning trigger (losing positions)
#  设计要点:
#    1) 标题区分"接近止损 📉" vs "已破止损 🛑"
#    2) 行动建议:亏损越深减仓越多
#    3) leftover 兜底位用 min(stop, current×0.98),不会出现"高于现价的止损"
# ══════════════════════════════════════════════════════════════════
def _fmt_stop_loss_warning(hit, session=None):
    d            = hit["data"]
    ticker_short = hit["ticker"].replace("US.", "")
    qty          = int(d.get("qty") or 0)
    cost         = d.get("cost") or 0
    current      = d.get("current") or 0
    pl_val       = d.get("pl_val") or 0
    pl_pct       = d.get("pl_pct") or 0
    stop         = d.get("stop")
    sub_kind     = d.get("sub_kind", "approaching")  # approaching / breached
    bad_data_mode = bool(d.get("bad_data_mode"))
    tier_text    = d.get("tier_text", "减仓控损")
    sell_qty     = int(d.get("sell_qty") or max(1, qty // 3))
    sell_price   = d.get("sell_price") or round(current * 0.998, 2)
    hold_sec     = int(d.get("hold_seconds") or 0)

    # 精确手续费 (与 _fmt_profit_target 一致)
    fee     = _estimate_roundtrip_fee(qty, current) if (qty and current) else 0
    true_pl = pl_val - fee

    breached = (sub_kind == "breached")

    # ── 标题
    title_emoji = "🛑" if breached else "📉"
    title_word  = "已破止损位" if breached else "接近止损位"
    title = f"{title_emoji} <b>{ticker_short} {pl_pct:.1f}% · {title_word}</b>"

    # ── 持仓时长
    hold_str = _format_hold_duration(hold_sec)

    # ── 关键指标行 (止损价 vs 现价关系明示)
    detail = []
    if bad_data_mode:
        detail.append("技术指标不可用: 本提醒只按真实持仓浮亏百分比触发")
    elif stop and stop > 0:
        if current < stop:
            # 已破止损:现价已经在 stop 之下,明示"已击穿"
            below_pct = (stop - current) / stop * 100
            detail.append(f"原止损 ${stop:.2f} · 现价 {_money(current)} 已击穿 {below_pct:.2f}%")
        else:
            # 接近止损:current >= stop
            gap_pct = (current - stop) / current * 100
            detail.append(f"原止损 ${stop:.2f} · 距现价 {gap_pct:+.2f}%")
    if cost and cost > 0:
        detail.append(f"成本 {_money(cost)} → 现价 {_money(current)} (浮亏 {pl_pct:.2f}%)")

    # ── 亏损不区分 pl_word
    lines = [
        title,
        "━━━━━━━━━━━━━━",
        f"{qty} 股 @{_money(cost)} → 现价 {_money(current)}",
        f"目前亏损 ${abs(pl_val):.2f} ({pl_pct:.2f}%) · 持仓 {hold_str}",
        f"手续费 ~${fee:.2f}  →  实际亏损 ${abs(true_pl):.2f}",
    ]
    if detail:
        lines.extend(detail)
    lines.append("")

    # ── 动作建议
    if sell_qty >= qty:
        action_line  = f"🎯 <b>全仓清仓止损</b>:卖 {sell_qty} 股 @{_money(sell_price)}"
        leftover_line = None
    else:
        action_line  = f"🎯 <b>{tier_text}</b>:卖 {sell_qty} 股 @{_money(sell_price)}"
        leftover_qty = qty - sell_qty
        # leftover 止损位:必须低于现价才有意义
        # | leftover stop must be below current price to be actionable
        if stop and stop > 0 and stop < current:
            hard_stop = stop
        else:
            hard_stop = round(current * 0.98, 2)
        leftover_line = f"剩 {leftover_qty} 股 · 若跌破 {_money(hard_stop)} 全清止损"

    lines.append(action_line)
    if leftover_line:
        lines.append(leftover_line)

    # ── 大白话解读 (CLAUDE.md 推送规范要求)
    if bad_data_mode:
        why = "技术指标不可用，不参考 ATR/VWAP/旧止损位；这里只提示真实浮亏风险，请人工判断。"
    elif breached:
        why = "现价已跌破原止损位,纪律要求立即减仓控损,避免继续扩大亏损"
    else:
        why = "浮亏已接近止损区间,先减仓降低风险敞口,留小仓等反弹或彻底退出"
    lines.append(f"💡 {why}")

    buttons = [
        [{"text": "🧠 AI", "callback_data": f"focus_ai_{ticker_short}"},
         {"text": "⏳ 忽略", "callback_data": "focus_ignore"}],
    ]
    return {"text": "\n".join(lines), "buttons": buttons, "style": "A"}


# ── 高位回撤 ──────────────────────────────────────────────
def _fmt_position_followup(hit, session=None):
    """Held-position follow-up copy. / 持仓跟进文案。"""
    d = hit.get("data") or {}
    ticker_short = hit.get("ticker", "").replace("US.", "")
    state = d.get("state") or "HOLD_OK"
    qty = int(d.get("qty") or 0)
    cost = d.get("cost") or 0
    current = d.get("current") or 0
    pl_val = d.get("pl_val") or 0
    pl_pct = d.get("pl_pct") or 0
    stop = d.get("stop")
    t1 = d.get("t1")
    hold_str = _format_hold_duration(d.get("hold_sec"))
    adverse = d.get("adverse_pct")
    rebound = d.get("rebound_pct")
    reason = d.get("reason") or ""

    if state == "COST_RETEST":
        title = f"🟨 <b>{ticker_short} 回到成本附近</b>"
        conclusion = "结论: 反弹回到成本区,先看能否站稳成本上方。"
        action = "若 5m 内不能站稳成本上方,这次反弹大概率只是回抽。"
    elif state == "INVALIDATED":
        title = f"🟥 <b>{ticker_short} 持仓方向失效</b>"
        conclusion = "结论: 持仓假设已经失效,优先控制风险。"
        action = "依据: ATR 失效位/成本回测失败/短线结构转弱。"
    elif state == "DATA_UNTRUSTED":
        title = f"⚠️ <b>{ticker_short} 持仓数据不可信</b>"
        conclusion = "结论: 技术指标暂不可信,只按价格和原 ATR 失效位保护。"
        action = f"原因: {reason}"
    else:
        title = f"🟦 <b>{ticker_short} 持仓跟进</b>"
        conclusion = "结论: 方向暂未失效。"
        action = "继续观察价格结构。"

    lines = [
        title,
        "━━━━━━━━━━━━━━",
        f"{qty} 股 @{_money(cost)} → 现价 {_money(current)}",
        f"当前盈亏 ${pl_val:.2f} ({pl_pct:+.2f}%) · 持仓 {hold_str}",
    ]
    if adverse is not None:
        lines.append(f"最大回撤约 {adverse:.2f}% · 低点反弹约 {(rebound or 0):.2f}%")
    if t1:
        lines.append(f"参考 T1 {_money(t1)}")
    if stop:
        gap = (current - stop) / current * 100 if current else 0
        lines.append(f"ATR 失效位 {_money(stop)} · 距现价 {gap:+.2f}%")
    lines += ["", conclusion, action]

    buttons = [[
        {"text": f"/detail {ticker_short}", "callback_data": f"detail:{ticker_short}"},
        {"text": "🧠 AI", "callback_data": f"focus_ai_{ticker_short}"},
    ]]
    return {"text": "\n".join(lines), "buttons": buttons, "style": "A"}


def _fmt_drawdown(hit, session=None):
    d            = hit["data"]
    ticker_short = hit["ticker"].replace("US.", "")
    pos          = d.get("position") or {}
    qty          = pos.get("qty", 0)
    current      = d.get("current") or 0

    lines = [
        f"🚨 <b>{ticker_short} 高位回撤</b>",
        f"━━━━━━━━━━━━━━",
        f"峰值 {_money(d.get('peak'))} → 现价 {_money(current)}  "
        f"回撤 {_pct(d.get('drawdown_pct'))}",
    ]
    buttons = [[{"text": "🧠 AI", "callback_data": f"focus_ai_{ticker_short}"}]]

    if qty > 0:
        pl   = pos.get("pl_val", 0) or 0
        plp  = pos.get("pl_pct", 0) or 0
        sign = "+" if pl >= 0 else ""

        # v0.5.22: 扣费后真实盈亏，中文标签
        fee = _estimate_roundtrip_fee(qty, current) if current else 0
        true_pl = pl - fee
        pl_word      = "目前盈利" if pl >= 0 else "目前亏损"
        true_pl_word = "实际盈利" if true_pl >= 0 else "实际亏损"

        lines += ["", f"💼 {qty:.0f}股 @{_money(pos.get('cost_price',0))}  "
                     f"{pl_word} ${abs(pl):.2f} ({sign}{plp:.2f}%)",
                  f"    手续费 ~${fee:.2f}  →  {true_pl_word} ${abs(true_pl):.2f}"]
        if pl >= PROFIT_SMALL_USD:
            act_half   = int(qty / 2)
            sell_price = round(current * 0.998, 2)
            lines += ["", f"🎯 方向风险: 高位回撤,关注能否重新转强"]
        else:
            lines += ["", "⚠️ 浮盈不足 $30,观察"]

    return {"text": "\n".join(lines), "buttons": buttons, "style": "B"}


# ══════════════════════════════════════════════════════════════════
#  v0.5.19 目标价计算（T1/T2/止损 三档）
# ══════════════════════════════════════════════════════════════════
def _target_round_step(price: float) -> float:
    """Dynamic target step by price band. / 按价格区间选择短线关口步长。"""
    if price < 5:
        return 0.5
    if price < 100:
        return 1.0
    return 5.0


def _min_invalid_gap_pct(ticker: str) -> float:
    """Minimum invalidation gap by instrument. / 按工具设置最小失效距离。"""
    short = (ticker or "").replace("US.", "")
    if short in LEVERAGED_FOLLOWERS:
        return MIN_INVALID_GAP_PCT
    return 0.45


def _short_symbol(ticker: str) -> str:
    return (ticker or "").replace("US.", "").upper()


def _is_leveraged_tool(ticker: str) -> bool:
    return _short_symbol(ticker) in LEVERAGED_FOLLOWERS


def _target_floor_pcts(ticker: str) -> tuple[float, float]:
    """Return (stop floor %, T1 floor %). / 返回止损与 T1 的最小有效距离。"""
    if _is_leveraged_tool(ticker):
        return 2.50, 1.50
    return 1.20, 0.80


def _target_rr_floor(ticker: str) -> float:
    if _is_leveraged_tool(ticker):
        return 1.6
    return 2.05


def _historical_1m_csv_path(ticker: str) -> str:
    try:
        from config.settings import DATA_DIR
    except Exception:
        data_dir = os.path.join(os.getcwd(), "data")
    else:
        data_dir = DATA_DIR
    return os.path.join(data_dir, "historical", f"{_short_symbol(ticker)}_1m.csv")


def _daily_atr_pct_from_local_history(ticker: str, period: int = 14) -> tuple[float, str]:
    """Daily ATR% from local Futu 1m archive, cached per ticker. / 用本地 Futu 1m 归档聚合日线 ATR%。"""
    key = (_short_symbol(ticker), period)
    if key in _DAILY_ATR_CACHE:
        return _DAILY_ATR_CACHE[key]

    path = _historical_1m_csv_path(ticker)
    if not os.path.exists(path):
        _DAILY_ATR_CACHE[key] = (0.0, "no daily ATR")
        return _DAILY_ATR_CACHE[key]

    days = {}
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts = (row.get("time_key") or "").strip()
                if len(ts) < 10:
                    continue
                day = ts[:10]
                try:
                    high = float(row.get("high") or 0)
                    low = float(row.get("low") or 0)
                    close = float(row.get("close") or 0)
                except (TypeError, ValueError):
                    continue
                if high <= 0 or low <= 0 or close <= 0:
                    continue
                item = days.setdefault(day, {"high": high, "low": low, "close": close, "count": 0})
                item["high"] = max(item["high"], high)
                item["low"] = min(item["low"], low)
                item["close"] = close
                item["count"] += 1
    except Exception as exc:
        print(f"  [pusher] daily ATR csv error {ticker}: {exc}")
        _DAILY_ATR_CACHE[key] = (0.0, "daily ATR error")
        return _DAILY_ATR_CACHE[key]

    ordered = [(day, data) for day, data in sorted(days.items()) if data.get("count", 0) >= 100]
    if len(ordered) < period + 1:
        _DAILY_ATR_CACHE[key] = (0.0, "daily ATR insufficient")
        return _DAILY_ATR_CACHE[key]

    recent = ordered[-(period + 1):]
    trs = []
    prev_close = recent[0][1]["close"]
    for _, data in recent[1:]:
        high = data["high"]
        low = data["low"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        # 跳过异常 TR 日,避免 RKLZ 拆分/坏行污染日线 ATR。
        # Skip abnormal TR days so split/bad-row data does not poison daily ATR.
        if data["close"] > 0 and (tr / data["close"] * 100.0) >= 25.0:
            trs = []
            prev_close = data["close"]
            continue
        trs.append(tr)
        prev_close = data["close"]
    last_close = recent[-1][1]["close"]
    if not trs or last_close <= 0:
        _DAILY_ATR_CACHE[key] = (0.0, "daily ATR invalid")
    else:
        _DAILY_ATR_CACHE[key] = ((sum(trs) / len(trs)) / last_close * 100.0, "daily ATR")
    return _DAILY_ATR_CACHE[key]


def _next_target_level(entry_price: float, direction: str) -> tuple[float, str]:
    """Nearest useful price level, not always $5. / 最近有效关口，不固定用 $5。"""
    step = _target_round_step(entry_price)
    if direction == "long":
        level = math.ceil(entry_price / step) * step
        if level <= entry_price:
            level += step
    else:
        level = math.floor(entry_price / step) * step
        if level >= entry_price:
            level -= step
    if step == 0.5:
        label = "半美元关口"
    elif step == 1.0:
        label = "整数关口"
    else:
        label = "$5关口"
    return round(float(level), 2), label


def _atr_from_kline_cache(kline_cache, period: int = 14) -> float:
    """True-range ATR from K_5M bars. / 用 5m K 线真实波幅计算 ATR。"""
    try:
        if kline_cache is None or len(kline_cache) < period + 1:
            return 0.0
        recent = kline_cache.tail(period + 1)
        highs = recent["high"].astype(float).tolist()
        lows = recent["low"].astype(float).tolist()
        closes = recent["close"].astype(float).tolist()
        trs = []
        for idx in range(1, len(recent)):
            prev_close = closes[idx - 1]
            trs.append(max(
                highs[idx] - lows[idx],
                abs(highs[idx] - prev_close),
                abs(lows[idx] - prev_close),
            ))
        return float(sum(trs) / len(trs)) if trs else 0.0
    except Exception:
        return 0.0


def _target_atr_for_ticker(session, ticker: str, entry_price: float) -> tuple[float, str]:
    """Return display ATR in ticker price domain. / 返回对应交易工具价格域的 ATR。"""
    if not entry_price:
        return 0.0, "fallback"
    daily_atr_pct, daily_source = _daily_atr_pct_from_local_history(ticker)
    if daily_atr_pct > 0:
        max_daily_atr_pct = 6.0 if _is_leveraged_tool(ticker) else 4.0
        daily_atr_pct = min(daily_atr_pct, max_daily_atr_pct)
        return entry_price * daily_atr_pct / 100.0, daily_source
    if not session:
        return 0.0, "fallback"
    kline_cache = getattr(session, "_last_kline_cache", None)
    master_atr = _atr_from_kline_cache(kline_cache)
    if master_atr <= 0:
        return 0.0, "fallback"

    master = getattr(session, "master", None)
    if ticker == master:
        return master_atr, "K_5M ATR"

    master_price = None
    try:
        master_price = session.get_last_price(master) if master else None
    except Exception:
        master_price = None
    if master_price and master_price > 0:
        short = (ticker or "").replace("US.", "")
        leverage = 2.0 if short in LEVERAGED_FOLLOWERS else 1.0
        return entry_price * (master_atr / master_price) * leverage, "RKLB K_5M ATR x2"
    return 0.0, "fallback"


def _calc_price_targets(session, ticker: str, direction: str, entry_price: float) -> dict:
    """
    v0.5.19 重写:
    候选目标价(多头): 近20价格最高点 / 最近$5整数关口 / entry+ATR×2.0
    候选目标价(空头): 近20价格最低点 / 最近$5整数关口 / entry-ATR×2.0
    → 按距离 entry 由近到远排序,最近=T1,次近=T2
    止损: entry ± ATR×1.5
    ATR 由最近20个价格点的标准差×1.5估算,最小 0.3% 兜底
    """
    result = {
        "t1": None, "t1_label": "",
        "t2": None, "t2_label": "",
        "stop": None, "atr": None,
        # 保留旧字段供 format_order_text 兼容
        "tech_target": None, "tech_stop": None,
        "stat_target": None, "stat_stop": None,
        "stat_samples": 0, "conflict": False,
    }

    if not entry_price or entry_price <= 0:
        return result

    try:
        import math
        prices_ts = session.prices.get(ticker, []) if session else []

        recent60 = [p for _, p in prices_ts[-60:]]
        recent20 = [p for _, p in prices_ts[-20:]] if len(prices_ts) >= 20 else recent60
        if not recent20:
            recent20 = [entry_price]

        # ATR 估算。2x 工具不能用过窄失效价，否则用户看到信号时已贴近失效。
        # ATR estimate. Leveraged ETFs need a wider practical invalidation gap.
        floor_stop_pct, floor_t1_pct = _target_floor_pcts(ticker)
        min_invalid_gap = entry_price * (floor_stop_pct / 100.0)
        kline_atr, atr_source = _target_atr_for_ticker(session, ticker, entry_price)
        if kline_atr > 0:
            atr = max(kline_atr * 0.6, min_invalid_gap)
        else:
            # 兜底才使用 tick 区间，避免把几十秒报价抖动当作真实 ATR。
            # Fallback only; do not treat short tick jitter as real ATR.
            atr = min_invalid_gap
            atr_source = "floor fallback"
        result["atr"] = round(atr, 4)
        result["atr_source"] = atr_source
        max_target_gap_pct = 12.0
        rr_floor = _target_rr_floor(ticker)
        min_target_gap = max(entry_price * (floor_t1_pct / 100.0), atr * rr_floor)

        if direction == "long":
            recent_extreme = max(recent20)
            price_level, level_label = _next_target_level(entry_price, "long")
            target_gap = min_target_gap
            candidates = [
                (round(recent_extreme, 2), "近期高点"),
                (price_level, level_label),
                (round(entry_price + target_gap, 2), "ATR"),
                (round(entry_price + atr * 2.0, 2), "ATR×2.0"),
            ]
            result["stop"] = round(entry_price - atr, 2)
            # 只取高于 entry 的候选
            above = [
                (p, l) for p, l in candidates
                if p > entry_price
                and (p - entry_price) >= min_target_gap
                and ((p - entry_price) / entry_price * 100) <= max_target_gap_pct
            ]
        else:
            recent_extreme = min(recent20)
            price_level, level_label = _next_target_level(entry_price, "short")
            target_gap = min_target_gap
            candidates = [
                (round(recent_extreme, 2), "近期低点"),
                (price_level, level_label),
                (round(entry_price - target_gap, 2), "ATR"),
                (round(entry_price - atr * 2.0, 2), "ATR×2.0"),
            ]
            result["stop"] = round(entry_price + atr, 2)
            above = [
                (p, l) for p, l in candidates
                if p < entry_price
                and (entry_price - p) >= min_target_gap
                and ((entry_price - p) / entry_price * 100) <= max_target_gap_pct
            ]

        # 兜底:主候选被 min_target_gap 全过滤光时(如动能信号正好在近期高/低点
        # 触发、ATR 偏宽,所有候选都贴近 entry),放宽 min_gap 下限、仍守 12% 上限,
        # 取最接近 entry 的有效候选,保证 master 域始终有 target_state 供
        # check_target_advance 参考。Fallback: if the min-gap filter removed every
        # candidate, relax the floor (keep the 12% ceiling) so master always lands a target.
        if not above:
            if direction == "long":
                above = [
                    (p, l) for p, l in candidates
                    if p > entry_price
                    and ((p - entry_price) / entry_price * 100) <= max_target_gap_pct
                ]
            else:
                above = [
                    (p, l) for p, l in candidates
                    if p < entry_price
                    and ((entry_price - p) / entry_price * 100) <= max_target_gap_pct
                ]

        # 按距离 entry 由近到远排序，去重（间距 < 0.5%视为同一价位）
        above.sort(key=lambda x: abs(x[0] - entry_price))
        deduped = []
        for p, l in above:
            if not deduped or abs(p - deduped[-1][0]) > entry_price * 0.005:
                deduped.append((p, l))

        if deduped:
            result["t1"], result["t1_label"] = deduped[0]
            result["tech_target"] = deduped[0][0]
            result["tech_stop"]   = result["stop"]
        if len(deduped) >= 2:
            result["t2"], result["t2_label"] = deduped[1]

    except Exception as e:
        print(f"  [pusher] target calc error: {e}")

    return result


def _fmt_price_targets(targets: dict, direction: str, entry_price: float,
                       ticker: str = "") -> str:
    """
    v0.5.22: 新增 ticker 参数，T1/T2/止损前加股票名（如"RKLX 目标 T1 $12.50"）
    """
    if not targets:
        return ""
    t1 = targets.get("t1")
    t2 = targets.get("t2")
    stop = targets.get("stop")
    if not (t1 or stop):
        return ""

    pfx = f"{ticker} " if ticker else ""
    lines = ["📐 <b>目标价</b>"]
    if t1:
        t1_pct = (t1 - entry_price) / entry_price * 100
        lbl = targets.get("t1_label", "")
        lines.append(f"   {pfx}目标 T1 {_money(t1)}  ({t1_pct:+.1f}%)  [{lbl}]")
    if t2:
        t2_pct = (t2 - entry_price) / entry_price * 100
        lbl = targets.get("t2_label", "")
        lines.append(f"   {pfx}目标 T2 {_money(t2)}  ({t2_pct:+.1f}%)  [{lbl}]")
    if stop:
        stop_pct = (stop - entry_price) / entry_price * 100
        lines.append(f"   {pfx}失效价 {_money(stop)}  ({stop_pct:+.1f}%)  [ATR/结构]")
        if t1 and entry_price:
            reward = abs(t1 - entry_price)
            risk   = abs(entry_price - stop)
            if risk > 0:
                lines.append(f"   盈亏比 {reward/risk:.1f}:1")
    return "\n".join(lines)


# ── 通用:带仓位冲突分析的信号推送 ──────────────────────────
def _compute_rr(targets: dict, entry_price: float | None) -> float | None:
    """Risk/reward gate helper. / 盈亏比闸门辅助。"""
    if not targets or not entry_price:
        return None
    try:
        entry = float(entry_price)
        t1 = targets.get("t1")
        stop = targets.get("stop")
        if not t1 or not stop or entry <= 0:
            return None
        risk = abs(entry - float(stop))
        if risk <= 0:
            return None
        reward = abs(float(t1) - entry)
        if reward < entry * 0.005:
            print(
                f"  [pusher] R/R gate skipped: reward ${reward:.4f} < 0.5% "
                f"of entry ${entry:.2f}"
            )
            return None
        return reward / risk
    except Exception:
        return None


def _direction_only_action_lines(lines: list[str]) -> list[str]:
    """Remove sizing/order-management copy from direction signals."""
    banned = (
        "仓位由你决定",
        "参考仓位",
        "可考虑介入",
        "可考虑顺势建",
        "再买",
        "加仓",
        "买 ",
        "买入",
        "剩余",
        "总现金",
        "可用资金不足",
        "最低建仓",
    )
    cleaned = []
    for line in lines or []:
        if any(word in line for word in banned):
            continue
        cleaned.append(line)
    return cleaned


def _downgrade_title_to_medium(title_line: str) -> str:
    """Replace STRONG label when pre-market low volume caps confidence. / 盘前低量降级标题。"""
    if not title_line:
        return title_line
    for label in ("[强烈]", "[STRONG]"):
        if label in title_line:
            return title_line.replace(label, "[中等]")
    return f"{title_line} [中等]"


def _downgrade_title_to_general(title_line: str) -> str:
    """Replace STRONG/MEDIUM labels when confidence is too low. / 信心不足时同步降级标题。"""
    if not title_line:
        return title_line
    for label in ("[强烈]", "[STRONG]", "[中等]"):
        if label in title_line:
            return title_line.replace(label, "[一般]")
    if "[一般]" in title_line:
        return title_line
    return f"{title_line} [一般]"


def _fmt_signal_with_conflict(hit, session, signal_direction, title_line, tech_line):
    master_short = hit["ticker"].replace("US.", "")
    strength     = hit.get("strength", "WEAK")
    entry_price  = session.get_last_price(hit["ticker"]) if session else None

    # v0.5.19: 信号强度进度条
    conf = _confidence_score(hit)
    conf, premarket_low_volume_downgraded = _premarket_low_volume_downgrade(
        hit, session, signal_direction, conf
    )
    downgrade_line = None
    if premarket_low_volume_downgraded:
        title_line = _downgrade_title_to_medium(title_line)
        strength = "WEAK"
        downgrade_line = "⬇️ 降级: 盘前低量，原强烈看多降为中等信心"
    conf_emoji = _confidence_emoji(conf)
    conf_line = f"{conf_emoji} 方向可信度: {_strength_bar(conf)}"

    # v0.5.20: 行情类型 + 方向偏向
    regime = _market_regime_label(hit)
    bias_word = "偏多" if signal_direction == "long" else "偏空" if signal_direction == "short" else "偏观望"
    intent    = _action_intent_label(conf, signal_direction)
    target_etf = pick_target_follower(session, signal_direction) if session else None
    etf_hint   = target_etf.replace("US.", "") if target_etf else ""
    etf_part   = f"，参考工具 {etf_hint}" if etf_hint else ""
    regime_line    = f"行情: {regime}"
    direction_line = f"方向倾向: {bias_word}{etf_part}  ·  {intent}"

    lines = [title_line, "━━━━━━━━━━━━━━", conf_line, regime_line, direction_line]
    lines += _trio_block(session)
    if tech_line:
        lines.append(tech_line)

    # v0.5.28: 目标价分两域计算
    #   master 域: 给 check_target_advance(master_ticker) 使用 — 检测 master 突破
    #   follower 域: 给推送显示和 follower 持仓的 profit_target 使用 — 价位与入场域一致
    # 此前用 master entry_price 算的 t1/t2/stop 被错标成 "RKLX 目标 T1 $XX",
    # 导致止损 $119(RKLB域) 显示在 RKLX $75 入场价上方,永不触发。
    master_targets = {}
    if entry_price:
        master_targets = _calc_price_targets(session, hit["ticker"], signal_direction, entry_price)

    follower_price = (session.get_last_price(target_etf)
                      if (session and target_etf) else None)
    follower_targets = {}
    if target_etf and follower_price:
        # target_etf is always the instrument to BUY for this signal.
        # 对 RKLB 看空时买的是 RKLZ，本质仍是做多 RKLZ；
        # follower 域目标/止损必须按买入工具的 long 方向计算。
        follower_targets = _calc_price_targets(session, target_etf, "long", follower_price)

    # 持久化两份目标态:master 用 master 价位、follower 用 follower 价位
    if session and not hasattr(session, '_target_state'):
        session._target_state = {}
    if session and entry_price and master_targets.get("t1"):
        session._target_state[hit["ticker"]] = {
            "direction":    signal_direction,
            "t1":           master_targets["t1"],
            "t2":           master_targets.get("t2"),
            "stop":         master_targets.get("stop"),
            "set_at_price": entry_price,
            "set_at_ts":    time.time(),
        }
    if session and target_etf and follower_price and follower_targets.get("t1"):
        session._target_state[target_etf] = {
            "direction":    signal_direction,
            "t1":           follower_targets["t1"],
            "t2":           follower_targets.get("t2"),
            "stop":         follower_targets.get("stop"),
            "set_at_price": follower_price,
            "set_at_ts":    time.time(),
        }

    conflict = analyze_position_conflict(session, signal_direction)
    # 显示给用户的 targets 必须用 follower 域 (与 same_price 同域),否则百分比/止损全错
    display_targets = follower_targets if follower_targets.get("t1") else master_targets
    rr_entry = follower_price if follower_targets.get("t1") else entry_price
    rr = _compute_rr(display_targets, rr_entry)
    if rr is not None and rr < 1.5:
        if strength == "STRONG":
            print(
                f"  [pusher] {hit.get('trigger')} {hit['ticker']} STRONG "
                f"bypasses R/R gate (R/R={rr:.2f}:1 < 1.5)"
            )
            rr = None
        else:
            print(
                f"  [pusher] {hit.get('trigger')} {hit['ticker']} "
                f"R/R {rr:.2f}:1 < 1.5; push blocked"
            )
            return None

    if rr is not None and 1.5 <= rr < 2.0 and conf > 60:
        print(
            f"  [pusher] {hit.get('trigger')} {hit['ticker']} "
            f"R/R {rr:.2f}:1 caps conf {conf} -> 60"
        )
        conf = 60

    chase_warn = False
    if (signal_direction == "long"
            and target_etf in ("US.RKLX", "US.RKLZ")
            and session is not None
            and hasattr(session, "get_day_change_pct")):
        follower_day_chg = session.get_day_change_pct(target_etf)
        if follower_day_chg is not None and follower_day_chg >= 10.0:
            chase_warn = True
            if conf > 60:
                print(
                    f"  [pusher] {target_etf} day_chg {follower_day_chg:+.2f}% "
                    f">= 10%; conf {conf} -> 60 (anti-chase)"
                )
                conf = 60
            strength = "WEAK"

    # Rebuild user-facing lines with valid UTF-8 copy after R/R and chase caps.
    # 在 R/R / 追高封顶后重建可读中文文案，避免乱码污染 Telegram。
    conf_line = f"{_confidence_emoji(conf)} 方向可信度: {_strength_bar(conf)}"
    if rr is not None:
        conf_line += f"  ·  盈亏比 {rr:.1f}:1"
    if chase_warn:
        conf_line += "  ·  高位追多,降级观察"
    cap_reasons = (hit.get("data", {}) or {}).get("cap_reasons") or []
    if "post_top_warning_cap" in cap_reasons:
        conf_line += "  ·  顶部风险后降级"
    if "rsi_rolling_over" in cap_reasons:
        conf_line += "  ·  RSI回落"
    if "rsi_rebounding" in cap_reasons:
        conf_line += "  ·  RSI反弹"
    if "held_same_direction_cap" in cap_reasons:
        conf_line += "  ·  持仓中降级"
    if strength == "STRONG" and conf < 65:
        title_line = _downgrade_title_to_general(title_line)
        strength = "WEAK"
        conf_line += "  ·  信心不足,强烈降级"
    intent = _action_intent_label(conf, signal_direction)
    direction_line = f"方向倾向: {bias_word}{etf_part}  ·  {intent}"
    lines = [title_line, "━━━━━━━━━━━━━━", conf_line, regime_line, direction_line]
    if downgrade_line:
        lines.insert(3, downgrade_line)
    lines += _trio_block(session)
    if tech_line:
        lines.append(tech_line)

    action   = _build_action_plan(session, signal_direction, strength, conflict,
                                  conf=conf, targets=display_targets)
    action["lines"] = _direction_only_action_lines(action.get("lines") or [])
    action["buttons"] = []
    action["caches"] = []

    lines.append("")
    lines += action["lines"]

    _cache_all(action["caches"], {"source": title_line, "direction": signal_direction})

    buttons = list(action["buttons"])
    buttons.append([
        {"text": "🧠 AI",    "callback_data": f"focus_ai_{master_short}"},
        {"text": "⏳ 忽略", "callback_data": "focus_ignore"},
    ])
    return {"text": "\n".join(lines), "buttons": buttons, "style": "B"}


def _fmt_swing_top(hit, session=None):
    d        = hit["data"]
    m        = hit["ticker"].replace("US.", "")
    candle   = d.get("candle") or {}
    strength = hit.get("strength", "WEAK")
    rsi      = d.get("rsi", 50) or 50

    tech = f"RSI {_num(rsi,'.1f')}"
    tech += " 🔥超买" if rsi >= 65 else " ⚠️偏买" if rsi >= 58 else ""
    if candle:
        tech += f"  ·  {candle.get('name','—')}"
    tech += f"  ·  量比 {_num(d.get('vol_ratio',1))}x"
    if strength == "WEAK":
        marks = [("RSI", d.get("cond_rsi",False)),
                 ("K线", d.get("cond_candle",False)),
                 ("近高", d.get("cond_near",False))]
        tech += "\n命中: " + " ".join(f"{'✅' if v else '❌'}{k}" for k,v in marks)

    return _fmt_signal_with_conflict(
        hit, session, "short", f"🔴 <b>{m} 波段顶</b> [{_strength_cn(strength)}]", tech)


def _fmt_swing_bottom(hit, session=None):
    d        = hit["data"]
    m        = hit["ticker"].replace("US.", "")
    candle   = d.get("candle") or {}
    strength = hit.get("strength", "WEAK")
    rsi      = d.get("rsi", 50) or 50

    tech = f"RSI {_num(rsi,'.1f')}"
    tech += " 💡超卖" if rsi <= 40 else " ⚠️偏卖" if rsi <= 48 else ""
    if candle:
        tech += f"  ·  {candle.get('name','—')}"
    tech += f"  ·  量比 {_num(d.get('vol_ratio',1))}x"
    if strength == "WEAK":
        marks = [("RSI", d.get("cond_rsi",False)),
                 ("K线", d.get("cond_candle",False)),
                 ("近低", d.get("cond_near",False))]
        tech += "\n命中: " + " ".join(f"{'✅' if v else '❌'}{k}" for k,v in marks)

    return _fmt_signal_with_conflict(
        hit, session, "long", f"🟢 <b>{m} 波段底</b> [{_strength_cn(strength)}]", tech)


def _fmt_direction_trend(hit, session=None):
    d         = hit["data"]
    m         = hit["ticker"].replace("US.", "")
    direction = hit["direction"]
    strength  = hit.get("strength", "WEAK")
    has_ind   = d.get("has_indicators", False)

    emoji, word = ("🚀", "看多") if direction == "long" else ("📉", "看空")
    title = f"{emoji} <b>{m} 方向信号 ({word})</b> [{_strength_cn(strength)}]"

    if has_ind:
        tech = (f"RSI {_num(d.get('rsi'),'.1f')}  ·  "
                f"VWAP {_money(d.get('vwap'))}  ·  "
                f"量比 {_num(d.get('vol_ratio',1))}x")
    else:
        tech = "⏳ K 线还未就绪(只看日内累计)"

    return _fmt_signal_with_conflict(hit, session, direction, title, tech)


def _fmt_intraday_reversal(hit, session=None):
    d         = hit["data"]
    m         = hit["ticker"].replace("US.", "")
    direction = hit["direction"]
    strength  = hit.get("strength", "STRONG")
    word      = "盘中转强" if direction == "long" else "盘中转弱"
    emoji     = "🔄🚀" if direction == "long" else "🔄📉"
    title = f"{emoji} <b>{m} {word}</b> [{_strength_cn(strength)}]"
    if direction == "short":
        move_line = f"高点回落 {_num(d.get('reversal_pct'),'.1f')}%"
    else:
        move_line = f"低点反弹 {_num(d.get('reversal_pct'),'.1f')}%"
    tech = (
        f"{move_line}  ·  RSI {_num(d.get('rsi'),'.1f')}  ·  "
        f"VWAP {_money(d.get('vwap'))}  ·  量比 {_num(d.get('vol_ratio',1))}x"
    )
    return _fmt_signal_with_conflict(hit, session, direction, title, tech)


def _fmt_breakdown_warning(hit, session=None):
    d = hit["data"]
    m = hit["ticker"].replace("US.", "")
    conf = _confidence_score(hit)
    move_pct = d.get("move_pct", 0) or 0
    window_sec = d.get("window_sec", 120) or 120
    lines = [
        f"⚠️ <b>{m} 方向破位（看空）</b> [强烈]",
        "━━━━━━━━━━━━━━",
        f"{_confidence_emoji(conf)} 方向可信度: {_strength_bar(conf)}",
        f"结论: 多头失效，短线方向转弱",
        f"RKLB {_money(d.get('current'))} ({_num(d.get('day_change_pct'), '+.2f')}%)",
        f"RSI {_num(d.get('rsi'), '.1f')}  ·  VWAP {_money(d.get('vwap'))}  ·  量比 {_num(d.get('vol_ratio'), '.2f')}x",
        f"{int(window_sec)}秒跌幅 {move_pct:+.2f}%",
        "",
        "信号: 破位风险已确认",
        "执行参考: 不再按看多处理；若反弹不上 VWAP，空头仍占优",
    ]
    text = "\n".join(lines)
    return {"text": text, "buttons": [[{"text": "🧠 AI", "callback_data": f"focus_ai_{m}"}]], "style": "B"}


def _fmt_capitulation_bottom_watch(hit, session=None):
    d = hit["data"]
    m = hit["ticker"].replace("US.", "")
    lines = [
        f"🟡 <b>{m} 恐慌底部观察</b>",
        "━━━━━━━━━━━━━━",
        "结论: 跌势进入极端区，开始观察止跌，不是追多信号",
        f"RKLB {_money(d.get('current'))} ({_num(d.get('day_change_pct'), '+.2f')}%)",
        f"RSI {_num(d.get('rsi'), '.1f')}  ·  VWAP {_money(d.get('vwap'))}  ·  量比 {_num(d.get('vol_ratio'), '.2f')}x",
        f"距日低 {d.get('dist_low', 0):.2f}%  ·  日低 {_money(d.get('session_low'))}",
        "",
        "观察: RSI/形态开始有止跌迹象",
        "确认: 重新站上 VWAP 或连续 5m K 线止跌，再看反弹质量",
    ]
    text = "\n".join(lines)
    return {"text": text, "buttons": [[{"text": "馃 AI", "callback_data": f"focus_ai_{m}"}]], "style": "C"}


def _fmt_panic_rebound(hit, session=None):
    d = hit["data"]
    m = hit["ticker"].replace("US.", "")
    strength = hit.get("strength", "WEAK")
    lines = [
        f"🔄 <b>{m} 底部反弹观察 [{strength}]</b>",
        "━━━━━━━━━━━━━━",
        "结论: 暴跌后出现第一段反抽，空头动能开始松动",
        f"现价 {_money(d.get('current'))}  日内 {_num(d.get('day_change_pct'), '+.2f')}%",
        f"从日低反弹 {_num(d.get('low_rebound_pct'), '.2f')}%  ·  {d.get('window_sec', 120)}秒涨 {_num(d.get('move_pct'), '+.2f')}%",
        f"RSI {_num(d.get('rsi'), '.1f')}  ·  VWAP {_money(d.get('vwap'))}  ·  量比 {_num(d.get('vol_ratio'), '.2f')}x",
        f"日低 {_money(d.get('session_low'))}",
        "",
        "观察: 这是反弹窗口，不是趋势反转确认",
        "确认: 继续放量并收回 VWAP，反弹质量才算提高",
        "失效: 跌回日低附近，说明只是弱反抽",
    ]
    text = "\n".join(lines)
    return {"text": text, "buttons": [[{"text": "🧠 AI", "callback_data": f"focus_ai_{m}"}]], "style": "B"}


def _fmt_crash_rebound_watch(hit, session=None):
    d = hit["data"]
    m = hit["ticker"].replace("US.", "")
    strength = hit.get("strength", "WEAK")
    lines = [
        f"🔎 <b>{m} 暴跌反弹观察 [{strength}]</b>",
        "━━━━━━━━━━━━━━",
        "结论: 暴跌后反弹开始出现，先看确认，不给仓位建议",
        f"现价 {_money(d.get('current'))}  日内 {_num(d.get('day_change_pct'), '+.2f')}%",
        f"从日低反弹 {_num(d.get('low_rebound_pct'), '.2f')}%  ·  {d.get('window_sec', 120)}秒 {_num(d.get('move_pct'), '+.2f')}%",
        f"RSI {_num(d.get('rsi'), '.1f')}  ·  VWAP {_money(d.get('vwap'))}  ·  量比 {_num(d.get('vol_ratio'), '.2f')}x",
        f"日低 {_money(d.get('session_low'))}  ·  VWAP收复 {'是' if d.get('vwap_reclaim') else '否'}",
        "",
        "确认: 继续站稳 VWAP / 放量上穿前高",
        "失效: 跌回日低附近，反弹失败",
    ]
    text = "\n".join(lines)
    return {"text": text, "buttons": [[{"text": "🧠 AI", "callback_data": f"focus_ai_{m}"}]], "style": "C"}


def _fmt_wave_moment(hit, session=None):
    d = hit["data"]
    m = hit["ticker"].replace("US.", "")
    is_rebound = hit.get("trigger") == "wave_trough_rebound"
    title = "波谷反弹时刻" if is_rebound else "波峰回落时刻"
    bias = "偏看多" if is_rebound else "偏看空"
    conclusion = (
        "空头动能开始松动，但还不是趋势反转确认"
        if is_rebound else
        "反弹动能开始转弱，短线先偏防守"
    )
    action = "不追买，等确认" if is_rebound else "不追空，等确认"
    lines = [
        f"{'🔄' if is_rebound else '🔻'} <b>{m} {title}</b>",
        "━━━━━━━━━━━━━━",
        f"结论: {conclusion}",
        f"属性: 看盘提醒 · {bias} · 无下单按钮",
        f"现价 {_money(d.get('current'))}  较昨收 {_num(d.get('day_change_pct'), '+.2f')}%",
        f"5m动量 {_num(d.get('move5_pct'), '+.2f')}%  ·  15m动量 {_num(d.get('move15_pct'), '+.2f')}%",
        f"RSI {_num(d.get('rsi'), '.1f')}  ·  VWAP {_money(d.get('vwap'))}  ·  量比 {_num(d.get('vol_ratio'), '.2f')}x",
        "",
        f"等待: {d.get('confirm_text')}",
        f"失效: {d.get('fail_text')}",
        f"操作: {action}",
    ]
    text = "\n".join(lines)
    return {"text": text, "buttons": [], "style": "C"}


def _fmt_rapid_move(hit, session=None):
    d            = hit["data"]
    master_short = hit["ticker"].replace("US.", "")
    chg          = d.get("change_pct", 0) or 0
    emoji        = "🚀" if chg > 0 else "⬇️"

    lines = [
        f"{emoji} <b>{master_short} {d.get('direction','异动')} {chg:+.2f}%</b>",
        f"━━━━━━━━━━━━━━",
    ]
    lines += _trio_block(session)
    lines.append(f"窗口:{d.get('window_sec',120)}秒")

    buttons = [[{"text": "🧠 AI", "callback_data": f"focus_ai_{master_short}"}]]
    return {"text": "\n".join(lines), "buttons": buttons, "style": "C"}


def format_order_text(etf_short):
    plan = LAST_PLAN_CACHE.get(etf_short)
    if not plan:
        return None

    action_code = plan.get("action", "BUY")
    action_label = "买入参考" if action_code == "BUY" else "卖出参考"
    qty    = plan.get("qty", 0)
    price  = plan.get("price", plan.get("entry", 0))
    target = plan.get("target")
    stop   = plan.get("stop")
    reason = plan.get("reason") or (plan.get("signal", {}) or {}).get("source", "")

    lines = [
        f"📋 <b>{etf_short} {action_label}</b>",
        f"━━━━━━━━━━━━━━",
        f"{etf_short}  {qty} 股  限价 {_money(price)}",
    ]
    if target is not None:
        lines.append(f"目标 {_money(target)} (+${plan.get('target_usd',0):.0f})")
    if stop is not None:
        lines.append(f"止损 {_money(stop)} (-${plan.get('stop_usd',0):.0f})")
    if reason:
        lines += ["", f"理由: {reason}"]
    lines += ["", "✂️ 复制到 Moomoo:",
              f"{etf_short}  {qty}  {_num(price)}", "", _footer()]
    return "\n".join(lines)
