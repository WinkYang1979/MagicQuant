"""
MagicQuant test_display_safety.py
VERSION : v0.1.0
DATE    : 2026-05-27
DEPENDS : core.focus.kline_display, core.focus.pusher
PURPOSE : Guard against misleading live Telegram display labels.
"""

import unittest
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
KLINE_DISPLAY = ROOT / "core" / "focus" / "kline_display.py"
spec = importlib.util.spec_from_file_location("kline_display_under_test", KLINE_DISPLAY)
kline_display = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kline_display)


class DisplaySafetyTest(unittest.TestCase):
    def test_future_kline_timestamp_is_not_shown_as_age_zero(self):
        future_bar = datetime.now(kline_display.ET) + timedelta(minutes=3)

        line = kline_display.format_kline_source_line(
            quality=SimpleNamespace(last_bar_time=future_bar)
        )

        self.assertIn("当前5m柱", line)
        self.assertNotIn("age 0s", line)


if __name__ == "__main__":
    unittest.main()
