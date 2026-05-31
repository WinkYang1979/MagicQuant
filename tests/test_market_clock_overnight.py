"""
MagicQuant tests - market_clock overnight sessions
VERSION : v0.1.0
DEPENDS : core.focus.market_clock
"""
import unittest
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.focus.market_clock import ET, get_market_status


class MarketClockOvernightTest(unittest.TestCase):
    def test_holiday_evening_opens_next_trading_day_overnight(self):
        # 2026-05-25 is Memorial Day. The 20:00+ ET overnight session belongs
        # to Tuesday 2026-05-26, so it must not be treated as closed.
        now = datetime(2026, 5, 25, 22, 23, tzinfo=ET)
        self.assertEqual(get_market_status(now), "overnight")

    def test_next_trading_day_early_morning_is_overnight(self):
        now = datetime(2026, 5, 26, 2, 30, tzinfo=ET)
        self.assertEqual(get_market_status(now), "overnight")

    def test_friday_night_is_closed(self):
        now = datetime(2026, 5, 22, 22, 0, tzinfo=ET)
        self.assertEqual(get_market_status(now), "closed")

    def test_sunday_evening_opens_monday_overnight(self):
        now = datetime(2026, 6, 7, 22, 0, tzinfo=ET)
        self.assertEqual(get_market_status(now), "overnight")


if __name__ == "__main__":
    unittest.main()
