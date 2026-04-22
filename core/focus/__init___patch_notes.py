"""
════════════════════════════════════════════════════════════════════
  core/focus/__init__.py — 补丁说明
  不要用这个文件覆盖你本地的 __init__.py!
  只要把下面 "【需要新增的部分】" 加到你本地文件里即可。
════════════════════════════════════════════════════════════════════

你本地 __init__.py 应该已经有这些(如 AI advisor / manual_consult / heartbeat 等):
    from .focus_manager import start_focus, stop_focus, get_focus_status, is_focused
    from .ai_advisor import ...
    from .manual_consult import ...
    ...

【需要新增的部分】— 追加到文件末尾,在现有 __all__ 之前:

# ── v0.5.8 新增:机会密度画像 ──────────────────────────────
try:
    from .activity_profile import (
        get_current_profile,
        format_profile_line,
        format_profile_forecast,
        scale_params as scale_activity_params,
    )
    HAS_ACTIVITY_PROFILE = True
except ImportError:
    HAS_ACTIVITY_PROFILE = False

# ── v0.5.8 新增:事件日历(巫日/月度期权到期) ──────────────
try:
    from .event_calendar import (
        get_event_type,
        is_triple_witching,
        is_witching_hour,
        next_triple_witching,
        format_event_line,
    )
    HAS_EVENT_CALENDAR = True
except ImportError:
    HAS_EVENT_CALENDAR = False

# ── v0.5.8 新增:主动提醒 ────────────────────────────────
try:
    from .proactive_reminder import (
        check_and_fire_reminders,
        format_reminder_schedule,
    )
    HAS_PROACTIVE_REMINDER = True
except ImportError:
    HAS_PROACTIVE_REMINDER = False

# ── 对应扩展 __all__ ────────────────────────────────────
# 如果你的 __all__ 是元组或列表,把下面这些加进去:
# "get_current_profile", "format_profile_line", "format_profile_forecast",
# "scale_activity_params",
# "get_event_type", "is_triple_witching", "is_witching_hour",
# "next_triple_witching", "format_event_line",
# "check_and_fire_reminders", "format_reminder_schedule",
# "HAS_ACTIVITY_PROFILE", "HAS_EVENT_CALENDAR", "HAS_PROACTIVE_REMINDER",
"""
