"""
VERSION : v0.5.1-test
DEPENDS : root.daily_briefing

Verify FIFO realized P/L and missed-signal matching for daily briefing.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "root"))
sys.path.insert(0, str(BASE))

import daily_briefing
from daily_briefing import _build_yesterday_review, _compute_fifo_pl, _load_initial_positions


class TestFifoPl(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path(tempfile.mkdtemp(prefix="mq_fifo_test_"))
        self.tmp_data = self.tmp_root / "data" / "review"
        self.tmp_data.mkdir(parents=True)
        self.old_base_dir = daily_briefing.BASE_DIR
        daily_briefing.BASE_DIR = self.tmp_root / "root"

    def tearDown(self):
        daily_briefing.BASE_DIR = self.old_base_dir
        shutil.rmtree(self.tmp_root, ignore_errors=True)

    def write_summary(self, date_str, positions_final):
        date_dir = self.tmp_data / date_str
        date_dir.mkdir(exist_ok=True)
        (date_dir / "session_summary.json").write_text(
            json.dumps({"date": date_str, "positions_final": positions_final}),
            encoding="utf-8",
        )

    def test_load_initial_positions_from_previous_trading_day(self):
        self.write_summary("2026-05-12", {
            "RKLX": {"qty": 18, "cost": 67.78, "pl_val": -10, "pl_pct": -0.5},
            "RKLZ": {"qty": 100, "cost": 5.50, "pl_val": 50, "pl_pct": 5.0},
        })
        positions = _load_initial_positions("2026-05-13")
        self.assertEqual(positions["US.RKLX"], {"qty": 18, "cost": 67.78})
        self.assertEqual(positions["US.RKLZ"], {"qty": 100, "cost": 5.50})

    def test_load_initial_positions_walks_back_across_missing_days(self):
        self.write_summary("2026-05-12", {"RKLX": {"qty": 18, "cost": 67.78}})
        positions = _load_initial_positions("2026-05-18")
        self.assertIn("US.RKLX", positions)

    def test_fifo_simple_buy_sell(self):
        deals = [
            {"code": "US.AAPL", "side": "BUY", "qty": 100, "price": 10.0, "create_time": "2026-05-13 09:30:00"},
            {"code": "US.AAPL", "side": "SELL", "qty": 50, "price": 12.0, "create_time": "2026-05-13 10:00:00"},
        ]
        result = _compute_fifo_pl(deals, initial_positions={})
        self.assertEqual(result["totals"]["realized_gross"], 100.0)
        self.assertEqual(result["totals"]["fees"], 1.0)
        self.assertEqual(result["totals"]["realized_net"], 99.0)
        self.assertEqual(result["trades"][1]["matched_lots"], [
            {"qty": 50, "buy_price": 10.0, "source": "09:30:00"}
        ])

    def test_fifo_consumes_inherited_lots_first(self):
        deals = [
            {"code": "US.RKLX", "side": "BUY", "qty": 44, "price": 67.78, "create_time": "2026-05-13 07:19:00"},
            {"code": "US.RKLX", "side": "SELL", "qty": 44, "price": 66.77, "create_time": "2026-05-13 08:36:00"},
            {"code": "US.RKLX", "side": "BUY", "qty": 20, "price": 74.08, "create_time": "2026-05-13 10:25:00"},
            {"code": "US.RKLX", "side": "SELL", "qty": 38, "price": 78.50, "create_time": "2026-05-13 14:55:00"},
        ]
        result = _compute_fifo_pl(deals, {"US.RKLX": {"qty": 18, "cost": 67.78}})
        self.assertEqual(result["trades"][1]["matched_lots"], [
            {"qty": 18, "buy_price": 67.78, "source": "继承"},
            {"qty": 26, "buy_price": 67.78, "source": "07:19:00"},
        ])
        self.assertAlmostEqual(result["trades"][1]["gross_pl"], -44.44, places=2)
        self.assertEqual(result["trades"][3]["matched_lots"], [
            {"qty": 18, "buy_price": 67.78, "source": "07:19:00"},
            {"qty": 20, "buy_price": 74.08, "source": "10:25:00"},
        ])
        self.assertAlmostEqual(result["trades"][3]["gross_pl"], 281.36, places=2)
        self.assertEqual(result["position_changes"], {"RKLX": (18, 0)})
        self.assertAlmostEqual(result["totals"]["realized_gross"], 236.92, places=2)
        self.assertAlmostEqual(result["totals"]["fees"], 1.64, places=2)

    def test_unmatched_sell_records_warning(self):
        deals = [
            {"code": "US.AAPL", "side": "BUY", "qty": 50, "price": 10.0, "create_time": "2026-05-13 09:30:00"},
            {"code": "US.AAPL", "side": "SELL", "qty": 100, "price": 12.0, "create_time": "2026-05-13 10:00:00"},
        ]
        result = _compute_fifo_pl(deals, {})
        self.assertEqual(result["trades"][1]["unmatched_qty"], 50)
        self.assertTrue(result["warnings"])

    def test_trade_matches_prior_signal_only(self):
        trigger_dir = self.tmp_data / "2026-05-14"
        trigger_dir.mkdir(exist_ok=True)
        triggers = [
            {"ts": "2026-05-14 09:05:00", "ticker": "US.RKLB", "direction": "long", "trigger": "direction_trend", "strength": "STRONG"},
            {"ts": "2026-05-14 10:00:00", "ticker": "US.RKLB", "direction": "long", "trigger": "swing_bottom", "strength": "STRONG"},
        ]
        (trigger_dir / "triggers.json").write_text(json.dumps(triggers), encoding="utf-8")
        self.write_summary("2026-05-13", {})
        review = _build_yesterday_review(
            "2026-05-14",
            [{"code": "US.RKLB", "side": "BUY", "qty": 10, "price": 100, "create_time": "2026-05-14 09:30:00"}],
            triggers,
        )
        self.assertEqual(review["trades"][0]["trigger"], "direction_trend")
        self.assertEqual(review["trades"][0]["gap_min"], 25.0)

    def test_existing_same_direction_position_is_not_missed(self):
        self.write_summary("2026-05-15", {"RKLB": {"qty": 50, "cost": 100.0}})
        review = _build_yesterday_review("2026-05-16", deals=[], triggers=[
            {"ts": "2026-05-16 09:00:00", "ticker": "US.RKLB", "direction": "long", "trigger": "direction_trend", "strength": "STRONG"}
        ])
        self.assertEqual(review["missed"], [])

    def test_trade_within_30_min_after_signal_is_not_missed(self):
        self.write_summary("2026-05-17", {})
        review = _build_yesterday_review(
            "2026-05-18",
            [{"code": "US.RKLB", "side": "BUY", "qty": 10, "price": 100, "create_time": "2026-05-18 09:20:00"}],
            [{"ts": "2026-05-18 09:00:00", "ticker": "US.RKLB", "direction": "long", "trigger": "direction_trend", "strength": "STRONG"}],
        )
        self.assertEqual(review["missed"], [])

    def test_no_position_and_no_trade_counts_as_missed(self):
        self.write_summary("2026-05-19", {})
        review = _build_yesterday_review("2026-05-20", deals=[], triggers=[
            {"ts": "2026-05-20 09:00:00", "ticker": "US.RKLB", "direction": "long", "trigger": "direction_trend", "strength": "STRONG"}
        ])
        self.assertEqual(len(review["missed"]), 1)


if __name__ == "__main__":
    unittest.main()
