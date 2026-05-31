"""
MagicQuant test_direction_gap_confirmation_v0_5_36.py
VERSION : v0.5.36-test
DATE    : 2026-05-30
DEPENDS : core.focus.context, core.focus.swing_detector
PURPOSE : Direction confidence should not call an overnight gap a STRONG intraday trend.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.focus.context import FocusSession
from core.focus import swing_detector as sd


MASTER = "US.RKLB"


def _session(day_change, current, bars):
    session = FocusSession(MASTER, ["US.RKLX", "US.RKLZ"])
    session.update_price(MASTER, current)
    session.quote_snapshot[MASTER] = {"change_pct": day_change}
    session._last_kline_cache = pd.DataFrame(bars)
    session._disable_review_log = True
    return session


def _ind(vwap):
    return {
        "data_ok": True,
        "is_today": True,
        "rsi_5m": 55.0,
        "vol_ratio": 1.2,
        "vwap": vwap,
        "session_high": 151.0,
        "session_low": 147.5,
    }


class DirectionGapConfirmationTest(unittest.TestCase):
    def test_gap_up_but_intraday_down_downgrades_long_only(self):
        session = _session(
            12.0,
            148.0,
            [
                {"time_key": "2026-05-28 09:30:00", "open": 150.0, "high": 151.0, "low": 149.0, "close": 150.5},
                {"time_key": "2026-05-28 09:35:00", "open": 150.5, "high": 150.8, "low": 148.5, "close": 148.7},
                {"time_key": "2026-05-28 09:40:00", "open": 148.7, "high": 149.0, "low": 147.8, "close": 148.0},
            ],
        )
        hit = sd.check_direction_trend(session, MASTER, _ind(vwap=149.0), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["direction"], "long")
        self.assertEqual(hit["strength"], "WEAK")
        self.assertIn("gap_not_intraday_confirmed", hit["data"]["cap_reasons"])

    def test_gap_up_with_intraday_confirmation_stays_strong(self):
        session = _session(
            12.0,
            145.0,
            [
                {"time_key": "2026-05-29 09:30:00", "open": 140.0, "high": 141.0, "low": 139.5, "close": 140.8},
                {"time_key": "2026-05-29 09:35:00", "open": 140.8, "high": 143.0, "low": 140.5, "close": 142.5},
                {"time_key": "2026-05-29 09:40:00", "open": 142.5, "high": 145.5, "low": 142.3, "close": 145.0},
            ],
        )
        hit = sd.check_direction_trend(session, MASTER, _ind(vwap=144.0), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["direction"], "long")
        self.assertEqual(hit["strength"], "STRONG")
        self.assertNotIn("gap_not_intraday_confirmed", hit["data"]["cap_reasons"])

    def test_gap_down_but_intraday_up_downgrades_short_only(self):
        session = _session(
            -12.0,
            102.0,
            [
                {"time_key": "2026-05-28 09:30:00", "open": 100.0, "high": 100.5, "low": 99.0, "close": 99.8},
                {"time_key": "2026-05-28 09:35:00", "open": 99.8, "high": 101.0, "low": 99.7, "close": 100.9},
                {"time_key": "2026-05-28 09:40:00", "open": 100.9, "high": 102.2, "low": 100.8, "close": 102.0},
            ],
        )
        indicators = _ind(vwap=101.0)
        indicators["rsi_5m"] = 45.0
        hit = sd.check_direction_trend(session, MASTER, indicators, sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["direction"], "short")
        self.assertEqual(hit["strength"], "WEAK")
        self.assertIn("gap_not_intraday_confirmed", hit["data"]["cap_reasons"])


if __name__ == "__main__":
    unittest.main()
