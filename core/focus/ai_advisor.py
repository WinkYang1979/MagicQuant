"""
MagicQuant — AI 顾问团 (Focus 触发时召集)

流程:
  1. Focus 触发 → trigger_advisors(trigger, market_ctx, portfolio_ctx)
  2. 并行调用 3 个顾问 (Haiku / DeepSeek / GPT-5)
  3. Opus Leader 汇总 + 最终决策
  4. 返回结构化建议给 focus_manager 推送

成本约 $0.04-$0.05/次,一晚 20 次触发 ≈ $0.80-$1.00
"""

import os
import json
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from core.agents.providers import (
    build_all_providers,
    ClaudeOpusProvider, ClaudeHaikuProvider,
    OpenAIProvider, DeepSeekProvider,
)


# ══════════════════════════════════════════════════════════════════
#  顾问 Prompt
# ══════════════════════════════════════════════════════════════════

ADVISOR_SYSTEM = """你是一名资深美股日内交易顾问,协助老杨做 RKLB 系列波段做 T 决策.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 核心规则(最重要,必读):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RKLB 只是信号源,不直接交易!
  
  老杨只在 RKLX 和 RKLZ 上做交易:
  - RKLB 涨的时候    → 买 RKLX(2x 做多 ETF 加速涨)
                     或平 RKLZ 空头止损
  - RKLB 跌的时候    → 买 RKLZ(2x 做空 ETF 加速涨)
                     或平 RKLX 多头止盈/止损
  
  ⛔ 禁止建议 "BUY RKLB" 或 "SELL RKLB",除非老杨已持有 RKLB 仓位需要清掉
  ⛔ ticker 字段只能填 "RKLX" 或 "RKLZ"(或 HOLD 时 null)
  
  🔒 TSLL 处理原则:
  - TSLL 是老杨的长期套牢仓 (成本 $22.5, 现价 ~$13, 浮亏 -41%),属于已冻结资金
  - 不在做 T 考虑范围,绝不建议任何 TSLL 相关操作
  - 分析时可以在风险提示里简短提一句,但不要让它影响 RKLX/RKLZ 主决策
  - 不要建议 "用做 T 收益来填补 TSLL 亏损",这是赌徒心态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

可交易标的:
  - RKLB  : Rocket Lab 正股(📊 信号源,不直接交易)
  - RKLX  : 2x 做多 RKLB ETF (RKLB 涨,RKLX 加速涨) ⭐ 交易目标
  - RKLZ  : 2x 做空 RKLB ETF (RKLB 跌,RKLZ 加速涨) ⭐ 交易目标

策略决策模型:
  信号(看 RKLB)      →    动作(操作 RKLX/RKLZ)
  ─────────────────────────────────────────────
  波段顶/RKLB 看跌   →    买 RKLZ(开空) 或 卖 RKLX(平多)
  波段底/RKLB 看涨   →    买 RKLX(开多) 或 卖 RKLZ(平空)
  持仓浮盈达标       →    卖已持有的 RKLX/RKLZ 止盈
  持仓回撤触发       →    卖已持有的 RKLX/RKLZ 止损

交易费率 (Moomoo AU):
  - 买入固定 $1.29
  - 卖出 $1.31-$1.60 (含 SEC + TAF)
  - 100 股往返成本约 $2.60-$3.00

策略风格:日内波段做 T,5-30 分钟级别,不过夜.

⚠️ 重要原则:
  - **HOLD 是最常见的正确答案**,不要为了操作而操作
  - 费用吃利润,没明显信号就观望
  - 如果信号不够清晰/矛盾/数据不足 → 必须 HOLD
  - 强行交易比错过机会更糟糕
  - **ticker 如果不是 RKLX 或 RKLZ,立即改为 HOLD**

输出严格 JSON(不要任何其他文字):
{
  "action":     "BUY" | "SELL" | "HOLD",
  "ticker":     "RKLX" | "RKLZ" | null,     (HOLD 时 null,绝不填 RKLB)
  "qty":        整数股数(HOLD 时为 0),
  "price":      建议 RKLX 或 RKLZ 的成交价,不是 RKLB 的价 (HOLD 时 null),
  "reason":     "一句话中文理由,说明为什么看多/看空 RKLB,对应操作 RKLX/RKLZ,不超过 50 字",
  "confidence": 0-100 整数,
  "risk":       "一句话风险提示,最多 30 字"
}

注意:
  - ticker 必须是 RKLX 或 RKLZ,不能是 RKLB
  - price 字段是 RKLX/RKLZ 的价格(不是 RKLB!2x ETF 价格不同)
  - 股数要合理,考虑老杨的现金和持仓
  - 2x 杠杆 ETF 波动大,控制股数
  - 没把握就 HOLD
"""


LEADER_SYSTEM = """你是 Claude Opus 4.7,作为 AI 顾问团 Leader,需要综合所有顾问的意见,给老杨最终建议.

老杨用 Moomoo AU 做 RKLB 系列波段做 T.你看到:
  1. Focus 盯盘系统刚触发的信号
  2. 当前市场数据
  3. 老杨的持仓
  4. 3-4 位 AI 顾问(Haiku / DeepSeek / GPT-5.4 / Kimi)的独立建议

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 核心规则(不可违背):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RKLB 只是信号源,实际交易只在 RKLX / RKLZ 执行:
  - 看多 RKLB → 买 RKLX(2x多)或平 RKLZ(空头)
  - 看空 RKLB → 买 RKLZ(2x空)或平 RKLX(多头)
  
  ⛔ 绝不建议交易 RKLB 本身
  ⛔ 如果下层顾问建议了 RKLB 操作,请校正为对应的 RKLX 或 RKLZ 操作
  ⛔ final_ticker 只能是 "RKLX" 或 "RKLZ"(或 HOLD 时 null)
  
  🔒 TSLL 是老杨的长期套牢仓(成本 $22.5 现 $13,浮亏 -41%):
  - 属于已冻结资金,不在做 T 范围
  - 任何下层顾问建议 TSLL 操作,你必须忽略/校正
  - risk_warning 里可简短提示"TSLL 套牢占 41%,做 T 资金已收缩"
  - 但 final_action 只围绕 RKLX/RKLZ 或 HOLD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

你的任务:
  1. 对比顾问们的意见,识别共识与分歧
  2. 结合原始数据做独立判断
  3. **校正任何误把 RKLB 当交易标的的建议**
  4. 给出最终建议,可以 BUY/SELL/HOLD
  5. 同意跟随多数顾问意见,但若你有更强的判断依据,应独立决策
  6. **如果顾问分歧大或信号弱,建议 HOLD 更安全**

输出严格 JSON(不要任何其他文字):
{
  "final_action":   "BUY" | "SELL" | "HOLD",
  "final_ticker":   "RKLX" | "RKLZ" | null,     (绝不填 RKLB)
  "final_qty":      整数股数,
  "final_price":    建议 RKLX/RKLZ 成交价 (HOLD 时 null),
  "final_reason":   "2-3 句话中文,说明 RKLB 信号解读 + 为什么选 RKLX/RKLZ,最多 120 字",
  "agreement":      "共识" | "多数同意" | "分歧较大" | "观望",
  "risk_warning":   "一句话风险提示,最多 50 字",
  "differs_from_advisors": true | false,
  "confidence":     0-100 整数
}
"""


# ══════════════════════════════════════════════════════════════════
#  Prompt 构造
# ══════════════════════════════════════════════════════════════════

def _format_trigger(trigger: dict) -> str:
    """把 Focus 触发信号格式化"""
    lines = [f"Focus 触发类型: {trigger.get('type', '?')}"]
    if trigger.get("reason"):
        lines.append(f"触发原因: {trigger['reason']}")
    if trigger.get("severity"):
        lines.append(f"严重度: {trigger['severity']}")
    return "\n".join(lines)


def _format_market(market_ctx: dict) -> str:
    """市场数据"""
    lines = ["【当前市场】"]
    prices = market_ctx.get("prices", {})
    for tk in ["RKLB", "RKLX", "RKLZ"]:
        info = prices.get(tk) or prices.get(f"US.{tk}")
        if info and isinstance(info, dict):
            p = info.get("price", 0)
            lo = info.get("low", p)
            hi = info.get("high", p)
            lines.append(f"  {tk}: ${p:.2f}  今低 ${lo:.2f}  今高 ${hi:.2f}")
    
    ind = market_ctx.get("indicators", {})
    if ind:
        lines.append("")
        lines.append("【RKLB 5M 技术指标】")
        if ind.get("rsi_5m"):
            lines.append(f"  RSI(5M): {ind['rsi_5m']}")
        if ind.get("vwap"):
            lines.append(f"  VWAP: ${ind['vwap']:.2f}")
        if ind.get("vol_ratio"):
            lines.append(f"  量比: {ind['vol_ratio']:.2f}x")
        candle = ind.get("candle", {})
        if candle.get("name"):
            lines.append(f"  K线形态: {candle['name']}")
    
    return "\n".join(lines)


def _format_portfolio(portfolio_ctx: dict) -> str:
    """账户持仓"""
    lines = ["【老杨账户】"]
    cash = portfolio_ctx.get("cash", 0)
    lines.append(f"  现金: ${cash:.2f}")
    
    positions = portfolio_ctx.get("positions", {})
    if positions:
        lines.append("  持仓:")
        for tk, pos in positions.items():
            qty = pos.get("qty", 0)
            cost = pos.get("cost_basis", 0)
            cur = pos.get("current_price", cost)
            pl = (cur - cost) * qty
            pl_pct = (cur - cost) / cost * 100 if cost else 0
            lines.append(
                f"    {tk}: {qty} 股 @${cost:.2f}, "
                f"现价 ${cur:.2f}, 浮盈 ${pl:+.2f} ({pl_pct:+.2f}%)"
            )
    else:
        lines.append("  持仓: 空仓")
    
    return "\n".join(lines)


def _build_advisor_prompt(trigger: dict, market_ctx: dict, portfolio_ctx: dict) -> str:
    """给顾问的 prompt"""
    return f"""⚠️ Focus 刚刚触发一个信号,需要你给老杨建议!

{_format_trigger(trigger)}

{_format_market(market_ctx)}

{_format_portfolio(portfolio_ctx)}

请基于以上信息,给出你的独立交易建议(JSON).
"""


def _build_leader_prompt(
    trigger: dict, market_ctx: dict, portfolio_ctx: dict,
    advisor_results: dict
) -> str:
    """给 Leader Opus 的 prompt"""
    lines = [
        f"⚠️ Focus 刚刚触发一个信号,需要你综合判断!",
        "",
        _format_trigger(trigger),
        "",
        _format_market(market_ctx),
        "",
        _format_portfolio(portfolio_ctx),
        "",
        "【顾问独立建议】",
    ]
    
    for name, result in advisor_results.items():
        display = {
            "claude_haiku": "Claude Haiku 4.5",
            "deepseek":     "DeepSeek V3",
            "gpt_5":        "GPT-5.4 mini",
            "kimi":         "Kimi K2.5",
        }.get(name, name)
        
        if result.get("parse_ok"):
            lines.append(
                f"\n顾问 {display}:"
                f"\n  动作: {result['action']}"
                f"\n  标的: {result.get('ticker', '-')}"
                f"\n  数量: {result.get('qty', 0)}"
                f"\n  理由: {result.get('reason', '')}"
                f"\n  信心: {result.get('confidence', 0)}%"
            )
        else:
            lines.append(f"\n顾问 {display}: 响应失败 ({result.get('raw', 'error')[:50]})")
    
    lines += [
        "",
        "请综合以上所有顾问的意见和原始数据,给出最终建议 (JSON).",
        "如果顾问之间有分歧,请用你的判断打破平局.",
        "如果顾问都同意但你有更强的依据,可以独立决策.",
    ]
    
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  JSON 解析
# ══════════════════════════════════════════════════════════════════

def _parse_advisor_json(raw: str) -> dict:
    """解析顾问的 JSON"""
    import re
    result = {
        "action": "HOLD", "ticker": None, "qty": 0,
        "price": None, "reason": "", "confidence": 50, "risk": "",
        "parse_ok": False, "raw": raw[:300],
    }
    if not raw:
        return result
    
    # 找 JSON
    m = re.search(r'\{[^{}]*"action"[^{}]*\}', raw, re.DOTALL)
    if not m:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        json_text = m.group(1) if m else None
    else:
        json_text = m.group(0)
    
    if not json_text:
        # 再尝试更宽松的括号匹配
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            json_text = raw[start:end+1]
    
    if not json_text:
        return result
    
    try:
        p = json.loads(json_text)
        action = str(p.get("action", "HOLD")).upper()
        if action not in ("BUY", "SELL", "HOLD"):
            action = "HOLD"
        ticker = p.get("ticker")
        if ticker:
            ticker = str(ticker).upper().replace("US.", "")
            # 🚨 关键: RKLB 不是交易标的,只是信号源
            # 如果 AI 返回 BUY/SELL RKLB,自动校正为 HOLD,reason 加注解
            if ticker == "RKLB" and action != "HOLD":
                action = "HOLD"
                ticker = None
                p["reason"] = "⚠️ 自动校正: RKLB 仅作信号源,不直接交易 | 原建议: " + str(p.get("reason", ""))[:100]
            elif ticker not in ("RKLX", "RKLZ"):
                ticker = None
        
        # price 可以是 null 或数字
        price = p.get("price")
        if price is not None:
            try:
                price = float(price)
                if price <= 0:
                    price = None
            except:
                price = None
        
        result.update({
            "action":     action,
            "ticker":     ticker if action != "HOLD" else None,
            "qty":        max(0, min(int(p.get("qty", 0) or 0), 10000)),
            "price":      price if action != "HOLD" else None,
            "reason":     str(p.get("reason", ""))[:200],
            "confidence": max(0, min(int(p.get("confidence", 50) or 50), 100)),
            "risk":       str(p.get("risk", ""))[:100],
            "parse_ok":   True,
        })
    except Exception as e:
        result["raw"] = f"[parse err] {str(e)[:80]} | {raw[:200]}"
    
    return result


def _parse_leader_json(raw: str) -> dict:
    """解析 Leader 的 JSON"""
    import re
    result = {
        "final_action": "HOLD", "final_ticker": None, "final_qty": 0,
        "final_price": None, "final_reason": "", "agreement": "观望",
        "risk_warning": "", "differs_from_advisors": False,
        "confidence": 50, "parse_ok": False, "raw": raw[:500],
    }
    if not raw:
        return result
    
    m = re.search(r'\{[^{}]*"final_action"[^{}]*\}', raw, re.DOTALL)
    if not m:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        json_text = m.group(1) if m else None
    else:
        json_text = m.group(0)
    
    if not json_text:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            json_text = raw[start:end+1]
    
    if not json_text:
        return result
    
    try:
        p = json.loads(json_text)
        action = str(p.get("final_action", "HOLD")).upper()
        if action not in ("BUY", "SELL", "HOLD"):
            action = "HOLD"
        ticker = p.get("final_ticker")
        if ticker:
            ticker = str(ticker).upper().replace("US.", "")
            # 🚨 RKLB 不是交易标的,只是信号源
            if ticker == "RKLB" and action != "HOLD":
                action = "HOLD"
                ticker = None
                p["final_reason"] = "⚠️ 自动校正: RKLB 仅作信号源,不直接交易 | 原建议: " + str(p.get("final_reason", ""))[:150]
            elif ticker not in ("RKLX", "RKLZ"):
                ticker = None
        
        price = p.get("final_price")
        if price is not None:
            try:
                price = float(price)
                if price <= 0:
                    price = None
            except:
                price = None
        
        result.update({
            "final_action": action,
            "final_ticker": ticker if action != "HOLD" else None,
            "final_qty":    max(0, min(int(p.get("final_qty", 0) or 0), 10000)),
            "final_price":  price if action != "HOLD" else None,
            "final_reason": str(p.get("final_reason", ""))[:400],
            "agreement":    str(p.get("agreement", "观望"))[:20],
            "risk_warning": str(p.get("risk_warning", ""))[:200],
            "differs_from_advisors": bool(p.get("differs_from_advisors", False)),
            "confidence":   max(0, min(int(p.get("confidence", 50) or 50), 100)),
            "parse_ok":     True,
        })
    except Exception as e:
        result["raw"] = f"[parse err] {str(e)[:80]} | {raw[:300]}"
    
    return result


# ══════════════════════════════════════════════════════════════════
#  智囊团主函数
# ══════════════════════════════════════════════════════════════════

def consult_advisors(
    trigger: dict,
    market_ctx: dict,
    portfolio_ctx: dict,
) -> dict:
    """
    召集 AI 智囊团,返回完整结果:
    {
      "advisors": {name: parsed_result, ...},
      "leader":   parsed_leader_result,
      "total_cost_usd": float,
      "total_tokens":   int,
      "total_duration_ms": int,
      "summary_text":   str,    # 已格式化的 TG 推送文本
    }
    """
    t_start = datetime.now()
    
    # 构建所有 providers
    try:
        all_providers = build_all_providers()
    except Exception as e:
        return _error_result(f"Provider 初始化失败: {e}")
    
    if "claude_opus" not in all_providers:
        return _error_result("❌ Claude Opus 不可用,无 Leader,跳过 AI 咨询")
    
    # 4 个顾问(按优先级,没有的跳过) - v0.4.1 加入 Kimi K2.5
    advisor_names = []
    for n in ["claude_haiku", "deepseek", "gpt_5", "kimi"]:
        if n in all_providers:
            advisor_names.append(n)
    
    if not advisor_names:
        return _error_result("❌ 没有可用的顾问 AI,只剩 Opus 一家")
    
    # ── Step 1: 并行调用顾问 ──
    advisor_prompt = _build_advisor_prompt(trigger, market_ctx, portfolio_ctx)
    advisor_results = {}
    total_cost = 0.0
    total_tokens = 0
    
    with ThreadPoolExecutor(max_workers=len(advisor_names)) as pool:
        tasks = {}
        for name in advisor_names:
            provider = all_providers[name]
            tasks[pool.submit(
                provider.call, ADVISOR_SYSTEM, advisor_prompt, 400, 20
            )] = name
        
        for future in as_completed(tasks):
            name = tasks[future]
            try:
                raw_result = future.result()
            except Exception as e:
                raw_result = {"text": "", "error": str(e)[:100],
                             "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
            
            if raw_result.get("error"):
                advisor_results[name] = {
                    "parse_ok": False,
                    "raw": f"API 错误: {raw_result['error'][:100]}",
                    "action": "HOLD", "ticker": None, "qty": 0,
                    "reason": "调用失败", "confidence": 0,
                }
            else:
                parsed = _parse_advisor_json(raw_result["text"])
                parsed["cost_usd"] = raw_result.get("cost_usd", 0)
                parsed["tokens"] = raw_result.get("input_tokens", 0) + raw_result.get("output_tokens", 0)
                advisor_results[name] = parsed
                total_cost += raw_result.get("cost_usd", 0)
                total_tokens += parsed["tokens"]
    
    # ── Step 2: Opus Leader 汇总 ──
    leader_prompt = _build_leader_prompt(trigger, market_ctx, portfolio_ctx, advisor_results)
    opus = all_providers["claude_opus"]
    
    try:
        leader_raw = opus.call(LEADER_SYSTEM, leader_prompt, max_tokens=600, timeout=30)
    except Exception as e:
        leader_raw = {"text": "", "error": str(e)[:100],
                     "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
    
    if leader_raw.get("error"):
        leader_parsed = {
            "parse_ok": False,
            "final_action": "HOLD",
            "final_reason": f"Leader 调用失败: {leader_raw['error'][:80]}",
            "raw": leader_raw.get("error", "")[:300],
            "final_ticker": None, "final_qty": 0,
            "agreement": "错误", "risk_warning": "Opus 不可用",
            "confidence": 0,
        }
    else:
        leader_parsed = _parse_leader_json(leader_raw["text"])
        total_cost += leader_raw.get("cost_usd", 0)
        total_tokens += leader_raw.get("input_tokens", 0) + leader_raw.get("output_tokens", 0)
    
    leader_parsed["cost_usd"] = leader_raw.get("cost_usd", 0)
    leader_parsed["tokens"] = (
        leader_raw.get("input_tokens", 0) + leader_raw.get("output_tokens", 0)
    )
    
    # ── Step 3: 组装 TG 推送文本 ──
    summary_text = _format_summary(
        trigger, advisor_results, leader_parsed,
        total_cost, total_tokens,
        market_ctx,
    )
    
    duration_ms = int((datetime.now() - t_start).total_seconds() * 1000)
    
    # ── Step 4: 保存历史 + 累计成本 ──
    try:
        _save_cumulative_cost(total_cost, total_tokens)
        _save_history({
            "timestamp":        t_start.isoformat(timespec="seconds"),
            "trigger":          trigger,
            "market":           {
                "prices":     market_ctx.get("prices", {}),
                "indicators": market_ctx.get("indicators", {}),
            },
            "portfolio":        portfolio_ctx,
            "advisors":         advisor_results,
            "leader":           leader_parsed,
            "total_cost_usd":   round(total_cost, 5),
            "total_tokens":     total_tokens,
            "duration_ms":      duration_ms,
        })
    except Exception as e:
        print(f"  [ai_advisor] save history failed: {e}")
    
    return {
        "advisors":          advisor_results,
        "leader":            leader_parsed,
        "total_cost_usd":    round(total_cost, 5),
        "total_tokens":      total_tokens,
        "total_duration_ms": duration_ms,
        "summary_text":      summary_text,
        "trigger":           trigger,
        "market_ctx":        market_ctx,
        "timestamp":         t_start.isoformat(timespec="seconds"),
    }


def _error_result(msg: str) -> dict:
    return {
        "advisors": {}, "leader": None,
        "total_cost_usd": 0, "total_tokens": 0,
        "total_duration_ms": 0, "summary_text": msg,
        "error": msg,
    }


# ══════════════════════════════════════════════════════════════════
#  TG 推送格式化
# ══════════════════════════════════════════════════════════════════

def _emoji(action: str) -> str:
    return {"BUY": "🛒", "SELL": "💰", "HOLD": "⏸️"}.get(action, "❓")


def _format_action_detail(action: str, ticker: Optional[str], qty: int,
                          price: Optional[float]) -> str:
    """格式化动作详情: BUY 100 RKLX @ $47.98"""
    if action == "HOLD":
        return "观望 (HOLD)"
    parts = [action]
    if qty > 0:
        parts.append(str(qty))
    if ticker:
        parts.append(ticker)
    if price is not None:
        parts.append(f"@ ${price:.2f}")
    return " ".join(parts)


def _format_summary(
    trigger: dict, advisors: dict, leader: dict,
    total_cost: float, total_tokens: int,
    market_ctx: dict,
) -> str:
    """组装 TG 推送文本 - 信息丰富版"""
    trigger_name = trigger.get("type", "未知触发")
    
    lines = [
        f"🤖 AI 智囊团建议 · {trigger_name}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    
    # 当前价格
    prices = market_ctx.get("prices", {})
    price_line_parts = []
    for tk in ["RKLB", "RKLX", "RKLZ"]:
        info = prices.get(tk) or prices.get(f"US.{tk}")
        if info:
            p = info.get("price", 0) if isinstance(info, dict) else info
            price_line_parts.append(f"{tk} ${p:.2f}")
    if price_line_parts:
        lines.append("📊 现价: " + " · ".join(price_line_parts))
    lines.append("")
    
    # 4 位顾问独立建议 (v0.4.1 加入 Kimi)
    advisor_display = {
        "claude_haiku": ("Haiku 4.5", "🟢"),
        "deepseek":     ("DeepSeek V3", "🟡"),
        "gpt_5":        ("GPT-5.4 mini", "🟣"),
        "kimi":         ("Kimi K2.5", "🔵"),
    }
    # 标题根据实际顾问数动态显示
    n_advisors = len([k for k in advisors if k in advisor_display])
    lines.append(f"🧑‍💼 {n_advisors} 位顾问独立建议:")
    lines.append("─────────────")
    
    for name, result in advisors.items():
        display, dot = advisor_display.get(name, (name, "⚪"))
        
        if result.get("parse_ok"):
            emoji = _emoji(result["action"])
            action_detail = _format_action_detail(
                result["action"], result.get("ticker"),
                result.get("qty", 0), result.get("price")
            )
            conf = result.get("confidence", 0)
            
            lines.append(f"{dot} {display}  信心{conf}%")
            lines.append(f"    {emoji} {action_detail}")
            if result.get("reason"):
                lines.append(f"    💭 {result['reason']}")
            if result.get("risk"):
                lines.append(f"    ⚠️  {result['risk']}")
        else:
            lines.append(f"{dot} {display}  ❌ 响应失败")
        lines.append("")
    
    # Opus Leader 最终建议
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🎯 Opus 4.7 Leader 最终决策:")
    lines.append("─────────────")
    
    if leader.get("parse_ok"):
        emoji = _emoji(leader["final_action"])
        action_detail = _format_action_detail(
            leader["final_action"], leader.get("final_ticker"),
            leader.get("final_qty", 0), leader.get("final_price")
        )
        conf = leader.get("confidence", 0)
        
        lines.append(f"{emoji} {action_detail}")
        lines.append(f"🎯 信心: {conf}%")
        lines.append(f"🤝 一致性: {leader.get('agreement', '-')}")
        
        if leader.get("differs_from_advisors"):
            lines.append(f"⚡ Leader 独立判断(与多数顾问不同)")
        
        lines.append("")
        lines.append(f"📝 {leader.get('final_reason', '')}")
        
        if leader.get("risk_warning"):
            lines.append(f"⚠️  风险: {leader['risk_warning']}")
    else:
        err_msg = leader.get("final_reason", "未知错误")
        lines.append(f"❌ Leader 失败: {err_msg}")
    
    # 成本明细
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💰 本次成本明细:")
    for name, result in advisors.items():
        display, _ = advisor_display.get(name, (name, "⚪"))
        cost = result.get("cost_usd", 0)
        tokens = result.get("tokens", 0)
        lines.append(f"  • {display:15s} ${cost:.4f}  ({tokens} tok)")
    
    leader_cost = leader.get("cost_usd", 0)
    leader_tokens = leader.get("tokens", 0)
    lines.append(f"  • Opus Leader     ${leader_cost:.4f}  ({leader_tokens} tok)")
    lines.append("─────────────")
    lines.append(f"  📊 本次总计:    ${total_cost:.4f}  ({total_tokens} tok)")
    
    # 累计成本
    cum = _get_cumulative_cost()
    lines.append(f"  📈 今日累计:    ${cum['cost']:.4f}  ({cum['calls']} 次)")
    
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  累计成本追踪 + 历史记录
# ══════════════════════════════════════════════════════════════════

import threading as _threading

_cost_lock = _threading.Lock()
_cost_file_path = None
_history_file_path = None


def _get_path(filename: str) -> str:
    """获取 data 目录下的文件路径"""
    try:
        from config.settings import BASE_DIR
        data_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, filename)
    except:
        return filename


def _get_cumulative_cost() -> dict:
    """读取今日累计成本"""
    path = _get_path("ai_advisor_cost.json")
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == today:
                return data
    except:
        pass
    return {"date": today, "cost": 0.0, "calls": 0, "tokens": 0}


def _save_cumulative_cost(delta_cost: float, delta_tokens: int):
    """累加今日成本"""
    path = _get_path("ai_advisor_cost.json")
    today = datetime.now().strftime("%Y-%m-%d")
    with _cost_lock:
        current = _get_cumulative_cost()
        current["date"] = today
        current["cost"] = round(current.get("cost", 0) + delta_cost, 5)
        current["calls"] = current.get("calls", 0) + 1
        current["tokens"] = current.get("tokens", 0) + delta_tokens
        current["last_update"] = datetime.now().isoformat(timespec="seconds")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [ai_advisor] save cost err: {e}")


def _save_history(record: dict):
    """保存完整历史记录(给 Dashboard 用)"""
    path = _get_path("ai_advisor_history.json")
    with _cost_lock:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            else:
                history = []
            history.append(record)
            # 只保留最近 200 条
            if len(history) > 200:
                history = history[-200:]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [ai_advisor] save history err: {e}")


def get_recent_history(limit: int = 20) -> list:
    """给 Dashboard 读最近的历史记录"""
    path = _get_path("ai_advisor_history.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
            return history[-limit:]
    except:
        pass
    return []


def get_today_cost() -> dict:
    """供 Dashboard/指令用"""
    return _get_cumulative_cost()
