"""
RKLB 盘前分析 — TradingAgents
date: 2026-04-28
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "TradingAgents"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "TradingAgents", ".env"))

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"]    = "anthropic"
config["deep_think_llm"]  = "claude-opus-4-6"
config["quick_think_llm"] = "claude-sonnet-4-6"
config["max_debate_rounds"]      = 1
config["max_risk_discuss_rounds"] = 1
config["output_language"] = "Chinese"

ta = TradingAgentsGraph(debug=False, config=config)

print("=" * 60)
print("  RKLB 盘前分析  2026-04-28")
print("=" * 60)

state, decision = ta.propagate("RKLB", "2026-04-28")
print("\n" + "=" * 60)
print("  最终决策")
print("=" * 60)
print(decision)
