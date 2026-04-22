"""
MagicQuant Risk Engine — Reason Code 定义
Dare to dream. Data to win.

15 个 reason_code 分成 4 组:
  HARD BLOCK → block  (法律/物理红线)
  QUALITY    → warn   (质量问题)
  CONTEXT    → advisory (场景提示)
  FLOW       → warn   (流程控制)
"""

from enum import Enum


class ReasonGroup(str, Enum):
    HARD_BLOCK = "hard_block"
    QUALITY    = "quality"
    CONTEXT    = "context"
    FLOW       = "flow"


class ReasonCode(str, Enum):
    # ── 通过 ──
    OK                       = "ok"
    
    # ── HARD BLOCK → block ──
    PDT_EXHAUSTED            = "pdt_exhausted"
    INSUFFICIENT_CASH        = "insufficient_cash"
    LEVERAGE_LIMIT           = "leverage_limit"
    DAILY_LOSS_LIMIT         = "daily_loss_limit"
    DRAWDOWN_LIMIT           = "drawdown_limit"
    
    # ── QUALITY → warn ──
    FEE_NOT_WORTH            = "fee_not_worth"
    RR_TOO_LOW               = "rr_too_low"
    SPREAD_TOO_WIDE          = "spread_too_wide"
    LOW_CONFIDENCE           = "low_confidence"
    CONFLICTING_SIGNAL       = "conflicting_signal"
    
    # ── CONTEXT → advisory ──
    MARKET_CLOSED            = "market_closed"
    PRE_EARNINGS             = "pre_earnings"
    PDT_GUARD                = "pdt_guard"              # 剩 1 次提示
    
    # ── FLOW → warn ──
    COOLDOWN                 = "cooldown"
    DUPLICATE_SIGNAL         = "duplicate_signal"
    POSITION_CONCENTRATION   = "position_concentration"


# 分组映射
REASON_GROUPS = {
    ReasonCode.OK:                        None,
    # HARD BLOCK
    ReasonCode.PDT_EXHAUSTED:             ReasonGroup.HARD_BLOCK,
    ReasonCode.INSUFFICIENT_CASH:         ReasonGroup.HARD_BLOCK,
    ReasonCode.LEVERAGE_LIMIT:            ReasonGroup.HARD_BLOCK,
    ReasonCode.DAILY_LOSS_LIMIT:          ReasonGroup.HARD_BLOCK,
    ReasonCode.DRAWDOWN_LIMIT:            ReasonGroup.HARD_BLOCK,
    # QUALITY
    ReasonCode.FEE_NOT_WORTH:             ReasonGroup.QUALITY,
    ReasonCode.RR_TOO_LOW:                ReasonGroup.QUALITY,
    ReasonCode.SPREAD_TOO_WIDE:           ReasonGroup.QUALITY,
    ReasonCode.LOW_CONFIDENCE:            ReasonGroup.QUALITY,
    ReasonCode.CONFLICTING_SIGNAL:        ReasonGroup.QUALITY,
    # CONTEXT
    ReasonCode.MARKET_CLOSED:             ReasonGroup.CONTEXT,
    ReasonCode.PRE_EARNINGS:              ReasonGroup.CONTEXT,
    ReasonCode.PDT_GUARD:                 ReasonGroup.CONTEXT,
    # FLOW
    ReasonCode.COOLDOWN:                  ReasonGroup.FLOW,
    ReasonCode.DUPLICATE_SIGNAL:          ReasonGroup.FLOW,
    ReasonCode.POSITION_CONCENTRATION:    ReasonGroup.FLOW,
}


# 分组 → 默认 severity
from .severity import Severity

GROUP_DEFAULT_SEVERITY = {
    ReasonGroup.HARD_BLOCK: Severity.BLOCK,
    ReasonGroup.QUALITY:    Severity.WARN,
    ReasonGroup.CONTEXT:    Severity.ADVISORY,
    ReasonGroup.FLOW:       Severity.WARN,
}


def default_severity(reason_code: str) -> str:
    """获取 reason_code 的默认 severity(字符串)"""
    try:
        code_enum = ReasonCode(reason_code)
    except ValueError:
        return Severity.WARN.value
    
    group = REASON_GROUPS.get(code_enum)
    if group is None:
        return Severity.PASS.value
    return GROUP_DEFAULT_SEVERITY[group].value


# 中文描述(TG 推送用)
REASON_DESCRIPTIONS = {
    "ok":                      "通过",
    "pdt_exhausted":           "PDT 今日已用完",
    "insufficient_cash":       "现金不足",
    "leverage_limit":          "有效杠杆超标",
    "daily_loss_limit":        "单日亏损熔断",
    "drawdown_limit":          "最大回撤熔断",
    "fee_not_worth":           "费用效率不达标",
    "rr_too_low":              "风险收益比过低",
    "spread_too_wide":         "盘口价差过大",
    "low_confidence":          "AI 信心不足",
    "conflicting_signal":      "信号冲突",
    "market_closed":           "非主盘时段",
    "pre_earnings":            "财报前高风险",
    "pdt_guard":               "PDT 剩最后 1 次",
    "cooldown":                "触发器冷却中",
    "duplicate_signal":        "重复信号",
    "position_concentration":  "单票持仓过集中",
}


def describe(reason_code: str) -> str:
    return REASON_DESCRIPTIONS.get(reason_code, reason_code)
