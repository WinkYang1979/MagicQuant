"""
MagicQuant Risk Engine — FLOW 规则
Dare to dream. Data to win.

3 条流程控制规则(默认 warn):
  COOLDOWN                触发器冷却中
  DUPLICATE_SIGNAL        重复信号
  POSITION_CONCENTRATION  单票持仓过集中
"""

from ..reason_codes import ReasonCode
from ..severity import Severity
from ..helpers import compute_position_concentration_pct


def check_flow_rules(action_type, ticker, qty, entry, stop, target,
                     direction, context) -> list:
    from ..config_loader import get_risk_config
    cfg = get_risk_config()
    
    return [
        _check_cooldown(context, cfg),
        _check_duplicate_signal(context, cfg),
        _check_position_concentration(ticker, qty, entry, context, cfg),
    ]


def _check_cooldown(context, cfg) -> dict:
    """同一触发器冷却期内重复命中"""
    cooldown_remain = context.get("cooldown_remaining_sec", 0)
    if cooldown_remain <= 0:
        return _pass(ReasonCode.COOLDOWN, "无冷却")
    
    return {
        "code":     ReasonCode.COOLDOWN.value,
        "severity": Severity.WARN.value,
        "passed":   False,
        "message":  f"触发器冷却中,剩 {cooldown_remain}s",
        "metrics":  {"cooldown_sec": cooldown_remain},
    }


def _check_duplicate_signal(context, cfg) -> dict:
    """和最近的信号重复"""
    dup = context.get("is_duplicate_signal", False)
    if not dup:
        return _pass(ReasonCode.DUPLICATE_SIGNAL, "非重复")
    
    return {
        "code":     ReasonCode.DUPLICATE_SIGNAL.value,
        "severity": Severity.WARN.value,
        "passed":   False,
        "message":  "本次信号与最近一次重复(短时间内同方向)",
        "metrics":  {},
    }


def _check_position_concentration(ticker, qty, entry, context, cfg) -> dict:
    """单票持仓集中度"""
    if qty <= 0 or entry <= 0:
        return _pass(ReasonCode.POSITION_CONCENTRATION, "无新仓位")
    
    positions = context.get("positions", {})
    cash = context.get("cash", 0)
    
    # 模拟加上新单后的集中度
    ticker_key = ticker if "US." in ticker else f"US.{ticker}"
    current_value = 0
    if ticker_key in positions:
        p = positions[ticker_key]
        current_value = (p.get("qty", 0) or p.get("qty_held", 0)) * \
                        (p.get("current_price") or p.get("cost_price", 0))
    
    new_value = current_value + qty * entry
    
    # 计算总资产
    total_assets = cash
    for pos in positions.values():
        q = pos.get("qty", 0) or pos.get("qty_held", 0)
        p = pos.get("current_price") or pos.get("cost_price", 0)
        total_assets += q * p
    
    if total_assets <= 0:
        return _pass(ReasonCode.POSITION_CONCENTRATION, "总资产为 0")
    
    concentration_pct = new_value / total_assets * 100
    max_concentration = cfg.get("max_concentration_pct", 40.0)
    
    if concentration_pct > max_concentration:
        return {
            "code":     ReasonCode.POSITION_CONCENTRATION.value,
            "severity": Severity.WARN.value,
            "passed":   False,
            "message":  f"单票 {concentration_pct:.1f}% > 上限 {max_concentration}%",
            "metrics":  {"concentration_pct": round(concentration_pct, 2),
                         "max": max_concentration},
        }
    
    return _pass(ReasonCode.POSITION_CONCENTRATION, 
                 f"集中度 {concentration_pct:.1f}%")


def _pass(code: ReasonCode, msg: str = "") -> dict:
    return {
        "code":     code.value,
        "severity": Severity.PASS.value,
        "passed":   True,
        "message":  msg,
        "metrics":  {},
    }
