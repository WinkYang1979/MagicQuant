"""
════════════════════════════════════════════════════════════════════
  MagicQuant — event_calendar.py
  VERSION : v0.1.0
  DATE    : 2026-04-22
  PURPOSE :
    特殊交易日事件日历:
      - Triple Witching Day (三重巫日):每季度第 3 个周五
        股指期货 + 股指期权 + 股票期权同时到期
        最后 1 小时 (15:00-16:00 ET) 波动爆炸
      - Monthly Opex (月度期权到期日):每月第 3 个周五(非季末月份)
      - Weekly Opex (周度期权到期日):每个周五(影响较弱)

  USAGE :
    from core.focus.event_calendar import (
        get_event_type,          # "triple_witching" / "monthly_opex" / "weekly_opex" / None
        is_witching_hour,        # 巫时刻 (当日 15:00-16:00 ET)
        next_triple_witching,    # 下一个巫日
        format_event_line,       # "🧙 巫日 · 距巫时刻 4 小时 32 分"
    )

  NOTES :
    Triple Witching: 每年 3/6/9/12 月的第 3 个周五
      2026: 03-20, 06-19, 09-18, 12-18
      2027: 03-19, 06-18, 09-17, 12-17
    "巫时刻" = 收盘前最后 1 小时 (15:00-16:00 ET)

  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta, time as dtime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# 巫时刻(收盘前最后 1 小时)
WITCHING_HOUR_START = dtime(15, 0)
WITCHING_HOUR_END   = dtime(16, 0)

# 季度巫日月份
QUARTERLY_MONTHS = {3, 6, 9, 12}

# 2026/2027 年已确认 Triple Witching(对应 NYSE 官方日历)
# 注意:2026-06-19 是 Juneteenth 休市,巫日提前到 2026-06-18 周四
#      2027 年无类似冲突
TRIPLE_WITCHING_DATES = {
    "2026-03-20", "2026-06-18", "2026-09-18", "2026-12-18",
    "2027-03-19", "2027-06-18", "2027-09-17", "2027-12-17",
}


def _third_friday(year: int, month: int) -> datetime:
    """给定年月,返回当月第 3 个周五"""
    first = datetime(year, month, 1)
    # 找出第 1 个周五
    days_to_friday = (4 - first.weekday()) % 7
    first_friday = first + timedelta(days=days_to_friday)
    return first_friday + timedelta(days=14)


def is_triple_witching(d: datetime = None) -> bool:
    """
    是否为 Triple Witching Day。
    优先查硬编码表(已处理节假日冲突)。
    """
    if d is None:
        d = datetime.now(ET)
    elif d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    else:
        d = d.astimezone(ET)
    date_str = d.strftime("%Y-%m-%d")
    return date_str in TRIPLE_WITCHING_DATES


def is_monthly_opex(d: datetime = None) -> bool:
    """
    是否为月度期权到期日(每月第 3 个周五,包括季末月份 — 巫日也算)
    如果当日为节假日休市,返回 False(期权实际已于前一交易日结算)
    """
    if d is None:
        d = datetime.now(ET)
    elif d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    else:
        d = d.astimezone(ET)
    if d.weekday() != 4:  # 必须周五
        return False
    # 排除节假日(本模块需读 market_clock 判断,避免循环导入用延迟 import)
    try:
        from .market_clock import _is_trading_day
        if not _is_trading_day(d):
            return False
    except ImportError:
        # 本模块独立测试时 fallback
        from market_clock import _is_trading_day
        if not _is_trading_day(d):
            return False
    return d.date() == _third_friday(d.year, d.month).date()


def is_weekly_opex(d: datetime = None) -> bool:
    """
    是否为周度期权到期日(每个周五)— 弱事件
    节假日休市的周五返回 False
    """
    if d is None:
        d = datetime.now(ET)
    elif d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    else:
        d = d.astimezone(ET)
    if d.weekday() != 4:
        return False
    try:
        from .market_clock import _is_trading_day
        if not _is_trading_day(d):
            return False
    except ImportError:
        from market_clock import _is_trading_day
        if not _is_trading_day(d):
            return False
    return True


def get_event_type(d: datetime = None) -> str | None:
    """
    返回当天事件类型(优先级高的优先):
      "triple_witching" > "monthly_opex" > "weekly_opex" > None
    """
    if is_triple_witching(d):
        return "triple_witching"
    if is_monthly_opex(d):
        return "monthly_opex"
    if is_weekly_opex(d):
        return "weekly_opex"
    return None


def is_witching_hour(d: datetime = None) -> bool:
    """是否处于当日的巫时刻(15:00-16:00 ET)— 仅在事件日有意义"""
    if d is None:
        d = datetime.now(ET)
    elif d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    else:
        d = d.astimezone(ET)
    return WITCHING_HOUR_START <= d.time() < WITCHING_HOUR_END


def next_triple_witching(d: datetime = None) -> datetime | None:
    """返回下一个 Triple Witching 的 datetime (15:00 ET, 巫时刻开始)"""
    if d is None:
        d = datetime.now(ET)
    elif d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    else:
        d = d.astimezone(ET)

    candidates = []
    for date_str in TRIPLE_WITCHING_DATES:
        y, m, day = map(int, date_str.split("-"))
        dt = datetime(y, m, day, 15, 0, tzinfo=ET)
        if dt > d:
            candidates.append(dt)
    if not candidates:
        return None
    return min(candidates)


def format_event_line(d: datetime = None) -> str:
    """
    生成事件状态单行摘要(若当日是事件日)
      "🧙 三重巫日  ·  距巫时刻 4h 32m"
      "📆 月度期权到期  ·  15:00 ET 后注意波动"
      "📅 周五周期权到期  ·  尾盘留意"
      ""  (非事件日)
    """
    if d is None:
        d = datetime.now(ET)
    elif d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    else:
        d = d.astimezone(ET)

    ev = get_event_type(d)
    if ev is None:
        return ""

    # 计算距离巫时刻
    witching_start = d.replace(hour=15, minute=0, second=0, microsecond=0)
    t = d.time()

    if ev == "triple_witching":
        if is_witching_hour(d):
            return "🧙 <b>巫时刻进行中</b>  ·  机构平仓/移仓,极端波动窗口"
        if t < WITCHING_HOUR_START:
            delta = witching_start - d
            mins = int(delta.total_seconds() // 60)
            h, m = divmod(mins, 60)
            if h > 0:
                return f"🧙 三重巫日  ·  距巫时刻 {h}h {m}m"
            return f"🧙 三重巫日  ·  距巫时刻 {m}m"
        return "🧙 三重巫日  ·  巫时刻已过"

    if ev == "monthly_opex":
        if is_witching_hour(d):
            return "📆 月度期权到期 · 尾盘活跃中"
        if t < WITCHING_HOUR_START:
            delta = witching_start - d
            mins = int(delta.total_seconds() // 60)
            h, m = divmod(mins, 60)
            return f"📆 月度期权到期日  ·  距尾盘 {h}h {m}m"
        return "📆 月度期权到期  ·  尾盘已过"

    if ev == "weekly_opex":
        return "📅 周五周期权到期  ·  尾盘留意"

    return ""


if __name__ == "__main__":
    # 自测
    from datetime import datetime as _dt
    cases = [
        ("今天(2026-04-22 周三)",  _dt(2026, 4, 22, 14, 0, tzinfo=ET), None),
        ("2026-03-20 周五 10:00 (三重巫日)",  _dt(2026, 3, 20, 10, 0, tzinfo=ET), "triple_witching"),
        ("2026-03-20 周五 15:30 (巫时刻)",    _dt(2026, 3, 20, 15, 30, tzinfo=ET), "triple_witching"),
        ("2026-04-17 周五 (月度 Opex,非季末)", _dt(2026, 4, 17, 12, 0, tzinfo=ET), "monthly_opex"),
        ("2026-04-24 周五 (普通周五周期权)",   _dt(2026, 4, 24, 12, 0, tzinfo=ET), "weekly_opex"),
        ("2026-06-19 周五 15:30 (Q2 巫时刻)",  _dt(2026, 6, 19, 15, 30, tzinfo=ET), "triple_witching"),
    ]
    for label, t, expect in cases:
        actual = get_event_type(t)
        mark = "✅" if actual == expect else "❌"
        line = format_event_line(t)
        print(f"{mark} {label}: {actual}  |  {line}")

    print()
    nxt = next_triple_witching()
    print(f"下个三重巫日: {nxt}")
    print(f"当前事件: {format_event_line() or '(非事件日)'}")
