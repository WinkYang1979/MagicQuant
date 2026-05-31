"""
MagicQuant test_dataframe_kline_inputs.py
VERSION : v0.1.0
DATE    : 2026-05-28
DEPENDS : core.focus.data_quality, core.focus.kline_display,
          core.focus.position_followup, core.focus.swing_detector
PURPOSE : Regression guard for pandas DataFrame K-line cache inputs.
"""

import unittest
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.focus import data_quality, kline_display, position_followup, swing_detector
from core.focus.context import FocusSession


class _GoodQuality:
    ok = True
    can_direction = True
    reason = "OK"
    last_bar_time = "2026-05-28 09:40:00"
    level = "OK"

    def to_dict(self):
        return {"ok": True, "can_direction": True, "reason": "OK"}


class DataFrameKlineInputsTest(unittest.TestCase):
    def setUp(self):
        self.bars = pd.DataFrame(
            [
                {"time_key": "2026-05-28 09:30:00", "high": 101.0, "close": 100.0},
                {"time_key": "2026-05-28 09:35:00", "high": 100.5, "close": 99.5},
                {"time_key": "2026-05-28 09:40:00", "high": 100.0, "close": 99.0},
            ]
        )
        self.session = SimpleNamespace(_last_kline_cache=self.bars)

    def test_display_reads_dataframe_last_bar(self):
        dt = kline_display.find_kline_last_time(indicators={"kline_bars": self.bars})
        self.assertIsNotNone(dt)
        self.assertEqual(dt.minute, 40)

    def test_data_quality_reads_dataframe_last_bar(self):
        dt = data_quality._last_bar_from_indicators({"kline_bars": self.bars})
        self.assertIsNotNone(dt)
        self.assertEqual(dt.minute, 40)

    def test_swing_detector_converts_dataframe_bars(self):
        bars = swing_detector._recent_bars_from_session_or_indicators(
            self.session, {"kline_bars": self.bars}
        )
        self.assertIsInstance(bars, list)
        self.assertEqual(bars[-1]["close"], 99.0)

    def test_position_followup_accepts_dataframe_cache(self):
        self.assertTrue(position_followup._bars_bearish(self.session, {"vwap": 100.0}))

    def test_run_all_triggers_accepts_dataframe_cache_with_position(self):
        session = FocusSession("US.RKLB", ["US.RKLX"])
        session._disable_review_log = True
        for price in [101.0, 100.5, 99.8, 99.0]:
            session.update_price("US.RKLB", price)
        for price in [100.0, 98.0, 96.0]:
            session.update_price("US.RKLX", price)
        session.quote_snapshot["US.RKLB"] = {"change_pct": -3.0}
        session._last_kline_cache = self.bars
        session.positions_snapshot = {
            "US.RKLX": {
                "qty": 10,
                "cost_price": 100.0,
                "current_price": 96.0,
                "pl_val": -40.0,
                "pl_pct": -4.0,
            }
        }
        session.trough_price = {"US.RKLX": 96.0}
        session._target_state = {
            "US.RKLX": {"stop": 97.0, "t1": 104.0, "atr": 1.0}
        }
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 45.0,
            "vol_ratio": 1.0,
            "vwap": 100.0,
            "kline_bars": self.bars,
            "session_high": 101.0,
            "session_low": 99.0,
        }
        original = swing_detector.evaluate_data_quality
        swing_detector.evaluate_data_quality = lambda *args, **kwargs: _GoodQuality()
        try:
            try:
                swing_detector.run_all_triggers(
                    session, "US.RKLB", ["US.RKLX"], indicators, swing_detector.DEFAULT_PARAMS
                )
            except ValueError as exc:
                self.fail(f"DataFrame cache should not raise ambiguous truth-value errors: {exc}")
        finally:
            swing_detector.evaluate_data_quality = original


if __name__ == "__main__":
    unittest.main()
