"""
MagicQuant breakout_core.py
VERSION : v0.1.0
DEPENDS : pandas, vectorbt

Single RKLB-style breakout template for isolated research.
单一 RKLB 式突破模板，仅用于 research/vectorbt_lab。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd

try:
    import vectorbt as vbt
except Exception:
    vbt = None


ET = ZoneInfo("America/New_York")
DEFAULT_INIT_CASH = 3000.0
DEFAULT_TRADE_VALUE = 2000.0
SLIPPAGE_BPS = 8.0


@dataclass(frozen=True)
class BreakoutParams:
    volume_multiplier: float = 1.5
    atr_threshold: float = 0.20
    breakout_pct: float = 0.30
    stop_atr: float = 1.4
    take_profit_atr: float = 2.0
    cooldown_minutes: int = 20


@dataclass
class BacktestResult:
    symbol: str
    params: dict
    net_profit: float
    fee_adjusted_pnl: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    trade_count: int
    false_breakout_rate: float
    signal_density_per_day: float


def moomoo_roundtrip_fee(qty: float, entry_price: float, exit_price: float) -> float:
    """Approximate Moomoo AU roundtrip fee. / 近似 Moomoo AU 往返手续费。"""
    if qty <= 0 or entry_price <= 0 or exit_price <= 0:
        return 0.0
    buy_fee = 1.29
    sell_notional = qty * exit_price
    sec_fee = sell_notional * 0.0000278
    taf_fee = max(0.01, min(8.30, qty * 0.000166))
    sell_fee = 0.99 + 0.30 + sec_fee + taf_fee
    return round(buy_fee + sell_fee, 4)


def _ensure_utc_timestamp(frame: pd.DataFrame) -> pd.Series:
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    return ts


def prepare_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare canonical bars and indicators. / 准备统一 K 线和基础指标。"""
    if frame.empty:
        return frame.copy()
    bars = frame.copy()
    bars["timestamp"] = _ensure_utc_timestamp(bars)
    bars = bars.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars = bars.dropna(subset=["open", "high", "low", "close"])

    et_ts = bars["timestamp"].dt.tz_convert(ET)
    bars["et_date"] = et_ts.dt.date
    bars["et_time"] = et_ts.dt.time
    bars["minute_of_day"] = et_ts.dt.hour * 60 + et_ts.dt.minute

    typical = (bars["high"] + bars["low"] + bars["close"]) / 3
    pv = typical * bars["volume"].clip(lower=0)
    grouped = bars.groupby("et_date", sort=False)
    vol_cum = bars["volume"].clip(lower=0).groupby(bars["et_date"]).cumsum()
    pv_cum = pv.groupby(bars["et_date"]).cumsum()
    bars["vwap"] = (pv_cum / vol_cum.where(vol_cum != 0)).astype(float)
    bars["vwap"] = bars["vwap"].ffill().fillna(bars["close"])

    prev_close = bars["close"].shift(1)
    tr = pd.concat([
        bars["high"] - bars["low"],
        (bars["high"] - prev_close).abs(),
        (bars["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    bars["atr"] = tr.rolling(14, min_periods=5).mean().fillna(tr.rolling(5, min_periods=1).mean())
    bars["atr_pct"] = (bars["atr"] / bars["close"] * 100).fillna(0)
    bars["vol_ma20"] = bars["volume"].shift(1).rolling(20, min_periods=5).mean()
    bars["rolling_high20"] = bars["high"].shift(1).rolling(20, min_periods=5).max()

    pre_mask = bars["minute_of_day"].between(4 * 60, 9 * 60 + 29)
    pre_high = bars[pre_mask].groupby("et_date")["high"].max()
    bars["premarket_high"] = bars["et_date"].map(pre_high).fillna(bars.groupby("et_date")["high"].transform("first"))
    bars["symbol"] = bars.get("symbol", "UNKNOWN")
    return bars


def _apply_cooldown(entries: pd.Series, timestamps: pd.Series, cooldown_minutes: int) -> pd.Series:
    allowed = []
    last_entry = None
    cooldown = pd.Timedelta(minutes=max(0, int(cooldown_minutes)))
    for idx, is_entry in enumerate(entries.fillna(False).tolist()):
        ts = timestamps.iloc[idx]
        if not is_entry:
            allowed.append(False)
            continue
        if last_entry is None or ts - last_entry >= cooldown:
            allowed.append(True)
            last_entry = ts
        else:
            allowed.append(False)
    return pd.Series(allowed, index=entries.index)


def generate_entries(bars: pd.DataFrame, params: BreakoutParams) -> pd.Series:
    """Generate breakout entries. / 生成突破入场信号。"""
    if bars.empty:
        return pd.Series(dtype=bool)
    start_min = 4 * 60
    end_min = 11 * 60 + 30
    in_window = bars["minute_of_day"].between(start_min, end_min)
    ref_high = pd.concat([bars["premarket_high"], bars["rolling_high20"]], axis=1).max(axis=1)
    breakout_level = ref_high * (1 + params.breakout_pct / 100.0)
    vol_ok = bars["volume"] >= (bars["vol_ma20"].fillna(0) * params.volume_multiplier)
    atr_ok = bars["atr_pct"] >= params.atr_threshold
    entries = (
        in_window
        & (bars["close"] > breakout_level)
        & (bars["close"] > bars["vwap"])
        & vol_ok
        & atr_ok
    )
    return _apply_cooldown(entries, bars["timestamp"], params.cooldown_minutes)


def make_vectorbt_portfolio(bars: pd.DataFrame, entries: pd.Series):
    """Build a vectorbt portfolio for framework compatibility. / 构建 vectorbt portfolio 供研究核对。"""
    if vbt is None or bars.empty:
        return None
    exits = pd.Series(False, index=entries.index)
    return vbt.Portfolio.from_signals(
        bars["close"],
        entries=entries,
        exits=exits,
        init_cash=DEFAULT_INIT_CASH,
        freq="1min",
    )


def simulate_trades(
    bars: pd.DataFrame,
    entries: pd.Series,
    params: BreakoutParams,
    init_cash: float = DEFAULT_INIT_CASH,
    trade_value: float = DEFAULT_TRADE_VALUE,
) -> list[dict]:
    """Simple deterministic intraday simulator. / 简单确定性日内模拟器。"""
    trades: list[dict] = []
    open_trade = None
    cash_basis = float(init_cash)

    for idx, row in bars.iterrows():
        current_time = row["et_time"]
        if open_trade is not None:
            exit_price = None
            reason = None
            if row["low"] <= open_trade["stop"]:
                exit_price = open_trade["stop"] * (1 - SLIPPAGE_BPS / 10000.0)
                reason = "stop"
            elif row["high"] >= open_trade["target"]:
                exit_price = open_trade["target"] * (1 - SLIPPAGE_BPS / 10000.0)
                reason = "target"
            elif current_time >= time(15, 59):
                exit_price = float(row["close"]) * (1 - SLIPPAGE_BPS / 10000.0)
                reason = "day_close"

            if exit_price is not None:
                qty = open_trade["qty"]
                gross = (exit_price - open_trade["entry_price"]) * qty
                fee = moomoo_roundtrip_fee(qty, open_trade["entry_price"], exit_price)
                net = gross - fee
                cash_basis += net
                trades.append({
                    **open_trade,
                    "exit_ts": row["timestamp"],
                    "exit_price": float(exit_price),
                    "exit_reason": reason,
                    "bars_to_exit": int(idx - open_trade.get("entry_idx", idx) + 1),
                    "gross_pnl": float(gross),
                    "fee": float(fee),
                    "net_pnl": float(net),
                    "equity_after": float(cash_basis),
                })
                open_trade = None

        if open_trade is None and bool(entries.iloc[idx]) and current_time < time(15, 30):
            if idx + 1 >= len(bars):
                continue
            next_row = bars.iloc[idx + 1]
            entry = float(next_row["open"]) * (1 + SLIPPAGE_BPS / 10000.0)
            atr_pct = max(float(row["atr_pct"]), params.atr_threshold)
            stop_dist = entry * (params.stop_atr * atr_pct / 100.0)
            target_dist = entry * (params.take_profit_atr * atr_pct / 100.0)
            qty = min(init_cash, trade_value) / entry
            open_trade = {
                "entry_ts": next_row["timestamp"],
                "signal_ts": row["timestamp"],
                "entry_idx": int(idx + 1),
                "entry_price": entry,
                "qty": float(qty),
                "stop": float(entry - stop_dist),
                "target": float(entry + target_dist),
                "atr_pct": atr_pct,
            }

    if open_trade is not None and len(bars) > 0:
        row = bars.iloc[-1]
        exit_price = float(row["close"]) * (1 - SLIPPAGE_BPS / 10000.0)
        qty = open_trade["qty"]
        gross = (exit_price - open_trade["entry_price"]) * qty
        fee = moomoo_roundtrip_fee(qty, open_trade["entry_price"], exit_price)
        net = gross - fee
        cash_basis += net
        trades.append({
            **open_trade,
            "exit_ts": row["timestamp"],
            "exit_price": exit_price,
            "exit_reason": "end_of_data",
            "bars_to_exit": int(len(bars) - open_trade.get("entry_idx", len(bars) - 1)),
            "gross_pnl": float(gross),
            "fee": float(fee),
            "net_pnl": float(net),
            "equity_after": float(cash_basis),
        })

    return trades


def _max_drawdown_from_equity(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, (value - peak) / peak * 100.0)
    return round(max_dd, 2)


def summarize_trades(
    symbol: str,
    params: BreakoutParams,
    trades: list[dict],
    entries: pd.Series | None = None,
    trading_days: int = 0,
    init_cash: float = DEFAULT_INIT_CASH,
) -> BacktestResult:
    gross = [trade["gross_pnl"] for trade in trades]
    net = [trade["net_pnl"] for trade in trades]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = [init_cash] + [trade["equity_after"] for trade in trades]
    trade_count = len(trades)
    false_breakouts = [
        trade for trade in trades
        if trade.get("exit_reason") == "stop" and int(trade.get("bars_to_exit") or 9999) <= 5
    ]
    signal_count = int(entries.sum()) if entries is not None and len(entries) else 0
    signal_density = signal_count / trading_days if trading_days else 0.0
    return BacktestResult(
        symbol=symbol,
        params=asdict(params),
        net_profit=round(sum(gross), 2),
        fee_adjusted_pnl=round(sum(net), 2),
        win_rate=round(len(wins) / trade_count * 100, 2) if trade_count else 0.0,
        profit_factor=round(gross_profit / gross_loss, 3) if gross_loss > 0 else (round(gross_profit, 3) if gross_profit > 0 else 0.0),
        max_drawdown=_max_drawdown_from_equity(equity),
        trade_count=trade_count,
        false_breakout_rate=round(len(false_breakouts) / trade_count * 100, 2) if trade_count else 0.0,
        signal_density_per_day=round(signal_density, 3),
    )


def run_backtest(
    frame: pd.DataFrame,
    params: BreakoutParams | None = None,
    use_vectorbt: bool = False,
) -> tuple[BacktestResult, pd.DataFrame]:
    params = params or BreakoutParams()
    bars = prepare_bars(frame)
    return run_prepared_backtest(bars, params, use_vectorbt=use_vectorbt)


def run_prepared_backtest(
    bars: pd.DataFrame,
    params: BreakoutParams | None = None,
    use_vectorbt: bool = False,
) -> tuple[BacktestResult, pd.DataFrame]:
    """Run backtest on precomputed bars. / 基于预计算指标运行回测。"""
    params = params or BreakoutParams()
    symbol = str(bars["symbol"].iloc[0]) if not bars.empty else "UNKNOWN"
    entries = generate_entries(bars, params)
    if use_vectorbt:
        make_vectorbt_portfolio(bars, entries)
    trades = simulate_trades(bars, entries, params)
    trading_days = int(bars["et_date"].nunique()) if "et_date" in bars.columns else 0
    result = summarize_trades(symbol, params, trades, entries=entries, trading_days=trading_days)
    return result, pd.DataFrame(trades)
