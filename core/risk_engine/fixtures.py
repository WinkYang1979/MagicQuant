"""
MagicQuant Risk Engine — 测试 Fixture 库
Dare to dream. Data to win.

28 个典型场景(15 业务 + 13 边界).
"""


FIXTURES = {
    # ══ 业务场景(15 个)══
    
    "normal_entry_ok": {
        "desc": "正常 RKLZ 做 T 入场,RR 2.4 合格",
        "input": {
            "action_type": "new_entry", "ticker": "US.RKLZ",
            "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80,
            "direction": "long",
        },
        "context": {"pdt_used": 0, "cash": 18000, "daily_pnl": 0,
                    "confidence": 0.72, "market_session": "main"},
        "expected": {"allowed": True, "severity": "pass"},
    },
    
    "pdt_last_slot_guard": {
        "desc": "PDT 剩 1 次,其他全合格,只触发 pdt_guard advisory",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 2, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": True, "severity": "advisory",
                     "primary_reason_code": "pdt_guard"},
    },
    
    "pdt_exhausted_block": {
        "desc": "PDT 已用完,入场必须 BLOCK",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 3, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": False, "severity": "block",
                     "primary_reason_code": "pdt_exhausted"},
    },
    
    "tiny_qty_fee_not_worth": {
        "desc": "10 股 RKLB 0.1% 波动,费用吃光",
        "input": {"action_type": "new_entry", "ticker": "US.RKLB",
                  "qty": 10, "entry": 90.0, "stop": 89.90, "target": 90.10},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": True, "severity": "warn",
                     "primary_reason_code": "fee_not_worth"},
    },
    
    "rr_too_low": {
        "desc": "RR 比过低,赚少亏多",
        "input": {"action_type": "new_entry", "ticker": "US.RKLB",
                  "qty": 100, "entry": 90.0, "stop": 89.70, "target": 90.05},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": True, "severity": "warn"},
    },
    
    "low_confidence_warn": {
        "desc": "AI 信心低于 60%,其他全合格",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.45,
                    "market_session": "main"},
        "expected": {"allowed": True, "severity": "warn",
                     "primary_reason_code": "low_confidence"},
    },
    
    "conflicting_signal_warn": {
        "desc": "多 AI 意见分歧,其他合格",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "ai_consensus": "split", "market_session": "main"},
        "expected": {"allowed": True, "severity": "warn",
                     "primary_reason_code": "conflicting_signal"},
    },
    
    "insufficient_cash_block": {
        "desc": "现金不足以买入",
        "input": {"action_type": "new_entry", "ticker": "US.RKLB",
                  "qty": 200, "entry": 100.0, "stop": 99.0, "target": 102.0},
        "context": {"pdt_used": 0, "cash": 5000, "confidence": 0.75,
                    "market_session": "main"},
        "expected": {"allowed": False, "severity": "block",
                     "primary_reason_code": "insufficient_cash"},
    },
    
    "daily_loss_block": {
        "desc": "今日亏损触及 $400 熔断",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 1, "cash": 18000, "daily_pnl": -400,
                    "confidence": 0.72, "market_session": "main"},
        "expected": {"allowed": False, "severity": "block",
                     "primary_reason_code": "daily_loss_limit"},
    },
    
    "drawdown_block": {
        "desc": "从峰值回撤 8.5% 触熔断",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "drawdown_from_peak": -8.5,
                    "confidence": 0.72, "market_session": "main"},
        "expected": {"allowed": False, "severity": "block",
                     "primary_reason_code": "drawdown_limit"},
    },
    
    "full_exit_always_allowed": {
        "desc": "FULL_EXIT 永远放行,哪怕 PDT 用完 + 亏损 + 回撤",
        "input": {"action_type": "full_exit", "ticker": "US.RKLX",
                  "qty": 100, "entry": 48.0, "direction": "long"},
        "context": {"pdt_used": 3, "cash": 18000, "daily_pnl": -500,
                    "drawdown_from_peak": -9.0, "market_session": "main"},
        "expected": {"allowed": True},
    },
    
    "partial_exit_loose": {
        "desc": "PARTIAL_EXIT 跳过质量检查",
        "input": {"action_type": "partial_exit", "ticker": "US.RKLX",
                  "qty": 50, "entry": 48.0, "direction": "long"},
        "context": {"pdt_used": 1, "cash": 18000, "confidence": 0.45,
                    "market_session": "main"},
        "expected": {"allowed": True},
    },
    
    "market_closed_advisory": {
        "desc": "盘后入场,其他合格,advisory",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "market_session": "post"},
        "expected": {"allowed": True, "severity": "advisory",
                     "primary_reason_code": "market_closed"},
    },
    
    "leverage_exceeded": {
        "desc": "已持大量 2x ETF,再买触发杠杆上限(现金充足)",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 250, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 5000, "confidence": 0.75,
                    "market_session": "main",
                    "positions": {"US.RKLX": {"qty": 300, "current_price": 48.0}}},
        "expected": {"allowed": False, "severity": "block",
                     "primary_reason_code": "leverage_limit"},
    },
    
    "reverse_action": {
        "desc": "反手正常场景",
        "input": {"action_type": "reverse", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 1, "cash": 18000, "confidence": 0.72,
                    "market_session": "main",
                    "positions": {"US.RKLX": {"qty": 100, "current_price": 48.0}}},
        "expected": {"allowed": True},
    },
    
    # ══ 边界测试(13 个)══
    
    "boundary_rr_just_below": {
        "desc": "RR 1.36 刚好低于 1.5",
        "input": {"action_type": "new_entry", "ticker": "US.RKLB",
                  "qty": 100, "entry": 90.0, "stop": 89.50, "target": 90.75},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": True, "severity": "warn",
                     "primary_reason_code": "rr_too_low"},
    },
    
    "boundary_rr_just_above": {
        "desc": "RR 1.6+ 通过",
        "input": {"action_type": "new_entry", "ticker": "US.RKLB",
                  "qty": 100, "entry": 90.0, "stop": 89.50, "target": 90.90},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": True, "severity": "pass"},
    },
    
    "boundary_net_profit_below_5": {
        "desc": "净利略低于 $5",
        "input": {"action_type": "new_entry", "ticker": "US.RKLB",
                  "qty": 50, "entry": 90.0, "stop": 89.70, "target": 90.15},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": True, "severity": "warn",
                     "primary_reason_code": "fee_not_worth"},
    },
    
    "boundary_pdt_exact_0": {
        "desc": "PDT 刚好用完",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 3, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": False, "severity": "block",
                     "primary_reason_code": "pdt_exhausted"},
    },
    
    "boundary_pdt_exact_1": {
        "desc": "PDT 剩整 1 次,advisory",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 2, "cash": 18000, "confidence": 0.72,
                    "market_session": "main"},
        "expected": {"allowed": True, "severity": "advisory",
                     "primary_reason_code": "pdt_guard"},
    },
    
    "boundary_daily_loss_90pct": {
        "desc": "今亏 $360 约熔断 90%,advisory",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "daily_pnl": -360,
                    "confidence": 0.72, "market_session": "main"},
        "expected": {"allowed": True, "severity": "advisory",
                     "primary_reason_code": "daily_loss_limit"},
    },
    
    "boundary_daily_loss_exact": {
        "desc": "今亏刚好 $400",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "daily_pnl": -400,
                    "confidence": 0.72, "market_session": "main"},
        "expected": {"allowed": False, "severity": "block"},
    },
    
    "boundary_emergency_stop_loss": {
        "desc": "爆仓日紧急止损: FULL_EXIT 必须放行",
        "input": {"action_type": "full_exit", "ticker": "US.RKLX",
                  "qty": 200, "entry": 48.0, "direction": "long"},
        "context": {"pdt_used": 3, "cash": 5000, "daily_pnl": -420,
                    "drawdown_from_peak": -9.5, "market_session": "main"},
        "expected": {"allowed": True},
    },
    
    "boundary_spread_wide_post_market": {
        "desc": "盘后 + 价差宽",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "spread_pct": 1.2, "market_session": "post"},
        "expected": {"allowed": True, "severity": "warn",
                     "primary_reason_code": "spread_too_wide"},
    },
    
    "boundary_concentration_warn": {
        "desc": "加仓 RKLB 导致单票超 60% 集中度(非 2x 票避免 leverage)",
        "input": {"action_type": "add_position", "ticker": "US.RKLB",
                  "qty": 50, "entry": 90.0, "stop": 89.80, "target": 90.60},
        "context": {
            "pdt_used": 0, "cash": 5500, "confidence": 0.72,
            "market_session": "main",
            "positions": {"US.RKLB": {"qty": 150, "current_price": 90.0}},
        },
        "expected": {"allowed": True, "severity": "warn",
                     "primary_reason_code": "position_concentration"},
    },
    
    "boundary_consec_losses_2": {
        "desc": "连亏 2 次,还未熔断",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "consecutive_losses": 2,
                    "confidence": 0.72, "market_session": "main"},
        "expected": {"allowed": True, "severity": "pass"},
    },
    
    "boundary_pre_earnings_warn": {
        "desc": "距财报 1 天,advisory",
        "input": {"action_type": "new_entry", "ticker": "US.RKLB",
                  "qty": 100, "entry": 90.0, "stop": 89.80, "target": 90.60},
        "context": {"pdt_used": 0, "cash": 18000, "days_to_earnings": 1,
                    "confidence": 0.72, "market_session": "main"},
        "expected": {"allowed": True, "severity": "advisory",
                     "primary_reason_code": "pre_earnings"},
    },
    
    "boundary_cooldown_active": {
        "desc": "同触发器 60 秒冷却内",
        "input": {"action_type": "new_entry", "ticker": "US.RKLZ",
                  "qty": 100, "entry": 15.42, "stop": 15.30, "target": 15.80},
        "context": {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                    "cooldown_remaining_sec": 60, "market_session": "main"},
        "expected": {"allowed": True, "severity": "warn",
                     "primary_reason_code": "cooldown"},
    },
}


def run_fixture(name: str) -> dict:
    from .engine import can_trade
    if name not in FIXTURES:
        return {"fixture": name, "passed": False, "error": "unknown"}
    
    fx = FIXTURES[name]
    try:
        result = can_trade(**fx["input"], context=fx["context"])
    except Exception as e:
        return {"fixture": name, "passed": False, "error": str(e)[:200],
                "desc": fx["desc"]}
    
    rd = result.to_dict() if hasattr(result, "to_dict") else result
    checks = []
    passed = True
    for key, exp in fx["expected"].items():
        actual = rd.get(key)
        if actual != exp:
            passed = False
            checks.append({"field": key, "expected": exp, "actual": actual})
    
    return {
        "fixture":  name,
        "desc":     fx["desc"],
        "passed":   passed,
        "result":   {"allowed": rd.get("allowed"), "severity": rd.get("severity"),
                     "primary_reason_code": rd.get("primary_reason_code")},
        "expected": fx["expected"],
        "mismatches": checks,
    }


def run_all_fixtures() -> dict:
    import time
    t0 = time.time()
    results = [run_fixture(n) for n in FIXTURES]
    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"]]
    return {
        "total": len(results), "passed": len(passed), "failed": failed,
        "duration_ms": int((time.time() - t0) * 1000),
    }


def format_test_result_for_tg(stats: dict) -> str:
    total = stats["total"]
    passed = stats["passed"]
    failed = stats["failed"]
    dur = stats.get("duration_ms", 0)
    status = "✅" if not failed else "⚠️"
    lines = [f"{status} 风控回归测试 · {passed}/{total}",
             "━━━━━━━━━━━━━━━━━━━━"]
    if not failed:
        lines.append("所有场景通过")
    else:
        lines.append(f"❌ 失败 {len(failed)} 项:")
        lines.append("")
        for f in failed[:5]:
            lines.append(f"• {f['fixture']}")
            if f.get("error"):
                lines.append(f"  ❌ 异常: {f['error'][:80]}")
            else:
                for mm in f.get("mismatches", [])[:3]:
                    lines.append(f"  {mm['field']}: 预期 {mm['expected']} ≠ 实际 {mm['actual']}")
            lines.append("")
    lines.append(f"⏱️ 耗时 {dur} ms")
    return "\n".join(lines)
