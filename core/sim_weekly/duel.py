"""SimWeekly Duel —— 公平 PK 擂台。

设计原则(决定 PK 是否算数):
  共享(中立、不可被任一选手操纵):
    - 同一份 1m→5m bar 数据
    - 同一手续费模型(fees.calc_fee)
    - 同一滑点(SimPortfolio.slippage)
    - 同一时间窗(周一开盘→周五收盘,RTH)
    - 同一起始资金 $10,000
    - 同一中立计分器(score 从成交流水算,选手不能自报分数)
  选手各自拥有(才叫"独立一套策略"):
    - 信号/择时、仓位大小、止损/止盈、选哪只工具(RKLB/RKLX/RKLZ)、加减仓
每个选手实现 Contestant 接口,harness 只喂数据 + 提供共享 portfolio + 计分。
完全离线、确定性、可复现;不 import core/focus 或 core/agents。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from .engine import _load_5m, _week_days, TICKERS, RTH_END
from .portfolio import SimPortfolio

CAPITAL = 10000.0


# ════════════════════════════════════════════════════════════════
#  选手接口
# ════════════════════════════════════════════════════════════════
class Contestant:
    """PK 选手基类。子类至少实现 on_bar()。

    每根已收线的 5m bar 调一次 on_bar(ctx),选手用 ctx.portfolio 自由下单。
    止损必须由选手自己在 on_bar 里用 ctx.bars_now 的 high/low 判定并平仓——
    harness 不替任何人管风险(这正是"独立策略"的含义)。
    """
    name: str = "base"

    def reset(self, capital: float) -> None:
        """新的一周开始(可选重置内部状态)。"""

    def on_bar(self, ctx: "BarContext") -> None:
        raise NotImplementedError


class BarContext:
    __slots__ = ("et_time", "ts", "bars_now", "history", "portfolio", "is_last_bar")

    def __init__(self, et_time, ts, bars_now, history, portfolio, is_last_bar):
        self.et_time = et_time          # datetime(本地无时区,代表 ET wall-clock)
        self.ts = ts                    # "YYYY-MM-DD HH:MM:SS"
        self.bars_now = bars_now        # {ticker: {open,high,low,close,volume}} 当前 5m bar
        self.history = history          # {ticker: [已收线 bar, ...]} 本周截至上一根
        self.portfolio = portfolio      # 选手自己的 SimPortfolio(共享手续费/滑点)
        self.is_last_bar = is_last_bar  # 周五最后一根(harness 之后会强平结算)

    def price(self, ticker: str) -> Optional[float]:
        b = self.bars_now.get(ticker)
        return float(b["close"]) if b else None


# ════════════════════════════════════════════════════════════════
#  单周 harness(中立)
# ════════════════════════════════════════════════════════════════
def run_week(contestant: Contestant, monday_str: str, capital: float = CAPITAL,
             slippage: float = 0.0006) -> dict:
    monday = datetime.strptime(monday_str, "%Y-%m-%d")
    day_set = set(_week_days(monday))
    bars = {tk: _load_5m(tk, day_set) for tk in TICKERS}
    if not bars["RKLB"]:
        return {"error": f"no RKLB RTH 5m bars for week {monday_str}"}

    timeline = sorted(bars["RKLB"].keys())
    pf = SimPortfolio(initial_capital=capital, slippage=slippage)
    contestant.reset(capital)

    history: Dict[str, List[dict]] = {tk: [] for tk in TICKERS}
    last_px = {tk: None for tk in TICKERS}
    week_open_rklb = bars["RKLB"][timeline[0]]["open"]

    for i, ts in enumerate(timeline):
        bars_now = {}
        for tk in TICKERS:
            b = bars[tk].get(ts)
            if b:
                last_px[tk] = b["close"]
                bars_now[tk] = b
        if "RKLB" not in bars_now:
            continue
        et_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        ctx = BarContext(et_time, ts, bars_now, history, pf, is_last_bar=(i == len(timeline) - 1))
        try:
            contestant.on_bar(ctx)
        except Exception as e:
            # 选手自己的 bug 不该让整场 PK 崩;记一笔并继续。
            pf.trades.append({"ts": ts, "side": "error", "ticker": "", "qty": 0,
                              "price": 0, "fee": 0, "reason": f"contestant error: {e}"})
        # 推进 history(本根收线后并入)
        for tk, b in bars_now.items():
            history[tk].append(b)
        pf.mark(ts, {tk: last_px[tk] for tk in TICKERS})

    # 周五收盘强制结算(中立,所有选手一致)
    last_ts = timeline[-1]
    final_prices = {tk: last_px[tk] for tk in TICKERS if last_px[tk]}
    pf.flatten(final_prices, last_ts, reason="friday close settle")
    pf.mark(last_ts, final_prices)
    return _score(contestant.name, pf, bars, timeline, monday_str, capital, week_open_rklb)


# ════════════════════════════════════════════════════════════════
#  中立计分器(从成交流水算,选手无法操纵)
# ════════════════════════════════════════════════════════════════
def _bh_return(open_px, close_px) -> Optional[float]:
    return round((close_px - open_px) / open_px * 100, 2) if open_px else None


def _max_drawdown(curve) -> float:
    peak, mdd = -1e18, 0.0
    for _, e in curve:
        peak = max(peak, e)
        if peak > 0:
            mdd = min(mdd, (e - peak) / peak)
    return round(mdd * 100, 2)


def _score(name, pf, bars, timeline, monday_str, capital, week_open_rklb) -> dict:
    sells = [t for t in pf.trades if t.get("side") == "sell"]
    wins = [t for t in sells if t.get("pnl", 0) > 0]
    final_equity = pf.equity_curve[-1][1] if pf.equity_curve else pf.cash
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = sum(t["pnl"] for t in sells if t.get("pnl", 0) <= 0)
    rklb_close = bars["RKLB"][timeline[-1]]["close"]
    rklx_present = [t for t in timeline if t in bars["RKLX"]]
    rklx_bh = None
    if rklx_present:
        rklx_bh = _bh_return(bars["RKLX"][rklx_present[0]]["open"], bars["RKLX"][rklx_present[-1]]["close"])
    return {
        "contestant": name,
        "week_start": monday_str,
        "final_equity": final_equity,
        "return_pct": round((final_equity - capital) / capital * 100, 2),
        "n_trades": len([t for t in pf.trades if t.get("side") == "buy"]),
        "n_round_trips": len(sells),
        "win_rate_pct": round(len(wins) / len(sells) * 100, 1) if sells else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(gross_loss / max(1, len(sells) - len(wins)), 2),
        "profit_factor": round(gross_win / abs(gross_loss), 3) if gross_loss < 0 else None,
        "max_drawdown_pct": _max_drawdown(pf.equity_curve),
        "total_fees": round(pf.total_fees, 2),
        "benchmark_buyhold_RKLB_pct": _bh_return(week_open_rklb, rklb_close),
        "benchmark_buyhold_RKLX_pct": rklx_bh,
        "errors": len([t for t in pf.trades if t.get("side") == "error"]),
        "trades": pf.trades,
    }


# ════════════════════════════════════════════════════════════════
#  多周 PK
# ════════════════════════════════════════════════════════════════
def run_duel(contestant_factories: Dict[str, Callable[[], Contestant]],
             weeks: List[str], capital: float = CAPITAL) -> dict:
    """contestant_factories: {name: () -> Contestant}(每周用工厂造新实例,状态不串周)。"""
    results: Dict[str, List[dict]] = {name: [] for name in contestant_factories}
    for wk in weeks:
        for name, factory in contestant_factories.items():
            sc = run_week(factory(), wk, capital)
            if not sc.get("error"):
                results[name].append(sc)
    return _aggregate(results)


def _aggregate(results: Dict[str, List[dict]]) -> dict:
    agg = {}
    for name, rows in results.items():
        if not rows:
            agg[name] = {"weeks": 0}
            continue
        rets = [r["return_pct"] for r in rows]
        beat = sum(1 for r in rows if r["return_pct"] > (r["benchmark_buyhold_RKLB_pct"] or 0))
        agg[name] = {
            "weeks": len(rows),
            "avg_return_pct": round(sum(rets) / len(rets), 2),
            "median_return_pct": round(sorted(rets)[len(rets) // 2], 2),
            "worst_week_pct": round(min(rets), 2),
            "best_week_pct": round(max(rets), 2),
            "positive_weeks": sum(1 for r in rets if r > 0),
            "beat_buyhold_weeks": beat,
            "total_trades": sum(r["n_trades"] for r in rows),
            "avg_max_dd_pct": round(sum(r["max_drawdown_pct"] for r in rows) / len(rows), 2),
            "by_week": {r["week_start"]: r["return_pct"] for r in rows},
        }
    return {"per_contestant": agg, "raw": results}
