"""
MagicQuant test_price_delta_display.py
VERSION : v0.1.0
DATE    : 2026-05-26
DEPENDS : core.focus.pusher
PURPOSE : Verify price delta display lines for signals and heartbeat.
"""

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.focus.pusher import (
    build_price_delta_lines,
    build_related_price_delta_lines,
    inject_price_delta_lines,
    remember_signal_price,
)


class FakeSession:
    def __init__(self):
        self.master = "US.RKLB"
        self.followers = ["US.RKLX", "US.RKLZ"]
        self.quote_snapshot = {
            "US.RKLB": {"prev_close": 100.0},
            "US.RKLX": {"prev_close": 80.0},
            "US.RKLZ": {"prev_close": 2.5},
        }
        self._last_price = {"US.RKLB": 105.0, "US.RKLX": 86.0, "US.RKLZ": 2.2}
        self._day_change = {"US.RKLB": 5.0, "US.RKLX": 7.5, "US.RKLZ": -12.0}

    def get_last_price(self, ticker):
        return self._last_price.get(ticker)

    def get_day_change_pct(self, ticker):
        return self._day_change.get(ticker)


class PriceDeltaDisplayTest(unittest.TestCase):
    def test_build_lines_include_prev_close_and_last_signal_delta(self):
        session = FakeSession()
        session._last_signal_price = {"US.RKLB": {"price": 102.0}}

        lines = build_price_delta_lines(session, "US.RKLB", current=105.0)

        joined = "\n".join(lines)
        self.assertIn("RKLB: 现价 $105.00", joined)
        self.assertIn("较昨收 $100.00", joined)
        self.assertIn("提升 $5.00 (+5.00%)", joined)
        self.assertIn("RKLB: 上次信号价 $102.00", joined)
        self.assertIn("提升 $3.00 (+2.94%)", joined)

    def test_related_lines_include_rklx_for_long_signal(self):
        session = FakeSession()
        session._last_signal_price = {
            "US.RKLB": {"price": 102.0},
            "US.RKLX": {"price": 84.0},
        }

        lines = build_related_price_delta_lines(session, "US.RKLB", current=105.0, direction="long")
        joined = "\n".join(lines)

        self.assertIn("RKLB: 现价 $105.00", joined)
        self.assertIn("RKLX: 现价 $86.00", joined)
        self.assertIn("RKLX: 上次信号价 $84.00", joined)

    def test_heartbeat_style_excludes_prev_close_and_tracks_accuracy(self):
        session = FakeSession()
        session._last_signal_price = {
            "US.RKLB": {"price": 102.0, "direction": "long"},
            "US.RKLX": {"price": 84.0, "direction": "long", "related_to": "US.RKLB"},
        }

        lines = build_related_price_delta_lines(
            session,
            "US.RKLB",
            current=105.0,
            direction="long",
            include_prev_close=False,
            include_accuracy=True,
        )
        joined = "\n".join(lines)

        self.assertIn("RKLB: 现价 $105.00", joined)
        self.assertIn("RKLX: 现价 $86.00", joined)
        self.assertNotIn("较昨收", joined)
        self.assertIn("RKLB: 信号跟踪: ✅ 信号有效", joined)
        self.assertIn("RKLX: 信号跟踪: ✅ 信号有效", joined)

    def test_inject_lines_after_separator(self):
        session = FakeSession()
        text = "标题\n━━━━━━━━━━━━━━\n原内容"

        out = inject_price_delta_lines(text, session, "US.RKLB", current=105.0, direction="long")

        self.assertIn("标题\n━━━━━━━━━━━━━━\nRKLB: 现价 $105.00", out)
        self.assertIn("RKLX: 现价 $86.00", out)
        self.assertIn("原内容", out)

    def test_remember_signal_price_uses_hit_current(self):
        session = FakeSession()
        remember_signal_price(
            session,
            {"ticker": "US.RKLB", "trigger": "direction_trend", "direction": "long", "data": {"current": 106.5}},
        )

        state = session._last_signal_price["US.RKLB"]
        self.assertEqual(state["price"], 106.5)
        self.assertEqual(state["trigger"], "direction_trend")
        self.assertEqual(state["direction"], "long")
        self.assertEqual(session._last_signal_price["US.RKLX"]["price"], 86.0)


if __name__ == "__main__":
    unittest.main()
