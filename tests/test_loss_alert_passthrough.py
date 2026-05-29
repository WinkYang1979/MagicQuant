"""
VERSION : v0.5.27-test
DEPENDS : core.focus.context, core.focus.swing_detector, core.focus.pusher

Verify losing positions are handled by stop_loss_warning, not profit_target.
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.focus.context import FocusSession
from core.focus.pusher import _fmt_profit_target, _fmt_stop_loss_warning
from core.focus.swing_detector import check_profit_target, check_stop_loss_warning


def make_session_with_loss(cost=74.08, current=71.83):
    session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
    prices = [76.5, 76.2, 75.8, 75.0, 74.5, 73.8, 73.0, 72.5, 72.2, 72.0, 71.9, 71.85, current]
    for price in prices:
        session.update_price("US.RKLX", price)
    session.positions_snapshot = {
        "US.RKLX": {
            "qty": 20,
            "cost_price": cost,
            "current_price": current,
            "market_val": 20 * current,
            "pl_val": round((current - cost) * 20, 2),
            "pl_pct": round((current - cost) / cost * 100, 2),
        }
    }
    session.get_position = lambda tk: session.positions_snapshot.get(tk)
    session.get_position_age_sec = lambda tk: 7200
    session._target_state = {
        "US.RKLX": {
            "direction": "long",
            "t1": 80.00,
            "t2": 81.31,
            "stop": 72.20,
            "set_at_price": 76.0,
            "set_at_ts": time.time() - 3600,
        }
    }
    return session


class TestLossAlertPassthrough(unittest.TestCase):
    def test_profit_target_is_silent_for_losing_position(self):
        session = make_session_with_loss()
        self.assertIsNone(check_profit_target(session, "US.RKLX", indicators=None))

    def test_stop_loss_warning_handles_losing_position(self):
        session = make_session_with_loss()
        hit = check_stop_loss_warning(session, "US.RKLX")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "stop_loss_warning")
        self.assertEqual(hit["data"]["sub_kind"], "breached")
        self.assertEqual(hit["level"], "URGENT")

        text = _fmt_stop_loss_warning(hit, session=session)["text"]
        self.assertIn("目前亏损", text)
        self.assertNotIn("目前盈利", text)
        self.assertTrue("🛑" in text or "📉" in text)

    def test_stop_above_current_uses_current_based_leftover_stop(self):
        session = make_session_with_loss()
        hit = check_stop_loss_warning(session, "US.RKLX")
        text = _fmt_stop_loss_warning(hit, session=session)["text"]
        self.assertIn("$70.39", text)

    def test_small_loss_is_silent(self):
        session = make_session_with_loss(cost=74.08, current=72.97)
        session.last_trigger_time = {}
        self.assertIsNone(check_stop_loss_warning(session, "US.RKLX"))

    def test_profit_path_still_works(self):
        session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
        for price in [76.0, 76.5, 77.0, 77.5, 78.0, 78.5, 79.0, 79.3, 79.5, 79.6, 79.7]:
            session.update_price("US.RKLX", price)
        session.positions_snapshot = {
            "US.RKLX": {
                "qty": 20,
                "cost_price": 74.08,
                "current_price": 79.7,
                "market_val": 20 * 79.7,
                "pl_val": round((79.7 - 74.08) * 20, 2),
                "pl_pct": round((79.7 - 74.08) / 74.08 * 100, 2),
            }
        }
        session.get_position = lambda tk: session.positions_snapshot.get(tk)
        session.get_position_age_sec = lambda tk: 7200
        session._target_state = {
            "US.RKLX": {
                "direction": "long",
                "t1": 80.00,
                "t2": 81.31,
                "stop": 72.20,
                "set_at_price": 76.0,
                "set_at_ts": time.time() - 3600,
            }
        }
        hit = check_profit_target(session, "US.RKLX", indicators=None)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["data"]["sub_reason"], "near_target")
        self.assertIn("目前盈利", _fmt_profit_target(hit, session=session)["text"])

    def test_peak_below_cost_does_not_trigger_profit_target(self):
        session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
        for price in [71.21, 71.10, 70.80, 70.50, 70.20, 70.00, 69.80, 69.70, 69.64]:
            session.update_price("US.RKLX", price)
        session.positions_snapshot = {
            "US.RKLX": {
                "qty": 20,
                "cost_price": 74.08,
                "current_price": 69.64,
                "market_val": 20 * 69.64,
                "pl_val": round((69.64 - 74.08) * 20, 2),
                "pl_pct": round((69.64 - 74.08) / 74.08 * 100, 2),
            }
        }
        session.get_position = lambda tk: session.positions_snapshot.get(tk)
        session.get_position_age_sec = lambda tk: 7200
        self.assertIsNone(check_profit_target(session, "US.RKLX", indicators=None))
        self.assertIsNotNone(check_stop_loss_warning(session, "US.RKLX"))


if __name__ == "__main__":
    unittest.main()
