"""
VERSION : v0.5.28-test
DEPENDS : core.focus.pusher, core.focus.context

Verify follower-domain target prices are not mixed with RKLB master prices.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.focus import pusher
from core.focus.context import FocusSession


class TestTargetFollowerFix(unittest.TestCase):
    def test_follower_targets_use_follower_price_domain(self):
        session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
        session.update_cash(5000.0, 5000.0)

        for i, (rklb, rklx) in enumerate([
            (115.88, 70.82), (116.01, 71.00), (116.45, 71.29), (116.89, 72.08),
            (117.08, 72.85), (117.61, 73.20), (117.91, 73.40), (118.07, 73.16),
            (118.21, 73.84), (118.39, 74.30), (118.57, 74.50), (118.67, 74.64),
            (118.95, 74.78), (119.06, 74.64), (119.13, 74.50), (119.33, 75.00),
            (119.86, 75.50), (119.90, 75.72), (120.12, 76.10), (120.35, 76.38),
        ]):
            session.update_price("US.RKLB", rklb)
            session.update_price("US.RKLX", rklx)
            session.update_price("US.RKLZ", 3.05 - i * 0.005)

        hit = {
            "ticker": "US.RKLB",
            "trigger": "direction_trend",
            "direction": "long",
            "strength": "STRONG",
            "data": {
                "has_indicators": True,
                "rsi": 52.7,
                "vwap": 117.98,
                "vol_ratio": 1.2,
                "regime": "choppy",
            },
        }

        out = pusher._fmt_signal_with_conflict(
            hit,
            session,
            "long",
            "RKLB direction signal",
            "RSI 52.7  VWAP $117.98  vol_ratio 1.2x",
        )
        text = out["text"]

        t1_match = re.search(r"RKLX .*?T1 \$([\d.]+)", text)
        self.assertIsNotNone(t1_match, text)
        t1 = float(t1_match.group(1))
        self.assertGreater(t1, 70)
        self.assertLess(t1, 90)

        stop_match = re.search(r"RKLX 失效价 \$([\d.]+).*?\[ATR/结构", text)
        self.assertIsNotNone(stop_match, text)
        stop = float(stop_match.group(1))
        self.assertGreater(stop, 60)
        self.assertLess(stop, session.get_last_price("US.RKLX"))

        self.assertIn("US.RKLB", session._target_state)
        self.assertIn("US.RKLX", session._target_state)
        self.assertGreater(session._target_state["US.RKLB"]["t1"], 110)
        self.assertLess(session._target_state["US.RKLX"]["t1"], 90)


if __name__ == "__main__":
    unittest.main()
