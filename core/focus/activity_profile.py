"""
════════════════════════════════════════════════════════════════════
  MagicQuant — activity_profile.py
  VERSION : v0.1.0
  DATE    : 2026-04-22
  PURPOSE :
    "机会密度" 单一真相源。所有动态频率/阈值/提醒的决策都读这里。

    基于真实市场数据研究(2025-2026):
      - S&P 500 学术研究:第 1 小时波动最高,最后 1 小时 DOW 波动 0.38-0.43%
      - StockTitan:9:30-10:00 ET 成交量最高,pre-market 8:00+ 流动性好
      - MDPI 2025:周一开盘 gap 后趋势持续数小时
      - Bloomberg:extended-hours 约 8% 日成交,主要在盘前盘后
      - Wikipedia/Bankrate:Triple Witching 当日成交翻倍,尾盘 1h 最剧

  USAGE :
    from core.focus.activity_profile import get_current_profile
    p = get_current_profile()
    # {
    #   "level":       "PEAK+" / "PEAK" / "HIGH" / "MEDIUM" / "LOW" / "MINIMAL" / "CLOSED",
    #   "poll_sec":    1,              # 轮询频率
    #   "scale":       0.6,            # 阈值缩放系数(<1 = 更敏感)
    #   "tag":         "🔥🔥开盘黄金时段",
    #   "reason":      "RTH 09:30-10:30 第一小时",
    #   "market":      "regular",
    #   "event":       "triple_witching" | None,
    #   "monday_boost": True | False,
    # }

  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, time as dtime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .market_clock import get_market_status, _is_trading_day
from .event_calendar import (
    get_event_type,
    is_witching_hour,
    is_triple_witching,
    is_monthly_opex,
)

ET = ZoneInfo("America/New_York")


# ══════════════════════════════════════════════════════════════════
#  等级定义(单一真相源)
# ══════════════════════════════════════════════════════════════════
#
#  level       poll_sec   scale    说明
#  ───────────────────────────────────────────────────────────────
#  PEAK+       0.5        0.60     巫时刻 / 周一开盘第一小时(最激进)
#  PEAK        1.0        0.75     RTH 第一 & 最后 1 小时
#  HIGH        2.0        0.90     盘前 8:00 后 / 盘后 16-17 点 / RTH 第二小时
#  MEDIUM      3.0        1.00     RTH 普通时段(默认基准)
#  LOW         10.0       1.30     盘前 4-8 点 / 盘后 17-20 点 / RTH 午间
#  MINIMAL     30.0       1.80     夜盘(流动性差,过滤假信号)
#  CLOSED      60.0       —        真休市(周末/节假日/空档)
#
LEVEL_SPECS = {
    "PEAK+":   {"poll_sec": 0.5,  "scale": 0.60, "emoji": "🔥🔥"},
    "PEAK":    {"poll_sec": 1.0,  "scale": 0.75, "emoji": "🔥"},
    "HIGH":    {"poll_sec": 2.0,  "scale": 0.90, "emoji": "🟢"},
    "MEDIUM":  {"poll_sec": 3.0,  "scale": 1.00, "emoji": "⚪"},
    "LOW":     {"poll_sec": 10.0, "scale": 1.30, "emoji": "🔵"},
    "MINIMAL": {"poll_sec": 30.0, "scale": 1.80, "emoji": "🌃"},
    "CLOSED":  {"poll_sec": 60.0, "scale": None, "emoji": "🌙"},
}

# 周一加速(PEAK/PEAK+ 除外,它们已经封顶)
MONDAY_POLL_MULTIPLIER  = 0.67   # poll_sec × 0.67  (等同于频率 × 1.5)
MONDAY_SCALE_MULTIPLIER = 0.92   # scale × 0.92     (阈值降 8%)


# ══════════════════════════════════════════════════════════════════
#  时段 → 等级 映射
# ══════════════════════════════════════════════════════════════════

def _classify_by_time(et_now: datetime, market_status: str) -> tuple[str, str]:
    """
    根据美东时间和市场状态,返回 (level, reason)
    不考虑事件和周一加速,那些在上层合成。
    """
    t = et_now.time()

    if market_status == "closed":
        return "CLOSED", "休市"

    if market_status == "regular":
        # 第一小时 9:30-10:30 和 最后一小时 15:00-16:00 最活跃
        if dtime(9, 30) <= t < dtime(10, 30):
            return "PEAK", "RTH 开盘第一小时(波动/成交最高)"
        if dtime(15, 0) <= t < dtime(16, 0):
            return "PEAK", "RTH 收盘前一小时(机构调仓)"
        # 第二小时次活跃
        if dtime(10, 30) <= t < dtime(11, 30):
            return "HIGH", "RTH 开盘第二小时"
        if dtime(14, 0) <= t < dtime(15, 0):
            return "HIGH", "RTH 收盘前第二小时(机构进场)"
        # 午间低迷
        if dtime(11, 30) <= t < dtime(14, 0):
            return "LOW", "RTH 午间低迷时段"
        return "MEDIUM", "RTH 普通时段"

    if market_status == "pre":
        # 08:00 后盘前开始活跃
        if t >= dtime(8, 0):
            return "HIGH", "盘前活跃时段(经济数据/开盘在即)"
        return "LOW", "盘前早时段(流动性低)"

    if market_status == "post":
        # 16:00-17:00 盘后第一小时财报集中
        if dtime(16, 0) <= t < dtime(17, 0):
            return "HIGH", "盘后第一小时(财报反应)"
        return "LOW", "盘后普通时段"

    if market_status == "overnight":
        return "MINIMAL", "夜盘(流动性差,过滤假信号)"

    return "MEDIUM", f"未知状态 {market_status}"


# ══════════════════════════════════════════════════════════════════
#  等级升级:事件日 / 周一加速
# ══════════════════════════════════════════════════════════════════

def _upgrade_for_event(level: str, et_now: datetime) -> tuple[str, str | None]:
    """
    事件日 + 巫时刻合流时,把等级升级。返回 (new_level, event_type)

    规则:
      - Triple Witching + 巫时刻(15:00-16:00)→ PEAK+
      - Triple Witching 全天 → 基础级别升 1 级(最高到 PEAK)
      - Monthly Opex + 巫时刻 → PEAK
      - 其他事件日 → 不升级
    """
    ev = get_event_type(et_now)
    if ev is None:
        return level, None

    if ev == "triple_witching":
        if is_witching_hour(et_now):
            return "PEAK+", ev
        # 巫日的其他 RTH 时段,整体升一级
        upgrade_map = {"MEDIUM": "HIGH", "HIGH": "PEAK", "LOW": "MEDIUM"}
        return upgrade_map.get(level, level), ev

    if ev == "monthly_opex":
        if is_witching_hour(et_now):
            return "PEAK", ev
        return level, ev

    # weekly_opex:不升级
    return level, ev


def _is_monday_open_window(et_now: datetime) -> bool:
    """周一开盘第一小时(9:30-10:30 ET)"""
    if et_now.weekday() != 0:   # 0 = Monday
        return False
    t = et_now.time()
    return dtime(9, 30) <= t < dtime(10, 30)


def _apply_monday_boost(level: str, et_now: datetime) -> tuple[str, bool]:
    """
    周一交易日(非 PEAK+ 级别)加速 50%。
    返回 (level, monday_boost_applied)
    """
    if et_now.weekday() != 0:     # 非周一
        return level, False
    if not _is_trading_day(et_now):
        return level, False

    # 周一开盘第一小时直接升到 PEAK+
    if _is_monday_open_window(et_now) and level == "PEAK":
        return "PEAK+", True

    # 其他周一时段,保留等级但给"加速"标记(频率/阈值在 get_current_profile 里再调)
    return level, True


# ══════════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════════

def get_current_profile(now: datetime = None) -> dict:
    """
    返回当前时刻的机会密度画像。其他模块只需要读这一个函数。
    """
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    market_status = get_market_status(now)

    # 1) 时段基础等级
    level, reason = _classify_by_time(now, market_status)

    # 2) 事件升级
    level, event = _upgrade_for_event(level, now)

    # 3) 周一加速
    level, monday_boost = _apply_monday_boost(level, now)

    # 4) 转换成实际参数
    spec = LEVEL_SPECS.get(level, LEVEL_SPECS["MEDIUM"])
    poll_sec = spec["poll_sec"]
    scale = spec["scale"]

    # 周一加速(PEAK+ 除外)
    if monday_boost and level != "PEAK+":
        poll_sec *= MONDAY_POLL_MULTIPLIER
        if scale is not None:
            scale *= MONDAY_SCALE_MULTIPLIER

    # 5) 标签
    tag = _build_tag(level, event, monday_boost)

    return {
        "level":        level,
        "poll_sec":     round(poll_sec, 2),
        "scale":        round(scale, 3) if scale is not None else None,
        "tag":          tag,
        "reason":       reason,
        "market":       market_status,
        "event":        event,
        "monday_boost": monday_boost,
        "et_time":      now.strftime("%H:%M ET"),
    }


def _build_tag(level: str, event: str | None, monday: bool) -> str:
    """人类可读的短标签,用于推送抬头"""
    spec = LEVEL_SPECS.get(level, LEVEL_SPECS["MEDIUM"])
    emoji = spec["emoji"]

    name_map = {
        "PEAK+":   "极致",
        "PEAK":    "黄金",
        "HIGH":    "活跃",
        "MEDIUM":  "平稳",
        "LOW":     "低迷",
        "MINIMAL": "夜盘",
        "CLOSED":  "休市",
    }
    parts = [f"{emoji}{name_map.get(level, level)}"]

    if event == "triple_witching":
        parts.append("🧙")
    elif event == "monthly_opex":
        parts.append("📆")

    if monday:
        parts.append("⚡周一")

    return " ".join(parts)


def scale_params(base_params: dict, scale: float) -> dict:
    """
    把基础阈值按 scale 缩放。返回新字典(不改原字典)。

    三类字段:
      1) 百分比阈值类(缩放敏感度):
         scale < 1 → 更敏感(PEAK/PEAK+ 时段更容易触发)
         scale > 1 → 更保守(LOW/MINIMAL 时段过滤假信号)
      2) 冷却时间类(缩放间隔):
         scale < 1 → 间隔更短,推送更频繁
         scale > 1 → 间隔更长,推送更稀疏
      3) RSI / 时间窗 / 量比:数学或业务语义固定,永不缩放

    匹配 swing_detector v0.5.4 的完整 DEFAULT_PARAMS 字段。
    """
    if scale is None or abs(scale - 1.0) < 1e-6:
        return dict(base_params)

    # 百分比/金额阈值(缩放决定触发敏感度)
    PCT_FIELDS = {
        "profit_target_pct",        # 浮盈 %
        "profit_target_usd",        # 浮盈 $
        "drawdown_pct",             # 回撤 %
        "rapid_move_pct",           # 快速异动 %
        "trend_day_change_pct",     # 方向趋势 %
        "swing_min_move",           # 波段幅度 %
        # 波段顶底的"距离高低点"阈值(有正负,直接乘系数即可)
        "near_high_pct_strong",
        "near_high_pct_weak",
        "near_low_pct_strong",
        "near_low_pct_weak",
    }

    # 冷却时间(缩放决定推送节奏)
    COOLDOWN_FIELDS = {
        "rapid_move_cooldown",
        "trend_cooldown_sec",
        "swing_cooldown_weak",
        "swing_cooldown_strong",
        "global_mutex_sec",
    }

    # 不缩:RSI / 时间窗 / 量比(显式列出避免遗漏)
    # UNTOUCHED = {
    #     "rsi_overbought", "rsi_oversold",
    #     "rsi_overbought_strong", "rsi_oversold_strong",
    #     "rsi_overbought_weak", "rsi_oversold_weak",
    #     "trend_rsi_long", "trend_rsi_short",
    #     "rapid_move_window", "breakout_vol_ratio",
    # }

    scaled = {}
    for k, v in base_params.items():
        if isinstance(v, (int, float)):
            if k in PCT_FIELDS:
                scaled[k] = round(v * scale, 4)
            elif k in COOLDOWN_FIELDS:
                # 冷却:保持整数秒,且设下限 10 秒(避免 PEAK+ 缩到 6s 过刷)
                scaled[k] = max(10, int(round(v * scale)))
            else:
                scaled[k] = v
        else:
            scaled[k] = v
    return scaled


def format_profile_line(profile: dict = None) -> str:
    """
    给 /status 和推送用的单行状态
      "🔥黄金 · 🧙 · RTH 开盘第一小时 · 轮询 1s · 阈值×0.75"
    """
    if profile is None:
        profile = get_current_profile()

    parts = [profile["tag"]]
    parts.append(profile["reason"])
    parts.append(f"轮询 {profile['poll_sec']}s")
    if profile["scale"] is not None:
        parts.append(f"阈值×{profile['scale']:.2f}")
    return "  ·  ".join(parts)


def format_profile_forecast(hours: int = 12, now: datetime = None) -> str:
    """
    生成未来 N 小时的机会密度时间线,给 /profile 指令用。
    每 30 分钟采样一次。
    """
    from datetime import timedelta
    if now is None:
        now = datetime.now(ET)

    lines = [f"📊 <b>机会密度时间线(未来 {hours} 小时)</b>", "━━━━━━━━━━━━━━"]

    prev_level = None
    for i in range(0, hours * 2):   # 每 30 分钟一个点
        t = now + timedelta(minutes=30 * i)
        p = get_current_profile(t)
        if p["level"] != prev_level:
            t_local = t.astimezone()  # 显示本地时间
            lines.append(f"{t_local.strftime('%m-%d %H:%M')}  {p['tag']}  ({p['reason']})")
            prev_level = p["level"]

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  自测
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    from datetime import datetime as _dt

    cases = [
        ("周一 09:45 ET (周一开盘)",    _dt(2026, 4, 20, 9, 45, tzinfo=ET)),
        ("周一 12:00 ET (周一午间)",    _dt(2026, 4, 20, 12, 0, tzinfo=ET)),
        ("周三 09:45 ET (普通开盘)",    _dt(2026, 4, 22, 9, 45, tzinfo=ET)),
        ("周三 12:00 ET (普通午间)",    _dt(2026, 4, 22, 12, 0, tzinfo=ET)),
        ("周三 15:30 ET (普通收盘)",    _dt(2026, 4, 22, 15, 30, tzinfo=ET)),
        ("周三 20:00 ET (夜盘开始)",    _dt(2026, 4, 22, 20, 0, tzinfo=ET)),
        ("周三 23:00 ET (夜盘)",        _dt(2026, 4, 22, 23, 0, tzinfo=ET)),
        ("2026-06-19 10:00 (巫日开盘)", _dt(2026, 6, 19, 10, 0, tzinfo=ET)),
        ("2026-06-19 15:30 (巫时刻)",   _dt(2026, 6, 19, 15, 30, tzinfo=ET)),
        ("2026-04-17 15:30 (月度Opex尾盘)", _dt(2026, 4, 17, 15, 30, tzinfo=ET)),
        ("周六 10:00 (周末)",           _dt(2026, 4, 25, 10, 0, tzinfo=ET)),
    ]
    for label, t in cases:
        p = get_current_profile(t)
        print(f"  {label:40s} {p['tag']:20s} poll={p['poll_sec']:5.2f}s "
              f"scale={p['scale']}")

    print("\n--- 当前画像 ---")
    print(format_profile_line())

    print("\n--- scale_params 示例 ---")
    base = {"rapid_move_pct": 1.0, "drawdown_pct": 1.2, "rsi_overbought": 70}
    print(f"  base  : {base}")
    print(f"  ×0.75 : {scale_params(base, 0.75)}")
    print(f"  ×1.30 : {scale_params(base, 1.30)}")
