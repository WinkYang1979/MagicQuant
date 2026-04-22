"""
MagicQuant Risk Engine — CONTEXT 规则
Dare to dream. Data to win.

3 条场景提示规则(默认 advisory,不拦):
  MARKET_CLOSED    非主盘时段
  PRE_EARNINGS     财报前高风险
  PDT_GUARD        PDT 剩最后 1 次
"""

from datetime import datetime
from ..reason_codes import ReasonCode
from ..severity import Severity


def check_context_rules(action_type, ticker, qty, entry, stop, target,
                        direction, context) -> list:
    from ..config_loader import get_risk_config
    cfg = get_risk_config()
    
    return [
        _check_market_closed(context, cfg),
        _check_pre_earnings(context, cfg),
        _check_pdt_guard(context, cfg),
    ]


def _check_market_closed(context, cfg) -> dict:
    """非主盘时段提示"""
    # 优先用 context 提供的 market_session
    session = context.get("market_session")
    
    if session is None:
        # 回退: 根据当前时间(AEST)推断
        h = datetime.now().hour
        if 4 <= h < 10:
            session = "main"
        elif h >= 22 or h < 4:
            session = "post"   # 盘后
        else:
            session = "pre"    # 盘前
    
    if session == "main":
        return _pass(ReasonCode.MARKET_CLOSED, "美股主盘时段")
    
    return {
        "code":     ReasonCode.MARKET_CLOSED.value,
        "severity": Severity.ADVISORY.value,
        "passed":   True,
        "message":  f"当前为 {session} 时段,流动性可能受限",
        "metrics":  {"market_session": session},
    }


def _check_pre_earnings(context, cfg) -> dict:
    """财报前风险提示"""
    days_to_earnings = context.get("days_to_earnings")   # None / int
    if days_to_earnings is None:
        return _pass(ReasonCode.PRE_EARNINGS, "无财报数据,跳过")
    
    warn_days = cfg.get("pre_earnings_warn_days", 2)
    
    if 0 <= days_to_earnings <= warn_days:
        return {
            "code":     ReasonCode.PRE_EARNINGS.value,
            "severity": Severity.ADVISORY.value,
            "passed":   True,
            "message":  f"距财报 {days_to_earnings} 天,波动风险放大",
            "metrics":  {"days_to_earnings": days_to_earnings},
        }
    
    return _pass(ReasonCode.PRE_EARNINGS, f"距财报 {days_to_earnings} 天")


def _check_pdt_guard(context, cfg) -> dict:
    """PDT 剩最后 1 次提醒"""
    pdt_used = context.get("pdt_used", 0)
    pdt_limit = cfg.get("pdt_limit", 3)
    pdt_remaining = pdt_limit - pdt_used
    
    # 剩 0 的由 hard_block 处理
    if pdt_remaining == 1:
        return {
            "code":     ReasonCode.PDT_GUARD.value,
            "severity": Severity.ADVISORY.value,
            "passed":   True,
            "message":  f"PDT 剩最后 1 次,确认非紧急再使用",
            "metrics":  {"pdt_remaining": 1},
        }
    
    return _pass(ReasonCode.PDT_GUARD, f"PDT 剩 {pdt_remaining}")


def _pass(code: ReasonCode, msg: str = "") -> dict:
    return {
        "code":     code.value,
        "severity": Severity.PASS.value,
        "passed":   True,
        "message":  msg,
        "metrics":  {},
    }
