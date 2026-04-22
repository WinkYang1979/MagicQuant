"""
════════════════════════════════════════════════════════════════════
  MagicQuant — proactive_reminder.py
  VERSION : v0.1.0
  DATE    : 2026-04-22
  PURPOSE :
    在黄金时段前主动推送提醒,让用户有时间准备:

    提醒点(按 ET):
      1) RTH 开盘前 15 分钟      (ET 09:15,墨尔本 23:15)
      2) RTH 收盘前 30 分钟      (ET 15:30,墨尔本 05:30 次日)
      3) 周一开盘前 45 分钟      (ET 周一 08:45,墨尔本 周一 22:45)
         — 额外 15 分钟让你消化周末新闻
      4) 巫日开盘前 45 分钟      (ET 巫日 08:45,墨尔本 22:45)
      5) 巫时刻前 15 分钟        (ET 14:45,墨尔本 04:45 次日)

    防打扰:
      - 每个提醒每天只推一次(按 ET 日期去重)
      - Focus 未启动时不推送
      - 重启 bot 不会补推历史点

  USAGE :
    from core.focus.proactive_reminder import check_and_fire_reminders
    check_and_fire_reminders(session, send_tg_fn)  # 每轮循环调一次

  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, time as dtime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .market_clock import _is_trading_day
from .event_calendar import is_triple_witching, is_monthly_opex

ET = ZoneInfo("America/New_York")

VERSION = "v0.1.0"

# ══════════════════════════════════════════════════════════════════
#  提醒点定义
# ══════════════════════════════════════════════════════════════════
#
#  每个提醒点有:
#   - key         : 用于去重(同 key 同日只推一次)
#   - window_min  : 触发窗口长度(分钟)— 落在窗口内则推
#   - check_fn    : 接收 et_now,返回是否触发
#   - build_fn    : 接收 (et_now, session),返回推送文本
#
#  用"触发窗口"而非"准确时间点"的原因:
#   主循环每 1-30 秒跑一次,可能错过准确分钟。给 60 秒窗口容错。

REMINDER_WINDOW_SEC = 90   # 到达提醒点前后 90 秒内任意时刻都算命中


def _in_window(et_now: datetime, target_time: dtime) -> bool:
    """et_now 是否在 target_time 的 ±90s 窗口内"""
    today_target = et_now.replace(
        hour=target_time.hour, minute=target_time.minute,
        second=0, microsecond=0,
    )
    delta = abs((et_now - today_target).total_seconds())
    return delta <= REMINDER_WINDOW_SEC


# ══════════════════════════════════════════════════════════════════
#  各提醒的检查 + 构造
# ══════════════════════════════════════════════════════════════════

def _check_rth_open(et_now: datetime) -> bool:
    """RTH 开盘前 15 分钟 = 09:15 ET,必须交易日"""
    if not _is_trading_day(et_now):
        return False
    return _in_window(et_now, dtime(9, 15))


def _build_rth_open(et_now: datetime, session) -> str:
    lines = [
        "🟢 <b>美股 15 分钟后开盘</b>",
        "━━━━━━━━━━━━━━",
        f"📡 ET 09:15  ·  墨尔本 {et_now.astimezone().strftime('%H:%M')}",
        "",
        "⏰ 开盘第一小时是 <b>黄金波动时段</b>",
        "   · 轮询 1 秒  ·  阈值 ×0.75  ·  信号密度翻倍",
        "",
        _positions_brief(session),
        "",
        "💡 准备: /status 看持仓  ·  /heartbeat 看心跳",
    ]
    return "\n".join(lines)


def _check_rth_close(et_now: datetime) -> bool:
    """RTH 收盘前 30 分钟 = 15:30 ET,必须交易日"""
    if not _is_trading_day(et_now):
        return False
    return _in_window(et_now, dtime(15, 30))


def _build_rth_close(et_now: datetime, session) -> str:
    lines = [
        "🟠 <b>美股 30 分钟后收盘</b>",
        "━━━━━━━━━━━━━━",
        f"📡 ET 15:30  ·  墨尔本 {et_now.astimezone().strftime('%H:%M')}",
        "",
        "⏰ 尾盘 30 分钟 = <b>机构调仓时段</b>",
        "   · 拉升 / 砸盘常见  ·  阈值 ×0.75",
        "",
        _positions_brief(session),
        "",
        "💡 考虑: 减仓锁利润?  日内 T+0 次数用尽?",
    ]
    return "\n".join(lines)


def _check_monday_open(et_now: datetime) -> bool:
    """周一 RTH 开盘前 45 分钟 = 周一 08:45 ET"""
    if et_now.weekday() != 0:
        return False
    if not _is_trading_day(et_now):
        return False
    return _in_window(et_now, dtime(8, 45))


def _build_monday_open(et_now: datetime, session) -> str:
    lines = [
        "⚡ <b>周一 45 分钟后开盘 — 周末消息消化窗口</b>",
        "━━━━━━━━━━━━━━",
        f"📡 ET 08:45  ·  墨尔本 {et_now.astimezone().strftime('%H:%M')}",
        "",
        "📰 <b>周末消息点检查表</b>",
        "   · 地缘政治(中东/台海)",
        "   · 美联储官员讲话  ·  周末经济数据",
        "   · 标的相关新闻(RKLB 发射/合同/竞品)",
        "",
        "⏰ 周一开盘第一小时 = <b>最激进时段 PEAK+</b>",
        "   · 轮询 0.5 秒  ·  阈值 ×0.55",
        "   · Gap 开盘后趋势常持续数小时",
        "",
        _positions_brief(session),
        "",
        "💡 看 RKLB 盘前: /detail RKLB",
    ]
    return "\n".join(lines)


def _check_witching_day_open(et_now: datetime) -> bool:
    """巫日开盘前 45 分钟 = 08:45 ET(同周一,但只在巫日生效)"""
    if not is_triple_witching(et_now):
        return False
    return _in_window(et_now, dtime(8, 45))


def _build_witching_day_open(et_now: datetime, session) -> str:
    lines = [
        "🧙 <b>三重巫日今日开盘 — 45 分钟后</b>",
        "━━━━━━━━━━━━━━",
        f"📡 ET 08:45  ·  墨尔本 {et_now.astimezone().strftime('%H:%M')}",
        "",
        "🧙 <b>股指期货 + 股指期权 + 股票期权同日到期</b>",
        "   · 全天成交量可达日均 <b>2 倍</b>",
        "   · 尾盘 15:00-16:00 ET 波动最剧(巫时刻)",
        "   · 机构平仓/移仓,做市商 pin 行权价",
        "",
        "⚠️ <b>风险与机会并存</b>",
        "   · SPX 历年巫日平均日内振幅扩大 7%",
        "   · 建议仓位保守,不建议持仓过夜",
        "",
        _positions_brief(session),
        "",
        "💡 巫时刻 15 分钟前会再推提醒",
    ]
    return "\n".join(lines)


def _check_witching_hour(et_now: datetime) -> bool:
    """巫时刻前 15 分钟 = 14:45 ET(仅巫日生效)"""
    if not is_triple_witching(et_now):
        return False
    return _in_window(et_now, dtime(14, 45))


def _build_witching_hour(et_now: datetime, session) -> str:
    lines = [
        "🧙🧙 <b>巫时刻 15 分钟后开启 — 最剧烈时段</b>",
        "━━━━━━━━━━━━━━",
        f"📡 ET 14:45  ·  墨尔本 {et_now.astimezone().strftime('%H:%M')}",
        "",
        "🔥 <b>15:00-16:00 ET 最后一小时</b>",
        "   · 历史上单分钟波动 > 1% 常见",
        "   · 期权做市商 pin 行权价",
        "   · 轮询 0.5 秒 · 阈值 ×0.60",
        "",
        _positions_brief(session),
        "",
        "⚠️ 如果不想扛尾盘波动,现在是减仓窗口",
    ]
    return "\n".join(lines)


def _positions_brief(session) -> str:
    """简短的持仓行"""
    if not session or not hasattr(session, "positions_snapshot"):
        return "(无持仓信息)"
    positions = session.positions_snapshot or {}
    tracked = [t for t in ["US.RKLB", "US.RKLX", "US.RKLZ"]
               if t in positions and positions[t].get("qty", 0) > 0]
    if not tracked:
        return "📊 当前无 RKLB 相关持仓"
    lines = ["📊 <b>当前持仓</b>"]
    for tk in tracked:
        p = positions[tk]
        qty = p.get("qty", 0)
        pl  = p.get("pl_val", 0)
        pl_pct = p.get("pl_pct", 0)
        sign = "+" if pl >= 0 else ""
        short = tk.replace("US.", "")
        lines.append(f"   · {short}: {qty:.0f}股  {sign}${pl:.2f} ({sign}{pl_pct:.2f}%)")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  提醒注册表 (按优先级排序)
# ══════════════════════════════════════════════════════════════════

REMINDERS = [
    {
        "key":   "witching_hour",
        "check": _check_witching_hour,
        "build": _build_witching_hour,
    },
    {
        "key":   "witching_day_open",
        "check": _check_witching_day_open,
        "build": _build_witching_day_open,
    },
    {
        "key":   "monday_open",
        "check": _check_monday_open,
        "build": _build_monday_open,
    },
    {
        "key":   "rth_open",
        "check": _check_rth_open,
        "build": _build_rth_open,
    },
    {
        "key":   "rth_close",
        "check": _check_rth_close,
        "build": _build_rth_close,
    },
]


# ══════════════════════════════════════════════════════════════════
#  主入口:每轮 focus loop 调一次
# ══════════════════════════════════════════════════════════════════

def check_and_fire_reminders(session, send_tg_fn) -> int:
    """
    检查所有提醒点,命中则发送,并用 session.fired_reminders 去重。
    每个提醒每 ET 日只推一次。
    返回推送的条数。
    """
    if session is None or send_tg_fn is None:
        return 0

    # 去重集合:{(key, et_date_str), ...}
    if not hasattr(session, "fired_reminders"):
        session.fired_reminders = set()

    et_now = datetime.now(ET)
    et_date = et_now.strftime("%Y-%m-%d")
    fired = 0

    for rem in REMINDERS:
        key = rem["key"]
        dedup_key = (key, et_date)
        if dedup_key in session.fired_reminders:
            continue

        try:
            if rem["check"](et_now):
                text = rem["build"](et_now, session)
                send_tg_fn(text)
                session.fired_reminders.add(dedup_key)
                fired += 1
                # 一轮内只推一条,避免撞车
                break
        except Exception as e:
            print(f"  [reminder] {key} failed: {e}")

    return fired


def format_reminder_schedule() -> str:
    """给 /status 或 /profile 显示今天的提醒清单"""
    et_now = datetime.now(ET)
    lines = [
        f"⏰ <b>今日提醒计划</b>  ({et_now.strftime('%Y-%m-%d')} ET)",
        "━━━━━━━━━━━━━━",
    ]

    schedule = []
    if _is_trading_day(et_now):
        if et_now.weekday() == 0:
            schedule.append(("⚡ 周一开盘前 45 分钟",   "08:45 ET"))
        if is_triple_witching(et_now):
            schedule.append(("🧙 巫日开盘前 45 分钟",   "08:45 ET"))
            schedule.append(("🧙🧙 巫时刻前 15 分钟",   "14:45 ET"))
        schedule.append(("🟢 RTH 开盘前 15 分钟",       "09:15 ET"))
        schedule.append(("🟠 RTH 收盘前 30 分钟",       "15:30 ET"))

    if not schedule:
        lines.append("(非交易日,无提醒)")
    else:
        for label, t in schedule:
            lines.append(f"   · {t}   {label}")

    return "\n".join(lines)


if __name__ == "__main__":
    # 模拟测试
    class FakeSession:
        positions_snapshot = {}
        fired_reminders = set()

    print(format_reminder_schedule())
    print()
    print("=== 触发测试 ===")
    # 假装现在是不同时间,看各个提醒是否触发
    from datetime import datetime as _dt
    cases = [
        ("周三 09:15 ET", _dt(2026, 4, 22, 9, 15, tzinfo=ET)),
        ("周一 08:45 ET", _dt(2026, 4, 20, 8, 45, tzinfo=ET)),
        ("巫日 08:45 ET", _dt(2026, 6, 18, 8, 45, tzinfo=ET)),
        ("巫日 14:45 ET", _dt(2026, 6, 18, 14, 45, tzinfo=ET)),
        ("周六 10:00 ET", _dt(2026, 4, 25, 10, 0, tzinfo=ET)),
    ]
    for label, t in cases:
        hits = []
        for rem in REMINDERS:
            if rem["check"](t):
                hits.append(rem["key"])
        print(f"  {label}: {hits or '(无触发)'}")
