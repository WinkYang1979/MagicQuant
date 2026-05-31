"""
TradingAgents — RKLB 分析
使用 claude-sonnet-4-6 运行完整多智能体分析
"""
import sys, os
sys.path.insert(0, "TradingAgents")
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv("TradingAgents/.env")

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"]      = "anthropic"
config["deep_think_llm"]    = "claude-sonnet-4-6"
config["quick_think_llm"]   = "claude-haiku-4-5"
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
config["output_language"]   = "English"
config["data_vendors"] = {
    "core_stock_apis":      "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data":     "yfinance",
    "news_data":            "yfinance",
}

TICKER = "RKLB"
DATE   = "2026-04-24"   # most recent Friday

print("=" * 60)
print(f"  TradingAgents  |  {TICKER}  |  {DATE}")
print(f"  LLM: anthropic / sonnet-4-6 + haiku-4-5")
print("=" * 60)

ta = TradingAgentsGraph(debug=False, config=config)
state, decision = ta.propagate(TICKER, DATE)

print("\n" + "=" * 60)
print("  FINAL DECISION")
print("=" * 60)
print(decision)

# 保存到文件
out_path = "data/review/rklb_tradingagents_20260424.md"
os.makedirs("data/review", exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    f.write(f"# TradingAgents Analysis: {TICKER} {DATE}\n\n")
    f.write(decision if isinstance(decision, str) else str(decision))
print(f"\n✅ 结果已保存: {out_path}")
