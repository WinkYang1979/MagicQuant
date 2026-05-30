"""PK 选手实现。

ClaudeRuleContestant —— 我方参赛策略:5m EMA/VWAP/RSI 方向 + 信念定仓 + ATR 跟踪止损 +
  抗横跳(同向不切、只翻转/止损动手)+ 强趋势放宽止损 + 回撤降挡。完整自带风险管理。
BuyHoldContestant —— 中立基准线(买入持有 RKLB / RKLX),作为擂台参照系。

OpenAI 的选手应在独立文件里实现 duel.Contestant 接口,无需 import 本文件。
"""
from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Optional

from . import strategy as strat
from .duel import Contestant, BarContext

ENTRY_CONV = 70
CONV_FRACTION = [(85, 0.75), (70, 0.45), (0, 0.0)]
MAX_LOSS_PER_TRADE = 0.15
DRAWDOWN_DERISK = 0.35
COOLDOWN_BARS = 3
ENTRY_CUTOFF = time(15, 30)   # 收盘前 30 分钟不再开新仓

# 夜间自适应配置(与 OpenAI 侧对称):每晚复盘脚本写,选手 reset 时读。
# profile=neutral 即当前默认行为;bull_ride 放宽止损/加仓/降 churn/牛市避空。
DEFAULT_ADAPTIVE_CONFIG = {
    "profile": "neutral",
    "hypothesis_id": "neutral_v1",
    "params": {
        "entry_conv": 70,
        "frac_strong": 0.75,        # conv>=85
        "frac_weak": 0.45,          # conv>=70
        "stop_mult": 1.0,           # 乘在 strat.STOP_PCT 上(>1 放宽,让赢家跑/降 churn)
        "cooldown_bars": 3,
        "avoid_shorts_in_bull": False,
        "bull_long_rsi_max": 80,    # bull_ride 容忍更热的 RSI
        # v1.3 regime-持有挡(2026-05-30 回放定稿,跨11周冻结集+近期):
        # 当周 RKLB 累计涨幅 >= regime_week_pct 且 EMA 多头排列 → 转"持有挡":
        # 满仓骑 regime_ride 标的、只用宽追踪止损,不做日内频繁进出(吃 beta/降 churn)。
        # 回放: 均收益 +0.91%→+4.30%、风调 0.21→0.37、去掉最好一周 +0.35%→+3.45%、
        # churn 124→39,最差周 -7.05% 不变。否则退回日内择时(v1.2 拐点过滤)。
        "regime_hold": True,
        "regime_week_pct": 3.0,     # 当周累计涨幅触发持有挡的阈值(%)
        "regime_hold_stop": 0.12,   # 持有挡宽追踪止损(让趋势跑,回撤 12% 才出)
        "regime_ride": "RKLB",      # 持有挡骑的标的(RKLB 稳/RKLX 2x激进但回撤大)
    },
}


def _config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "sim_weekly" / "claude_adaptive_config.json"


def _load_adaptive_config(path=None) -> dict:
    p = Path(path) if path else _config_path()
    try:
        loaded = json.loads(p.read_text(encoding="utf-8"))
        cfg = json.loads(json.dumps(DEFAULT_ADAPTIVE_CONFIG))
        cfg.update({k: v for k, v in loaded.items() if k != "params"})
        cfg["params"].update(loaded.get("params") or {})
        return cfg
    except Exception:
        return json.loads(json.dumps(DEFAULT_ADAPTIVE_CONFIG))


def _target_fraction(conv: int, frac_strong: float = 0.75, frac_weak: float = 0.45) -> float:
    if conv >= 85:
        return frac_strong
    if conv >= 70:
        return frac_weak
    return 0.0


class BuyHoldContestant(Contestant):
    """买入持有基准:第一根可交易 bar 全仓买入,持到周五收盘(harness 强平)。"""
    def __init__(self, ticker: str = "RKLB"):
        self.name = f"buyhold_{ticker}"
        self.ticker = ticker
        self._bought = False

    def reset(self, capital: float) -> None:
        self._bought = False

    def on_bar(self, ctx: BarContext) -> None:
        if self._bought:
            return
        px = ctx.price(self.ticker)
        if not px:
            return
        qty = int(ctx.portfolio.cash / (px * 1.001))
        if qty > 0:
            ctx.portfolio.buy(self.ticker, qty, px, ctx.ts, reason="buy&hold")
            self._bought = True


class ClaudeRuleContestant(Contestant):
    """我方策略,完整自带方向/仓位/止损/风控。"""
    name = "claude_rule"

    def __init__(self, adaptive_config_path=None):
        self.adaptive_config_path = adaptive_config_path
        self.cfg = _load_adaptive_config(adaptive_config_path)
        self.peak_equity = 0.0
        self.last_exit_idx = -999
        self.last_exit_dir: Optional[str] = None
        self.bar_idx = 0
        self._week_open = None      # v1.3 regime-持有挡: 本周首根 RKLB 收盘价

    def reset(self, capital: float) -> None:
        # 每周/每次开跑重读配置 —— 夜间复盘写的调整在此生效(活的自适应)
        self.cfg = _load_adaptive_config(self.adaptive_config_path)
        self.peak_equity = capital
        self.last_exit_idx = -999
        self.last_exit_dir = None
        self.bar_idx = 0
        self._week_open = None

    def _strong_uptrend(self, ctx) -> bool:
        """v1.3: 当周 RKLB 累计涨幅达标 + EMA 多头排列 + 价在 e9 上 → 强上行。"""
        from . import indicators as ind
        hist = ctx.history["RKLB"] + [ctx.bars_now["RKLB"]]
        if len(hist) < 25:
            return False
        if self._week_open is None:
            self._week_open = hist[0]["close"]
        cur = hist[-1]["close"]
        if not self._week_open:
            return False
        week_chg = (cur - self._week_open) / self._week_open * 100
        closes = [b["close"] for b in hist]
        e9, e21 = ind.ema(closes[-30:], 9), ind.ema(closes[-30:], 21)
        if e9 is None or e21 is None:
            return False
        return (week_chg >= float(self._p.get("regime_week_pct", 3.0))
                and e9 > e21 and cur >= e9)

    @property
    def _p(self) -> dict:
        return self.cfg.get("params") or DEFAULT_ADAPTIVE_CONFIG["params"]

    @property
    def _bull(self) -> bool:
        return str(self.cfg.get("profile") or "neutral") == "bull_ride"

    def _held(self, pf):
        if not pf.positions:
            return None
        tk = next(iter(pf.positions))
        return "short" if tk == "RKLZ" else "long"

    def on_bar(self, ctx: BarContext) -> None:
        self.bar_idx += 1
        pf = ctx.portfolio
        prices = {tk: ctx.price(tk) for tk in ("RKLB", "RKLX", "RKLZ")}

        # 0) v1.3 regime-持有挡: 强上行周 → 满仓骑趋势 + 宽追踪止损,不做日内进出
        p0 = self._p
        if p0.get("regime_hold") and not ctx.is_last_bar and self._strong_uptrend(ctx):
            ride = p0.get("regime_ride", "RKLB")
            hold_stop = float(p0.get("regime_hold_stop", 0.12))
            px = ctx.price(ride)
            held_tk = next(iter(pf.positions)) if pf.positions else None
            # 持有非 ride 标的(如日内 RKLZ 空头)→ 先平,转入趋势骑乘
            if held_tk and held_tk != ride:
                pf.sell(held_tk, pf.positions[held_tk]["qty"],
                        ctx.price(held_tk) or pf.positions[held_tk]["cost_price"],
                        ctx.ts, reason="regime flip to hold")
                held_tk = None
            if held_tk is None and px:
                qty = int(pf.cash / (px * 1.001))
                if qty > 0:
                    pf.buy(ride, qty, px, ctx.ts, reason=f"regime hold ride {ride}",
                           stop=round(px * (1 - hold_stop), 4))
                    if ride in pf.positions:
                        pf.positions[ride]["stop_pct"] = hold_stop
            # 宽追踪止损(让趋势跑,回撤才出)
            for tk in list(pf.positions.keys()):
                pos = pf.positions[tk]; bar = ctx.bars_now.get(tk)
                if not bar:
                    continue
                pos["peak"] = max(pos.get("peak", pos["cost_price"]), bar["high"])
                trail = round(pos["peak"] * (1 - hold_stop), 4)
                pos["stop"] = trail if pos.get("stop") is None else max(pos["stop"], trail)
                if bar["low"] <= pos["stop"]:
                    pf.sell(tk, pos["qty"], pos["stop"], ctx.ts, reason="hold trail stop")
            return

        # 1) 跟踪止损(用本根 bar 的 low 判穿)
        for tk in list(pf.positions.keys()):
            pos = pf.positions[tk]
            bar = ctx.bars_now.get(tk)
            if not bar:
                continue
            pos["peak"] = max(pos.get("peak", pos["cost_price"]), bar["high"])
            stop_pct = pos.get("stop_pct", strat.STOP_PCT.get(tk, 0.04))
            trail = round(pos["peak"] * (1 - stop_pct), 4)  # stop_pct 已含 profile 放宽
            pos["stop"] = trail if pos.get("stop") is None else max(pos["stop"], trail)
            if bar["low"] <= pos["stop"]:
                pf.sell(tk, pos["qty"], pos["stop"], ctx.ts, reason="trail/stop hit")
                self.last_exit_idx, self.last_exit_dir = self.bar_idx, ("short" if tk == "RKLZ" else "long")

        if ctx.is_last_bar:
            return  # 最后一根交给 harness 强平,不再开仓

        # 2) 方向决策(全周历史做 EMA/RSI/ATR,当日做 VWAP)
        rklb_hist = ctx.history["RKLB"] + [ctx.bars_now["RKLB"]]
        cur_day = ctx.ts[:10]
        today = [b for b in rklb_hist if b["time"][:10] == cur_day]
        target = strat.decide({"rklb_bars": rklb_hist, "rklb_today_bars": today})
        tdir = target.get("direction", "flat")
        p = self._p

        # bull_ride: 牛市避免反向做空(不买 RKLZ),把赌注让给趋势
        if self._bull and p.get("avoid_shorts_in_bull") and tdir == "short":
            tdir = "flat"
        held = self._held(pf)

        equity = pf.equity(prices)
        self.peak_equity = max(self.peak_equity, equity)
        derisk = equity <= self.peak_equity * (1 - DRAWDOWN_DERISK)

        # 3) 方向翻转才平(让赢家跑;flat 不平,交给跟踪止损)
        if held and tdir != "flat" and tdir != held:
            tk = next(iter(pf.positions))
            pf.sell(tk, pf.positions[tk]["qty"], prices.get(tk) or pf.positions[tk]["cost_price"],
                    ctx.ts, reason="flip exit")
            self.last_exit_idx, self.last_exit_dir = self.bar_idx, held
            held = None

        # 4) 空仓 + 有方向 + 信念够 + 过冷却 + 未到截止 → 进场
        entry_conv = int(p.get("entry_conv", ENTRY_CONV))
        cooldown = int(p.get("cooldown_bars", COOLDOWN_BARS))
        if held is None and tdir in ("long", "short") and target["conviction"] >= entry_conv:
            if ctx.et_time.time() >= ENTRY_CUTOFF:
                return
            in_cooldown = (tdir == self.last_exit_dir) and (self.bar_idx - self.last_exit_idx < cooldown)
            inst = target["instrument"]
            if not in_cooldown and inst and prices.get(inst):
                entry = prices[inst]
                frac = _target_fraction(target["conviction"], p.get("frac_strong", 0.75),
                                        p.get("frac_weak", 0.45)) * (0.5 if derisk else 1.0)
                # profile 放宽止损(bull_ride: stop_mult>1 → 让赢家跑、降 churn)
                stop_pct = (target["stop_pct"] or 0.04) * float(p.get("stop_mult", 1.0))
                if frac > 0:
                    qty = min(int(equity * frac / entry),
                              int(equity * MAX_LOSS_PER_TRADE / (entry * stop_pct)))
                    if qty > 0:
                        pf.buy(inst, qty, entry, ctx.ts,
                               reason=f"conv{target['conviction']} {target['reason']}",
                               stop=round(entry * (1 - stop_pct), 4))
                        if inst in pf.positions:
                            pf.positions[inst]["stop_pct"] = stop_pct
