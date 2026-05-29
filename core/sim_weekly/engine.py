"""SimWeekly 回放引擎 + 周记分卡 —— 自包含,只读历史 1m CSV,不碰任何现有模块。

v1.1: 方向制决策(抗横跳)——同方向内不切工具、不因信念抖动平仓;只在
      方向翻转 / 跟踪止损 才动手;止损后同向冷却。decider 可注入(规则/agent委员会)。
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from . import strategy as strat
from .deciders import RuleDecider
from .portfolio import SimPortfolio

TICKERS = ["RKLB", "RKLX", "RKLZ"]
RTH_START = (9, 30)
RTH_END = (16, 0)

CONV_FRACTION = [(85, 0.75), (70, 0.45), (0, 0.0)]
ENTRY_CONV = 70
MAX_LOSS_PER_TRADE = 0.15
DRAWDOWN_DERISK = 0.35
COOLDOWN_BARS = 3       # 止损后,同方向至少隔 3 根 5m(15min)才再进


def _hist_path(ticker: str) -> str:
    try:
        from config.settings import DATA_DIR
        base = DATA_DIR
    except Exception:
        base = os.path.join(os.getcwd(), "data")
    return os.path.join(base, "historical", f"{ticker}_1m.csv")


def _in_rth(dt: datetime) -> bool:
    return RTH_START <= (dt.hour, dt.minute) < RTH_END


def _load_5m(ticker: str, day_set: set) -> Dict[str, dict]:
    path = _hist_path(ticker)
    buckets: Dict[str, dict] = {}
    if not os.path.exists(path):
        return buckets
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ts = (row.get("time_key") or "").strip()
            if len(ts) < 16 or ts[:10] not in day_set:
                continue
            try:
                dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if not _in_rth(dt):
                continue
            key = dt.replace(minute=(dt.minute // 5) * 5, second=0).strftime("%Y-%m-%d %H:%M:%S")
            try:
                o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
                v = float(row.get("volume", 0) or 0)
            except (TypeError, ValueError):
                continue
            cur = buckets.get(key)
            if not cur:
                buckets[key] = {"time": key, "open": o, "high": h, "low": l, "close": c, "volume": v}
            else:
                cur["high"] = max(cur["high"], h)
                cur["low"] = min(cur["low"], l)
                cur["close"] = c
                cur["volume"] += v
    return buckets


def _week_days(monday: datetime) -> List[str]:
    return [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]


def _target_fraction(conv: int) -> float:
    for thr, frac in CONV_FRACTION:
        if conv >= thr:
            return frac
    return 0.0


def _held_direction(pf: SimPortfolio) -> Optional[str]:
    if not pf.positions:
        return None
    tk = next(iter(pf.positions))
    return "short" if tk == "RKLZ" else "long"


def run_week(monday_str: str, capital: float = 10000.0, decider=None) -> dict:
    decider = decider or RuleDecider()
    monday = datetime.strptime(monday_str, "%Y-%m-%d")
    days = _week_days(monday)
    day_set = set(days)
    bars = {tk: _load_5m(tk, day_set) for tk in TICKERS}
    if not bars["RKLB"]:
        return {"error": f"no RKLB RTH 5m bars for week {monday_str}"}

    timeline = sorted(bars["RKLB"].keys())
    last_px = {tk: None for tk in TICKERS}

    def px_at(tk, ts):
        b = bars[tk].get(ts)
        if b:
            last_px[tk] = b["close"]
        return last_px[tk]

    pf = SimPortfolio(initial_capital=capital)
    rklb_hist: List[dict] = []
    peak_equity = capital
    last_exit_idx = -999
    last_exit_dir: Optional[str] = None

    for i, ts in enumerate(timeline):
        cur_day = ts[:10]
        rklb_hist.append(bars["RKLB"][ts])
        prices = {tk: px_at(tk, ts) for tk in TICKERS}
        if prices["RKLB"] is None:
            continue

        # 1) 跟踪止损
        for tk in list(pf.positions.keys()):
            pos = pf.positions[tk]
            bar = bars[tk].get(ts)
            if not bar:
                continue
            pos["peak"] = max(pos.get("peak", pos["cost_price"]), bar["high"])
            trail = round(pos["peak"] * (1 - pos.get("stop_pct", strat.STOP_PCT.get(tk, 0.04))), 4)
            pos["stop"] = trail if pos.get("stop") is None else max(pos["stop"], trail)
            if bar["low"] <= pos["stop"]:
                pf.sell(tk, pos["qty"], pos["stop"], ts, reason="trail/stop hit")
                last_exit_idx, last_exit_dir = i, ("short" if tk == "RKLZ" else "long")

        # 2) 决策
        today_bars = [b for b in rklb_hist if b["time"][:10] == cur_day]
        target = decider.decide({"rklb_bars": rklb_hist, "rklb_today_bars": today_bars})
        tdir = target.get("direction", "flat")
        held_dir = _held_direction(pf)

        equity = pf.equity(prices)
        peak_equity = max(peak_equity, equity)
        derisk = equity <= peak_equity * (1 - DRAWDOWN_DERISK)

        # 3) 持仓:只在方向翻转才平(让赢家跑;flat 不平,交给跟踪止损)
        if held_dir and tdir != "flat" and tdir != held_dir:
            held_tk = next(iter(pf.positions))
            pf.sell(held_tk, pf.positions[held_tk]["qty"],
                    prices.get(held_tk) or pf.positions[held_tk]["cost_price"], ts, reason="flip exit")
            last_exit_idx, last_exit_dir = i, held_dir
            held_dir = None

        # 4) 空仓 + 有方向 + 信念够 + 过冷却 -> 进场(同向止损后需冷却)
        if held_dir is None and tdir in ("long", "short") and target["conviction"] >= ENTRY_CONV:
            in_cooldown = (tdir == last_exit_dir) and (i - last_exit_idx < COOLDOWN_BARS)
            inst = target["instrument"]
            if not in_cooldown and inst and prices.get(inst):
                entry = prices[inst]
                frac = _target_fraction(target["conviction"]) * (0.5 if derisk else 1.0)
                stop_pct = target["stop_pct"] or 0.04
                if frac > 0:
                    qty = min(int(equity * frac / entry),
                              int(equity * MAX_LOSS_PER_TRADE / (entry * stop_pct)))
                    if qty > 0:
                        pf.buy(inst, qty, entry, ts,
                               reason=f"conv{target['conviction']} {target['reason']}",
                               stop=round(entry * (1 - stop_pct), 4))
                        if inst in pf.positions:
                            pf.positions[inst]["stop_pct"] = stop_pct

        pf.mark(ts, prices)

    last_ts = timeline[-1]
    final_prices = {tk: px_at(tk, last_ts) for tk in TICKERS}
    pf.flatten(final_prices, last_ts, reason="friday close settle")
    pf.mark(last_ts, final_prices)
    sc = _scorecard(pf, bars, timeline, monday_str, capital)
    sc["decider"] = getattr(decider, "name", "rule")
    return sc


def _buy_hold_return(bars, timeline, tk) -> Optional[float]:
    present = [t for t in timeline if t in bars[tk]]
    if not present:
        return None
    o, c = bars[tk][present[0]]["open"], bars[tk][present[-1]]["close"]
    return round((c - o) / o * 100, 2) if o > 0 else None


def _max_drawdown(curve) -> float:
    peak, mdd = -1e18, 0.0
    for _, e in curve:
        peak = max(peak, e)
        if peak > 0:
            mdd = min(mdd, (e - peak) / peak)
    return round(mdd * 100, 2)


def _scorecard(pf, bars, timeline, monday_str, capital) -> dict:
    sells = [t for t in pf.trades if t["side"] == "sell"]
    wins = [t for t in sells if t.get("pnl", 0) > 0]
    final_equity = pf.equity_curve[-1][1] if pf.equity_curve else pf.cash
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = sum(t["pnl"] for t in sells if t.get("pnl", 0) <= 0)
    return {
        "week_start": monday_str, "initial_capital": capital,
        "final_equity": final_equity,
        "return_pct": round((final_equity - capital) / capital * 100, 2),
        "n_trades": len([t for t in pf.trades if t["side"] == "buy"]),
        "n_round_trips": len(sells),
        "win_rate_pct": round(len(wins) / len(sells) * 100, 1) if sells else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(gross_loss / max(1, len(sells) - len(wins)), 2),
        "max_drawdown_pct": _max_drawdown(pf.equity_curve),
        "total_fees": round(pf.total_fees, 2), "realized_pnl": pf.realized_pnl(),
        "benchmark_buyhold_RKLB_pct": _buy_hold_return(bars, timeline, "RKLB"),
        "benchmark_buyhold_RKLX_pct": _buy_hold_return(bars, timeline, "RKLX"),
        "n_5m_bars": len(timeline), "trades": pf.trades,
    }


def format_scorecard(sc: dict) -> str:
    if sc.get("error"):
        return f"[sim_weekly] {sc['error']}"
    return "\n".join([
        f"📒 SimWeekly 记分卡 · 周一 {sc['week_start']}  (纸面 ${sc['initial_capital']:.0f}, decider={sc.get('decider')})",
        f"  期末权益 ${sc['final_equity']:.2f}   周收益 {sc['return_pct']:+.2f}%",
        f"  对照 买入持有 RKLB {sc['benchmark_buyhold_RKLB_pct']:+}%  /  RKLX {sc['benchmark_buyhold_RKLX_pct']:+}%",
        f"  交易 {sc['n_trades']} 笔 / 平 {sc['n_round_trips']} 笔  胜率 {sc['win_rate_pct']}%",
        f"  均盈 ${sc['avg_win']}  均亏 ${sc['avg_loss']}  最大回撤 {sc['max_drawdown_pct']}%",
        f"  手续费 ${sc['total_fees']}  已实现盈亏 ${sc['realized_pnl']}",
    ])
