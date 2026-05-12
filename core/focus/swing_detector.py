"""
════════════════════════════════════════════════════════════════════
  MagicQuant Focus — swing_detector.py
  VERSION : v0.5.26
  DATE    : 2026-05-13
  CHANGES :
    v0.5.26 (2026-05-13):
      - [FIX] check_profit_target: 亏损时也允许 near_stop / drawdown
              告警通过。之前 pl_val<$5 / 扣费后亏损 两个抑制把所有
              sub_reason 一刀切,导致亏损时连"接近止损位""高点回撤"
              都静默 → 用户在 RKLX 跌 8% 期间没收到任何卖出推送。
              · in_loss 标志只过滤盈利专属类型 (near_target/
                broke_target/overbought_surge)
              · near_stop/drawdown 是风险告警语义,亏损时更应该推送
              · tier_info 在 pl_pct<0 时自然得到 tier=1(减仓 1/3)
    v0.5.25 (2026-05-12):
      - [FIX] swing_top / swing_bottom / overbought_surge:严格要求
              indicators.is_today=True 才触发。盘前 RTH K 线缺失时
              fallback 用昨日数据,RSI 反映昨日跌势但 day_chg 是盘前涨幅,
              时段错配 → 直接 skip
      - [NEW] swing_bottom 加强趋势过滤:日内涨幅 >= swing_bottom_strong_trend_pct
              (5%) 时禁触看多,对称于 swing_top 的处理。已经大涨不存在"底"
      - [NEW] buy 方向信号现金门槛过滤:run_all_triggers 在出口检查
              session.cash_available < MIN_BUDGET_USD($2000) 时,
              静默 swing_bottom / near_support / direction_trend long
              避免推送无法操作的信号造成噪声
    v0.5.24 (2026-05-12):
      - [REWRITE] check_profit_target 完全重写,从"机械金额触发"改为
                  "利益最大化的上下文感知止盈"
                  · 抑制:无持仓 / 盈利<$5 / 扣费后亏损 / <30min非紧急
                          / 趋势锁定且距 T1>2% 且最近创新高 (让利润奔跑)
                  · 触发:接近 T1 / 突破 T1 / RSI>=78+量比>=3x
                         / 高点回撤>=2% / 接近止损<1%
                  · 紧急触发豁免 30 分钟最短持仓限制
                  · 文案按 pl_pct 档位 (<3/3-8/8-15/>15) 给不同卖出比例
                  · trigger 名保留 profit_target_hit (向后兼容日志/dashboard)
      - [NEW] DEFAULT_PARAMS: 删除 profit_target_pct/profit_target_usd
              新增 profit_min_pl_usd / profit_min_hold_sec
              / profit_let_run_dist_pct / profit_let_run_new_high_window
              / profit_near_t1_pct / profit_near_stop_pct
              / profit_drawdown_pct / profit_overbought_rsi
              / profit_overbought_vol / profit_tier_pct (3/8/15)
              / profit_fee_per_share (扣费估算)
      - [CHG] run_all_triggers: master 也调用 check_profit_target
              drawdown_from_peak / overbought_surge / near_resistance
              命中时若持仓盈利已被 profit_target 覆盖,则跳过避免重复
    v0.5.22 (2026-05-12):
      - [FIX] check_near_resistance(): 突破阻力位后自动上移到下一档
              新增 session._near_resist_last[ticker] 记录上次预警阻力位
              只有 session_high 上移 ≥1% 才重新预警，消除同档阻力位刷屏
      - [FIX] check_rapid_move(): data 字段新增 has_indicators
              便于 triggers.json 复盘判断 RSI/vol_ratio 是否实际可用
      - [FIX] rapid_move_pct: 0.8% → 1.0%，降低噪音触发频率
      - [FIX] check_near_resistance / check_large_day_gain: direction 改为 neutral
              action_intent 分别标 avoid_chasing / take_profit，不再误标 short
              避免用户误认为是做空建议
    v0.5.21 (2026-05-11):
      - [NEW] check_near_resistance(): 价格距阻力位 <3% → 准备卖出预警
              trigger=near_resistance, cooldown=600s
      - [NEW] check_near_support(): 价格距支撑位 <3% → 准备买入预警
              trigger=near_support, cooldown=600s
      - [NEW] check_overbought_surge(): RSI>80 + 量比>3x → 超买放量止盈警告
              trigger=overbought_surge, cooldown=600s
      - [NEW] check_large_day_gain(): 日内涨幅>10% → 大幅上涨注意锁定利润
              trigger=large_day_gain, cooldown=1800s
      - [NEW] 多空转换确认机制: direction_trend SHORT 方向新增回落确认
              价格从近20点高点回落 < flip_short_confirm_pct(2%) 则不转空
              防止单靠 rapid_move 误转空导致频繁横跳
      - 对应新参数: near_resist_warn_pct=3.0 / near_support_warn_pct=3.0
                   near_warn_cooldown=600 / overbought_surge_rsi=80
                   overbought_surge_vol=3.0 / large_day_gain_pct=10.0
                   flip_short_confirm_pct=2.0
    v0.5.20 (2026-05-09):
      - [NEW] check_swing_top 强趋势过滤:
              日内涨幅 >= swing_top_strong_trend_pct(5%) 时禁触 swing_top 看空
              强趋势中不逆势操作，避免在上涨行情中误发做空信号
              对应新参数: swing_top_strong_trend_pct=5.0
    v0.5.19 (2026-05-08):
      - [FIX] profit_target_hit 冷却 300s → 600s(同 ticker 至少 10 分钟才再推)
              原因:同日触发 82 次,严重刷屏
    v0.5.18 (2026-05-08):
      - [NEW] direction_trend SHORT 信号额外条件: vol_ratio >= 0.8
              无量回调(量比<0.8)不视为空头趋势信号,过滤假突破误判
              对应新参数: trend_vol_ratio_short_guard=0.8
    v0.5.17 (2026-05-07):
      - [OPT] trend_rsi_oversold_guard: 40 → 38 (基于真实数据分析,RSI<38 时 SHORT 信号
              准确率仅 12.5%,收紧为严格屏蔽而非旧值)
      - [NEW] rapid_move_pct_follower=1.20: RKLX/RKLZ 等 follower 标的独立阈值
              (杠杆标的 0.65% 移动 ≈ RKLB 0.3%,纯噪声;1.2% 才有意义)
      - [NEW] rapid_move_rsi_short_guard=70: RSI>70 时屏蔽 rapid_move SHORT
              (真实数据 RSI>70 SHORT 准确率 0/4)
      - [NEW] rapid_move_reverse_cooldown=180: 上一次反向 rapid_move 信号
              不足 180 秒则跳过,消除"配对噪声"(~40% 信号为来回翻转)
    v0.5.7 (2026-05-06):
      - [NEW] check_direction_trend 极端 RSI 过滤(has_indicators=True 时):
              short 方向但 RSI < 40 → 超卖不追空
              long  方向但 RSI > 75 → 超买不追多
              对应新参数: trend_rsi_oversold_guard=40, trend_rsi_overbought_guard=75
    v0.5.6 (2026-05-01):
      - [NEW] check_rapid_move 加 indicators 参数:
              读取 rsi_5m / vol_ratio,vol_ratio < 0.8 时压制低量噪音
              master ticker 传实际 indicators,followers 传 None
    v0.5.5 (2026-04-24):
      - [FIX] direction_trend 全天刷 STRONG 看空的问题:
              1. STRONG 门槛提高: abs(day_chg)>=1.5 → >=2.0
              2. has_indicators=False 时加"二次确认"机制:
                 需要 prices 最近 5 分钟价格方向与 day_chg 一致
                 避免夜盘低开后震荡市误判为趋势
              3. has_indicators=False 只推 WEAK,不推 STRONG
      - [FIX] rapid_move 噪声过多:
              阈值 0.4% → 0.8% (提高灵敏度门槛)
              冷却 600s → 1200s (20分钟)
      - [NEW] 震荡市过滤 _is_choppy():
              计算最近 N 个价格的 high-low 范围 vs 总涨跌幅
              比值 > 3 认为是震荡,压制 direction_trend 和 rapid_move
    v0.5.4 (2026-04-22):
      - [FIX] 推送频率大幅降低
      - [NEW] 全局互斥 60 秒
  DEPENDS :
    context.py ≥ v0.5.2  (last_any_trigger_ts 字段)
    pairs.py   any
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

import time
from typing import Optional


DEFAULT_PARAMS = {
    # v0.5.24: profit_target 完全重写 — 旧固定阈值删除
    # 抑制阈值
    "profit_min_pl_usd":            5.0,    # 浮盈 < $5 不触发
    "profit_min_hold_sec":          1800,   # 持仓 < 30 分钟非紧急不触发
    "profit_fee_per_share":         0.02,   # roundtrip 单股估算费 (用于扣费判定)
    # 让利润奔跑 (三条同时满足才抑制)
    "profit_let_run_dist_pct":      2.0,    # 距 T1 > 2% 才让奔跑
    "profit_let_run_new_high_window": 300,  # 最近 5 分钟创新高 (秒)
    # 触发阈值
    "profit_near_t1_pct":           1.0,    # 距 T1 < 1% → near_target
    "profit_near_stop_pct":         1.0,    # 距 stop < 1% → near_stop
    "profit_drawdown_pct":          2.0,    # 从 peak 回撤 >= 2% → drawdown
    "profit_overbought_rsi":        78,     # RSI >= 78 + vol >= 3x → overbought
    "profit_overbought_vol":        3.0,
    # 档位 (盈利百分比边界)
    "profit_tier1_max_pct":         3.0,    # <3%   → 1/3 仓
    "profit_tier2_max_pct":         8.0,    # 3-8%  → 1/2 仓
    "profit_tier3_max_pct":         15.0,   # 8-15% → 3/4 仓
                                            # >15%  → 全仓

    "drawdown_pct":         0.8,

    # v0.5.5: 快速异动阈值提高,冷却加长
    "rapid_move_pct":             1.0,    # master ticker (RKLB) 阈值 (v0.5.22: 0.8→1.0 降低噪音)
    "rapid_move_pct_follower":    1.20,   # v0.5.17: follower (RKLX/RKLZ) 独立阈值
    "rapid_move_window":          120,
    "rapid_move_cooldown":        1200,   # ← 600 → 1200 (20分钟)
    "rapid_move_reverse_cooldown": 180,   # v0.5.17: 反向信号最小间隔 180s
    "rapid_move_rsi_short_guard":  70,    # v0.5.17: RSI>70 时屏蔽 SHORT rapid_move

    "rsi_overbought_strong": 65,
    "rsi_oversold_strong":   40,
    "rsi_overbought_weak":   58,
    "rsi_oversold_weak":     48,

    "near_high_pct_strong": -0.8,
    "near_high_pct_weak":   -1.5,
    "near_low_pct_strong":   0.8,
    "near_low_pct_weak":     1.5,

    # v0.5.5: STRONG 门槛提高
    "trend_day_change_pct":  0.8,
    "trend_day_change_strong": 2.0,  # ← 新增:STRONG 需要 >=2%
    "trend_rsi_long":        52,
    "trend_rsi_short":       48,
    "trend_rsi_overbought_guard": 75,   # long 方向但 RSI > 75 → 超买不追多
    "trend_rsi_oversold_guard":   38,   # short 方向但 RSI < 38 → 超卖不追空 (v0.5.17: 40→38)
    "trend_vol_ratio_short_guard": 0.8, # v0.5.18: short 方向量比必须 >= 0.8,无量回调不推空
    "trend_cooldown_sec":    1200,

    "swing_cooldown_weak":   900,
    "swing_cooldown_strong": 600,

    "global_mutex_sec":      60,

    # v0.5.20: 强趋势过滤——日内涨幅超此值时禁触 swing_top 看空
    "swing_top_strong_trend_pct": 5.0,
    # v0.5.25: 日内大涨/大跌时禁触反向 swing 信号
    "swing_bottom_strong_trend_pct": 5.0,    # 日内涨幅 >= 5% 时禁触 swing_bottom 看多

    # v0.5.5 新增:震荡市判断
    "choppy_window_pts":     10,     # 用最近 10 个价格点
    "choppy_ratio":          3.0,    # high-low / |总涨跌| > 3 = 震荡

    # v0.5.21: 波峰/波谷接近预警
    "near_resist_warn_pct":  3.0,    # 距阻力位 <3% → 卖出预警
    "near_support_warn_pct": 3.0,    # 距支撑位 <3% → 买入预警
    "near_warn_cooldown":    600,    # 接近预警冷却 10 分钟

    # v0.5.21: 超买放量预警
    "overbought_surge_rsi":  80,     # RSI 超买阈值
    "overbought_surge_vol":  3.0,    # 量比超量阈值

    # v0.5.21: 大幅上涨预警
    "large_day_gain_pct":    10.0,   # 日内涨幅触发阈值

    # v0.5.21: 多空转换确认 — 看空需要价格从近期高点回落此比例
    "flip_short_confirm_pct": 2.0,
}


# ══════════════════════════════════════════════════════════════════
#  全局互斥
# ══════════════════════════════════════════════════════════════════
def _global_mutex_ok(session, mutex_sec: int = 60) -> bool:
    last_ts = getattr(session, "last_any_trigger_ts", 0) or 0
    return (time.time() - last_ts) >= mutex_sec


def _mark_global_triggered(session):
    session.last_any_trigger_ts = time.time()


# ══════════════════════════════════════════════════════════════════
#  v0.5.5 震荡市过滤
# ══════════════════════════════════════════════════════════════════
def _is_choppy(session, ticker, window_pts: int = 10, ratio: float = 3.0) -> bool:
    """
    用最近 N 个价格点判断是否处于震荡市。
    高低差 / |总涨跌| > ratio → 震荡(往返运动为主)
    高低差 / |总涨跌| <= ratio → 趋势(单方向为主)

    返回 True = 震荡市(压制信号)
    返回 False = 趋势市或数据不足(允许信号)
    """
    try:
        prices_ts = session.prices.get(ticker, [])
        if len(prices_ts) < window_pts:
            return False  # 数据不足,不压制

        recent = [p for _, p in prices_ts[-window_pts:]]
        if not recent:
            return False

        high = max(recent)
        low  = min(recent)
        total_move = abs(recent[-1] - recent[0])

        if total_move < 0.001:
            return True  # 几乎不动 = 极度震荡

        chop_ratio = (high - low) / total_move
        return chop_ratio > ratio
    except Exception:
        return False  # 出错则不压制


def _recent_price_direction(session, ticker, window_pts: int = 5) -> Optional[str]:
    """
    看最近 N 个价格点的方向,用于 has_indicators=False 时的二次确认。
    返回 'up' / 'down' / None(不确定)
    """
    try:
        prices_ts = session.prices.get(ticker, [])
        if len(prices_ts) < window_pts:
            return None
        recent = [p for _, p in prices_ts[-window_pts:]]
        delta = recent[-1] - recent[0]
        if delta > 0.05:
            return "up"
        elif delta < -0.05:
            return "down"
        return None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
#  v0.5.24 profit_target 重写 — 上下文感知止盈
# ══════════════════════════════════════════════════════════════════
def _profit_tier(pl_pct: float, params: dict) -> dict:
    """根据浮盈% 返回 {tier, sell_ratio, tier_text}"""
    t1 = params["profit_tier1_max_pct"]
    t2 = params["profit_tier2_max_pct"]
    t3 = params["profit_tier3_max_pct"]
    if pl_pct < t1:
        return {"tier": 1, "sell_ratio": 1/3, "tier_text": "考虑部分止盈"}
    if pl_pct < t2:
        return {"tier": 2, "sell_ratio": 0.5, "tier_text": "分批止盈半仓,剩余继续持有"}
    if pl_pct < t3:
        return {"tier": 3, "sell_ratio": 0.75, "tier_text": "止盈大部分,留小仓博后续"}
    return {"tier": 4, "sell_ratio": 1.0, "tier_text": "强烈建议全部止盈,锁定利润"}


def _is_making_new_high(session, ticker, window_sec: int) -> bool:
    """最近 window_sec 内是否在创 session_high"""
    try:
        prices_ts = session.prices.get(ticker, [])
        if not prices_ts:
            return False
        now = time.time()
        recent = [(ts, p) for ts, p in prices_ts if (now - ts) <= window_sec]
        if len(recent) < 3:
            return False
        sess_high = session.session_high.get(ticker, 0) or 0
        if sess_high <= 0:
            return False
        # 最近 window 里有点触及 session_high (允许 0.05% 误差)
        recent_max = max(p for _, p in recent)
        return recent_max >= sess_high * 0.9995
    except Exception:
        return False


def _is_trend_locked_long(session, max_age_sec: int = 1800) -> bool:
    """最近 30 分钟内是否推过 long 方向的 direction_trend / target_advance"""
    try:
        state = getattr(session, "_target_state", {}) or {}
        for ticker, st in state.items():
            if (st.get("direction") == "long"
                and (time.time() - (st.get("set_at_ts", 0) or 0)) <= max_age_sec):
                return True
    except Exception:
        pass
    return False


def check_profit_target(session, ticker, indicators=None, params=None):
    """
    v0.5.24: 上下文感知止盈触发器。
    返回 dict 时附带 data.sub_reason ∈ {near_target, broke_target,
                                       overbought_surge, drawdown, near_stop}
    及 data.tier (1/2/3/4) 供 pusher 文案分支使用。
    """
    params = params or DEFAULT_PARAMS
    pos = session.get_position(ticker)
    if not pos or pos.get("qty", 0) <= 0:
        return None

    qty    = pos.get("qty", 0)
    cost   = pos.get("cost_price", 0) or 0
    pl_val = pos.get("pl_val", 0) or 0
    pl_pct = pos.get("pl_pct", 0) or 0
    current = session.get_last_price(ticker) or pos.get("current_price", 0) or 0
    if current <= 0:
        return None

    # v0.5.26: in_loss 不再直接 return — 仅用作末尾过滤,
    # 让 near_stop / drawdown 这两类风险告警在亏损时也能推出去。
    fee_est = qty * params["profit_fee_per_share"] * 2   # 双边
    in_loss = (pl_val < params["profit_min_pl_usd"]) or (pl_val - fee_est <= 0)

    # ── 准备 T1 / stop (优先 _target_state,否则 cost±3% 兜底)
    target_state = (getattr(session, "_target_state", {}) or {}).get(ticker) or {}
    t1   = target_state.get("t1")   or (cost * 1.03 if cost else None)
    stop = target_state.get("stop") or (cost * 0.97 if cost else None)

    # ── 触发条件判定
    sub_reason = None
    # 接近 T1 < 1%
    if t1 and t1 > 0:
        dist_t1_pct = (t1 - current) / current * 100
        if 0 <= dist_t1_pct < params["profit_near_t1_pct"]:
            sub_reason = "near_target"
        elif current >= t1:
            sub_reason = "broke_target"

    # RSI + 量比 (受"让利润奔跑"保护:趋势锁定+距 T1 远+创新高时不止盈)
    # v0.5.25: 非当日 K 线时 RSI/vol_ratio 不可信,跳过此分支
    if (sub_reason is None and indicators and indicators.get("data_ok")
        and indicators.get("is_today", True)):
        rsi = indicators.get("rsi_5m", 50) or 50
        vol_ratio = indicators.get("vol_ratio", 1) or 1
        if (rsi >= params["profit_overbought_rsi"]
            and vol_ratio >= params["profit_overbought_vol"]):
            # let_run:趋势锁多 + 距 T1 > 2% + 最近 5min 创新高 → 让利润奔跑
            dist_t1_pct_now = ((t1 - current) / current * 100) if (t1 and t1 > 0) else 0
            let_run = (
                _is_trend_locked_long(session)
                and dist_t1_pct_now > params["profit_let_run_dist_pct"]
                and _is_making_new_high(session, ticker,
                                        params["profit_let_run_new_high_window"])
            )
            if not let_run:
                sub_reason = "overbought_surge"

    # 从 peak 回撤
    if sub_reason is None:
        peak_dd = session.get_peak_drawdown_pct(ticker)
        if peak_dd is not None and peak_dd <= -params["profit_drawdown_pct"]:
            sub_reason = "drawdown"

    # 接近 stop < 1%
    if sub_reason is None and stop and stop > 0:
        dist_stop_pct = (current - stop) / current * 100
        if 0 <= dist_stop_pct < params["profit_near_stop_pct"]:
            sub_reason = "near_stop"

    if sub_reason is None:
        return None  # 无触发条件命中

    # v0.5.26: 盈利专属 sub_reason 在亏损状态下抑制
    # (near_target / broke_target / overbought_surge 是"赚钱了该锁利润"语义,
    #  亏损时推送语义不通;near_stop / drawdown 是"风险告警",必须放行)
    if in_loss and sub_reason not in ("near_stop", "drawdown"):
        return None

    # ── 抑制 3: 持仓时间 < 30 分钟 (紧急条件全部豁免;此处所有 sub_reason 都算紧急)
    # 设计取舍:所有 sub_reason 都是市场结构条件,出现即紧急,故全部豁免最短持仓限制
    # 留 hold_seconds 给 pusher 做新仓位提示文案
    hold_sec = session.get_position_age_sec(ticker)
    if hold_sec is None:
        hold_sec = 0
    short_hold = hold_sec < params["profit_min_hold_sec"]

    # ── 抑制 4: 让利润奔跑 (仅在"无任何紧急触发"时生效 — 但能进到这里说明已有触发)
    # 例外:near_target / broke_target / overbought_surge / drawdown / near_stop 都不让奔跑
    # 仅 drawdown 是被动信号,其余主动信号优先于"让奔跑"

    # ── 冷却
    cool_key = f"profit_target_{ticker}_{sub_reason}"
    if not session.can_trigger(cool_key, cooldown_sec=600):
        return None
    session.mark_triggered(cool_key)

    # ── 档位 → 卖出股数
    tier_info = _profit_tier(pl_pct, params)
    sell_qty = max(1, int(round(qty * tier_info["sell_ratio"])))
    sell_qty = min(sell_qty, qty)
    sell_price = round(current * (1.003 if sub_reason != "near_stop" else 0.998), 2)

    # ── 标题
    m = ticker.replace("US.", "")
    sign = "+" if pl_pct >= 0 else ""
    reason_title = {
        "near_target":      f"接近 ${t1:.2f} 目标位" if t1 else "接近目标位",
        "broke_target":     f"突破 ${t1:.2f} 目标位" if t1 else "突破目标位",
        "overbought_surge": "超买放量",
        "drawdown":         "从高点回落",
        "near_stop":        f"接近 ${stop:.2f} 止损位" if stop else "接近止损位",
    }[sub_reason]
    title = f"💰 {m} {sign}{pl_pct:.1f}% · {reason_title}"

    return {
        "trigger": "profit_target_hit",
        "level":   "URGENT",
        "style":   "A",
        "ticker":  ticker,
        "direction": "neutral",
        "strength": "STRONG" if pl_pct >= params["profit_tier2_max_pct"] else "WEAK",
        "data": {
            "qty":         qty,
            "cost":        cost,
            "current":     current,
            "pl_val":      pl_val,
            "pl_pct":      pl_pct,
            "sub_reason":  sub_reason,
            "tier":        tier_info["tier"],
            "tier_text":   tier_info["tier_text"],
            "sell_qty":    sell_qty,
            "sell_ratio":  tier_info["sell_ratio"],
            "sell_price":  sell_price,
            "t1":          t1,
            "stop":        stop,
            "hold_seconds": int(hold_sec),
            "short_hold":  short_hold,
            "fee_est":     fee_est,
            "true_pl":     pl_val - fee_est,
            "stop_upgrade_to": round(cost * 1.002, 2) if cost else None,
        },
        "title": title,
    }


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
    # v0.5.25: 非当日 K 线(盘前/夜盘 RTH 缺失 fallback) 不触发
    if not indicators.get("is_today", True):
        return None

    # v0.5.20: 强趋势过滤 — 日内涨幅 >= 5% 时不逆势触发看空
    day_chg = _get_day_change(session, ticker)
    if day_chg is not None and day_chg >= params["swing_top_strong_trend_pct"]:
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
    # v0.5.25: 非当日 K 线(盘前/夜盘 RTH 缺失 fallback) 不触发
    if not indicators.get("is_today", True):
        return None

    # v0.5.25: 强趋势过滤 — 日内涨幅 >= 5% 时不逆势触发看多 ("已涨 8% 不存在底")
    day_chg = _get_day_change(session, ticker)
    if day_chg is not None and day_chg >= params["swing_bottom_strong_trend_pct"]:
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
    """
    v0.5.5 重大改动:
    1. STRONG 门槛: abs(day_chg) >= 2.0 (原 1.5)
    2. has_indicators=False 时:
       - 只推 WEAK,不推 STRONG
       - 加"近期价格方向二次确认":最近 5 个价格点必须和 day_chg 方向一致
       - 加"震荡市压制":检测到震荡则不推
    3. has_indicators=True 时:
       - 加震荡市压制
    """
    params = params or DEFAULT_PARAMS

    day_chg = _get_day_change(session, ticker)
    if day_chg is None:
        return None

    has_indicators = bool(indicators and indicators.get("data_ok"))
    rsi       = indicators.get("rsi_5m",    50) if has_indicators else 50
    vol_ratio = indicators.get("vol_ratio",  1) if has_indicators else None

    # 判断方向
    if day_chg >= params["trend_day_change_pct"]:
        if has_indicators and rsi < params["trend_rsi_long"]:
            return None
        # 超买区不追多(RSI 过高说明已经拉过头,容易回踩)
        if has_indicators and rsi > params["trend_rsi_overbought_guard"]:
            return None
        direction, emoji, word = "long", "🚀", "看多"
    elif day_chg <= -params["trend_day_change_pct"]:
        if has_indicators and rsi > params["trend_rsi_short"]:
            return None
        # 超卖区不追空(RSI 过低说明已经砸过头,容易反弹)
        if has_indicators and rsi < params["trend_rsi_oversold_guard"]:
            return None
        # v0.5.18: 量比不足 0.8 = 无量回调,不视为真空头
        if vol_ratio is not None and vol_ratio < params.get("trend_vol_ratio_short_guard", 0.8):
            return None
        # v0.5.21: 多空转换确认 — 价格必须从近20点高点回落 ≥ flip_short_confirm_pct
        confirm_pct = params.get("flip_short_confirm_pct", 2.0)
        prices_ts = session.prices.get(ticker, [])
        if len(prices_ts) >= 5:
            recent20 = [p for _, p in prices_ts[-20:]]
            recent_high = max(recent20)
            current_p   = recent20[-1]
            if recent_high > 0:
                drop_pct = (recent_high - current_p) / recent_high * 100
                if drop_pct < confirm_pct:
                    return None  # 未确认充分回落,不转空
        direction, emoji, word = "short", "📉", "看空"
    else:
        return None

    # v0.5.5: 震荡市过滤(有无指标都适用)
    if _is_choppy(session, ticker,
                  window_pts=params["choppy_window_pts"],
                  ratio=params["choppy_ratio"]):
        return None  # 震荡市静默

    # v0.5.5: has_indicators=False 时的额外限制
    if not has_indicators:
        # 1. 只推 WEAK,不推 STRONG(避免夜盘低开盲目给 STRONG)
        # 2. 二次确认:近期价格方向必须和 day_chg 一致
        recent_dir = _recent_price_direction(session, ticker, window_pts=5)
        expected_dir = "up" if direction == "long" else "down"
        if recent_dir != expected_dir:
            return None  # 近期价格方向不一致,不推

    # v0.5.5: STRONG 门槛提高
    strong_threshold = params.get("trend_day_change_strong", 2.0)
    if not has_indicators:
        # 无指标时永远只推 WEAK
        strength = "WEAK"
    else:
        strength = "STRONG" if abs(day_chg) >= strong_threshold else "WEAK"

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
            "vol_ratio": vol_ratio if vol_ratio is not None else 1,
            "vwap": indicators.get("vwap", 0) if has_indicators else 0,
            "current": session.get_last_price(ticker),
            "session_high": indicators.get("session_high") if has_indicators else None,
            "session_low":  indicators.get("session_low")  if has_indicators else None,
            "has_indicators": has_indicators,
            "choppy_filtered": False,  # 到这里说明通过了震荡过滤
        },
        "title": f"{emoji} {ticker.replace('US.','')} 方向信号({word} {day_chg:+.2f}%)",
    }


def check_rapid_move(session, ticker, indicators=None, params=None):
    """
    v0.5.5: 阈值 0.4% → 0.8%,冷却 600s → 1200s,加震荡市过滤
    v0.5.6: 从 indicators 读取 rsi_5m / vol_ratio,低量噪音压制
    """
    params = params or DEFAULT_PARAMS
    chg = session.get_price_change_pct(ticker, params["rapid_move_window"])
    if chg is None:
        return None

    if abs(chg) >= params["rapid_move_pct"]:
        # 震荡市过滤
        if _is_choppy(session, ticker,
                      window_pts=params["choppy_window_pts"],
                      ratio=params["choppy_ratio"]):
            return None

        # 读取 indicators
        has_ind = bool(indicators and indicators.get("data_ok"))
        rsi = indicators.get("rsi_5m", 50) or 50 if has_ind else None
        vol_ratio = indicators.get("vol_ratio", 1) or 1 if has_ind else None

        # 低量成交压制:成交量不足均量 80% 认为是噪音
        if vol_ratio is not None and vol_ratio < 0.8:
            return None

        # v0.5.17: RSI 过高时屏蔽 SHORT 急跌(真实数据 RSI>70 SHORT 准确率 0%)
        rsi_short_guard = params.get("rapid_move_rsi_short_guard", 70)
        if chg < 0 and rsi is not None and rsi > rsi_short_guard:
            return None

        direction_key = "up" if chg > 0 else "down"
        cool_key = f"rapid_{ticker}_{direction_key}"
        if not session.can_trigger(cool_key, cooldown_sec=params["rapid_move_cooldown"]):
            return None

        # v0.5.17: 反向冷却 — 上一次反向信号不足 180s 则跳过
        opp_dir_key = "down" if direction_key == "up" else "up"
        opp_cool_key = f"rapid_{ticker}_{opp_dir_key}"
        rev_cd = params.get("rapid_move_reverse_cooldown", 180)
        if not session.can_trigger(opp_cool_key, cooldown_sec=rev_cd):
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
                "rsi": rsi,
                "vol_ratio": vol_ratio,
                "has_indicators": has_ind,  # v0.5.22: 便于复盘判断 RSI 是否实际可用
            },
            "title": f"⚡ {ticker.replace('US.','')} {direction_word} {chg:+.2f}%",
        }
    return None


# ══════════════════════════════════════════════════════════════════
#  v0.5.21 新触发器：接近阻力/支撑、超买放量、大幅上涨
# ══════════════════════════════════════════════════════════════════
def check_near_resistance(session, ticker, indicators, params=None):
    """价格距阻力位 <3% → 推送准备卖出预警（不在 swing_top 强区域内）"""
    params = params or DEFAULT_PARAMS
    if not indicators.get("data_ok"):
        return None
    # v0.5.25: 非当日 K 线 不触发 (session_high/dist_high 是昨日数据)
    if not indicators.get("is_today", True):
        return None

    dist_high = indicators.get("dist_high", 0) or 0
    warn_pct  = -params.get("near_resist_warn_pct", 3.0)  # 负值：低于高点的%
    strong_pct = params.get("near_high_pct_strong", -0.8)  # swing_top 强区域边界

    # 在预警区（warn_pct <= dist_high < strong_pct）触发，已进入 swing_top 区域不重复
    if not (warn_pct <= dist_high < strong_pct):
        return None

    session_high = indicators.get("session_high", 0)

    # v0.5.22: 突破后自动上移阻力位 — session_high 未上移 ≥1% 不重复预警同一档阻力
    if not hasattr(session, '_near_resist_last'):
        session._near_resist_last = {}
    last_resist = session._near_resist_last.get(ticker, 0)
    if last_resist > 0 and session_high > 0 and session_high < last_resist * 1.01:
        return None

    cool_key = f"near_resist_{ticker}"
    if not session.can_trigger(cool_key, cooldown_sec=params.get("near_warn_cooldown", 600)):
        return None
    session.mark_triggered(cool_key)
    session._near_resist_last[ticker] = session_high  # 记录本次预警的阻力位

    current  = session.get_last_price(ticker) or 0
    dist_pct = abs(dist_high)

    return {
        "trigger": "near_resistance",
        "level": "INFO", "style": "C",
        "ticker": ticker,
        "direction": "neutral",        # v0.5.22: 止盈提示，非看空信号
        "action_intent": "avoid_chasing",
        "strength": "WEAK",
        "data": {
            "current": current,
            "resistance": session_high,
            "dist_pct": dist_pct,
            "day_change_pct": _get_day_change(session, ticker),
        },
        "title": f"⚠️ {ticker.replace('US.','')} 接近阻力位 还差 {dist_pct:.1f}%",
    }


def check_near_support(session, ticker, indicators, params=None):
    """价格距支撑位 <3% → 推送准备买入预警（不在 swing_bottom 强区域内）"""
    params = params or DEFAULT_PARAMS
    if not indicators.get("data_ok"):
        return None
    # v0.5.25: 非当日 K 线 不触发 (session_low/dist_low 是昨日数据)
    if not indicators.get("is_today", True):
        return None

    dist_low   = indicators.get("dist_low", 0) or 0
    warn_pct   = params.get("near_support_warn_pct", 3.0)
    strong_pct = params.get("near_low_pct_strong", 0.8)  # swing_bottom 强区域边界

    # 在预警区（strong_pct < dist_low <= warn_pct）触发
    if not (strong_pct < dist_low <= warn_pct):
        return None

    cool_key = f"near_support_{ticker}"
    if not session.can_trigger(cool_key, cooldown_sec=params.get("near_warn_cooldown", 600)):
        return None
    session.mark_triggered(cool_key)

    session_low = indicators.get("session_low", 0)
    current     = session.get_last_price(ticker) or 0

    return {
        "trigger": "near_support",
        "level": "INFO", "style": "C",
        "ticker": ticker,
        "direction": "long",
        "strength": "WEAK",
        "data": {
            "current": current,
            "support": session_low,
            "dist_pct": dist_low,
            "day_change_pct": _get_day_change(session, ticker),
        },
        "title": f"💡 {ticker.replace('US.','')} 接近支撑位 还差 {dist_low:.1f}%",
    }


def check_target_advance(session, ticker, indicators, params=None):
    """
    v0.5.23: 目标价升级检测
      当前价突破上次推送的 T1（多头）或跌破上次推送的 T1（空头）→ 推 "📐 目标升级"
      状态由 pusher._fmt_signal_with_conflict / _fmt_target_advance 在每次推目标时写入
        session._target_state[ticker] = {direction, t1, t2, stop, set_at_price, set_at_ts}
    冷却 60 秒；状态被自身推送时同步刷新，下一次升级以新 T1 为准
    """
    if not hasattr(session, '_target_state'):
        return None
    state = session._target_state.get(ticker)
    if not state:
        return None

    cool_key = f"target_advance_{ticker}"
    if not session.can_trigger(cool_key, cooldown_sec=60):
        return None

    cur_px = session.get_last_price(ticker) or 0
    if cur_px <= 0:
        return None

    direction = state.get("direction", "long")
    old_t1 = state.get("t1") or 0

    broken = (direction == "long"  and old_t1 > 0 and cur_px > old_t1) or \
             (direction == "short" and old_t1 > 0 and cur_px < old_t1)
    if not broken:
        return None

    session.mark_triggered(cool_key)

    return {
        "trigger": "target_advance",
        "level": "INFO", "style": "B",
        "ticker": ticker,
        "direction": direction,
        "strength": "WEAK",
        "data": {
            "current":          cur_px,
            "old_t1":           old_t1,
            "old_t2":           state.get("t2"),
            "old_stop":         state.get("stop"),
            "old_set_at_price": state.get("set_at_price"),
        },
        "title": f"📐 {ticker.replace('US.','')} 突破 T1 目标升级",
    }


def check_overbought_surge(session, ticker, indicators, params=None):
    """RSI > 80 + 量比 > 3x → 超买放量，强烈建议止盈"""
    params = params or DEFAULT_PARAMS
    if not indicators.get("data_ok"):
        return None
    # v0.5.25: 非当日 K 线 不触发 (RSI/vol_ratio 基于昨日数据,不可信)
    if not indicators.get("is_today", True):
        return None

    rsi       = indicators.get("rsi_5m", 50) or 50
    vol_ratio = indicators.get("vol_ratio", 1) or 1

    rsi_thr = params.get("overbought_surge_rsi", 80)
    vol_thr = params.get("overbought_surge_vol", 3.0)

    if not (rsi >= rsi_thr and vol_ratio >= vol_thr):
        return None

    cool_key = f"overbought_surge_{ticker}"
    if not session.can_trigger(cool_key, cooldown_sec=params.get("near_warn_cooldown", 600)):
        return None
    session.mark_triggered(cool_key)

    return {
        "trigger": "overbought_surge",
        "level": "WARN", "style": "B",
        "ticker": ticker,
        "direction": "short",
        "strength": "STRONG",
        "data": {
            "rsi": rsi,
            "vol_ratio": vol_ratio,
            "current": session.get_last_price(ticker),
            "day_change_pct": _get_day_change(session, ticker),
        },
        "title": f"🔥 {ticker.replace('US.','')} 超买放量 RSI {rsi:.0f} 量比 {vol_ratio:.1f}x",
    }


def check_large_day_gain(session, ticker, params=None):
    """日内涨幅 > 10% → 推送大幅上涨注意锁定利润"""
    params = params or DEFAULT_PARAMS
    day_chg = _get_day_change(session, ticker)
    if day_chg is None:
        return None

    if day_chg < params.get("large_day_gain_pct", 10.0):
        return None

    cool_key = f"large_gain_{ticker}"
    if not session.can_trigger(cool_key, cooldown_sec=1800):
        return None
    session.mark_triggered(cool_key)

    return {
        "trigger": "large_day_gain",
        "level": "WARN", "style": "B",
        "ticker": ticker,
        "direction": "neutral",        # v0.5.22: 涨多止盈提示，非看空信号
        "action_intent": "take_profit",
        "strength": "WEAK",
        "data": {
            "day_change_pct": day_chg,
            "current": session.get_last_price(ticker),
        },
        "title": f"🚀 {ticker.replace('US.','')} 大幅上涨 +{day_chg:.1f}% 注意锁定利润",
    }


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
    choppy = _is_choppy(session, ticker,
                        window_pts=params["choppy_window_pts"],
                        ratio=params["choppy_ratio"])

    distances = []
    if choppy:
        distances.append("🌀 当前处于震荡市,方向信号被压制")

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
        "choppy": choppy,
        "dist_high": indicators.get("dist_high") if has_ind else None,
        "dist_low":  indicators.get("dist_low")  if has_ind else None,
        "distances": distances, "has_indicators": has_ind,
    }


# ══════════════════════════════════════════════════════════════════
#  主调度
# ══════════════════════════════════════════════════════════════════
def run_all_triggers(session, master_ticker, followers, indicators, params=None):
    params = params or DEFAULT_PARAMS

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

        # v0.5.21+: 接近阻力/支撑预警 + 超买放量预警 + (v0.5.23) 目标升级
        for fn in (check_near_resistance, check_near_support, check_overbought_surge,
                   check_target_advance):
            h = fn(session, master_ticker, indicators, params)
            if h:
                hits.append(h)

    # v0.5.21: 大幅上涨预警(不依赖 K 线指标,只需 day_chg)
    h = check_large_day_gain(session, master_ticker, params)
    if h:
        hits.append(h)

    master_rapid = check_rapid_move(session, master_ticker, indicators, params)
    if master_rapid:
        hits.append(master_rapid)

    master_dir = None
    if master_rapid:
        master_dir = master_rapid["direction"]
    elif trend_hit:
        master_dir = trend_hit["direction"]

    # v0.5.17: follower 标的使用更高的 rapid_move 阈值(1.20%)
    follower_params = {**params, "rapid_move_pct": params.get("rapid_move_pct_follower", params["rapid_move_pct"])}
    for tk in followers:
        fh = check_rapid_move(session, tk, None, follower_params)
        if fh:
            if master_dir and _is_linked(tk, fh["direction"], master_ticker, master_dir):
                continue
            hits.append(fh)

    # v0.5.24: profit_target 扩展到 master + followers,master 传 indicators,follower 传 None
    pt_master = check_profit_target(session, master_ticker, indicators, params)
    if pt_master:
        hits.append(pt_master)
    for tk in followers:
        pt = check_profit_target(session, tk, None, params)
        if pt:
            hits.append(pt)
        dd = check_drawdown_from_peak(session, tk, params)
        if dd:
            hits.append(dd)

    # v0.5.24: 去重 — 若某 ticker 当前持仓且盈利覆盖,则 drawdown/overbought/near_resistance
    # 已由 profit_target 接管,移除这些重复 hits 避免两条推送
    pt_covered = {h["ticker"] for h in hits if h["trigger"] == "profit_target_hit"}
    if pt_covered:
        hits = [h for h in hits
                if not (h["trigger"] in ("drawdown_from_peak", "overbought_surge",
                                          "near_resistance", "large_day_gain")
                        and h["ticker"] in pt_covered)]

    # v0.5.25: 现金不足时静默"买入方向"信号,避免推送无法操作的噪声
    # 已持仓的 ticker 不静默(可能加仓用 MIN_ADD_BUDGET_USD $500 门槛)
    cash = getattr(session, "cash_available", None)
    if cash is not None and cash < 2000:   # MIN_BUDGET_USD
        BUY_DIR_TRIGGERS = ("swing_bottom", "near_support")
        filtered = []
        for h in hits:
            is_buy_dir = (
                h["trigger"] in BUY_DIR_TRIGGERS
                or (h["trigger"] == "direction_trend" and h.get("direction") == "long")
                or (h["trigger"] == "rapid_move"      and h.get("direction") == "long")
            )
            # 已持仓 ticker 走加仓门槛($500),不静默
            pos = session.get_position(h["ticker"]) if hasattr(session, "get_position") else None
            has_position = bool(pos and pos.get("qty", 0) > 0)
            if is_buy_dir and not has_position:
                print(f"  [swing] silenced {h['trigger']} {h['ticker']} (cash ${cash:.0f} < $2000)")
                continue
            filtered.append(h)
        hits = filtered

    level_order    = {"URGENT": 0, "WARN": 1, "INFO": 2}
    strength_order = {"STRONG": 0, "WEAK": 1}
    hits.sort(key=lambda h: (
        level_order.get(h.get("level"), 3),
        strength_order.get(h.get("strength"), 2),
    ))

    if hits:
        _mark_global_triggered(session)
        return [hits[0]]

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
