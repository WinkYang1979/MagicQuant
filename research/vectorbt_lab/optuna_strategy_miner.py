"""
MagicQuant optuna_strategy_miner.py
VERSION : v0.1.3
DEPENDS : pandas, optuna(optional), research.vectorbt_lab.breakout_core, research.vectorbt_lab._tg_notify(optional)

Offline strategy miner for RKLB -> RKLX/RKLZ paper trading.
离线策略搜索器：用 RKLB 生成信号，用 RKLX/RKLZ 做纸面表达。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from breakout_core import moomoo_roundtrip_fee


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1]
HIST_DIR = PROJECT_ROOT / "data" / "historical"
OUT_DIR = BASE_DIR / "output" / "strategy_miner"
ET = ZoneInfo("America/New_York")

INIT_CASH = 10000.0
SLIPPAGE_BPS = 8.0
TRAIN_DAYS = 40
TEST_DAYS = 10
HOLDOUT_DAYS = 20
MIN_TEST_TRADES = 6


@dataclass
class StrategySpec:
    name: str
    params: dict
    score: float = 0.0
    train_summary: dict = field(default_factory=dict)
    walk_summary: dict = field(default_factory=dict)
    trades: list[dict] = field(default_factory=list)


def _load_optuna():
    try:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        return optuna
    except Exception:
        return None


def _load_csv_symbol(symbol: str) -> pd.DataFrame:
    path = HIST_DIR / f"{symbol.upper()}_1m.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing historical data: {path}")
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["time_key"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    frame["timestamp"] = frame["timestamp"].dt.tz_localize(ET)
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    return frame[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp").drop_duplicates("timestamp")


def _resample_5m(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    df = frame.set_index("timestamp")
    out = df.resample("5min", label="right", closed="right").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"])
    out["symbol"] = symbol
    out = out.reset_index()
    et = out["timestamp"].dt.tz_convert(ET)
    out["et_date"] = et.dt.date
    out["minute"] = et.dt.hour * 60 + et.dt.minute
    return out


def _prepare_master(frame: pd.DataFrame) -> pd.DataFrame:
    bars = frame.copy().reset_index(drop=True)
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    vol = bars["volume"].clip(lower=0)
    pv = typical * vol
    vol_cum = vol.groupby(bars["et_date"]).cumsum()
    pv_cum = pv.groupby(bars["et_date"]).cumsum()
    bars["vwap"] = (pv_cum / vol_cum.where(vol_cum != 0)).ffill().fillna(bars["close"])
    prev_close = bars["close"].shift(1)
    tr = pd.concat([
        bars["high"] - bars["low"],
        (bars["high"] - prev_close).abs(),
        (bars["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    bars["atr"] = tr.rolling(14, min_periods=5).mean().bfill()
    bars["atr_pct"] = (bars["atr"] / bars["close"] * 100.0).fillna(0)
    bars["ema8"] = bars["close"].ewm(span=8, adjust=False).mean()
    bars["ema20"] = bars["close"].ewm(span=20, adjust=False).mean()
    bars["ema34"] = bars["close"].ewm(span=34, adjust=False).mean()
    delta = bars["close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=5).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=5).mean()
    rs = gain / loss.where(loss != 0)
    bars["rsi"] = (100 - 100 / (1 + rs)).fillna(50)
    bars["vol_ma20"] = bars["volume"].shift(1).rolling(20, min_periods=5).mean().fillna(0)
    bars["roll_high"] = bars["high"].shift(1).rolling(20, min_periods=5).max()
    bars["roll_low"] = bars["low"].shift(1).rolling(20, min_periods=5).min()
    bars["day_open"] = bars.groupby("et_date")["open"].transform("first")
    bars["day_high_sofar"] = bars.groupby("et_date")["high"].cummax()
    bars["day_low_sofar"] = bars.groupby("et_date")["low"].cummin()
    bars["move3"] = bars["close"].pct_change(3) * 100.0
    bars["move6"] = bars["close"].pct_change(6) * 100.0
    bars["dist_vwap"] = (bars["close"] - bars["vwap"]) / bars["vwap"] * 100.0
    bars["day_chg"] = (bars["close"] - bars["day_open"]) / bars["day_open"] * 100.0
    return bars


def load_market() -> pd.DataFrame:
    rklb = _prepare_master(_resample_5m(_load_csv_symbol("RKLB"), "RKLB"))
    rklx = _resample_5m(_load_csv_symbol("RKLX"), "RKLX")[["timestamp", "open", "high", "low", "close"]].add_prefix("rklx_")
    rklz = _resample_5m(_load_csv_symbol("RKLZ"), "RKLZ")[["timestamp", "open", "high", "low", "close"]].add_prefix("rklz_")
    rklx = rklx.rename(columns={"rklx_timestamp": "timestamp"})
    rklz = rklz.rename(columns={"rklz_timestamp": "timestamp"})
    merged = rklb.merge(rklx, on="timestamp", how="left").merge(rklz, on="timestamp", how="left")
    merged = merged.dropna(subset=["rklx_close", "rklz_close"]).reset_index(drop=True)
    return merged


def date_splits(bars: pd.DataFrame, max_windows: int | None = None) -> list[tuple[set, set]]:
    days = list(bars["et_date"].drop_duplicates())
    splits = []
    step = TEST_DAYS
    idx = 0
    while idx + TRAIN_DAYS + TEST_DAYS <= len(days):
        train = set(days[idx: idx + TRAIN_DAYS])
        test = set(days[idx + TRAIN_DAYS: idx + TRAIN_DAYS + TEST_DAYS])
        splits.append((train, test))
        idx += step
    if max_windows:
        splits = splits[-max_windows:]
    return splits


def train_holdout_split(bars: pd.DataFrame, holdout_days: int = HOLDOUT_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split latest trading days as holdout. / 将最近交易日切成留出验证集。"""
    days = list(bars["et_date"].drop_duplicates())
    if holdout_days <= 0 or len(days) <= holdout_days:
        return bars.copy().reset_index(drop=True), bars.iloc[0:0].copy().reset_index(drop=True)
    holdout_set = set(days[-holdout_days:])
    train = bars[~bars["et_date"].isin(holdout_set)].reset_index(drop=True)
    holdout = bars[bars["et_date"].isin(holdout_set)].reset_index(drop=True)
    return train, holdout


def _hold_minutes(entry_ts, exit_ts) -> float:
    """Holding time in minutes. / 持仓分钟数。"""
    try:
        return round((pd.Timestamp(exit_ts) - pd.Timestamp(entry_ts)).total_seconds() / 60.0, 2)
    except Exception:
        return 0.0


def signal_breakout(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    sig = pd.DataFrame(index=bars.index)
    vol_ok = bars["volume"] >= bars["vol_ma20"] * p["volume_multiplier"]
    long = (
        bars["minute"].between(570, 720)
        & (bars["close"] > bars["roll_high"] * (1 + p["breakout_pct"] / 100))
        & (bars["close"] > bars["vwap"])
        & (bars["atr_pct"] >= p["atr_min"])
        & vol_ok
    )
    short = (
        bars["minute"].between(570, 720)
        & (bars["close"] < bars["roll_low"] * (1 - p["breakout_pct"] / 100))
        & (bars["close"] < bars["vwap"])
        & (bars["atr_pct"] >= p["atr_min"])
        & vol_ok
    )
    sig["direction"] = 0
    sig.loc[long, "direction"] = 1
    sig.loc[short, "direction"] = -1
    return sig


def signal_vwap_reclaim(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    sig = pd.DataFrame(index=bars.index)
    prior_below = bars["close"].shift(1) < bars["vwap"].shift(1) * (1 - p["vwap_gap"] / 100)
    reclaim = bars["close"] > bars["vwap"] * (1 + p["confirm_pct"] / 100)
    long = bars["minute"].between(570, 780) & prior_below & reclaim & bars["rsi"].between(p["rsi_min"], p["rsi_max"])
    prior_above = bars["close"].shift(1) > bars["vwap"].shift(1) * (1 + p["vwap_gap"] / 100)
    lose = bars["close"] < bars["vwap"] * (1 - p["confirm_pct"] / 100)
    short = bars["minute"].between(570, 780) & prior_above & lose & bars["rsi"].between(100 - p["rsi_max"], 100 - p["rsi_min"])
    sig["direction"] = 0
    sig.loc[long, "direction"] = 1
    sig.loc[short, "direction"] = -1
    return sig


def signal_crash_rebound(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    sig = pd.DataFrame(index=bars.index)
    rebound_from_low = (bars["close"] - bars["day_low_sofar"]) / bars["day_low_sofar"] * 100.0
    long = (
        bars["minute"].between(570, 840)
        & (bars["day_chg"] <= -p["drop_pct"])
        & (rebound_from_low >= p["rebound_pct"])
        & (bars["move3"] > p["move3_min"])
        & bars["rsi"].between(p["rsi_min"], p["rsi_max"])
    )
    fade_from_high = (bars["day_high_sofar"] - bars["close"]) / bars["day_high_sofar"] * 100.0
    short = (
        bars["minute"].between(570, 840)
        & (bars["day_chg"] >= p["surge_pct"])
        & (fade_from_high >= p["rebound_pct"])
        & (bars["move3"] < -p["move3_min"])
        & bars["rsi"].between(100 - p["rsi_max"], 100 - p["rsi_min"])
    )
    sig["direction"] = 0
    sig.loc[long, "direction"] = 1
    sig.loc[short, "direction"] = -1
    return sig


def signal_trend_follow(bars: pd.DataFrame, p: dict) -> pd.DataFrame:
    sig = pd.DataFrame(index=bars.index)
    gap_atr = (bars["ema8"] - bars["ema20"]).abs() / bars["atr"].where(bars["atr"] != 0)
    long = (
        bars["minute"].between(570, 900)
        & (bars["ema8"] > bars["ema20"])
        & (bars["close"] > bars["vwap"])
        & (gap_atr >= p["gap_atr"])
        & (bars["rsi"].between(p["rsi_long_min"], p["rsi_long_max"]))
    )
    short = (
        bars["minute"].between(570, 900)
        & (bars["ema8"] < bars["ema20"])
        & (bars["close"] < bars["vwap"])
        & (gap_atr >= p["gap_atr"])
        & (bars["rsi"].between(p["rsi_short_min"], p["rsi_short_max"]))
    )
    sig["direction"] = 0
    sig.loc[long, "direction"] = 1
    sig.loc[short, "direction"] = -1
    return sig


SIGNAL_FUNCS: dict[str, Callable[[pd.DataFrame, dict], pd.DataFrame]] = {
    "breakout": signal_breakout,
    "vwap_reclaim": signal_vwap_reclaim,
    "crash_rebound": signal_crash_rebound,
    "trend_follow": signal_trend_follow,
}


def _apply_cooldown(raw: pd.Series, timestamps: pd.Series, cooldown_bars: int) -> pd.Series:
    out = []
    last_idx = -10_000
    for idx, val in enumerate(raw.tolist()):
        if val == 0:
            out.append(0)
            continue
        if idx - last_idx >= cooldown_bars:
            out.append(int(val))
            last_idx = idx
        else:
            out.append(0)
    return pd.Series(out, index=raw.index)


def simulate(bars: pd.DataFrame, strategy_name: str, params: dict, trade_value: float = 9500.0) -> tuple[dict, list[dict]]:
    signal = SIGNAL_FUNCS[strategy_name](bars, params)["direction"].fillna(0).astype(int)
    signal = _apply_cooldown(signal, bars["timestamp"], int(params.get("cooldown_bars", 4)))
    cash = INIT_CASH
    equity = INIT_CASH
    peak = INIT_CASH
    max_dd = 0.0
    position = None
    trades = []
    for idx, row in bars.iterrows():
        if position is not None:
            side = position["direction"]
            tool = position["tool"]
            low = float(row[f"{tool.lower()}_low"])
            high = float(row[f"{tool.lower()}_high"])
            close = float(row[f"{tool.lower()}_close"])
            qty = position["qty"]
            held = idx - position["entry_idx"]
            adverse_pct = (low - position["entry_price"]) / position["entry_price"] * 100.0
            favorable_pct = (high - position["entry_price"]) / position["entry_price"] * 100.0
            if adverse_pct < position.get("mae_pct", 0.0):
                position["mae_pct"] = adverse_pct
                position["bars_to_mae"] = int(held)
            if favorable_pct > position.get("mfe_pct", 0.0):
                position["mfe_pct"] = favorable_pct
                position["bars_to_mfe"] = int(held)
            marked_equity = cash + (close - position["entry_price"]) * qty
            peak = max(peak, marked_equity)
            max_dd = min(max_dd, (marked_equity - peak) / peak * 100.0 if peak else 0.0)
            exit_price = None
            reason = None
            if low <= position["stop"]:
                exit_price = position["stop"] * (1 - SLIPPAGE_BPS / 10000)
                reason = "stop"
            elif high >= position["target"]:
                exit_price = position["target"] * (1 - SLIPPAGE_BPS / 10000)
                reason = "target"
            if exit_price is None and held >= int(params["max_hold_bars"]):
                exit_price = close * (1 - SLIPPAGE_BPS / 10000)
                reason = "time"
            if exit_price is None and int(signal.iloc[idx]) == -side:
                exit_price = close * (1 - SLIPPAGE_BPS / 10000)
                reason = "opposite"
            if exit_price is None and int(row["minute"]) >= 955:
                exit_price = close * (1 - SLIPPAGE_BPS / 10000)
                reason = "day_close"
            if exit_price is not None:
                gross = (exit_price - position["entry_price"]) * qty
                fee = moomoo_roundtrip_fee(qty, position["entry_price"], exit_price)
                net = gross - fee
                cash += net
                equity = cash
                trades.append({**position, "exit_ts": row["timestamp"].isoformat(), "exit_et": row["timestamp"].astimezone(ET).strftime("%Y-%m-%d %H:%M"), "exit_price": exit_price, "exit_reason": reason, "hold_minutes": _hold_minutes(position["entry_ts"], row["timestamp"]), "tool_return_pct": (exit_price - position["entry_price"]) / position["entry_price"] * 100.0, "net_pnl": net, "gross_pnl": gross, "fee": fee, "equity_after": equity})
                position = None
        if position is None:
            peak = max(peak, equity)
            max_dd = min(max_dd, (equity - peak) / peak * 100.0 if peak else 0.0)
        if position is None and int(signal.iloc[idx]) != 0 and idx + 1 < len(bars) and int(row["minute"]) < 930:
            side = int(signal.iloc[idx])
            tool = "RKLX" if side == 1 else "RKLZ"
            nxt = bars.iloc[idx + 1]
            raw_entry = float(nxt[f"{tool.lower()}_open"])
            if raw_entry <= 0 or not math.isfinite(raw_entry):
                continue
            entry = raw_entry * (1 + SLIPPAGE_BPS / 10000)
            qty = min(trade_value, cash) / entry
            stop_pct = max(float(params["stop_pct"]), float(row["atr_pct"]) * float(params["stop_atr_mult"]))
            target_pct = max(float(params["target_pct"]), stop_pct * float(params["rr_min"]))
            stop = entry * (1 - stop_pct / 100)
            target = entry * (1 + target_pct / 100)
            position = {"strategy": strategy_name, "params": json.dumps(params, ensure_ascii=False), "direction": side, "tool": tool, "signal_ts": row["timestamp"].isoformat(), "signal_et": row["timestamp"].astimezone(ET).strftime("%Y-%m-%d %H:%M"), "entry_ts": nxt["timestamp"].isoformat(), "entry_et": nxt["timestamp"].astimezone(ET).strftime("%Y-%m-%d %H:%M"), "entry_idx": int(idx + 1), "entry_price": entry, "qty": qty, "stop": stop, "target": target, "mae_pct": 0.0, "mfe_pct": 0.0, "bars_to_mae": 0, "bars_to_mfe": 0}
    if position is not None:
        row = bars.iloc[-1]
        tool = position["tool"]
        exit_price = float(row[f"{tool.lower()}_close"]) * (1 - SLIPPAGE_BPS / 10000)
        qty = position["qty"]
        gross = (exit_price - position["entry_price"]) * qty
        fee = moomoo_roundtrip_fee(qty, position["entry_price"], exit_price)
        net = gross - fee
        cash += net
        trades.append({**position, "exit_ts": row["timestamp"].isoformat(), "exit_et": row["timestamp"].astimezone(ET).strftime("%Y-%m-%d %H:%M"), "exit_price": exit_price, "exit_reason": "end", "hold_minutes": _hold_minutes(position["entry_ts"], row["timestamp"]), "tool_return_pct": (exit_price - position["entry_price"]) / position["entry_price"] * 100.0, "net_pnl": net, "gross_pnl": gross, "fee": fee, "equity_after": cash})
    sells = trades
    wins = [t for t in sells if t["net_pnl"] > 0]
    losses = [t for t in sells if t["net_pnl"] <= 0]
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    summary = {
        "fee_adjusted_pnl": cash - INIT_CASH,
        "return_pct": (cash - INIT_CASH) / INIT_CASH * 100.0,
        "trade_count": len(trades),
        "win_rate": len(wins) / len(trades) * 100.0 if trades else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        "max_drawdown": max_dd,
        "avg_trade": (cash - INIT_CASH) / len(trades) if trades else 0.0,
    }
    return summary, trades


def sample_params(trial, strategy_name: str) -> dict:
    def sf(name, lo, hi, step=None):
        if trial is None:
            if step:
                n = int(round((hi - lo) / step))
                return lo + random.randint(0, n) * step
            return random.uniform(lo, hi)
        return trial.suggest_float(name, lo, hi, step=step)

    def si(name, lo, hi, step=1):
        if trial is None:
            return random.randrange(lo, hi + 1, step)
        return trial.suggest_int(name, lo, hi, step=step)

    common = {
        "stop_pct": sf("stop_pct", 1.4, 4.0, 0.2),
        "target_pct": sf("target_pct", 1.6, 7.0, 0.2),
        "stop_atr_mult": sf("stop_atr_mult", 0.2, 0.9, 0.1),
        "rr_min": sf("rr_min", 1.0, 2.2, 0.1),
        "max_hold_bars": si("max_hold_bars", 6, 54, 3),
        "cooldown_bars": si("cooldown_bars", 2, 12, 1),
    }
    if strategy_name == "breakout":
        common.update({"volume_multiplier": sf("volume_multiplier", 0.7, 2.5, 0.1), "breakout_pct": sf("breakout_pct", 0.05, 0.8, 0.05), "atr_min": sf("atr_min", 0.05, 0.9, 0.05)})
    elif strategy_name == "vwap_reclaim":
        common.update({"vwap_gap": sf("vwap_gap", 0.1, 1.8, 0.1), "confirm_pct": sf("confirm_pct", 0.02, 0.5, 0.02), "rsi_min": si("rsi_min", 30, 52, 2), "rsi_max": si("rsi_max", 55, 77, 2)})
    elif strategy_name == "crash_rebound":
        common.update({"drop_pct": sf("drop_pct", 1.5, 9.0, 0.5), "surge_pct": sf("surge_pct", 2.0, 12.0, 0.5), "rebound_pct": sf("rebound_pct", 0.4, 3.5, 0.1), "move3_min": sf("move3_min", 0.05, 1.2, 0.05), "rsi_min": si("rsi_min", 25, 50, 1), "rsi_max": si("rsi_max", 52, 78, 1)})
    else:
        common.update({"gap_atr": sf("gap_atr", 0.05, 1.5, 0.05), "rsi_long_min": si("rsi_long_min", 40, 58, 2), "rsi_long_max": si("rsi_long_max", 62, 82, 2), "rsi_short_min": si("rsi_short_min", 18, 42, 2), "rsi_short_max": si("rsi_short_max", 45, 61, 2)})
    return common


def score_summary(summary: dict) -> float:
    if summary["trade_count"] < MIN_TEST_TRADES:
        return -100000.0 + summary["trade_count"]
    return float(summary["fee_adjusted_pnl"] + summary["profit_factor"] * 20.0 + summary["win_rate"] * 2.0 + summary["max_drawdown"] * 25.0)


def optimize_strategy(bars: pd.DataFrame, strategy_name: str, trials: int, seed: int) -> StrategySpec:
    splits = date_splits(bars, max_windows=6)
    train_days = set()
    for train, _test in splits:
        train_days.update(train)
    train_bars = bars[bars["et_date"].isin(train_days)].reset_index(drop=True)
    optuna = _load_optuna()
    random.seed(seed)

    def objective(trial):
        params = sample_params(trial, strategy_name)
        summary, _trades = simulate(train_bars, strategy_name, params)
        return score_summary(summary)

    if optuna is not None:
        sampler = optuna.samplers.TPESampler(seed=seed)
        study = optuna.create_study(direction="maximize", sampler=sampler)
        study.optimize(objective, n_trials=trials, show_progress_bar=False)
        params = sample_params(study.best_trial, strategy_name)
    else:
        best_score = -1e18
        params = {}
        for _ in range(trials):
            candidate = sample_params(None, strategy_name)
            summary, _trades = simulate(train_bars, strategy_name, candidate)
            score = score_summary(summary)
            if score > best_score:
                best_score = score
                params = candidate
    train_summary, _ = simulate(train_bars, strategy_name, params)
    walk_summaries = []
    all_test_trades = []
    for idx, (_train, test) in enumerate(splits, 1):
        test_bars = bars[bars["et_date"].isin(test)].reset_index(drop=True)
        summary, trades = simulate(test_bars, strategy_name, params)
        summary["window"] = idx
        walk_summaries.append(summary)
        for trade in trades:
            trade["window"] = idx
        all_test_trades.extend(trades)
    total_pnl = sum(item["fee_adjusted_pnl"] for item in walk_summaries)
    total_trades = sum(item["trade_count"] for item in walk_summaries)
    wins = sum(1 for t in all_test_trades if t["net_pnl"] > 0)
    gross_win = sum(t["net_pnl"] for t in all_test_trades if t["net_pnl"] > 0)
    gross_loss = abs(sum(t["net_pnl"] for t in all_test_trades if t["net_pnl"] <= 0))
    walk_summary = {
        "windows": len(walk_summaries),
        "fee_adjusted_pnl": total_pnl,
        "return_pct": total_pnl / INIT_CASH * 100.0,
        "trade_count": total_trades,
        "win_rate": wins / len(all_test_trades) * 100.0 if all_test_trades else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        "avg_window_pnl": total_pnl / len(walk_summaries) if walk_summaries else 0.0,
        "worst_window_pnl": min((x["fee_adjusted_pnl"] for x in walk_summaries), default=0.0),
        "avg_max_drawdown": sum(x["max_drawdown"] for x in walk_summaries) / len(walk_summaries) if walk_summaries else 0.0,
    }
    score = walk_summary["fee_adjusted_pnl"] + walk_summary["profit_factor"] * 40 + walk_summary["win_rate"] * 3 + walk_summary["worst_window_pnl"] * 0.7 + walk_summary["avg_max_drawdown"] * 30
    return StrategySpec(strategy_name, params, score, train_summary, walk_summary, all_test_trades)


def write_outputs(specs: list[StrategySpec], out_dir: Path) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rank_path = out_dir / "strategy_miner_ranking.csv"
    trade_path = out_dir / "strategy_miner_trades.csv"
    report_path = out_dir / "strategy_miner_report.md"
    with rank_path.open("w", encoding="utf-8-sig", newline="") as fh:
        fields = ["rank", "strategy", "score", "test_pnl", "test_return_pct", "test_trades", "test_win_rate", "test_profit_factor", "worst_window_pnl", "avg_max_drawdown", "params"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for rank, spec in enumerate(specs, 1):
            ws = spec.walk_summary
            writer.writerow({"rank": rank, "strategy": spec.name, "score": round(spec.score, 2), "test_pnl": round(ws["fee_adjusted_pnl"], 2), "test_return_pct": round(ws["return_pct"], 2), "test_trades": ws["trade_count"], "test_win_rate": round(ws["win_rate"], 2), "test_profit_factor": round(ws["profit_factor"], 2), "worst_window_pnl": round(ws["worst_window_pnl"], 2), "avg_max_drawdown": round(ws["avg_max_drawdown"], 2), "params": json.dumps(spec.params, ensure_ascii=False)})
    with trade_path.open("w", encoding="utf-8-sig", newline="") as fh:
        fields = ["strategy", "window", "direction", "tool", "signal_ts", "signal_et", "entry_ts", "entry_et", "entry_price", "qty", "stop", "target", "exit_ts", "exit_et", "exit_price", "exit_reason", "hold_minutes", "tool_return_pct", "mae_pct", "mfe_pct", "bars_to_mae", "bars_to_mfe", "gross_pnl", "fee", "net_pnl", "equity_after"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for spec in specs:
            for trade in spec.trades:
                row = {key: trade.get(key, "") for key in fields}
                row["strategy"] = spec.name
                writer.writerow(row)
    lines = [
        "# VectorBT/Optuna Strategy Miner",
        "",
        "VERSION: v0.1.3",
        "DEPENDS: data/historical/RKLB_1m.csv, RKLX_1m.csv, RKLZ_1m.csv",
        "",
        "Research-only. This report searches bounded strategy templates on historical data and does not change live trading.",
        "",
        "## Plain-Language Summary",
        "",
        "这份报告只用于离线研究, 不会修改实盘盯盘逻辑。",
        "评分优先看扣费后的测试收益、交易次数、胜率、profit factor 和最差窗口。",
        "RKLX/RKLZ 都按买入工具处理: 看多 RKLB 买 RKLX, 看空 RKLB 买 RKLZ。",
        "",
        "## Ranking",
        "",
        "| Rank | Strategy | Test PnL | Return | Trades | Win Rate | Profit Factor | Worst Window | Avg MDD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, spec in enumerate(specs, 1):
        ws = spec.walk_summary
        lines.append(f"| {rank} | {spec.name} | ${ws['fee_adjusted_pnl']:.2f} | {ws['return_pct']:+.2f}% | {ws['trade_count']} | {ws['win_rate']:.1f}% | {ws['profit_factor']:.2f} | ${ws['worst_window_pnl']:.2f} | {ws['avg_max_drawdown']:.2f}% |")
    lines += ["", "## Best Parameters", ""]
    for rank, spec in enumerate(specs[:3], 1):
        lines.append(f"### {rank}. {spec.name}")
        for key, value in spec.params.items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    lines += [
        "## Files",
        "",
        f"- Ranking CSV: `{rank_path}`",
        f"- Trade CSV: `{trade_path}`",
        "",
        "## Decision Rule",
        "",
        "A candidate should only move to shadow mode if it beats the current benchmark after fees, has enough trades, and does not rely on one lucky window.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path, rank_path, trade_path


def send_telegram_summary(specs: list[StrategySpec], report_path: Path) -> bool:
    if not specs:
        return False
    best = specs[0]
    ws = best.walk_summary
    text = (
        "🧪 VectorBT/Optuna 策略搜索完成\n"
        f"最佳模板: {best.name}\n"
        f"扣费后测试收益: ${ws['fee_adjusted_pnl']:.2f} ({ws['return_pct']:+.2f}%)\n"
        f"交易: {ws['trade_count']} 笔 · 胜率 {ws['win_rate']:.1f}% · PF {ws['profit_factor']:.2f}\n"
        f"最差窗口: ${ws['worst_window_pnl']:.2f} · 平均回撤 {ws['avg_max_drawdown']:.2f}%\n"
        "结论: 仅进入离线候选池, 不能直接替换实盘策略。\n"
        f"报告: {report_path}"
    )
    try:
        from _tg_notify import send_review

        return bool(send_review(text))
    except Exception as exc:
        print(f"[miner] telegram skipped: {exc}")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine bounded RKLB/RKLX/RKLZ strategies with Optuna.")
    parser.add_argument("--trials", type=int, default=80, help="Trials per strategy template.")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--telegram", action="store_true", help="Send a personal Telegram summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bars = load_market()
    specs = []
    for idx, name in enumerate(SIGNAL_FUNCS, 1):
        print(f"[miner] optimizing {name} trials={args.trials}")
        specs.append(optimize_strategy(bars, name, args.trials, args.seed + idx))
    specs.sort(key=lambda item: item.score, reverse=True)
    report_path, rank_path, trade_path = write_outputs(specs, Path(args.out_dir))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_report = OUT_DIR / "strategy_miner_report_latest.md"
    latest_rank = OUT_DIR / "strategy_miner_ranking_latest.csv"
    latest_trades = OUT_DIR / "strategy_miner_trades_latest.csv"
    latest_report.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_rank.write_text(rank_path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
    latest_trades.write_text(trade_path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
    if args.telegram:
        send_telegram_summary(specs, report_path)
    print(f"[miner] report: {report_path}")
    print(f"[miner] ranking: {rank_path}")
    print(f"[miner] trades: {trade_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
