"""
MagicQuant AI Racing — AI 虚拟操盘大赛
"""

from .race_manager import (
    start_race,
    stop_race,
    is_race_active,
    get_race_summary,
    get_portfolios,
    get_providers,
    reset_all_portfolios,
)

from .portfolio import VirtualPortfolio, INITIAL_CAPITAL
from .providers import build_all_providers

__all__ = [
    "start_race",
    "stop_race",
    "is_race_active",
    "get_race_summary",
    "get_portfolios",
    "get_providers",
    "reset_all_portfolios",
    "VirtualPortfolio",
    "INITIAL_CAPITAL",
    "build_all_providers",
]
