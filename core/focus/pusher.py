"""
════════════════════════════════════════════════════════════════════
  MagicQuant Focus — pusher.py
  VERSION : v0.5.29
  DATE    : 2026-05-13
  CHANGES :
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

import time
from datetime import datetime
from typing import Optional

VERSION = "v0.5.28"
SWING_VERSION = "v0.5.25"

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

    if rsi is not None:
        try:
            r = float(rsi)
            if direction == "long":
                if 50 < r < 65:    score += 15
                elif 45 < r <= 50: score += 10
                elif r >= 75:      score -= 20
                elif r >= 70:      score -= 10
            elif direction == "short":
                if 35 < r < 50:    score += 15
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

    return max(0, min(100, score))


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
    """生成进度条, 如 [████████░░] 80%"""
    filled = max(0, min(width, round(pct / 100 * width)))
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct}%"


def _pct_by_conf(conf: int) -> float:
    """信心指数 → 仓位比例 (占可用现金)"""
    if conf >= 90: return 0.90
    if conf >= 80: return 0.70
    if conf >= 60: return 0.40
    return 0.30


def _pct_label(conf: int) -> str:
    """仓位比例中文标签"""
    if conf >= 90: return "九成仓"
    if conf >= 80: return "七成仓"
    if conf >= 60: return "四成仓"
    return "三成仓"


def _market_regime_label(hit: dict) -> str:
    """从 hit data 推断行情类型（中文），用于信号推送"行情:"行"""
    d = hit.get("data", {}) or {}
    has_ind = d.get("has_indicators", False)
    if not has_ind:
        return "数据不足"
    vol_ratio = d.get("vol_ratio", 1) or 1
    rsi       = d.get("rsi", 50) or 50
    if vol_ratio >= 1.5 and 40 < rsi < 70:
        return "趋势行情"
    if vol_ratio < 0.8:
        return "噪音行情"
    return "混合行情"


def _action_intent_label(conf: int, direction: str) -> str:
    """信心 + 方向 → 操作意图中文（参考 action_intent 规范）"""
    if direction == "long":
        if conf >= 80: return "可轻仓偏多"
        if conf >= 60: return "等回调再进"
        return "等待，暂时观望"
    if direction == "short":
        if conf >= 80: return "可轻仓偏空"
        if conf >= 60: return "等突破确认"
        return "等待，暂时观望"
    return "等待，暂时观望"


# ══════════════════════════════════════════════════════════════════
#  交易参数
# ══════════════════════════════════════════════════════════════════
STRONG_POSITION_PCT = 0.70
WEAK_POSITION_PCT   = 0.50
MAX_BUDGET_USD      = 15000
MIN_BUDGET_USD      = 2000      # 开新仓最低资金
MIN_ADD_BUDGET_USD  = 500       # v0.5.9:加仓最低资金(低很多,能买几股就行)

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
    if trigger in ("direction_trend", "swing_top", "swing_bottom"):
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

    # ── A 空仓 ────────────────────────────────────────────
    if scenario == "A":
        if not same_price:
            lines.append(f"📋 {same_short}(报价失败,请手动确认)")
            return {"scenario": "A", "lines": lines, "buttons": [], "caches": []}

        cash = get_available_cash(session)
        pct = _pct_by_conf(conf)
        pct_lbl = _pct_label(conf)
        budget = min(cash * pct, MAX_BUDGET_USD)

        if budget < MIN_BUDGET_USD:
            lines += [
                f"⚠️ <b>可用资金不足</b>",
                f"可用 ${cash:,.0f} × {pct*100:.0f}% = ${budget:,.0f} < 最低 ${MIN_BUDGET_USD:,.0f}",
            ]
            return {"scenario": "A", "lines": lines, "buttons": [], "caches": []}

        qty = max(1, int(budget / same_price))
        notional = round(qty * same_price, 2)

        lines += [
            f"📋 <b>可考虑介入: {same_short}  ×  {qty} 股</b>  @  {_money(same_price)}",
            f"   参考仓位 {pct_lbl}: {_money(notional, ',.0f')}  /  可用 {_money(cash, ',.0f')}",
            f"   仓位由你决定",
        ]
        # 目标价 T1/T2/止损
        tgt_str = _fmt_price_targets(targets, signal_direction, same_price, same_short)
        if tgt_str:
            lines.append(tgt_str)

        t1_price   = targets.get("t1")
        stop_price = targets.get("stop")
        buttons.append([
            {"text": f"📋 买 {qty}股 {same_short}",
             "callback_data": f"focus_order_{same_short}"},
        ])
        caches.append((same_short, {
            "action": "BUY", "ticker": same_short,
            "price": same_price, "qty": qty,
            "entry": same_price, "notional": notional,
            "target": t1_price, "stop": stop_price,
            "target_usd": round((t1_price - same_price) * qty, 2) if t1_price else 0,
            "stop_usd":   round((same_price - stop_price) * qty, 2) if stop_price else 0,
        }))

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
        from datetime import datetime as _dt

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

        # 组装记录
        record = {
            "ts": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger": hit.get("trigger"),
            "ticker": hit.get("ticker"),
            "direction": hit.get("direction"),
            "strength": hit.get("strength"),
            "confidence": _confidence_score(hit),   # v0.5.21: 信心指数写入日志
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
def format_trigger_message(hit, session=None):
    trigger = hit["trigger"]
    if trigger == "profit_target_hit":
        result = _fmt_profit_target(hit, session)
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

    manual = _manual_cmd_line(hit, session)
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
    hold_min = hold_sec // 60
    if hold_min < 60:
        hold_str = f"{hold_min} 分钟"
    elif hold_min < 60 * 24:
        hold_str = f"{hold_min // 60} 小时{hold_min % 60} 分"
    else:
        hold_str = f"{hold_min // (60*24)} 天"

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
    if sell_qty >= qty:
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

    lines.append(action_line)
    if leftover_line:
        lines.append(leftover_line)
    if why:
        lines.append(f"💡 {why}")
    if short_hold:
        lines.append(f"⚠️ 注意:持仓仅 {hold_str},短线翻动大,确认条件再下手")

    LAST_PLAN_CACHE[ticker_short] = {
        "action": "SELL", "ticker": ticker_short,
        "qty": sell_qty, "price": sell_price,
        "reason": (f"{header_word} · 亏损 {pl_pct:.1f}%" if is_loss
                   else f"{header_word} · 浮盈 +{pl_pct:.1f}%"),
    }
    buttons = [
        [{"text": f"📋 卖 {sell_qty}股", "callback_data": f"focus_order_{ticker_short}"}],
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
    hold_min = hold_sec // 60
    if hold_min < 60:
        hold_str = f"{hold_min} 分钟"
    elif hold_min < 60 * 24:
        hold_str = f"{hold_min // 60} 小时{hold_min % 60} 分"
    else:
        hold_str = f"{hold_min // (60 * 24)} 天"

    # ── 关键指标行 (止损价 vs 现价关系明示)
    detail = []
    if stop and stop > 0:
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
    if breached:
        why = "现价已跌破原止损位,纪律要求立即减仓控损,避免继续扩大亏损"
    else:
        why = "浮亏已接近止损区间,先减仓降低风险敞口,留小仓等反弹或彻底退出"
    lines.append(f"💡 {why}")

    LAST_PLAN_CACHE[ticker_short] = {
        "action": "SELL", "ticker": ticker_short,
        "qty": sell_qty, "price": sell_price,
        "reason": f"{title_word} · 亏损 {pl_pct:.1f}%",
    }
    buttons = [
        [{"text": f"📋 卖 {sell_qty}股", "callback_data": f"focus_order_{ticker_short}"}],
        [{"text": "🧠 AI", "callback_data": f"focus_ai_{ticker_short}"},
         {"text": "⏳ 忽略", "callback_data": "focus_ignore"}],
    ]
    return {"text": "\n".join(lines), "buttons": buttons, "style": "A"}


# ── 高位回撤 ──────────────────────────────────────────────
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
            lines += ["", f"🎯 卖 {act_half} 股 @{_money(sell_price)} 保利润"]
            LAST_PLAN_CACHE[ticker_short] = {
                "action": "SELL", "ticker": ticker_short,
                "qty": act_half, "price": sell_price,
                "reason": f"高位回撤,保 ${pl:.0f}",
            }
            buttons = [
                [{"text": f"📋 卖 {act_half}股", "callback_data": f"focus_order_{ticker_short}"}],
                [{"text": "🧠 AI", "callback_data": f"focus_ai_{ticker_short}"}],
            ]
        else:
            lines += ["", "⚠️ 浮盈不足 $30,观察"]

    return {"text": "\n".join(lines), "buttons": buttons, "style": "B"}


# ══════════════════════════════════════════════════════════════════
#  v0.5.19 目标价计算（T1/T2/止损 三档）
# ══════════════════════════════════════════════════════════════════
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
        import math, statistics
        prices_ts = session.prices.get(ticker, []) if session else []
        if len(prices_ts) < 5:
            return result

        recent60 = [p for _, p in prices_ts[-60:]]
        recent20 = [p for _, p in prices_ts[-20:]] if len(prices_ts) >= 20 else recent60

        # ATR 估算
        sample = recent20 if len(recent20) >= 5 else recent60
        std = statistics.stdev(sample) if len(sample) >= 2 else 0
        atr = max(std * 1.5, entry_price * 0.003)
        result["atr"] = round(atr, 4)

        if direction == "long":
            recent_extreme = max(recent20)
            # 最近$5关口 (entry 上方)
            round5 = math.ceil(entry_price / 5) * 5
            if round5 <= entry_price:
                round5 += 5
            candidates = [
                (round(recent_extreme, 2), "近期高点"),
                (round(float(round5), 2),  "整数关口"),
                (round(entry_price + atr * 2.0, 2), "ATR×2.0"),
            ]
            result["stop"] = round(entry_price - atr * 1.5, 2)
            # 只取高于 entry 的候选
            above = [(p, l) for p, l in candidates if p > entry_price]
        else:
            recent_extreme = min(recent20)
            round5 = math.floor(entry_price / 5) * 5
            if round5 >= entry_price:
                round5 -= 5
            candidates = [
                (round(recent_extreme, 2), "近期低点"),
                (round(float(round5), 2),  "整数关口"),
                (round(entry_price - atr * 2.0, 2), "ATR×2.0"),
            ]
            result["stop"] = round(entry_price + atr * 1.5, 2)
            above = [(p, l) for p, l in candidates if p < entry_price]

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
        lines.append(f"   {pfx}止损 {_money(stop)}  ({stop_pct:+.1f}%)  [ATR×1.5]")
        if t1 and entry_price:
            reward = abs(t1 - entry_price)
            risk   = abs(entry_price - stop)
            if risk > 0:
                lines.append(f"   盈亏比 {reward/risk:.1f}:1")
    return "\n".join(lines)


# ── 通用:带仓位冲突分析的信号推送 ──────────────────────────
def _fmt_signal_with_conflict(hit, session, signal_direction, title_line, tech_line):
    master_short = hit["ticker"].replace("US.", "")
    strength     = hit.get("strength", "WEAK")
    entry_price  = session.get_last_price(hit["ticker"]) if session else None

    # v0.5.19: 信号强度进度条
    conf = _confidence_score(hit)
    conf_emoji = _confidence_emoji(conf)
    conf_line = f"{conf_emoji} 信心: {_strength_bar(conf)}"

    # v0.5.20: 行情类型 + 方向偏向
    regime = _market_regime_label(hit)
    bias_word = "偏多" if signal_direction == "long" else "偏空" if signal_direction == "short" else "偏观望"
    intent    = _action_intent_label(conf, signal_direction)
    target_etf = pick_target_follower(session, signal_direction) if session else None
    etf_hint   = target_etf.replace("US.", "") if target_etf else ""
    etf_part   = f"，适合{'做多' if signal_direction == 'long' else '做空'} {etf_hint}" if etf_hint else ""
    regime_line    = f"行情: {regime}"
    direction_line = f"方向: {bias_word}{etf_part}  ·  {intent}"

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
        follower_targets = _calc_price_targets(session, target_etf, signal_direction, follower_price)

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
    action   = _build_action_plan(session, signal_direction, strength, conflict,
                                  conf=conf, targets=display_targets)

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
