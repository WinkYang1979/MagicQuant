"""
MagicQuant Risk Engine — 主引擎
Dare to dream. Data to win.

核心原则 (Final Lock):
  Risk Engine > Signal > AI
  BLOCK entry, RARELY block exit
  FULL_EXIT 永远允许

用法:
    from core.risk_engine import can_trade, RiskCheckResult
    
    result = can_trade(
        action_type="new_entry",
        ticker="US.RKLZ",
        qty=100,
        entry=15.42,
        stop=15.20,
        target=15.80,
        direction="long",
        context={
            "pdt_remaining": 2,
            "daily_pnl": -45.0,
            "cash": 18500,
            "positions": {...},
            "confidence": 0.72,
            ...
        }
    )
    
    if not result.allowed:
        # 拦截, 推送 result.message
        pass
    elif result.severity == "warn":
        # 警告但放行, 带覆盖按钮
        pass
    else:
        # 通过
        pass
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from .severity import Severity, max_severity, SEVERITY_WEIGHT, is_blocking
from .reason_codes import (
    ReasonCode, ReasonGroup, REASON_GROUPS, 
    default_severity, describe,
)
from .action_types import ActionType, is_exit_action, is_entry_action


# ══════════════════════════════════════════════════════════════════
#  单条 Check 结果
# ══════════════════════════════════════════════════════════════════

@dataclass
class CheckResult:
    """单个规则的检查结果"""
    code:       str           # reason_code 值
    severity:   str           # pass/advisory/warn/block
    passed:     bool          # 是否通过这个检查
    message:    str = ""      # 人读说明
    metrics:    dict = field(default_factory=dict)  # 量化指标

    def to_dict(self):
        return asdict(self)


# ══════════════════════════════════════════════════════════════════
#  总体风控结果
# ══════════════════════════════════════════════════════════════════

@dataclass
class RiskCheckResult:
    """
    完整风控检查结果.
    
    字段说明:
      allowed         最终是否放行(bool)
      severity        最终严重度(取所有 check 里最高的)
      primary_reason_code  主要违规原因(最严重的那个)
      all_checks      所有检查明细(含通过的)
      message         给用户看的总结文本
      metrics         关键指标(RR, net_profit, fees 等)
      actions         建议动作(suggested_qty, allow_exit 等)
      
      check_id        本次 check 的 UUID(便于 override log 关联)
      timestamp       时间戳
      action_type     本次动作类型
      ticker          标的
    """
    allowed:             bool
    severity:            str                          # 字符串形式
    primary_reason_code: str
    all_checks:          list                         # List[CheckResult.to_dict()]
    message:             str
    metrics:             dict                         = field(default_factory=dict)
    actions:             dict                         = field(default_factory=dict)
    
    # 追溯性字段
    check_id:            str                          = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:           str                          = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    action_type:         str                          = ""
    ticker:              str                          = ""
    
    def to_dict(self):
        return asdict(self)
    
    def is_hard_block(self):
        return is_blocking(self.severity)
    
    def emoji(self):
        from .severity import severity_emoji
        return severity_emoji(self.severity)


# ══════════════════════════════════════════════════════════════════
#  主检查函数
# ══════════════════════════════════════════════════════════════════

def can_trade(action_type: str,
              ticker: str,
              qty: int = 0,
              entry: float = 0.0,
              stop: float = 0.0,
              target: float = 0.0,
              direction: str = "long",
              context: dict = None) -> RiskCheckResult:
    """
    统一风控闸门.
    
    返回 RiskCheckResult,调用方根据 result.allowed 和 result.severity 决定.
    """
    context = context or {}
    
    # 规范化 action_type
    try:
        action_enum = ActionType(action_type)
    except ValueError:
        action_enum = ActionType.NEW_ENTRY
    
    # 跑所有规则
    from .rules.hard_block import check_hard_block_rules
    from .rules.quality   import check_quality_rules
    from .rules.context   import check_context_rules
    from .rules.flow      import check_flow_rules
    
    all_checks: list = []
    metrics: dict = {}
    
    # ── 顺序跑 4 组规则 ──
    # 关键原则: FULL_EXIT 跳过所有非安全类检查
    is_full_exit = (action_enum == ActionType.FULL_EXIT)
    
    # HARD BLOCK: 哪怕 FULL_EXIT 也要查,但特别对待
    hard_results = check_hard_block_rules(
        action_type, ticker, qty, entry, stop, target, direction, context
    )
    all_checks.extend(hard_results)
    
    # 如果是 FULL_EXIT,除了 INSUFFICIENT_CASH 外,把 hard_block 的 severity 降级
    if is_full_exit:
        for chk in all_checks:
            if chk.get("code") != ReasonCode.INSUFFICIENT_CASH.value:
                if chk.get("severity") == Severity.BLOCK.value:
                    chk["severity"] = Severity.ADVISORY.value
                    chk["passed"]   = True  # FULL_EXIT 永远放行
                    chk["message"]  = "⚠️ " + chk.get("message", "") + " [FULL_EXIT 豁免]"
    
    # QUALITY: 入场类才跑(出场不查质量)
    if is_entry_action(action_type) or action_enum == ActionType.REVERSE:
        quality_results = check_quality_rules(
            action_type, ticker, qty, entry, stop, target, direction, context
        )
        all_checks.extend(quality_results)
    
    # CONTEXT: 始终跑(advisory 级别,不拦)
    context_results = check_context_rules(
        action_type, ticker, qty, entry, stop, target, direction, context
    )
    all_checks.extend(context_results)
    
    # FLOW: 入场和反手跑
    if is_entry_action(action_type) or action_enum == ActionType.REVERSE:
        flow_results = check_flow_rules(
            action_type, ticker, qty, entry, stop, target, direction, context
        )
        all_checks.extend(flow_results)
    
    # ── 汇总计算 ──
    # metrics 合并
    from .helpers import (
        estimate_fees, estimate_expected_net_profit,
        estimate_net_loss, compute_rr_ratio,
    )
    
    if qty > 0 and entry > 0:
        fees = estimate_fees(qty, entry)
        metrics["fees_roundtrip"] = fees["roundtrip"]
        if target > 0:
            metrics["expected_net_profit"] = estimate_expected_net_profit(
                entry, target, qty, direction
            )
        if stop > 0:
            metrics["net_loss_if_stop"] = estimate_net_loss(
                entry, stop, qty, direction
            )
        if target > 0 and stop > 0:
            metrics["rr_ratio"] = compute_rr_ratio(
                entry, target, stop, qty, direction
            )
    
    # 账户状态 metrics
    metrics["pdt_remaining"]       = context.get("pdt_remaining", 3)
    metrics["daily_pnl"]           = context.get("daily_pnl", 0)
    metrics["drawdown_from_peak"]  = context.get("drawdown_from_peak", 0)
    metrics["consecutive_losses"]  = context.get("consecutive_losses", 0)
    
    # ── 最终 severity 和 primary_reason_code ──
    # 规则:
    #   1. 所有 severity != PASS 的 check 都参与汇总(包括 passed=True 但 severity=advisory 的)
    #   2. 按严重度排序: block > warn > advisory
    #   3. primary 是最严重的那个
    non_pass_checks = [
        c for c in all_checks 
        if c["severity"] != Severity.PASS.value
    ]
    
    if not non_pass_checks:
        final_severity  = Severity.PASS.value
        primary_reason  = ReasonCode.OK.value
        message         = "✅ 通过所有风控检查"
    else:
        # 按严重度降序排序
        non_pass_checks.sort(
            key=lambda c: SEVERITY_WEIGHT.get(Severity(c["severity"]), 0),
            reverse=True
        )
        primary        = non_pass_checks[0]
        final_severity = primary["severity"]
        primary_reason = primary["code"]
        message        = f"{primary['severity'].upper()}: {primary['message']}"
    
    # ── 最终 allowed 判定 ──
    # 核心规则:
    #   1. FULL_EXIT 永远 allowed = True
    #   2. severity == block 且不是 FULL_EXIT -> allowed = False
    #   3. 其他情况 allowed = True
    if is_full_exit:
        allowed = True
    else:
        allowed = not is_blocking(final_severity)
    
    # ── actions ──
    actions = {}
    if not allowed:
        actions["allow_exit"] = True   # block 时仍允许出场
    
    # 如果是 FEE_NOT_WORTH,给出 min_profitable_qty
    for chk in non_pass_checks:
        if chk["code"] == ReasonCode.FEE_NOT_WORTH.value and chk["severity"] != Severity.PASS.value:
            if entry > 0 and target > 0:
                from .helpers import min_profitable_qty
                actions["suggested_min_qty"] = min_profitable_qty(entry, target, 5.0)
    
    return RiskCheckResult(
        allowed             = allowed,
        severity            = final_severity,
        primary_reason_code = primary_reason,
        all_checks          = all_checks,
        message             = message,
        metrics             = metrics,
        actions             = actions,
        action_type         = action_type,
        ticker              = ticker,
    )


# ══════════════════════════════════════════════════════════════════
#  TG 格式化
# ══════════════════════════════════════════════════════════════════

def format_result_for_tg(result: RiskCheckResult, verbose: bool = False) -> str:
    """格式化 RiskCheckResult 为 TG 推送文本"""
    from .severity import severity_emoji
    from .action_types import action_label
    
    ticker_short = result.ticker.replace("US.", "") if result.ticker else "?"
    
    lines = [
        f"{result.emoji()} 风控 · {action_label(result.action_type)} {ticker_short}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    
    # 主要原因
    primary = describe(result.primary_reason_code)
    if result.severity == "pass":
        lines.append("✅ 全部检查通过")
    else:
        lines.append(f"主因: {primary}")
        lines.append(f"说明: {result.message[:200]}")
    
    # 关键 metrics
    m = result.metrics
    lines.append("")
    lines.append("📊 关键指标:")
    if "rr_ratio" in m:
        rr = m["rr_ratio"]
        lines.append(f"  RR 比: {rr}  {'✅' if rr >= 1.5 else '⚠️'}")
    if "expected_net_profit" in m:
        lines.append(f"  预期净利: ${m['expected_net_profit']:.2f}")
    if "fees_roundtrip" in m:
        lines.append(f"  往返费用: ${m['fees_roundtrip']:.2f}")
    if m.get("pdt_remaining", 3) < 3:
        lines.append(f"  PDT 剩余: {m['pdt_remaining']}/3")
    if m.get("daily_pnl", 0) != 0:
        pnl = m["daily_pnl"]
        lines.append(f"  今日盈亏: ${pnl:+.2f}")
    
    # 其他提醒(non-primary)
    others = [c for c in result.all_checks 
              if not c["passed"] and c["code"] != result.primary_reason_code]
    if others:
        lines.append("")
        lines.append(f"📋 其他提醒 ({len(others)}):")
        for c in others[:3]:
            emoji = severity_emoji(c["severity"])
            lines.append(f"  {emoji} {describe(c['code'])}: {c['message'][:60]}")
    
    # 建议动作
    if result.actions:
        lines.append("")
        if "suggested_min_qty" in result.actions:
            lines.append(f"💡 建议: 最少 {result.actions['suggested_min_qty']} 股才够费用")
        if result.actions.get("allow_exit"):
            lines.append(f"💡 入场被拦,但出场指令仍会放行")
    
    lines.append("")
    lines.append(f"🔖 check_id: {result.check_id}")
    
    return "\n".join(lines)
