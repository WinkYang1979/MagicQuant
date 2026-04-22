"""
MagicQuant Focus Module — 波段做 T 盯盘系统
Dare to dream. Data to win.

v0.3.6 新增:
  - manual_consult: 主动召集 AI 智囊团(不依赖触发器)
  - heartbeat:      系统心跳监控(解决沉默感)
"""

from .focus_manager import (
    start_focus,
    stop_focus,
    get_focus_status,
    is_focused,
    set_ai_advise,
    is_ai_advise_enabled,
)

from .feedback import (
    verify_trigger,
    mark_ignored,
    recompute_price,
    get_pending_count,
)

# v0.3.5: AI 智囊团
try:
    from .ai_advisor import consult_advisors
    HAS_AI_ADVISOR = True
except ImportError:
    HAS_AI_ADVISOR = False

# v0.3.6: 手动召集接口
try:
    from .manual_consult import manual_consult
    HAS_MANUAL_CONSULT = True
except ImportError:
    HAS_MANUAL_CONSULT = False

# v0.3.6: 心跳监控
try:
    from .heartbeat import (
        format_heartbeat,
        get_heartbeat_text,
        start_heartbeat_loop,
        stop_heartbeat_loop,
        is_heartbeat_enabled,
        get_heartbeat_interval,
    )
    HAS_HEARTBEAT = True
except ImportError:
    HAS_HEARTBEAT = False

# v0.4.1: 做 T 决策面板
try:
    from .tactical_panel import build_tactical_panel
    HAS_TACTICAL_PANEL = True
except ImportError as e:
    HAS_TACTICAL_PANEL = False
    print(f"  [focus] tactical_panel not available: {e}")


__all__ = [
    # Focus 主体
    "start_focus",
    "stop_focus",
    "get_focus_status",
    "is_focused",
    "set_ai_advise",
    "is_ai_advise_enabled",
    # Feedback
    "verify_trigger",
    "mark_ignored",
    "recompute_price",
    "get_pending_count",
    # AI 智囊团
    "HAS_AI_ADVISOR",
    # 手动召集(v0.3.6)
    "manual_consult",
    "HAS_MANUAL_CONSULT",
    # 心跳(v0.3.6)
    "format_heartbeat",
    "get_heartbeat_text",
    "start_heartbeat_loop",
    "stop_heartbeat_loop",
    "is_heartbeat_enabled",
    "get_heartbeat_interval",
    "HAS_HEARTBEAT",
]
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

# ── v0.5.8 新增:事件日历 ──────────────────────────────────
try:
    from .event_calendar import (
        get_event_type, is_triple_witching, is_witching_hour,
        next_triple_witching, format_event_line,
    )
    HAS_EVENT_CALENDAR = True
except ImportError:
    HAS_EVENT_CALENDAR = False

# ── v0.5.8 新增:主动提醒 ──────────────────────────────────
try:
    from .proactive_reminder import (
        check_and_fire_reminders, format_reminder_schedule,
    )
    HAS_PROACTIVE_REMINDER = True
except ImportError:
    HAS_PROACTIVE_REMINDER = False