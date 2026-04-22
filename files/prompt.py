"""
MagicQuant — AI 决策 Prompt 模板 + 响应解析
"""

import re
import json
from typing import Optional


SYSTEM_PROMPT = """你是一名专业的美股日内交易员,正在参加 AI 操盘大赛.

你的账户: $20,000 USD 起始资金.
可交易标的只有 3 只:
  - RKLB  : Rocket Lab 正股(信号源)
  - RKLX  : 2x 做多 RKLB ETF (RKLB 涨,RKLX 加速涨)
  - RKLZ  : 2x 做空 RKLB ETF (RKLB 跌,RKLZ 加速涨)

你的策略偏好:日内波段做 T,不长持过夜.

交易规则:
  - 买入费用固定 $1.29 USD/笔
  - 卖出费用约 $1.31-$1.60 USD/笔 (含 SEC + FINRA TAF, 大单更高)
  - 100 股往返总成本约 $2.60-$2.90
  - 建议每笔 50-200 股
  - 不能做空(只能买多/卖出已有仓位)
  - 现金不够就不能买

输出格式(严格 JSON,不要额外文字):
{
  "action": "BUY" | "SELL" | "HOLD",
  "ticker": "RKLB" | "RKLX" | "RKLZ" | null,
  "qty": 整数(股数,HOLD 时为 0),
  "reason": "一句话中文理由(不超过 30 字)",
  "confidence": 0-100 整数
}

决策原则:
  - 没信心就 HOLD,不强行交易
  - 谨慎是美德,费用会吃利润
  - 波段顶看跌 → 买 RKLZ 或卖 RKLX
  - 波段底看涨 → 买 RKLX 或卖 RKLZ
"""


def build_user_prompt(market_data: dict, portfolio_summary: dict) -> str:
    """构建用户 prompt"""
    m = market_data
    p = portfolio_summary
    
    # 市场数据
    prices_str = []
    for tk in ["RKLB", "RKLX", "RKLZ"]:
        info = m["prices"].get(tk, {})
        if info:
            prices_str.append(
                f"  {tk}: ${info['price']:.2f}  "
                f"今低 ${info.get('low', 0):.2f}  "
                f"今高 ${info.get('high', 0):.2f}"
            )
    
    # 技术指标(只有 RKLB 有)
    ind = m.get("indicators", {})
    indicators_str = ""
    if ind and ind.get("rsi_5m"):
        indicators_str = (
            f"\nRKLB 5M 指标:\n"
            f"  RSI: {ind.get('rsi_5m', '?')}\n"
            f"  VWAP: ${ind.get('vwap', 0):.2f}\n"
            f"  量比: {ind.get('vol_ratio', 0):.2f}x\n"
            f"  K线形态: {ind.get('candle', {}).get('name', '—')}\n"
        )
    
    # 持仓情况
    pos_str = "空仓"
    if p["positions"]:
        pos_lines = []
        for tk, pos in p["positions"].items():
            cur = m["prices"].get(tk, {}).get("price", pos["cost_basis"])
            pl = (cur - pos["cost_basis"]) * pos["qty"]
            pl_pct = (cur - pos["cost_basis"]) / pos["cost_basis"] * 100
            pos_lines.append(
                f"  {tk}: {pos['qty']} 股 @${pos['cost_basis']:.2f}, "
                f"现价 ${cur:.2f}, 浮盈 ${pl:+.2f} ({pl_pct:+.2f}%)"
            )
        pos_str = "\n".join(pos_lines)
    
    current_time = m.get("time", "")
    
    return f"""时间: {current_time}

【当前价格】
{chr(10).join(prices_str) if prices_str else "数据获取中"}
{indicators_str}
【你的账户】
  现金: ${p['cash']:.2f}
  持仓:
{pos_str}
  总权益: ${p['equity']:.2f}
  今日盈亏: ${p['total_pnl']:+.2f} ({p['total_pnl_pct']:+.2f}%)
  已交易: {p['total_trades']} 次

【任务】
基于以上信息,做出本轮操作决策.如果没有强信号就 HOLD.
严格输出 JSON,不要任何其他文字.
"""


def parse_decision(raw_text: str) -> dict:
    """
    从 AI 输出提取 JSON 决策.
    返回统一格式:
      {action, ticker, qty, reason, confidence, parse_ok, raw}
    """
    result = {
        "action":     "HOLD",
        "ticker":     None,
        "qty":        0,
        "reason":     "",
        "confidence": 50,
        "parse_ok":   False,
        "raw":        raw_text[:500],
    }
    
    if not raw_text:
        result["reason"] = "(空响应)"
        return result
    
    # 尝试提取 JSON
    json_match = re.search(r'\{[^}]*"action"[^}]*\}', raw_text, re.DOTALL)
    if not json_match:
        # 第二次尝试:markdown 代码块
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            result["reason"] = "(未找到 JSON)"
            return result
    else:
        json_text = json_match.group(0)
    
    try:
        parsed = json.loads(json_text)
        action = str(parsed.get("action", "HOLD")).upper()
        if action not in ("BUY", "SELL", "HOLD"):
            action = "HOLD"
        
        ticker = parsed.get("ticker")
        if ticker:
            ticker = str(ticker).upper().replace("US.", "")
            if ticker not in ("RKLB", "RKLX", "RKLZ"):
                ticker = None
        
        qty = int(parsed.get("qty", 0) or 0)
        qty = max(0, min(qty, 10000))  # 限制在合理范围
        
        reason = str(parsed.get("reason", ""))[:100]
        confidence = int(parsed.get("confidence", 50) or 50)
        confidence = max(0, min(confidence, 100))
        
        if action == "HOLD":
            ticker = None
            qty = 0
        
        result.update({
            "action":     action,
            "ticker":     ticker,
            "qty":        qty,
            "reason":     reason,
            "confidence": confidence,
            "parse_ok":   True,
        })
    except Exception as e:
        result["reason"] = f"(解析失败: {str(e)[:50]})"
    
    return result
