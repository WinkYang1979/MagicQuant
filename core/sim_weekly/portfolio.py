"""SimPortfolio —— 自包含纸面组合(现金/持仓/成交/盈亏),含手续费 + 滑点。

约束:纯纸面;只 long ETF 工具(看空通过买反向 ETF 表达,故持仓永远是正股数)。
"""
from __future__ import annotations

import json
import math
from typing import Dict, List, Optional

from .fees import calc_fee

DEFAULT_SLIPPAGE = 0.0006   # 0.06% 单边滑点(杠杆 ETF 点差不可忽略)


class SimPortfolio:
    def __init__(self, initial_capital: float = 10000.0, slippage: float = DEFAULT_SLIPPAGE):
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.slippage = float(slippage)
        self.positions: Dict[str, dict] = {}   # ticker -> {qty, cost_price, open_ts, stop, peak}
        self.trades: List[dict] = []
        self.total_fees = 0.0
        self.equity_curve: List[tuple] = []     # (ts, equity)

    # ── 成交 ────────────────────────────────────────────────
    def buy(self, ticker: str, qty: int, price: float, ts: str, reason: str = "",
            stop: Optional[float] = None) -> Optional[dict]:
        qty = int(qty)
        if qty <= 0 or price <= 0:
            return None
        fill = round(price * (1 + self.slippage), 4)
        fee = calc_fee("buy", fill, qty)
        cost = round(fill * qty + fee, 2)
        if cost > self.cash + 1e-6:
            # 现金不足:按可买上限缩减
            qty = int((self.cash - fee) // fill)
            if qty <= 0:
                return None
            cost = round(fill * qty + fee, 2)
        self.cash = round(self.cash - cost, 2)
        self.total_fees = round(self.total_fees + fee, 4)
        pos = self.positions.get(ticker)
        if pos:
            new_qty = pos["qty"] + qty
            pos["cost_price"] = round((pos["cost_price"] * pos["qty"] + fill * qty) / new_qty, 4)
            pos["qty"] = new_qty
            if stop is not None:
                pos["stop"] = stop
        else:
            self.positions[ticker] = {"qty": qty, "cost_price": fill, "open_ts": ts,
                                      "stop": stop, "peak": fill}
        rec = {"ts": ts, "side": "buy", "ticker": ticker, "qty": qty, "price": fill,
               "fee": fee, "reason": reason}
        self.trades.append(rec)
        return rec

    def sell(self, ticker: str, qty: int, price: float, ts: str, reason: str = "") -> Optional[dict]:
        pos = self.positions.get(ticker)
        if not pos or price <= 0:
            return None
        qty = min(int(qty), pos["qty"])
        if qty <= 0:
            return None
        fill = round(price * (1 - self.slippage), 4)
        fee = calc_fee("sell", fill, qty)
        proceeds = round(fill * qty - fee, 2)
        pnl = round(proceeds - pos["cost_price"] * qty, 2)
        self.cash = round(self.cash + proceeds, 2)
        self.total_fees = round(self.total_fees + fee, 4)
        pos["qty"] -= qty
        if pos["qty"] <= 0:
            del self.positions[ticker]
        rec = {"ts": ts, "side": "sell", "ticker": ticker, "qty": qty, "price": fill,
               "fee": fee, "pnl": pnl, "reason": reason}
        self.trades.append(rec)
        return rec

    def flatten(self, prices: Dict[str, float], ts: str, reason: str = "flatten"):
        for tk in list(self.positions.keys()):
            px = prices.get(tk)
            if px:
                self.sell(tk, self.positions[tk]["qty"], px, ts, reason)

    # ── 估值 ────────────────────────────────────────────────
    def market_value(self, prices: Dict[str, float]) -> float:
        mv = 0.0
        for tk, pos in self.positions.items():
            px = prices.get(tk) or pos["cost_price"]
            mv += px * pos["qty"]
        return round(mv, 2)

    def equity(self, prices: Dict[str, float]) -> float:
        return round(self.cash + self.market_value(prices), 2)

    def mark(self, ts: str, prices: Dict[str, float]):
        self.equity_curve.append((ts, self.equity(prices)))

    def realized_pnl(self) -> float:
        return round(sum(t.get("pnl", 0.0) for t in self.trades if t["side"] == "sell"), 2)

    def to_dict(self, prices: Optional[Dict[str, float]] = None) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "positions": self.positions,
            "equity": self.equity(prices) if prices else self.cash,
            "realized_pnl": self.realized_pnl(),
            "total_fees": round(self.total_fees, 2),
            "n_trades": len([t for t in self.trades if t["side"] == "buy"]),
            "trades": self.trades,
        }

    def save(self, path: str, prices: Optional[Dict[str, float]] = None):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(prices), f, ensure_ascii=False, indent=2, default=str)
