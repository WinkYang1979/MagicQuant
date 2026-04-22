"""
MagicQuant Focus Module — 波段做 T 盯盘系统
Dare to dream. Data to win.
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

try:
    from .ai_advisor import consult_advisors
    HAS_AI_ADVISOR = True
except ImportError:
    HAS_AI_ADVISOR = False

__all__ = [
    "start_focus",
    "stop_focus",
    "get_focus_status",
    "is_focused",
    "set_ai_advise",
    "is_ai_advise_enabled",
    "verify_trigger",
    "mark_ignored",
    "recompute_price",
    "get_pending_count",
    "HAS_AI_ADVISOR",
]
