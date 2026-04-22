"""
════════════════════════════════════════════════════════════════════
  MagicQuant — market_clock.py
  VERSION : v0.2.0
  DATE    : 2026-04-22
  CHANGES :
    v0.2.0 (2026-04-22):
      - 🆕 新增 "overnight" 状态:20:00 ET - 次日 03:50 ET
        对应 Moomoo Overnight Session + Futu overnight_price 字段
      - is_market_open(strict=False) 把 overnight 纳入开盘判断
      - next_overnight_close() 辅助函数(夜盘终结时间)
      - format_market_status() 夜盘显示 🌃 + 距 RTH 开盘倒计时
      - 向下兼容:其他接口不变,get_market_status 新增一种返回值
    v0.1.0:
      - 美股 regular/pre/post/closed 四态
  USAGE :
    from core.focus.market_clock import get_market_status, format_market_status
    status = get_market_status()
    # "regular" / "pre" / "post" / "overnight" / "closed"
  DEPENDS :
    Python 3.9+ (zoneinfo)
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta, time as dtime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# 2026 + 2027 美股休市日(RTH 整天不开,overnight 不会启动)
US_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
    "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
    "2027-11-25", "2027-12-24",
}

# 交易时段定义 (ET)
#   夜盘 OVERNIGHT : 20:00 (post 结束) → 次日 03:50
#   空档  CLOSED   : 03:50 → 04:00 (10 分钟结算窗)
#   盘前 PRE       : 04:00 → 09:30
#   盘中 REGULAR   : 09:30 → 16:00
#   盘后 POST      : 16:00 → 20:00
OVERNIGHT_END     = dtime(3, 50)   # 夜盘结束
PRE_MARKET_OPEN   = dtime(4, 0)
REGULAR_OPEN      = dtime(9, 30)
REGULAR_CLOSE     = dtime(16, 0)
POST_MARKET_CLOSE = dtime(20, 0)   # = OVERNIGHT_START


def _is_trading_day(d: datetime) -> bool:
    """RTH 交易日判断"""
    if d.weekday() >= 5:
        return False
    if d.strftime("%Y-%m-%d") in US_HOLIDAYS:
        return False
    return True


def _prev_day_is_trading(d: datetime) -> bool:
    """前一天是否为交易日(用于判断夜盘:周一 00:30 ET 属于上周五盘后延伸的夜盘)"""
    prev = d - timedelta(days=1)
    return _is_trading_day(prev)


def get_market_status(now=None) -> str:
    """
    返回美股当前市场状态:
      "regular"   — 盘中     9:30-16:00 ET
      "pre"       — 盘前     4:00-9:30 ET
      "post"      — 盘后     16:00-20:00 ET
      "overnight" — 夜盘     20:00-次日 3:50 ET (Overnight Session)
      "closed"    — 休市     周末/节假日/3:50-4:00 空档
    """
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    t = now.time()

    # 1) 凌晨 00:00-03:50:属于"上一交易日"的夜盘
    if t < OVERNIGHT_END:
        return "overnight" if _prev_day_is_trading(now) else "closed"

    # 2) 03:50-04:00:夜盘刚结算完,盘前未开,归 closed 空档
    if OVERNIGHT_END <= t < PRE_MARKET_OPEN:
        return "closed"

    # 3) 04:00 之后所有时段都要求"今天是交易日"
    if not _is_trading_day(now):
        return "closed"

    if PRE_MARKET_OPEN <= t < REGULAR_OPEN:
        return "pre"
    if REGULAR_OPEN <= t < REGULAR_CLOSE:
        return "regular"
    if REGULAR_CLOSE <= t < POST_MARKET_CLOSE:
        return "post"
    # 20:00 之后到 00:00:夜盘(前提:今天是交易日,上面已排除节假日)
    return "overnight"


def is_market_open(strict=False) -> bool:
    """
    strict=True  → 只有盘中算开盘
    strict=False → 盘前/盘中/盘后/夜盘 都算开盘(Moomoo AU 支持全时段)
    """
    status = get_market_status()
    if strict:
        return status == "regular"
    return status in ("regular", "pre", "post", "overnight")


def market_status_emoji(status: str) -> str:
    return {
        "regular":   "🟢",
        "pre":       "🟡",
        "post":      "🟠",
        "overnight": "🌃",
        "closed":    "🌙",
    }.get(status, "⚪")


def market_status_name_zh(status: str) -> str:
    return {
        "regular":   "盘中",
        "pre":       "盘前",
        "post":      "盘后",
        "overnight": "夜盘",
        "closed":    "休市",
    }.get(status, "未知")


def market_status_tag(status: str) -> str:
    """用于推送抬头的短标签,带 emoji + 中文"""
    return f"{market_status_emoji(status)}{market_status_name_zh(status)}"


def next_market_open(now=None) -> datetime:
    """返回下一次盘中开盘 (9:30 ET) 的 datetime"""
    if now is None:
        now = datetime.now(ET)

    today_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now < today_open and _is_trading_day(now):
        return today_open

    candidate = (now + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
    for _ in range(10):
        if _is_trading_day(candidate):
            return candidate
        candidate += timedelta(days=1)
    return None


def time_until_open(now=None):
    """距离下次 RTH 盘中开盘的 timedelta"""
    if now is None:
        now = datetime.now(ET)
    next_o = next_market_open(now)
    if next_o is None:
        return None
    return next_o - now


def next_overnight_close(now=None) -> datetime:
    """下次夜盘结束 (03:50 ET) — 仅在 overnight 状态下有意义"""
    if now is None:
        now = datetime.now(ET)
    t = now.time()
    # 如果在 20:00-24:00,夜盘在"明天"的 03:50 结束
    if t >= POST_MARKET_CLOSE:
        end = (now + timedelta(days=1)).replace(hour=3, minute=50, second=0, microsecond=0)
    else:
        # 如果在 00:00-03:50,夜盘就在"今天"的 03:50 结束
        end = now.replace(hour=3, minute=50, second=0, microsecond=0)
    return end


def format_time_delta(td: timedelta) -> str:
    if td is None or td.total_seconds() < 0:
        return "—"
    total_mins = int(td.total_seconds() / 60)
    days = total_mins // (24 * 60)
    hours = (total_mins % (24 * 60)) // 60
    mins = total_mins % 60
    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if mins > 0 or not parts:
        parts.append(f"{mins}分")
    return " ".join(parts)


def format_market_status(now=None) -> str:
    """生成市场状态单行摘要"""
    if now is None:
        now = datetime.now(ET)
    status = get_market_status(now)
    emoji = market_status_emoji(status)
    name = market_status_name_zh(status)
    et_time = now.strftime("%H:%M ET")

    if status == "closed":
        tu = time_until_open(now)
        if tu:
            return f"{emoji} 美股{name}  ·  {et_time}  ·  距开盘 {format_time_delta(tu)}"
    if status == "overnight":
        # 夜盘时同时显示距离夜盘结束 + 距离 RTH 开盘
        overnight_end = next_overnight_close(now)
        to_end = overnight_end - now
        to_rth = time_until_open(now)
        parts = [f"{emoji} 美股{name}", et_time, f"距夜盘收 {format_time_delta(to_end)}"]
        if to_rth:
            parts.append(f"距盘中 {format_time_delta(to_rth)}")
        return "  ·  ".join(parts)
    return f"{emoji} 美股{name}  ·  {et_time}"


if __name__ == "__main__":
    print(format_market_status())
    print(f"status:    {get_market_status()}")
    print(f"strict:    {is_market_open(strict=True)}")
    print(f"宽松:      {is_market_open(strict=False)}")
    print(f"next open: {next_market_open()}")

    # 自测不同时间点
    from datetime import datetime as _dt
    for label, t in [
        ("周二 10:00 ET", _dt(2026, 4, 21, 10, 0, tzinfo=ET)),
        ("周二 17:00 ET", _dt(2026, 4, 21, 17, 0, tzinfo=ET)),
        ("周二 23:30 ET", _dt(2026, 4, 21, 23, 30, tzinfo=ET)),
        ("周三 02:00 ET", _dt(2026, 4, 22, 2, 0, tzinfo=ET)),
        ("周三 03:55 ET", _dt(2026, 4, 22, 3, 55, tzinfo=ET)),
        ("周三 05:00 ET", _dt(2026, 4, 22, 5, 0, tzinfo=ET)),
        ("周六 10:00 ET", _dt(2026, 4, 25, 10, 0, tzinfo=ET)),
        ("周日 22:00 ET", _dt(2026, 4, 26, 22, 0, tzinfo=ET)),  # 周日夜盘?不
        ("周一 01:00 ET", _dt(2026, 4, 27, 1, 0, tzinfo=ET)),   # 周一凌晨?不(周日非交易日)
    ]:
        print(f"  {label}: {get_market_status(t)}")
