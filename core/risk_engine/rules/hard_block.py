"""
MagicQuant Risk Engine — HARD BLOCK 规则
Dare to dream. Data to win.

5 条硬拦截规则(必然是 block 级别):
  PDT_EXHAUSTED        今日 PDT 次数用完
  INSUFFICIENT_CASH    现金不足
  LEVERAGE_LIMIT       有效杠杆超标
  DAILY_LOSS_LIMIT     单日亏损触及熔断
  DRAWDOWN_LIMIT       最大回撤触及熔断
"""

from ..reason_codes import ReasonCode
from ..severity import Severity
from ..helpers import compute_effective_leverage


def check_hard_block_rules(action_type, ticker, qty, entry, stop, target,
                            direction, context) -> list:
    """跑所有 hard block 规则,返回 list of dict (CheckResult)"""
    from ..config_loader import get_risk_config
    cfg = get_risk_config()
    
    results = []
    
    results.append(_check_pdt_exhausted(context, cfg))
    results.append(_check_insufficient_cash(qty, entry, context, cfg))
    results.append(_check_leverage_limit(ticker, qty, entry, context, cfg))
    results.append(_check_daily_loss_limit(context, cfg))
    results.append(_check_drawdown_limit(context, cfg))
    
    return results


# ══════════════════════════════════════════════════════════════════
#  规则实现
# ══════════════════════════════════════════════════════════════════

def _check_pdt_exhausted(context: dict, cfg: dict) -> dict:
    """PDT 次数已用完"""
    pdt_used = context.get("pdt_used", 0)
    pdt_limit = cfg.get("pdt_limit", 3)
    pdt_remaining = pdt_limit - pdt_used
    
    if pdt_remaining <= 0:
        return {
            "code":     ReasonCode.PDT_EXHAUSTED.value,
            "severity": Severity.BLOCK.value,
            "passed":   False,
            "message":  f"PDT 已用 {pdt_used}/{pdt_limit},今日禁止日内",
            "metrics":  {"pdt_used": pdt_used, "pdt_limit": pdt_limit},
        }
    return {
        "code":     ReasonCode.PDT_EXHAUSTED.value,
        "severity": Severity.PASS.value,
        "passed":   True,
        "message":  f"PDT 剩余 {pdt_remaining}",
        "metrics":  {"pdt_remaining": pdt_remaining},
    }


def _check_insufficient_cash(qty: int, entry: float, context: dict, cfg: dict) -> dict:
    """现金不足"""
    if qty <= 0 or entry <= 0:
        return _pass(ReasonCode.INSUFFICIENT_CASH, "无仓位无需检查")
    
    required = qty * entry + 1.29   # 含买入手续费
    cash = context.get("cash", 0)
    
    # 加一个安全边际(避免 $0.01 擦边)
    safety_margin = cfg.get("cash_safety_margin", 10.0)
    
    if cash < required + safety_margin:
        return {
            "code":     ReasonCode.INSUFFICIENT_CASH.value,
            "severity": Severity.BLOCK.value,
            "passed":   False,
            "message":  f"现金 ${cash:.2f} < 所需 ${required:.2f} + 安全边际 ${safety_margin}",
            "metrics":  {"cash": cash, "required": round(required, 2)},
        }
    return _pass(ReasonCode.INSUFFICIENT_CASH, f"现金 ${cash:.2f} 充足")


def _check_leverage_limit(ticker: str, qty: int, entry: float,
                           context: dict, cfg: dict) -> dict:
    """
    有效杠杆限制.
    
    RKLX/RKLZ 都是 2x ETF.
    单独持一只 2x → 杠杆 2.0(正常)
    同时持正反两只 → 杠杆对冲 or 叠加(要查方向)
    """
    if qty <= 0 or entry <= 0:
        return _pass(ReasonCode.LEVERAGE_LIMIT, "无新仓位")
    
    positions = dict(context.get("positions", {}))
    
    # 模拟加上这笔新单后的总持仓
    ticker_key = ticker if "US." in ticker else f"US.{ticker}"
    sim_positions = dict(positions)
    
    if ticker_key in sim_positions:
        old = sim_positions[ticker_key]
        sim_positions[ticker_key] = {
            "qty":           (old.get("qty", 0) or old.get("qty_held", 0)) + qty,
            "current_price": entry,
        }
    else:
        sim_positions[ticker_key] = {"qty": qty, "current_price": entry}
    
    cash_after = context.get("cash", 0) - (qty * entry + 1.29)
    effective_lev = compute_effective_leverage(sim_positions, cash_after)
    
    max_lev = cfg.get("max_effective_leverage", 1.8)
    
    if effective_lev > max_lev:
        return {
            "code":     ReasonCode.LEVERAGE_LIMIT.value,
            "severity": Severity.BLOCK.value,
            "passed":   False,
            "message":  f"有效杠杆 {effective_lev:.2f} > 上限 {max_lev}",
            "metrics":  {"effective_leverage": effective_lev, "max": max_lev},
        }
    return _pass(ReasonCode.LEVERAGE_LIMIT, 
                 f"有效杠杆 {effective_lev:.2f} ≤ {max_lev}")


def _check_daily_loss_limit(context: dict, cfg: dict) -> dict:
    """单日亏损熔断"""
    daily_pnl = context.get("daily_pnl", 0)
    limit = cfg.get("daily_loss_limit_usd", -400.0)   # 默认 -$400
    
    if daily_pnl <= limit:
        return {
            "code":     ReasonCode.DAILY_LOSS_LIMIT.value,
            "severity": Severity.BLOCK.value,
            "passed":   False,
            "message":  f"今日亏损 ${daily_pnl:.2f} 触及熔断 ${limit}",
            "metrics":  {"daily_pnl": daily_pnl, "limit": limit},
        }
    
    # 接近熔断(90%+)给 advisory
    if daily_pnl <= limit * 0.9:
        return {
            "code":     ReasonCode.DAILY_LOSS_LIMIT.value,
            "severity": Severity.ADVISORY.value,
            "passed":   True,
            "message":  f"今日亏损 ${daily_pnl:.2f} 接近熔断 ${limit}",
            "metrics":  {"daily_pnl": daily_pnl, "limit": limit},
        }
    
    return _pass(ReasonCode.DAILY_LOSS_LIMIT, f"今日盈亏 ${daily_pnl:.2f}")


def _check_drawdown_limit(context: dict, cfg: dict) -> dict:
    """最大回撤熔断"""
    dd = context.get("drawdown_from_peak", 0)   # 负数
    limit = cfg.get("max_drawdown_pct", -8.0)   # 默认 -8%
    
    if dd <= limit:
        return {
            "code":     ReasonCode.DRAWDOWN_LIMIT.value,
            "severity": Severity.BLOCK.value,
            "passed":   False,
            "message":  f"从峰值回撤 {dd:.1f}% 触及熔断 {limit}%",
            "metrics":  {"drawdown": dd, "limit": limit},
        }
    
    if dd <= limit * 0.9:
        return {
            "code":     ReasonCode.DRAWDOWN_LIMIT.value,
            "severity": Severity.ADVISORY.value,
            "passed":   True,
            "message":  f"回撤 {dd:.1f}% 接近熔断 {limit}%",
            "metrics":  {"drawdown": dd, "limit": limit},
        }
    
    return _pass(ReasonCode.DRAWDOWN_LIMIT, f"回撤 {dd:.1f}%")


# ══════════════════════════════════════════════════════════════════
#  辅助
# ══════════════════════════════════════════════════════════════════

def _pass(code: ReasonCode, msg: str = "") -> dict:
    """生成一个通过的 check dict"""
    return {
        "code":     code.value,
        "severity": Severity.PASS.value,
        "passed":   True,
        "message":  msg,
        "metrics":  {},
    }
