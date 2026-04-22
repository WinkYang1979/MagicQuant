"""
MagicQuant Risk Engine (v0.4)
Dare to dream. Data to win.

核心原则:
  Risk Engine > Signal > AI
  BLOCK entry, RARELY block exit
  FULL_EXIT 永远允许

用法:
    from core.risk_engine import can_trade
    
    result = can_trade(
        action_type="new_entry",  # new_entry/add_position/partial_exit/full_exit/reverse
        ticker="US.RKLZ",
        qty=100,
        entry=15.42, stop=15.20, target=15.80,
        direction="long",
        context={
            "pdt_used": 1,
            "cash": 18000,
            "daily_pnl": -45,
            "confidence": 0.72,
            "positions": {...},
            "market_session": "main",
        },
    )
    
    if not result.allowed:
        # 拦截
        print(result.message)
    elif result.severity == "warn":
        # 警告但放行,TG 推送加覆盖按钮
        pass
"""

from .engine import (
    can_trade,
    RiskCheckResult,
    CheckResult,
    format_result_for_tg,
)
from .severity import (
    Severity,
    severity_emoji,
    is_blocking,
    max_severity,
)
from .reason_codes import (
    ReasonCode,
    ReasonGroup,
    describe,
    default_severity,
)
from .action_types import (
    ActionType,
    is_entry_action,
    is_exit_action,
    action_emoji,
    action_label,
)
from .helpers import (
    estimate_fees,
    estimate_expected_net_profit,
    estimate_net_loss,
    compute_rr_ratio,
    min_profitable_qty,
    compute_effective_leverage,
    compute_position_concentration_pct,
)
from .logger import (
    log_risk_check,
    read_recent_logs,
    compute_stats,
    format_stats_for_tg,
)
from .fixtures import (
    FIXTURES,
    run_fixture,
    run_all_fixtures,
    format_test_result_for_tg,
)
from .config_loader import (
    get_risk_config,
    save_default_config,
)


__version__ = "0.4.0"

__all__ = [
    # 主入口
    "can_trade",
    "RiskCheckResult",
    "CheckResult",
    "format_result_for_tg",
    # 枚举
    "Severity",
    "ReasonCode",
    "ReasonGroup",
    "ActionType",
    # 判定
    "severity_emoji",
    "is_blocking",
    "is_entry_action",
    "is_exit_action",
    "action_emoji",
    "action_label",
    "describe",
    # Helper
    "estimate_fees",
    "estimate_expected_net_profit",
    "estimate_net_loss",
    "compute_rr_ratio",
    "min_profitable_qty",
    "compute_effective_leverage",
    "compute_position_concentration_pct",
    # 日志
    "log_risk_check",
    "read_recent_logs",
    "compute_stats",
    "format_stats_for_tg",
    # 测试
    "FIXTURES",
    "run_fixture",
    "run_all_fixtures",
    "format_test_result_for_tg",
    # 配置
    "get_risk_config",
    "save_default_config",
]
