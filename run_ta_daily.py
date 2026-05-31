"""
run_ta_daily.py — TradingAgents RKLB 每日自动分析
每天 22:00 (墨尔本时间) 由 Windows Task Scheduler 触发
结果保存到 daily_briefing.py 可自动读取的路径

日期逻辑:
  墨尔本 22:00 = 美东 08:00 (EDT)，当天 US 盘尚未开盘
  → 分析对象为"前一个 US 交易日"
  公式: date.today() - 1 天，再向前找最近工作日（跳过周末）
"""

import sys, os, subprocess
from pathlib import Path
from datetime import date, timedelta, datetime

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE / "TradingAgents"))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(BASE / ".env")
load_dotenv(BASE / "TradingAgents" / ".env")

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


# ──────────────────────────────────────────────────────────────────
#  日期工具
# ──────────────────────────────────────────────────────────────────
def last_us_trading_day() -> str:
    """
    墨尔本 22:00 运行时，美股前一个完整交易日的日期。
    今天(墨尔本) - 1 天，再往前跳过周末。
    """
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:   # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


# ──────────────────────────────────────────────────────────────────
#  配置
# ──────────────────────────────────────────────────────────────────
TICKER     = "RKLB"
TRADE_DATE = last_us_trading_day()
TA_OUT_DIR = Path.home() / ".tradingagents" / "logs" / TICKER / TRADE_DATE / "reports"

config = DEFAULT_CONFIG.copy()
config.update({
    "llm_provider":           "anthropic",
    "deep_think_llm":         "claude-sonnet-4-6",
    "quick_think_llm":        "claude-haiku-4-5",
    "max_debate_rounds":       1,
    "max_risk_discuss_rounds": 1,
    "output_language":        "English",
    "data_vendors": {
        "core_stock_apis":      "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data":     "yfinance",
        "news_data":            "yfinance",
    },
})


# ──────────────────────────────────────────────────────────────────
#  主程序
# ──────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"  TradingAgents Daily  |  {TICKER}  |  {TRADE_DATE}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  (Melbourne time)")
    print(f"  LLM: claude-sonnet-4-6 (deep) + claude-haiku-4-5 (quick)")
    print("=" * 60)

    ta = TradingAgentsGraph(debug=False, config=config)
    state, decision = ta.propagate(TICKER, TRADE_DATE)

    # ── 提取报告内容 ──
    market_report = ""
    final_decision_text = ""
    if isinstance(state, dict):
        market_report       = state.get("market_report", "") or ""
        final_decision_text = state.get("final_trade_decision", "") or ""

    # market_report 为空时用 final_trade_decision 兜底
    if not market_report.strip():
        decision_upper = str(decision).strip().upper()
        market_report = (
            f"FINAL TRANSACTION PROPOSAL: **{decision_upper}**\n\n"
            f"{final_decision_text}"
        )

    # ── 保存文件 ──
    TA_OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. market_report.md — daily_briefing.py 读取此文件
    report_path = TA_OUT_DIR / "market_report.md"
    report_path.write_text(market_report, encoding="utf-8")
    print(f"\n  ✅ market_report.md  → {report_path}")

    # 2. final_decision.md — 完整决策原文，供人工复盘
    if final_decision_text:
        final_path = TA_OUT_DIR / "final_decision.md"
        final_path.write_text(
            f"# TradingAgents: {TICKER} {TRADE_DATE}\n\n{final_decision_text}",
            encoding="utf-8",
        )
        print(f"  ✅ final_decision.md → {final_path}")

    print(f"\n  Decision: {decision}")
    print("=" * 60)

    notify_script = BASE / "tradingagents_notify.py"
    if notify_script.exists():
        try:
            subprocess.run(
                [sys.executable, str(notify_script), "--ticker", TICKER, "--date", TRADE_DATE],
                cwd=str(BASE),
                timeout=30,
            )
        except Exception as e:
            print(f"  TradingAgents notify failed: {e}")


if __name__ == "__main__":
    main()
