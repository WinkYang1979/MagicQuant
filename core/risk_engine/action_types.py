"""
MagicQuant Risk Engine — Action Type 定义
Dare to dream. Data to win.

核心原则(Final Lock):
  Risk Engine > Signal > AI
  BLOCK entry, RARELY block exit
  FULL_EXIT 永远允许
"""

from enum import Enum


class ActionType(str, Enum):
    NEW_ENTRY     = "new_entry"      # 新建仓(空仓 -> 有仓)
    ADD_POSITION  = "add_position"   # 加仓(已有仓继续买入同方向)
    PARTIAL_EXIT  = "partial_exit"   # 部分止盈/止损
    FULL_EXIT     = "full_exit"      # 全部清仓
    REVERSE       = "reverse"        # 反手(多转空 or 空转多)


# 按 action_type 区分默认风控严格度
ACTION_STRICTNESS = {
    ActionType.NEW_ENTRY:    "strict",     # 最严格
    ActionType.ADD_POSITION: "strict",     # 严格(会放大敞口)
    ActionType.REVERSE:      "medium",     # 中等(部分平仓 + 部分新开)
    ActionType.PARTIAL_EXIT: "loose",      # 宽松(减少风险)
    ActionType.FULL_EXIT:    "never",      # 永远放行(止损不能自拦)
}


def is_exit_action(action_type: str) -> bool:
    """是否为出场类动作"""
    return action_type in (
        ActionType.PARTIAL_EXIT.value,
        ActionType.FULL_EXIT.value,
    )


def is_entry_action(action_type: str) -> bool:
    """是否为入场类动作"""
    return action_type in (
        ActionType.NEW_ENTRY.value,
        ActionType.ADD_POSITION.value,
    )


def action_emoji(action_type: str) -> str:
    """给 TG 推送用"""
    return {
        "new_entry":    "🆕",
        "add_position": "➕",
        "partial_exit": "✂️",
        "full_exit":    "🏁",
        "reverse":      "🔄",
    }.get(action_type, "❓")


def action_label(action_type: str) -> str:
    """中文标签"""
    return {
        "new_entry":    "新建仓",
        "add_position": "加仓",
        "partial_exit": "部分出场",
        "full_exit":    "全部出场",
        "reverse":      "反手",
    }.get(action_type, action_type)
