"""
MagicQuant test_vectorbt_lab.py
VERSION : v0.1.0
DEPENDS : research.vectorbt_lab.breakout_core
PURPOSE : Verify isolated vectorbt lab behavior.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "research" / "vectorbt_lab"
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

from breakout_core import BreakoutParams, prepare_bars, run_backtest, summarize_trades


def synthetic_breakout_frame() -> pd.DataFrame:
    ts = pd.date_range("2026-05-01 13:00:00+00:00", periods=180, freq="1min")
    rows = []
    price = 100.0
    for idx, stamp in enumerate(ts):
        if idx < 40:
            price += 0.01
        elif idx == 45:
            price += 1.0
        elif idx > 45:
            price += 0.05
        high = price + 0.08
        low = price - 0.08
        volume = 1000 if idx < 45 else 5000
        rows.append({
            "timestamp": stamp,
            "open": price - 0.02,
            "high": high,
            "low": low,
            "close": price,
            "volume": volume,
            "symbol": "TEST",
        })
    return pd.DataFrame(rows)


class VectorBTLabTest(unittest.TestCase):
    def test_prepare_bars_keeps_utc_timestamp_and_indicators(self):
        bars = prepare_bars(synthetic_breakout_frame())

        self.assertTrue(str(bars["timestamp"].dt.tz).upper() in ("UTC", "UTC+00:00"))
        self.assertIn("vwap", bars.columns)
        self.assertIn("atr_pct", bars.columns)
        self.assertFalse(bars["timestamp"].duplicated().any())

    def test_backtest_is_deterministic_and_fee_adjusted(self):
        frame = synthetic_breakout_frame()
        params = BreakoutParams(volume_multiplier=1.2, atr_threshold=0.01, breakout_pct=0.05)

        first, _ = run_backtest(frame, params)
        second, _ = run_backtest(frame, params)

        self.assertEqual(first.__dict__, second.__dict__)
        self.assertLessEqual(first.fee_adjusted_pnl, first.net_profit)
        self.assertGreaterEqual(first.trade_count, 1)

    def test_entry_uses_next_bar_open_with_slippage(self):
        frame = synthetic_breakout_frame()
        params = BreakoutParams(volume_multiplier=1.2, atr_threshold=0.01, breakout_pct=0.05)

        _result, trades = run_backtest(frame, params)

        self.assertFalse(trades.empty)
        first_trade = trades.iloc[0]
        signal_ts = pd.Timestamp(first_trade["signal_ts"])
        entry_ts = pd.Timestamp(first_trade["entry_ts"])
        self.assertGreater(entry_ts, signal_ts)
        next_open = frame.loc[frame["timestamp"] == entry_ts, "open"].iloc[0]
        self.assertGreater(first_trade["entry_price"], next_open)

    def test_false_breakout_rate_is_not_losing_trade_ratio(self):
        trades = [
            {"gross_pnl": -10.0, "net_pnl": -12.0, "equity_after": 2988.0, "exit_reason": "stop", "bars_to_exit": 3},
            {"gross_pnl": -20.0, "net_pnl": -22.0, "equity_after": 2966.0, "exit_reason": "stop", "bars_to_exit": 12},
        ]

        result = summarize_trades("TEST", BreakoutParams(), trades)

        self.assertEqual(result.win_rate, 0.0)
        self.assertEqual(result.false_breakout_rate, 50.0)
        self.assertNotEqual(result.false_breakout_rate, 100.0)


if __name__ == "__main__":
    unittest.main()
