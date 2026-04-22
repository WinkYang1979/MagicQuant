"""
MagicQuant Risk Engine — QUALITY 规则
Dare to dream. Data to win.

5 条质量规则(默认 warn,可覆盖):
  FEE_NOT_WORTH        费用效率不达标
  RR_TOO_LOW           风险收益比过低
  SPREAD_TOO_WIDE      盘口价差过大
  LOW_CONFIDENCE       AI 信心不足
  CONFLICTING_SIGNAL   多 AI 意见冲突
"""

from ..reason_codes import ReasonCode
from ..severity import Severity
from ..helpers import (
    estimate_fees, estimate_expected_net_profit,
    estimate_net_loss, compute_rr_ratio,
)


def check_quality_rules(action_type, ticker, qty, entry, stop, target,
                        direction, context) -> list:
    from ..config_loader import get_risk_config
    cfg = get_risk_config()
    
    return [
        _check_fee_not_worth(qty, entry, target, direction, cfg),
        _check_rr_too_low(qty, entry, stop, target, direction, cfg),
        _check_spread_too_wide(context, cfg),
        _check_low_confidence(context, cfg),
        _check_conflicting_signal(context, cfg),
    ]


def _check_fee_not_worth(qty, entry, target, direction, cfg) -> dict:
    """三维判断: 净利润 + RR + 绝对阈值"""
    if qty <= 0 or entry <= 0 or target <= 0:
        return _pass(ReasonCode.FEE_NOT_WORTH, "参数不足,跳过")
    
    net_profit = estimate_expected_net_profit(entry, target, qty, direction)
    fees = estimate_fees(qty, entry)["roundtrip"]
    
    min_net_profit    = cfg.get("min_net_profit_usd", 5.0)
    min_profit_over_fee = cfg.get("min_profit_over_fee_multiplier", 2.0)
    
    # 维度 1: 绝对净利润
    if net_profit < min_net_profit:
        return {
            "code":     ReasonCode.FEE_NOT_WORTH.value,
            "severity": Severity.WARN.value,
            "passed":   False,
            "message":  f"预期净利 ${net_profit:.2f} < 最低 ${min_net_profit}",
            "metrics":  {"net_profit": net_profit, "fees": fees},
        }
    
    # 维度 2: 净利润 vs 费用倍数
    if net_profit < fees * min_profit_over_fee:
        return {
            "code":     ReasonCode.FEE_NOT_WORTH.value,
            "severity": Severity.WARN.value,
            "passed":   False,
            "message":  f"净利 ${net_profit:.2f} < 费用 ${fees:.2f} × {min_profit_over_fee}",
            "metrics":  {"net_profit": net_profit, "fees": fees},
        }
    
    return _pass(ReasonCode.FEE_NOT_WORTH, 
                 f"净利 ${net_profit:.2f} ≥ 费用 {fees:.2f}×{min_profit_over_fee}")


def _check_rr_too_low(qty, entry, stop, target, direction, cfg) -> dict:
    """风险收益比"""
    if qty <= 0 or entry <= 0 or stop <= 0 or target <= 0:
        return _pass(ReasonCode.RR_TOO_LOW, "参数不足,跳过")
    
    rr = compute_rr_ratio(entry, target, stop, qty, direction)
    min_rr = cfg.get("min_rr_ratio", 1.5)
    
    if rr < min_rr:
        return {
            "code":     ReasonCode.RR_TOO_LOW.value,
            "severity": Severity.WARN.value,
            "passed":   False,
            "message":  f"RR {rr:.2f} < 最低 {min_rr} (建议≥1.5优秀≥2.0)",
            "metrics":  {"rr": rr, "min": min_rr},
        }
    
    return _pass(ReasonCode.RR_TOO_LOW, f"RR {rr:.2f} ≥ {min_rr}")


def _check_spread_too_wide(context, cfg) -> dict:
    """盘口买卖价差"""
    spread_pct = context.get("spread_pct", 0)   # 可选,没有则不查
    if spread_pct is None or spread_pct <= 0:
        return _pass(ReasonCode.SPREAD_TOO_WIDE, "无价差数据,跳过")
    
    max_spread_pct = cfg.get("max_spread_pct", 0.5)   # 默认 0.5%
    
    if spread_pct > max_spread_pct:
        return {
            "code":     ReasonCode.SPREAD_TOO_WIDE.value,
            "severity": Severity.WARN.value,
            "passed":   False,
            "message":  f"盘口价差 {spread_pct:.2f}% > 上限 {max_spread_pct}%",
            "metrics":  {"spread_pct": spread_pct, "max": max_spread_pct},
        }
    
    return _pass(ReasonCode.SPREAD_TOO_WIDE, f"价差 {spread_pct:.2f}%")


def _check_low_confidence(context, cfg) -> dict:
    """AI 信心分数"""
    confidence = context.get("confidence", None)   # 0-1 或 0-100
    if confidence is None:
        return _pass(ReasonCode.LOW_CONFIDENCE, "无信心数据,跳过")
    
    # 标准化: 支持 0-1 和 0-100
    if confidence > 1:
        confidence = confidence / 100.0
    
    min_conf = cfg.get("min_confidence", 0.60)
    
    if confidence < min_conf:
        return {
            "code":     ReasonCode.LOW_CONFIDENCE.value,
            "severity": Severity.WARN.value,
            "passed":   False,
            "message":  f"AI 信心 {confidence:.0%} < 最低 {min_conf:.0%}",
            "metrics":  {"confidence": confidence, "min": min_conf},
        }
    
    return _pass(ReasonCode.LOW_CONFIDENCE, f"信心 {confidence:.0%}")


def _check_conflicting_signal(context, cfg) -> dict:
    """多 AI 意见冲突"""
    consensus = context.get("ai_consensus", None)
    # 值: "consensus"/"majority"/"split"/"none"
    
    if consensus is None:
        return _pass(ReasonCode.CONFLICTING_SIGNAL, "无智囊团数据,跳过")
    
    if consensus == "split":
        return {
            "code":     ReasonCode.CONFLICTING_SIGNAL.value,
            "severity": Severity.WARN.value,
            "passed":   False,
            "message":  "多 AI 意见分歧(split),建议谨慎",
            "metrics":  {"consensus": consensus},
        }
    
    return _pass(ReasonCode.CONFLICTING_SIGNAL, f"共识: {consensus}")


def _pass(code: ReasonCode, msg: str = "") -> dict:
    return {
        "code":     code.value,
        "severity": Severity.PASS.value,
        "passed":   True,
        "message":  msg,
        "metrics":  {},
    }
