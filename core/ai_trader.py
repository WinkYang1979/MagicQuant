"""
MagicQuant 慧投 — AI 虚拟操盘引擎 v0.3.0
AI Virtual Trading Engine

核心原则：
  - 与真实市场同步，使用相同数据源
  - 所有操作带时间戳，不可篡改
  - 遵守 PDT 规则，计算实际手续费
  - 决策过程完全透明，推送到 Telegram

数据文件：data/ai_portfolio.json
操作日志：data/ai_trades.json

Owner: Zhen Yang
"""

import json, os, sys, time
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\MagicQuant")
from config.settings import (
    BASE_DIR, SIGNALS_FILE, CLAUDE_API_KEY, CLAUDE_MODEL,
    CLAUDE_PRICE_IN, CLAUDE_PRICE_OUT
)

import urllib.request

# ── 文件路径 ──────────────────────────────────────────────────────
AI_PORTFOLIO_FILE = os.path.join(BASE_DIR, "data", "ai_portfolio.json")
AI_TRADES_FILE    = os.path.join(BASE_DIR, "data", "ai_trades.json")

# ── 虚拟账户初始配置 ──────────────────────────────────────────────
INITIAL_CASH      = 20000.0   # 与真实账户相同起始资金
MAX_POSITION_PCT  = 0.30      # 单票最大仓位 30%
RISK_PER_TRADE    = 0.05      # 每笔风险 5%
PDT_WINDOW_DAYS   = 7         # PDT 滚动窗口
PDT_LIMIT         = 3         # PDT 限制次数

# ── 手续费（与真实账户一致）──────────────────────────────────────
FEE_BUY  = 1.29   # 买入每笔
FEE_SELL = 1.31   # 卖出每笔


# ══════════════════════════════════════════════════════════════════
#  数据读写
# ══════════════════════════════════════════════════════════════════

def load_portfolio() -> dict:
    """加载 AI 虚拟账户 / Load AI virtual portfolio"""
    if os.path.exists(AI_PORTFOLIO_FILE):
        try:
            return json.load(open(AI_PORTFOLIO_FILE, encoding="utf-8"))
        except:
            pass
    # 初始化
    return {
        "created_at":   datetime.now().isoformat(),
        "initial_cash": INITIAL_CASH,
        "cash":         INITIAL_CASH,
        "positions":    {},   # ticker -> {qty, cost_price, buy_time}
        "total_trades": 0,
        "win_trades":   0,
        "pdt_trades":   [],   # 记录日内交易用于 PDT 计数
    }


def save_portfolio(portfolio: dict):
    os.makedirs(os.path.dirname(AI_PORTFOLIO_FILE), exist_ok=True)
    portfolio["updated_at"] = datetime.now().isoformat()
    json.dump(portfolio, open(AI_PORTFOLIO_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


def load_trades() -> list:
    """加载交易历史 / Load trade history"""
    if os.path.exists(AI_TRADES_FILE):
        try:
            return json.load(open(AI_TRADES_FILE, encoding="utf-8"))
        except:
            pass
    return []


def save_trades(trades: list):
    os.makedirs(os.path.dirname(AI_TRADES_FILE), exist_ok=True)
    json.dump(trades, open(AI_TRADES_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


def load_signals() -> dict | None:
    try:
        return json.load(open(SIGNALS_FILE, encoding="utf-8"))
    except:
        return None


# ══════════════════════════════════════════════════════════════════
#  PDT 检查
# ══════════════════════════════════════════════════════════════════

def count_pdt(portfolio: dict, ticker: str) -> int:
    """
    统计滚动5个交易日内的日内交易次数
    Count day trades in rolling 5 trading days
    """
    cutoff = (datetime.now() - timedelta(days=PDT_WINDOW_DAYS)).isoformat()
    count  = 0
    for record in portfolio.get("pdt_trades", []):
        if record.get("time", "") >= cutoff:
            count += 1
    return count


def can_day_trade(portfolio: dict, ticker: str) -> bool:
    """检查是否还有 PDT 余量"""
    return count_pdt(portfolio, ticker) < PDT_LIMIT


# ══════════════════════════════════════════════════════════════════
#  仓位计算
# ══════════════════════════════════════════════════════════════════

def calc_buy_shares(portfolio: dict, price: float, stop_loss: float) -> int:
    """
    计算可买股数：
    1. 基于风险（账户5%）
    2. 不超过总资产30%
    3. 不超过可用现金（扣手续费）
    """
    total_assets = get_total_assets(portfolio, {})
    rps = abs(price - stop_loss)
    if rps <= 0:
        return 0

    # 按风险计算
    risk_shares = int(total_assets * RISK_PER_TRADE / rps)
    # 按仓位上限计算
    max_shares  = int(total_assets * MAX_POSITION_PCT / price)
    # 按现金计算
    cash_shares = int((portfolio["cash"] - FEE_BUY) / price)

    shares = min(risk_shares, max_shares, cash_shares)
    return max(0, shares)


def get_total_assets(portfolio: dict, prices: dict) -> float:
    """计算 AI 账户总资产"""
    total = portfolio["cash"]
    for ticker, pos in portfolio["positions"].items():
        price = prices.get(ticker, pos["cost_price"])
        total += pos["qty"] * price
    return round(total, 2)


def get_position_pnl(portfolio: dict, ticker: str, current_price: float) -> dict:
    """计算某持仓盈亏"""
    pos = portfolio["positions"].get(ticker)
    if not pos:
        return {}
    qty    = pos["qty"]
    cost   = pos["cost_price"]
    pl_val = round((current_price - cost) * qty, 2)
    pl_pct = round((current_price - cost) / cost * 100, 2) if cost > 0 else 0
    return {
        "qty":       qty,
        "cost":      cost,
        "price":     current_price,
        "mkt_val":   round(qty * current_price, 2),
        "pl_val":    pl_val,
        "pl_pct":    pl_pct,
    }


# ══════════════════════════════════════════════════════════════════
#  Claude AI 决策
# ══════════════════════════════════════════════════════════════════

def ask_claude_decision(ticker: str, signal_data: dict,
                        portfolio: dict, prices: dict) -> dict:
    """
    调用 Claude API 做投资决策
    返回：{action, qty, reason, confidence}
    action: "BUY" / "SELL" / "HOLD"
    """
    if not CLAUDE_API_KEY:
        # 无 API Key 时用规则引擎降级
        return rule_based_decision(ticker, signal_data, portfolio)

    ind    = signal_data.get("indicators", {})
    risk   = signal_data.get("risk", {})
    price  = signal_data.get("price", 0)
    sig    = signal_data.get("signal", "HOLD")
    pos    = portfolio["positions"].get(ticker)
    total  = get_total_assets(portfolio, prices)
    cash   = portfolio["cash"]
    pdt_used = count_pdt(portfolio, ticker)

    # 当前持仓信息
    if pos:
        pnl    = get_position_pnl(portfolio, ticker, price)
        pos_desc = (
            f"当前持仓 {pos['qty']} 股，成本 ${pos['cost_price']}，"
            f"浮盈亏 {pnl['pl_pct']:+.1f}% (${pnl['pl_val']:+.2f})"
        )
    else:
        pos_desc = "当前无持仓"

    prompt = (
        f"你是 MagicQuant AI 操盘系统，现在对 {ticker} 做交易决策。\n\n"
        f"账户状态：\n"
        f"  总资产: ${total:,.2f}  可用现金: ${cash:,.2f}\n"
        f"  PDT已用: {pdt_used}/3次（滚动5日）\n"
        f"  {pos_desc}\n\n"
        f"市场数据：\n"
        f"  现价: ${price:.2f}  系统信号: {sig}\n"
        f"  RSI(相对强弱): {ind.get('rsi','?')}\n"
        f"  MACD柱(动量): {ind.get('macd_hist',0):+.4f}\n"
        f"  量比(成交量): {ind.get('vol_ratio',0)}x\n"
        f"  布林%B(价格位置): {ind.get('pct_b',0):.2f}\n"
        f"  ATR(波动幅度): {ind.get('atr','?')}\n"
        f"  MA5/20/60: {ind.get('ma5','?')} / {ind.get('ma20','?')} / {ind.get('ma60','?')}\n"
        f"  止损参考: ${risk.get('stop_loss','?')}  目标1: ${risk.get('target1','?')}\n\n"
        f"信号依据:\n"
        + "\n".join(f"  {i+1}. {r}"
                    for i, r in enumerate(signal_data.get("reasons", [])[:4]))
        + "\n\n"
        f"请严格按以下 JSON 格式输出决策（不要其他内容）：\n"
        f'{{"action":"BUY/SELL/HOLD","qty":整数或0,"reason":"一句话决策依据","confidence":0-100}}\n\n'
        f"规则：\n"
        f"  - BUY：买入股数不超过现金的30%且不超过{int(cash*0.3/price) if price>0 else 0}股\n"
        f"  - SELL：只能卖已持有的{pos['qty'] if pos else 0}股，部分或全部\n"
        f"  - HOLD：qty填0\n"
        f"  - PDT余量为0时，今日不做日内交易（当天买当天卖）"
    )

    try:
        payload = json.dumps({
            "model":      CLAUDE_MODEL,
            "max_tokens": 150,
            "system":     (
                "你是专业量化交易AI，严格按JSON格式输出决策，"
                "不输出任何其他内容，不加markdown标记。"
            ),
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        ai_text = "".join(
            b["text"] for b in result.get("content", [])
            if b.get("type") == "text"
        ).strip()

        # 记录费用
        usage    = result.get("usage", {})
        tin      = usage.get("input_tokens", 0)
        tout     = usage.get("output_tokens", 0)
        cost_usd = tin * CLAUDE_PRICE_IN + tout * CLAUDE_PRICE_OUT

        # 解析 JSON
        decision = json.loads(ai_text)
        decision["cost_usd"] = cost_usd
        decision["tokens"]   = tin + tout
        return decision

    except Exception as e:
        print(f"  AI decision error: {e}")
        return rule_based_decision(ticker, signal_data, portfolio)


def rule_based_decision(ticker: str, signal_data: dict,
                        portfolio: dict) -> dict:
    """
    规则引擎降级（无 API Key 时使用）
    Rule-based fallback decision
    """
    sig   = signal_data.get("signal", "HOLD")
    price = signal_data.get("price", 0)
    risk  = signal_data.get("risk", {})
    pos   = portfolio["positions"].get(ticker)
    sl    = risk.get("stop_loss", 0)

    if sig == "BUY" and not pos:
        qty = calc_buy_shares(portfolio, price, sl)
        return {
            "action":     "BUY",
            "qty":        qty,
            "reason":     f"系统信号买入，RSI={signal_data.get('indicators',{}).get('rsi','?')}",
            "confidence": signal_data.get("confidence", 50),
            "cost_usd":   0,
            "tokens":     0,
        }
    elif sig == "SELL" and pos:
        return {
            "action":     "SELL",
            "qty":        pos["qty"],
            "reason":     "系统信号卖出",
            "confidence": signal_data.get("confidence", 50),
            "cost_usd":   0,
            "tokens":     0,
        }
    else:
        return {
            "action":     "HOLD",
            "qty":        0,
            "reason":     "持有观望",
            "confidence": 50,
            "cost_usd":   0,
            "tokens":     0,
        }


# ══════════════════════════════════════════════════════════════════
#  执行虚拟交易
# ══════════════════════════════════════════════════════════════════

def execute_trade(portfolio: dict, trades: list,
                  ticker: str, decision: dict,
                  price: float) -> dict | None:
    """
    执行虚拟交易，更新持仓和现金
    Returns: 交易记录 或 None（无操作）
    """
    action = decision.get("action", "HOLD")
    qty    = int(decision.get("qty", 0))
    now    = datetime.now().isoformat()

    if action == "HOLD" or qty <= 0:
        return None

    trade_record = {
        "time":       now,
        "ticker":     ticker,
        "action":     action,
        "qty":        qty,
        "price":      price,
        "reason":     decision.get("reason", ""),
        "confidence": decision.get("confidence", 0),
        "cost_usd":   decision.get("cost_usd", 0),
    }

    if action == "BUY":
        total_cost = round(price * qty + FEE_BUY, 2)
        if total_cost > portfolio["cash"]:
            return None  # 现金不足

        portfolio["cash"] = round(portfolio["cash"] - total_cost, 2)
        if ticker in portfolio["positions"]:
            # 加仓：计算新均价
            old = portfolio["positions"][ticker]
            old_val  = old["qty"] * old["cost_price"]
            new_val  = qty * price
            new_qty  = old["qty"] + qty
            new_cost = round((old_val + new_val) / new_qty, 4)
            portfolio["positions"][ticker] = {
                "qty":        new_qty,
                "cost_price": new_cost,
                "buy_time":   old["buy_time"],  # 保留原始买入时间
            }
        else:
            portfolio["positions"][ticker] = {
                "qty":        qty,
                "cost_price": round(price, 4),
                "buy_time":   now,
            }

        trade_record["fee"]       = FEE_BUY
        trade_record["net_cost"]  = total_cost
        portfolio["total_trades"] += 1

    elif action == "SELL":
        pos = portfolio["positions"].get(ticker)
        if not pos or pos["qty"] < qty:
            return None  # 持仓不足

        proceeds = round(price * qty - FEE_SELL, 2)
        cost_val  = round(pos["cost_price"] * qty, 2)
        pnl       = round(proceeds - cost_val, 2)

        portfolio["cash"] = round(portfolio["cash"] + proceeds, 2)

        if qty >= pos["qty"]:
            del portfolio["positions"][ticker]
        else:
            portfolio["positions"][ticker]["qty"] -= qty

        # PDT 判断：当天买当天卖 = 日内交易
        buy_time = pos.get("buy_time", "")
        if buy_time[:10] == now[:10]:
            portfolio["pdt_trades"].append({
                "time":   now,
                "ticker": ticker,
            })
            # 只保留最近 PDT_WINDOW_DAYS 天
            cutoff = (datetime.now() - timedelta(days=PDT_WINDOW_DAYS)).isoformat()
            portfolio["pdt_trades"] = [
                r for r in portfolio["pdt_trades"]
                if r.get("time", "") >= cutoff
            ]

        trade_record["fee"]      = FEE_SELL
        trade_record["proceeds"] = proceeds
        trade_record["pnl"]      = pnl

        portfolio["total_trades"] += 1
        if pnl > 0:
            portfolio["win_trades"] += 1

    trades.append(trade_record)
    return trade_record


# ══════════════════════════════════════════════════════════════════
#  主入口：处理一次信号刷新
# ══════════════════════════════════════════════════════════════════

def run_once() -> list[dict]:
    """
    读取最新信号，对每只股票做决策并执行
    Returns: 本次所有交易记录列表
    """
    signals_data = load_signals()
    if not signals_data:
        print("  AI Trader: No signal data")
        return []

    signals   = signals_data.get("signals", [])
    portfolio = load_portfolio()
    trades    = load_trades()
    executed  = []

    # 构建当前价格字典（用于总资产计算）
    prices = {
        s["ticker"]: s["price"]
        for s in signals
        if "error" not in s
    }

    print(f"\n  AI Trader | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  总资产: ${get_total_assets(portfolio, prices):,.2f}  "
          f"现金: ${portfolio['cash']:,.2f}  "
          f"PDT已用: {count_pdt(portfolio, '')}/3")

    for s in signals:
        if "error" in s:
            continue
        ticker = s["ticker"]
        price  = s["price"]
        ticker_short = ticker.replace("US.", "")

        # 止损检查：持仓跌破止损价自动卖出
        pos = portfolio["positions"].get(ticker)
        if pos:
            sl = s.get("risk", {}).get("stop_loss", 0)
            pnl = get_position_pnl(portfolio, ticker, price)
            if sl and price <= sl:
                print(f"  {ticker_short}: 触发止损 ${price:.2f} <= ${sl}")
                stop_decision = {
                    "action":     "SELL",
                    "qty":        pos["qty"],
                    "reason":     f"触发止损，现价${price:.2f}跌破止损${sl}",
                    "confidence": 100,
                    "cost_usd":   0,
                    "tokens":     0,
                }
                rec = execute_trade(portfolio, trades, ticker, stop_decision, price)
                if rec:
                    executed.append(rec)
                continue

        # AI 决策
        decision = ask_claude_decision(ticker, s, portfolio, prices)
        print(f"  {ticker_short}: {decision.get('action')} "
              f"{decision.get('qty')}股 | {decision.get('reason','')[:30]}")

        if decision.get("action") != "HOLD":
            rec = execute_trade(portfolio, trades, ticker, decision, price)
            if rec:
                executed.append(rec)

    save_portfolio(portfolio)
    save_trades(trades)

    total = get_total_assets(portfolio, prices)
    pnl   = round(total - portfolio["initial_cash"], 2)
    pct   = round(pnl / portfolio["initial_cash"] * 100, 2)
    print(f"  执行 {len(executed)} 笔 | "
          f"总资产 ${total:,.2f} | 累计盈亏 {'+' if pnl>=0 else ''}{pnl:.2f} ({pct:+.1f}%)")

    return executed


# ══════════════════════════════════════════════════════════════════
#  查询接口（供 bot_controller 调用）
# ══════════════════════════════════════════════════════════════════

def get_summary(prices: dict = None) -> dict:
    """获取 AI 账户摘要 / Get AI account summary"""
    portfolio = load_portfolio()
    prices    = prices or {}
    total     = get_total_assets(portfolio, prices)
    initial   = portfolio["initial_cash"]
    pnl       = round(total - initial, 2)
    pct       = round(pnl / initial * 100, 2) if initial > 0 else 0
    trades    = load_trades()
    win       = portfolio.get("win_trades", 0)
    total_tr  = portfolio.get("total_trades", 0)
    win_rate  = round(win / total_tr * 100, 1) if total_tr > 0 else 0

    # 计算运行天数
    created   = portfolio.get("created_at", datetime.now().isoformat())
    days      = max(1, (datetime.now() - datetime.fromisoformat(created)).days)

    return {
        "initial_cash":  initial,
        "cash":          portfolio["cash"],
        "total_assets":  total,
        "pnl":           pnl,
        "pnl_pct":       pct,
        "positions":     portfolio["positions"],
        "total_trades":  total_tr,
        "win_trades":    win,
        "win_rate":      win_rate,
        "pdt_used":      count_pdt(portfolio, ""),
        "days_running":  days,
        "recent_trades": trades[-5:] if trades else [],
    }


def get_positions_detail(prices: dict = None) -> list:
    """获取 AI 持仓明细 / Get AI position details"""
    portfolio = load_portfolio()
    prices    = prices or {}
    result    = []
    for ticker, pos in portfolio["positions"].items():
        price = prices.get(ticker, pos["cost_price"])
        pnl   = get_position_pnl(portfolio, ticker, price)
        result.append({
            "ticker":     ticker,
            "qty":        pos["qty"],
            "cost_price": pos["cost_price"],
            "price":      price,
            "mkt_val":    pnl.get("mkt_val", 0),
            "pl_val":     pnl.get("pl_val", 0),
            "pl_pct":     pnl.get("pl_pct", 0),
            "buy_time":   pos.get("buy_time", "")[:16],
        })
    return result


def reset_portfolio():
    """重置 AI 账户（谨慎使用）/ Reset AI portfolio"""
    if os.path.exists(AI_PORTFOLIO_FILE):
        os.remove(AI_PORTFOLIO_FILE)
    if os.path.exists(AI_TRADES_FILE):
        os.remove(AI_TRADES_FILE)
    print("  AI 账户已重置")


# ══════════════════════════════════════════════════════════════════
#  命令行测试
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        confirm = input("确认重置 AI 账户？(yes/no): ")
        if confirm.lower() == "yes":
            reset_portfolio()
    elif len(sys.argv) > 1 and sys.argv[1] == "--summary":
        summary = get_summary()
        print(f"\nAI 账户摘要")
        print(f"  运行天数: {summary['days_running']} 天")
        print(f"  总资产: ${summary['total_assets']:,.2f}")
        print(f"  累计盈亏: {'+' if summary['pnl']>=0 else ''}{summary['pnl']:.2f} ({summary['pnl_pct']:+.1f}%)")
        print(f"  胜率: {summary['win_rate']}% ({summary['win_trades']}/{summary['total_trades']})")
    else:
        executed = run_once()
        print(f"\n  本次执行 {len(executed)} 笔交易")
