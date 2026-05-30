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
    "hypothesis_id": "rklx_hold_v1",
    "params": {
        # v1.4 框架(2026-05-31 美元口径回放定稿): 默认 "RKLX 趋势持有, 偏向躺平/收益优先"。
        # 约束: Claude 只交易 RKLX(用 RKLB 判趋势, 买卖 RKLX), 不碰 RKLB/RKLZ。
        # 诊断: 强上行行情里, 主动日内择时(v1.2)赚得远少于躺平(8周$1664 vs 躺平RKLX$14495)。
        # 用户定向: 趋势持有 + 偏躺平。低进场门(早进)+宽出场(几乎不避险)→ 最大化捕获。
        # v1.5 浮盈锁定(2026-05-31, 学 OpenAI 思路自实现): 浮盈达 th_lock_trig → 追踪止损
        #   收紧到 th_lock_tight, 锁住大部分浮盈。A/B 实测 15%/8% 最优(既多赚又不增回撤);
        #   金字塔加仓三档全部拉低收益+增 churn, 弃用。
        # framework="day_trade" 可退回 v1.2 日内拐点过滤。
        "framework": "rklx_hold",
        "th_ema_slow": 40,          # 慢趋势 EMA 周期(根 5m bar)
        "th_enter_dist": 0.0,       # price 高于 EMA_slow >=此% 且多头结构 → 进场买 RKLX
        "th_exit_margin": 0.08,     # price 跌破 EMA_slow*(1-此值) → 趋势明确破, 出场(宽=偏躺平)
        "th_hold_stop": 0.18,       # 持有追踪止损(宽=让趋势跑/逼近躺平)
        "th_lock_trig": 0.15,       # v1.5: 浮盈(现价较成本)达此 → 触发锁定
        "th_lock_tight": 0.08,      # v1.5: 锁定后追踪止损收紧到此(保住浮盈)
        # --- 以下为 day_trade 框架(v1.2)参数, framework="day_trade" 时生效 ---
        "entry_conv": 70,
        "frac_strong": 0.75,        # conv>=85
        "frac_weak": 0.45,          # conv>=70
        "stop_mult": 1.0,           # 乘在 strat.STOP_PCT 上(>1 放宽,让赢家跑/降 churn)
        "cooldown_bars": 3,
        "avoid_shorts_in_bull": False,
        "bull_long_rsi_max": 80,    # bull_ride 容忍更热的 RSI
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

    def reset(self, capital: float) -> None:
        # 每周/每次开跑重读配置 —— 夜间复盘写的调整在此生效(活的自适应)
        self.cfg = _load_adaptive_config(self.adaptive_config_path)
        self.peak_equity = capital
        self.last_exit_idx = -999
        self.last_exit_dir = None
        self.bar_idx = 0

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

    def _rklx_hold_ind(self, ctx):
        """v1.4: 慢趋势 EMA + 多头结构。返回 (price, ema_slow, e9, e21) 或 None。"""
        from . import indicators as ind
        ema_slow = int(self._p.get("th_ema_slow", 40))
        hist = ctx.history["RKLB"] + [ctx.bars_now["RKLB"]]
        if len(hist) < ema_slow:
            return None
        closes = [b["close"] for b in hist]
        e_slow = ind.ema(closes[-ema_slow - 5:], ema_slow)
        e9, e21 = ind.ema(closes[-30:], 9), ind.ema(closes[-30:], 21)
        if None in (e_slow, e9, e21) or e_slow <= 0:
            return None
        return closes[-1], e_slow, e9, e21

    def _on_bar_rklx_hold(self, ctx: BarContext) -> None:
        """v1.4 RKLX 趋势持有(偏躺平): 早进 + 宽出, 几乎不避险, 最大化趋势捕获。
        只交易 RKLX(用 RKLB 判趋势)。"""
        pf = ctx.portfolio
        p = self._p
        exit_margin = float(p.get("th_exit_margin", 0.08))
        hold_stop = float(p.get("th_hold_stop", 0.18))
        enter_dist = float(p.get("th_enter_dist", 0.0))
        held = next(iter(pf.positions)) if pf.positions else None
        info = self._rklx_hold_ind(ctx)

        # 持仓中: 仅 趋势明确破(price < EMA_slow*(1-exit_margin)) 或 追踪止损 才退
        if held:
            pos = pf.positions[held]
            bar = ctx.bars_now.get(held)
            if bar:
                pos["peak"] = max(pos.get("peak", pos["cost_price"]), bar["high"])
                # v1.5 浮盈锁定: 浮盈达 lock_trig → 追踪止损收紧, 保住大部分浮盈
                stop_pct = hold_stop
                lock_trig = p.get("th_lock_trig")
                if lock_trig is not None and pos["cost_price"] > 0:
                    gain = (bar["high"] - pos["cost_price"]) / pos["cost_price"]
                    if gain >= float(lock_trig):
                        stop_pct = float(p.get("th_lock_tight", hold_stop))
                trail = round(pos["peak"] * (1 - stop_pct), 4)
                pos["stop"] = trail if pos.get("stop") is None else max(pos["stop"], trail)
                broke = info is not None and info[0] < info[1] * (1 - exit_margin)
                if bar["low"] <= pos["stop"] or broke or ctx.is_last_bar:
                    px = pos["stop"] if bar["low"] <= pos["stop"] else (ctx.price(held) or pos["cost_price"])
                    pf.sell(held, pos["qty"], px, ctx.ts,
                            reason="hold trail stop" if bar["low"] <= pos["stop"] else "trend broke")
            return

        # 空仓: 多头结构 且 price 高于 EMA_slow 达 enter_dist% → 满仓买 RKLX
        if not ctx.is_last_bar and info is not None:
            cur, e_slow, e9, e21 = info
            dist = (cur - e_slow) / e_slow * 100
            if e9 > e21 and dist >= enter_dist:
                px = ctx.price("RKLX")
                if px:
                    qty = int(pf.cash / (px * 1.001))
                    if qty > 0:
                        pf.buy("RKLX", qty, px, ctx.ts, reason="rklx trend hold",
                               stop=round(px * (1 - hold_stop), 4))
                        if "RKLX" in pf.positions:
                            pf.positions["RKLX"]["stop_pct"] = hold_stop

    def on_bar(self, ctx: BarContext) -> None:
        self.bar_idx += 1
        # v1.4: 默认 RKLX 趋势持有框架; framework="day_trade" 退回 v1.2 日内
        if str(self._p.get("framework", "rklx_hold")) == "rklx_hold":
            self._on_bar_rklx_hold(ctx)
            return

        pf = ctx.portfolio
        prices = {tk: ctx.price(tk) for tk in ("RKLB", "RKLX", "RKLZ")}

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
