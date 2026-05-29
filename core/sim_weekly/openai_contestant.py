"""VERSION: openai_duel_v1.1
DEPENDS: core/sim_weekly/duel.py, core/sim_weekly/portfolio.py, data/sim_weekly/openai_adaptive_config.json

OpenAIContestant —— independent SimWeekly duel contestant.
OpenAIContestant —— 独立 SimWeekly 擂台选手。

Research-only: this file does not import Claude contestants, the shared replay
engine, or live trading modules. The duel harness provides only bars, portfolio,
fees, slippage, and scoring.
仅研究：不导入 Claude 选手、共享回放引擎或实盘模块；擂台只提供行情、组合、费率、
滑点和计分。
"""
from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Optional

from .duel import BarContext, Contestant


ENTRY_CUTOFF = time(15, 25)
MIN_WARMUP_BARS = 36
COOLDOWN_BARS = 5
MAX_LOSS_PER_TRADE = 0.11
DEFAULT_ADAPTIVE_CONFIG = {
    "profile": "neutral",
    "hypothesis_id": "base",
    "params": {
        "rklx_fraction": 0.52,
        "rklb_fraction": 0.34,
        "rklx_stop_pct": 0.060,
        "rklb_stop_pct": 0.038,
        "short_fraction": 0.26,
        "short_stop_pct": 0.065,
        "cooldown_bars": COOLDOWN_BARS,
        "long_rsi_max": 76,
        "bull_long_rsi_max": 82,
        "bull_gap_atr": 0.55,
        "bull_week_change": 1.0,
        "avoid_shorts_in_bull": True,
    },
}


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "sim_weekly" / "openai_adaptive_config.json"


def _deepcopy_config() -> dict:
    return json.loads(json.dumps(DEFAULT_ADAPTIVE_CONFIG))


def _load_adaptive_config(path: str | Path | None) -> dict:
    cfg = _deepcopy_config()
    if not path:
        return cfg
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return cfg
    if isinstance(loaded, dict):
        cfg["profile"] = loaded.get("profile") or cfg["profile"]
        cfg["hypothesis_id"] = loaded.get("hypothesis_id") or cfg["hypothesis_id"]
        params = loaded.get("params") or {}
        if isinstance(params, dict):
            cfg["params"].update(params)
    return cfg


def _ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema = values[-period]
    for value in values[-period + 1:]:
        ema = value * k + ema * (1 - k)
    return ema


def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    window = closes[-period - 1:]
    for i in range(1, len(window)):
        delta = window[i] - window[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(bars: list[dict], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs = []
    recent = bars[-period - 1:]
    for i in range(1, len(recent)):
        high = float(recent[i]["high"])
        low = float(recent[i]["low"])
        prev_close = float(recent[i - 1]["close"])
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs) / len(trs) if trs else None


def _vwap(bars: list[dict]) -> Optional[float]:
    pv = vol = 0.0
    for bar in bars:
        volume = float(bar.get("volume", 0) or 0)
        typical = (float(bar["high"]) + float(bar["low"]) + float(bar["close"])) / 3.0
        pv += typical * volume
        vol += volume
    return pv / vol if vol > 0 else (float(bars[-1]["close"]) if bars else None)


class OpenAIContestant(Contestant):
    """OpenAI independent trend/risk contestant. / OpenAI 独立趋势风控选手。"""

    name = "openai_trend_guard_v1"

    def __init__(self, adaptive_config_path: str | Path | None = None):
        self.bar_idx = 0
        self.last_exit_idx = -999
        self.last_exit_dir: Optional[str] = None
        self.week_open = 0.0
        self.peak_equity = 0.0
        self.adaptive_config_path = adaptive_config_path
        self.adaptive_config = _load_adaptive_config(adaptive_config_path)

    def reset(self, capital: float) -> None:
        self.bar_idx = 0
        self.last_exit_idx = -999
        self.last_exit_dir = None
        self.week_open = 0.0
        self.peak_equity = capital
        self.adaptive_config = _load_adaptive_config(self.adaptive_config_path)

    @property
    def _params(self) -> dict:
        return self.adaptive_config.get("params") or DEFAULT_ADAPTIVE_CONFIG["params"]

    @property
    def _profile(self) -> str:
        return str(self.adaptive_config.get("profile") or "neutral")

    def _held_ticker(self, ctx: BarContext) -> Optional[str]:
        return next(iter(ctx.portfolio.positions), None)

    def _held_direction(self, ticker: Optional[str]) -> Optional[str]:
        if not ticker:
            return None
        return "short" if ticker == "RKLZ" else "long"

    def _mark_week_open(self, bars: list[dict]) -> None:
        if not self.week_open and bars:
            self.week_open = float(bars[0]["open"])

    def _signal(self, ctx: BarContext) -> dict:
        rklb = ctx.history["RKLB"] + [ctx.bars_now["RKLB"]]
        self._mark_week_open(rklb)
        if len(rklb) < MIN_WARMUP_BARS or self.week_open <= 0:
            return {"direction": "flat", "ticker": None, "fraction": 0.0, "stop_pct": 0.0, "reason": "warmup"}

        closes = [float(b["close"]) for b in rklb]
        price = closes[-1]
        ema_fast = _ema(closes, 8)
        ema_slow = _ema(closes, 34)
        rsi = _rsi(closes)
        atr = _atr(rklb)
        today = [b for b in rklb if b["time"][:10] == ctx.ts[:10]]
        vwap = _vwap(today)
        if None in (ema_fast, ema_slow, rsi, atr, vwap) or atr <= 0 or price <= 0:
            return {"direction": "flat", "ticker": None, "fraction": 0.0, "stop_pct": 0.0, "reason": "indicators-na"}

        week_change = (price - self.week_open) / self.week_open * 100.0
        gap_atr = abs(ema_fast - ema_slow) / atr
        above_trend = ema_fast > ema_slow and price > vwap
        below_trend = ema_fast < ema_slow and price < vwap

        params = self._params
        bull_profile = self._profile == "bull_ride"
        long_rsi_max = float(params.get("bull_long_rsi_max" if bull_profile else "long_rsi_max", 76))
        strong_gap = float(params.get("bull_gap_atr" if bull_profile else "bull_gap_atr", 0.75))
        strong_week = float(params.get("bull_week_change", 1.0))

        # Long bias needs trend confirmation; bull ride mode tolerates hotter RSI.
        # 多头需要趋势确认；牛市骑乘挡允许更热的 RSI，减少过早下车。
        if above_trend and 47 <= rsi <= long_rsi_max and week_change > -4.0:
            strong = gap_atr >= strong_gap and week_change >= strong_week and price >= self.week_open
            ticker = "RKLX" if strong else "RKLB"
            fraction = float(params.get("rklx_fraction" if strong else "rklb_fraction", 0.52 if strong else 0.34))
            stop_pct = float(params.get("rklx_stop_pct" if ticker == "RKLX" else "rklb_stop_pct", 0.060 if ticker == "RKLX" else 0.038))
            return {
                "direction": "long",
                "ticker": ticker,
                "fraction": fraction,
                "stop_pct": stop_pct,
                "reason": f"{self._profile} trend long rsi{rsi:.0f} week{week_change:+.1f}% gapATR{gap_atr:.1f}",
            }

        # Short bias is deliberately smaller because RKLZ is noisy and costly.
        # 空头仓位刻意更小，因为 RKLZ 噪声和成本都更高。
        if bull_profile and bool(params.get("avoid_shorts_in_bull", True)) and week_change > 0:
            return {"direction": "flat", "ticker": None, "fraction": 0.0, "stop_pct": 0.0, "reason": "bull profile avoids countertrend short"}

        if below_trend and 24 <= rsi <= 55 and week_change <= -1.2 and gap_atr >= 0.35:
            return {
                "direction": "short",
                "ticker": "RKLZ",
                "fraction": float(params.get("short_fraction", 0.26)),
                "stop_pct": float(params.get("short_stop_pct", 0.065)),
                "reason": f"{self._profile} guard short rsi{rsi:.0f} week{week_change:+.1f}% gapATR{gap_atr:.1f}",
            }

        return {"direction": "flat", "ticker": None, "fraction": 0.0, "stop_pct": 0.0, "reason": "no-setup"}

    def _manage_stops(self, ctx: BarContext) -> None:
        for ticker in list(ctx.portfolio.positions.keys()):
            pos = ctx.portfolio.positions[ticker]
            bar = ctx.bars_now.get(ticker)
            if not bar:
                continue
            high = float(bar["high"])
            low = float(bar["low"])
            pos["peak"] = max(pos.get("peak", pos["cost_price"]), high)
            stop_pct = float(pos.get("stop_pct") or 0.05)
            trail = round(pos["peak"] * (1.0 - stop_pct), 4)
            pos["stop"] = trail if pos.get("stop") is None else max(float(pos["stop"]), trail)
            if low <= pos["stop"]:
                ctx.portfolio.sell(ticker, pos["qty"], pos["stop"], ctx.ts, reason="openai trail stop")
                self.last_exit_idx = self.bar_idx
                self.last_exit_dir = self._held_direction(ticker)

    def on_bar(self, ctx: BarContext) -> None:
        self.bar_idx += 1
        prices = {tk: ctx.price(tk) for tk in ("RKLB", "RKLX", "RKLZ")}
        equity = ctx.portfolio.equity(prices)
        self.peak_equity = max(self.peak_equity, equity)

        self._manage_stops(ctx)
        if ctx.is_last_bar:
            return

        signal = self._signal(ctx)
        held_ticker = self._held_ticker(ctx)
        held_dir = self._held_direction(held_ticker)
        target_dir = signal["direction"]

        # Exit only on a real opposite signal; flat/no-setup lets the trail decide.
        # 只有明确反向信号才退出；无信号时交给跟踪止损。
        if held_ticker and target_dir in ("long", "short") and target_dir != held_dir:
            pos = ctx.portfolio.positions[held_ticker]
            ctx.portfolio.sell(held_ticker, pos["qty"], prices.get(held_ticker) or pos["cost_price"],
                               ctx.ts, reason="openai opposite signal")
            self.last_exit_idx = self.bar_idx
            self.last_exit_dir = held_dir
            held_ticker = None

        if held_ticker or target_dir not in ("long", "short"):
            return
        if ctx.et_time.time() >= ENTRY_CUTOFF:
            return
        cooldown = int(self._params.get("cooldown_bars", COOLDOWN_BARS))
        if target_dir == self.last_exit_dir and self.bar_idx - self.last_exit_idx < cooldown:
            return

        ticker = signal["ticker"]
        entry = prices.get(ticker)
        if not ticker or not entry:
            return
        stop_pct = float(signal["stop_pct"])
        derisk = equity <= self.peak_equity * 0.90
        fraction = float(signal["fraction"]) * (0.55 if derisk else 1.0)
        qty_by_budget = int(equity * fraction / entry)
        qty_by_risk = int(equity * MAX_LOSS_PER_TRADE / (entry * stop_pct))
        qty = min(qty_by_budget, qty_by_risk)
        if qty <= 0:
            return
        stop = round(entry * (1.0 - stop_pct), 4)
        ctx.portfolio.buy(ticker, qty, entry, ctx.ts, reason=signal["reason"], stop=stop)
        if ticker in ctx.portfolio.positions:
            ctx.portfolio.positions[ticker]["stop_pct"] = stop_pct
