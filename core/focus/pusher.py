"""
════════════════════════════════════════════════════════════════════
  MagicQuant Focus — pusher.py
  VERSION : v0.5.11
  DATE    : 2026-04-22
  CHANGES :
    v0.5.11 (2026-04-22):
      - [NEW] 推送抬头加入 activity_profile tag
              🔥黄金 / 🔥🔥极致 / 🧙 / 📆 / ⚡周一 等标签
              一眼看出此信号是什么等级时段 + 事件日触发
      - 依赖 activity_profile v0.1.0
    v0.5.10 (2026-04-22):
      - 推送抬头加市场时段标签 🟢盘中 / 🌃夜盘 等
    v0.5.9 (2026-04-22):
      - [FIX] C 场景加仓"资金不足"的 bug
              加仓最低门槛 $2000 → $500
  DEPENDS :
    context.py           ≥ v0.5.2
    swing_detector.py    ≥ v0.5.4
    market_clock.py      ≥ v0.2.0
    activity_profile.py  ≥ v0.1.0
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

from datetime import datetime
from typing import Optional

VERSION = "v0.5.11"
SWING_VERSION = "v0.5.4"

try:
    from .pairs import get_long_tools, get_short_tools, classify_follower
except ImportError:
    def get_long_tools(m): return []
    def get_short_tools(m): return []
    def classify_follower(m, f): return "unknown"


# ══════════════════════════════════════════════════════════════════
#  交易参数
# ══════════════════════════════════════════════════════════════════
ACCOUNT_SIZE_USD    = 20000
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
    例:"⚙️ swing v0.5.4 · pusher v0.5.11 · 轮询 1.0s · 阈值×0.75"
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
            qty = pos["qty"]
            pl  = pos.get("pl_val", 0) or 0
            sign = "+" if pl >= 0 else ""
            line += f"  💼 {qty:.0f}股 {sign}${pl:.0f}"
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
    return ACCOUNT_SIZE_USD * 0.5


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


def _build_action_plan(session, signal_direction, strength, conflict):
    scenario   = conflict["scenario"]
    same_etf   = conflict["same_etf"]
    rev_etf    = conflict["reverse_etf"]
    same_short = (same_etf or "").replace("US.", "")
    rev_short  = (rev_etf  or "").replace("US.", "")

    lines = []
    buttons = []
    caches = []

    same_price = session.get_last_price(same_etf) if (session and same_etf) else None

    # ── A 空仓 ────────────────────────────────────────────
    if scenario == "A":
        plan = plan_by_strength(same_price, strength, session) if same_price else None
        if not plan:
            lines.append(f"🎯 {same_short}(报价失败,手动确认)")
            return {"scenario": "A", "lines": lines, "buttons": [], "caches": []}
        if plan.get("insufficient_cash"):
            lines += [
                f"⚠️ <b>可用资金不足</b>",
                f"可用 ${plan['budget_usd']:,.0f} < 最低 ${plan['min_required']:,.0f}",
            ]
            return {"scenario": "A", "lines": lines, "buttons": [], "caches": []}

        pct_tag = "七成仓" if strength == "STRONG" else "半仓"
        cash_info = f"  /  可用 ${get_available_cash(session):,.0f}"
        lines += [
            f"🎯 <b>{same_short} × {plan['qty']} 股</b>  "
            f"(${plan['notional']:,.0f} / {pct_tag}{cash_info})",
            f"入场 {_money(plan['entry'])}  "
            f"目标 {_money(plan['target'])} (+${plan['target_usd']:.0f})  "
            f"止损 {_money(plan['stop'])} (-${plan['stop_usd']:.0f})",
        ]
        buttons.append([
            {"text": f"📋 买 {plan['qty']}股 {same_short}",
             "callback_data": f"focus_order_{same_short}"},
        ])
        caches.append((same_short, {
            **plan, "action": "BUY", "ticker": same_short,
            "price": plan["entry"], "qty": plan["qty"],
        }))

    # ── B 反向持仓 ────────────────────────────────────────
    elif scenario == "B":
        rev_pos    = conflict["reverse_pos"]
        rev_qty    = rev_pos["qty"]
        rev_pl     = rev_pos.get("pl_val", 0) or 0
        rev_cur    = session.get_last_price(rev_etf) or rev_pos.get("current_price", 0)
        sell_price = round(rev_cur * 0.998, 2)
        plan       = plan_by_strength(same_price, strength, session) if same_price else None

        lines += [
            f"⚠️ <b>方向冲突!持有反向头寸 {rev_short}</b>",
            f"{rev_short}: {rev_qty:.0f}股 @{_money(rev_pos.get('cost_price',0))}  "
            f"浮亏 ${rev_pl:+.0f}",
            f"",
            f"🅰️ <b>Step 1 — 先平 {rev_short}</b>",
            f"卖 {rev_qty:.0f} 股 @{_money(sell_price)}",
        ]
        caches.append((rev_short, {
            "action": "SELL", "ticker": rev_short,
            "qty": rev_qty, "price": sell_price,
            "reason": f"先平反向,准备买 {same_short}",
        }))

        if plan and not plan.get("insufficient_cash"):
            lines += [
                f"",
                f"🅱️ <b>Step 2 — 再买 {same_short}</b>",
                f"买 {plan['qty']} 股 @{_money(plan['entry'])}  (${plan['notional']:,.0f})",
                f"目标 {_money(plan['target'])} (+${plan['target_usd']:.0f})  "
                f"止损 {_money(plan['stop'])} (-${plan['stop_usd']:.0f})",
            ]
            caches.append((same_short, {
                **plan, "action": "BUY", "ticker": same_short,
                "price": plan["entry"], "qty": plan["qty"],
            }))
            buttons += [
                [{"text": f"1️⃣ 卖 {rev_qty:.0f}股 {rev_short}",
                  "callback_data": f"focus_order_{rev_short}"}],
                [{"text": f"2️⃣ 买 {plan['qty']}股 {same_short}",
                  "callback_data": f"focus_order_{same_short}"}],
            ]
        else:
            buttons.append([{"text": f"1️⃣ 卖 {rev_qty:.0f}股 {rev_short}",
                             "callback_data": f"focus_order_{rev_short}"}])

    # ── C 顺势持仓 — A+B 并列 ────────────────────────────
    elif scenario == "C":
        same_pos = conflict["same_pos"]
        cur_qty  = same_pos["qty"]
        cur_cost = same_pos.get("cost_price", 0)
        cur_pl   = same_pos.get("pl_val", 0) or 0

        lines += [
            f"✅ <b>你已顺势持仓 {same_short}</b>",
            f"现仓 {cur_qty:.0f}股 @{_money(cur_cost)}  "
            f"{'+'if cur_pl>=0 else ''}${cur_pl:.0f}",
            f"",
            f"<b>🅰️ 继续持有</b>",
        ]

        # 目标/止损基于当前成本
        tgt_usd  = STRONG_TARGET_USD if strength == "STRONG" else WEAK_TARGET_USD
        stop_usd = STRONG_STOP_USD   if strength == "STRONG" else WEAK_STOP_USD
        target_price = round(cur_cost + tgt_usd  / max(cur_qty, 1), 2)
        stop_price   = round(cur_cost - stop_usd / max(cur_qty, 1), 2)
        gap = (target_price - (same_price or cur_cost))
        lines += [
            f"  等目标 {_money(target_price)}  (还差 {gap:+.2f})",
            f"  或止损 {_money(stop_price)}",
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
#  主入口
# ══════════════════════════════════════════════════════════════════
def format_trigger_message(hit, session=None):
    trigger = hit["trigger"]
    if trigger == "profit_target_hit":
        result = _fmt_profit_target(hit, session)
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
    else:
        result = {"text": hit.get("title", "未知"), "buttons": None, "style": hit.get("style", "C")}

    manual = _manual_cmd_line(hit, session)
    result["text"] = _wrap_message(result["text"], session, hit.get("ticker"), manual)
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


# ── 浮盈达标 ──────────────────────────────────────────────
def _fmt_profit_target(hit, session=None):
    d            = hit["data"]
    ticker_short = hit["ticker"].replace("US.", "")
    qty          = d["qty"]
    pl_val       = d.get("pl_val") or 0
    current      = d.get("current") or 0
    cost         = d.get("cost") or 0

    if pl_val >= PROFIT_BIG_USD:
        sell_qty  = qty
        strategy  = "🎯 <b>全仓兑现</b>"
        sell_price = round(current * 1.001, 2)
    else:
        sell_qty  = int(qty / 2)
        strategy  = "🎯 <b>分批兑现(卖半仓)</b>"
        sell_price = round(current * 1.003, 2)

    stop_up = round(cost * 1.002, 2)
    sign    = "+" if pl_val >= 0 else ""

    lines = [
        f"💰 <b>{ticker_short} 浮盈达标</b>",
        f"━━━━━━━━━━━━━━",
        f"{ticker_short} {_money(current)}  {qty:.0f}股 @{_money(cost)}  浮盈 {sign}${pl_val:.2f}",
        f"",
        strategy,
        f"卖 {sell_qty} 股 @{_money(sell_price)}",
    ]
    if sell_qty < qty:
        lines.append(f"剩 {qty-sell_qty:.0f} 股 止损上移 {_money(stop_up)}")

    LAST_PLAN_CACHE[ticker_short] = {
        "action": "SELL", "ticker": ticker_short,
        "qty": sell_qty, "price": sell_price,
        "reason": f"浮盈 {sign}${pl_val:.2f} 达标",
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
        lines += ["", f"💼 {qty:.0f}股 @{_money(pos.get('cost_price',0))}  "
                     f"{sign}${pl:.2f} ({sign}{plp:.2f}%)"]
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


# ── 通用:带仓位冲突分析的信号推送 ──────────────────────────
def _fmt_signal_with_conflict(hit, session, signal_direction, title_line, tech_line):
    master_short = hit["ticker"].replace("US.", "")
    strength     = hit.get("strength", "WEAK")

    lines = [title_line, "━━━━━━━━━━━━━━"]
    lines += _trio_block(session)
    if tech_line:
        lines.append(tech_line)

    conflict = analyze_position_conflict(session, signal_direction)
    action   = _build_action_plan(session, signal_direction, strength, conflict)

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
        hit, session, "short", f"🔴 <b>{m} 波段顶</b> [{strength}]", tech)


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
        hit, session, "long", f"🟢 <b>{m} 波段底</b> [{strength}]", tech)


def _fmt_direction_trend(hit, session=None):
    d         = hit["data"]
    m         = hit["ticker"].replace("US.", "")
    direction = hit["direction"]
    strength  = hit.get("strength", "WEAK")
    has_ind   = d.get("has_indicators", False)

    emoji, word = ("🚀", "看多") if direction == "long" else ("📉", "看空")
    title = f"{emoji} <b>{m} 方向信号 ({word})</b> [{strength}]"

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

    action = plan.get("action", "BUY")
    qty    = plan.get("qty", 0)
    price  = plan.get("price", plan.get("entry", 0))
    target = plan.get("target")
    stop   = plan.get("stop")
    reason = plan.get("reason") or (plan.get("signal", {}) or {}).get("source", "")

    lines = [
        f"📋 <b>{etf_short} {action} 下单</b>",
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
