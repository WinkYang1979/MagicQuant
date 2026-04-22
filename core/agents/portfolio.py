"""
MagicQuant — AI 虚拟操盘账户
每个 AI 一个账户,$20,000 起始,记录所有操作和盈亏.

费用模型: Moomoo AU 美股交易真实费率 (2026-04 实测)
  买入: 固定 $1.29 (Platform $0.99 + Settlement $0.30)
  卖出: $0.99 + $0.30 + SEC费(成交额×0.0000278) + FINRA TAF(股数×$0.000166, 上限$8.30)
"""

import json
import os
import threading
from datetime import datetime
from typing import Optional


# ── Moomoo AU 真实费率 ────────────────────────────────
PLATFORM_FEE   = 0.99
SETTLEMENT_FEE = 0.30
SEC_FEE_RATE   = 0.0000278
TAF_RATE       = 0.000166
TAF_MIN        = 0.01
TAF_MAX        = 8.30

INITIAL_CAPITAL = 20000.00


def calc_moomoo_au_fee(side: str, price: float, qty: int) -> float:
    """Moomoo AU 美股交易费用计算
    side: 'buy' or 'sell'
    返回: 总费用 USD
    """
    platform = PLATFORM_FEE
    settle   = SETTLEMENT_FEE
    if side == "buy":
        return round(platform + settle, 4)   # 固定 $1.29
    # sell: 额外有 SEC 费 + TAF
    amount  = price * qty
    sec_fee = round(amount * SEC_FEE_RATE, 2)
    taf     = min(max(round(qty * TAF_RATE, 2), TAF_MIN), TAF_MAX)
    return round(platform + settle + sec_fee + taf, 4)


class VirtualPortfolio:
    """
    每个 AI 一个虚拟账户.
    
    状态:
      cash           — 现金
      positions      — {ticker: {qty, cost_basis, total_cost}}
      trades         — 所有交易记录
      decisions      — 所有 AI 决策记录(包括 HOLD)
      ai_costs       — AI 调用累计成本
      total_fees     — 累计佣金
    """
    
    def __init__(self, ai_name: str, initial_capital: float = INITIAL_CAPITAL):
        self.ai_name = ai_name
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}   # {ticker: {qty, cost_basis}}
        self.trades = []      # 交易流水
        self.decisions = []   # 决策流水(含 HOLD)
        self.ai_cost_usd = 0.0
        self.ai_tokens = 0
        self.ai_calls = 0
        self.total_commission = 0.0
        self.started_at = datetime.now()
        self.lock = threading.Lock()
    
    def can_buy(self, ticker: str, qty: int, price: float) -> bool:
        fee = calc_moomoo_au_fee("buy", price, qty)
        need = qty * price + fee
        return self.cash >= need
    
    def can_sell(self, ticker: str, qty: int) -> bool:
        pos = self.positions.get(ticker)
        return pos is not None and pos.get("qty", 0) >= qty
    
    def buy(self, ticker: str, qty: int, price: float, reason: str = "") -> dict:
        """买入,返回执行结果"""
        with self.lock:
            fee = calc_moomoo_au_fee("buy", price, qty)
            if not self.can_buy(ticker, qty, price):
                return {"ok": False, "error": "insufficient_cash",
                        "need": qty * price + fee,
                        "have": self.cash}
            
            cost = qty * price
            self.cash -= cost + fee
            self.total_commission += fee
            
            # 更新持仓(成本摊薄)
            if ticker in self.positions:
                old = self.positions[ticker]
                new_qty = old["qty"] + qty
                new_avg = (old["qty"] * old["cost_basis"] + qty * price) / new_qty
                self.positions[ticker] = {"qty": new_qty, "cost_basis": round(new_avg, 4)}
            else:
                self.positions[ticker] = {"qty": qty, "cost_basis": price}
            
            trade = {
                "time":    datetime.now().isoformat(timespec="seconds"),
                "action":  "BUY",
                "ticker":  ticker,
                "qty":     qty,
                "price":   price,
                "cost":    cost,
                "fee":     fee,
                "reason":  reason,
                "cash_after": round(self.cash, 2),
            }
            self.trades.append(trade)
            return {"ok": True, "trade": trade}
    
    def sell(self, ticker: str, qty: int, price: float, reason: str = "") -> dict:
        """卖出,返回执行结果"""
        with self.lock:
            if not self.can_sell(ticker, qty):
                pos = self.positions.get(ticker, {})
                return {"ok": False, "error": "insufficient_shares",
                        "need": qty, "have": pos.get("qty", 0)}
            
            fee = calc_moomoo_au_fee("sell", price, qty)
            revenue = qty * price
            self.cash += revenue - fee
            self.total_commission += fee
            
            # 更新持仓
            old = self.positions[ticker]
            realized_pnl = (price - old["cost_basis"]) * qty - fee
            new_qty = old["qty"] - qty
            if new_qty == 0:
                del self.positions[ticker]
            else:
                self.positions[ticker] = {"qty": new_qty, "cost_basis": old["cost_basis"]}
            
            trade = {
                "time":    datetime.now().isoformat(timespec="seconds"),
                "action":  "SELL",
                "ticker":  ticker,
                "qty":     qty,
                "price":   price,
                "revenue": revenue,
                "fee":     fee,
                "realized_pnl": round(realized_pnl, 2),
                "reason":  reason,
                "cash_after": round(self.cash, 2),
            }
            self.trades.append(trade)
            return {"ok": True, "trade": trade}
    
    def record_decision(self, ticker_prices: dict, decision: dict,
                        tokens: int, cost_usd: float, raw_response: str = ""):
        """记录每次 AI 决策(包括 HOLD)"""
        with self.lock:
            self.ai_tokens += tokens
            self.ai_cost_usd += cost_usd
            self.ai_calls += 1
            
            rec = {
                "time":       datetime.now().isoformat(timespec="seconds"),
                "prices":     ticker_prices.copy(),
                "decision":   decision,
                "tokens":     tokens,
                "cost_usd":   cost_usd,
                "raw_first_100": raw_response[:100],
            }
            self.decisions.append(rec)
    
    def market_value(self, current_prices: dict) -> float:
        """用当前价计算持仓市值"""
        total = 0.0
        for tk, pos in self.positions.items():
            p = current_prices.get(tk, pos["cost_basis"])
            total += pos["qty"] * p
        return round(total, 2)
    
    def equity(self, current_prices: dict) -> float:
        """总权益 = 现金 + 持仓市值"""
        return round(self.cash + self.market_value(current_prices), 2)
    
    def unrealized_pnl(self, current_prices: dict) -> float:
        """未实现盈亏"""
        total = 0.0
        for tk, pos in self.positions.items():
            p = current_prices.get(tk, pos["cost_basis"])
            total += (p - pos["cost_basis"]) * pos["qty"]
        return round(total, 2)
    
    def realized_pnl(self) -> float:
        """已实现盈亏(含费用)"""
        return round(sum(
            t.get("realized_pnl", 0) for t in self.trades if t["action"] == "SELL"
        ), 2)
    
    def summary(self, current_prices: dict) -> dict:
        """完整快照"""
        eq = self.equity(current_prices)
        total_pnl = eq - self.initial_capital
        total_pnl_pct = total_pnl / self.initial_capital * 100
        
        return {
            "ai_name":          self.ai_name,
            "started_at":       self.started_at.isoformat(timespec="seconds"),
            "initial_capital":  self.initial_capital,
            "cash":             round(self.cash, 2),
            "positions":        dict(self.positions),
            "market_value":     self.market_value(current_prices),
            "equity":           eq,
            "total_pnl":        round(total_pnl, 2),
            "total_pnl_pct":    round(total_pnl_pct, 2),
            "unrealized_pnl":   self.unrealized_pnl(current_prices),
            "realized_pnl":     self.realized_pnl(),
            "total_trades":     len(self.trades),
            "total_decisions":  len(self.decisions),
            "total_commission": round(self.total_commission, 2),
            "ai_tokens":        self.ai_tokens,
            "ai_cost_usd":      round(self.ai_cost_usd, 4),
            "ai_calls":         self.ai_calls,
        }
    
    def save(self, path: str):
        """持久化到文件"""
        with self.lock:
            data = {
                "ai_name":          self.ai_name,
                "started_at":       self.started_at.isoformat(),
                "initial_capital":  self.initial_capital,
                "cash":             self.cash,
                "positions":        self.positions,
                "trades":           self.trades,
                "decisions":        self.decisions[-500:],  # 只保留最近 500 条决策
                "ai_tokens":        self.ai_tokens,
                "ai_cost_usd":      self.ai_cost_usd,
                "ai_calls":         self.ai_calls,
                "total_commission": self.total_commission,
            }
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, path: str, ai_name: str):
        """从文件恢复"""
        p = cls(ai_name)
        if not os.path.exists(path):
            return p
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            p.started_at = datetime.fromisoformat(data["started_at"])
            p.initial_capital = data["initial_capital"]
            p.cash = data["cash"]
            p.positions = data.get("positions", {})
            p.trades = data.get("trades", [])
            p.decisions = data.get("decisions", [])
            p.ai_tokens = data.get("ai_tokens", 0)
            p.ai_cost_usd = data.get("ai_cost_usd", 0.0)
            p.ai_calls = data.get("ai_calls", 0)
            p.total_commission = data.get("total_commission", 0.0)
        except Exception as e:
            print(f"  [portfolio] load error: {e}")
        return p
    
    def reset(self):
        """重置账户(重新开始)"""
        with self.lock:
            self.cash = self.initial_capital
            self.positions = {}
            self.trades = []
            self.decisions = []
            self.ai_tokens = 0
            self.ai_cost_usd = 0.0
            self.ai_calls = 0
            self.total_commission = 0.0
            self.started_at = datetime.now()
