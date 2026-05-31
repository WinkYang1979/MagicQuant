import unittest
import contextlib
import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = PROJECT_ROOT / "research" / "vectorbt_lab"
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))

import scheduler


class VectorBTSchedulerTests(unittest.TestCase):
    def local_dt(self, year, month, day, hour, minute=0):
        return datetime(year, month, day, hour, minute, tzinfo=scheduler.LOCAL_TZ)

    def test_daily_runs_after_7_once_per_local_date(self):
        now = self.local_dt(2026, 5, 29, 7, 1)
        self.assertTrue(scheduler.should_run_daily(now, {}, force=False))
        state = {"last_daily_run": {"date": "2026-05-29", "success": True}}
        self.assertFalse(scheduler.should_run_daily(now, state, force=False))

    def test_daily_waits_until_7(self):
        now = self.local_dt(2026, 5, 29, 6, 59)
        self.assertFalse(scheduler.should_run_daily(now, {}, force=False))

    def test_weekly_runs_sunday_after_9_and_retries_failed_week(self):
        now = self.local_dt(2026, 5, 31, 9, 1)
        year, week = scheduler.iso_week_key(now)
        self.assertTrue(scheduler.should_run_weekly(now, {}, force=False))
        self.assertFalse(scheduler.should_run_weekly(now, {"last_weekly_run": {"iso_year": year, "iso_week": week, "success": True}}, force=False))
        self.assertTrue(scheduler.should_run_weekly(now, {"last_weekly_run": {"iso_year": year, "iso_week": week, "success": False}}, force=False))

    def test_daily_review_runs_after_8_once_per_local_date(self):
        now = self.local_dt(2026, 5, 29, 8, 1)
        self.assertTrue(scheduler.should_run_daily_review(now, {}, force=False))
        state = {"last_daily_review": {"date": "2026-05-29", "success": True}}
        self.assertFalse(scheduler.should_run_daily_review(now, state, force=False))

    def test_daily_review_waits_until_8(self):
        now = self.local_dt(2026, 5, 29, 7, 59)
        self.assertFalse(scheduler.should_run_daily_review(now, {}, force=False))

    def test_weekly_waits_until_sunday_9(self):
        saturday = self.local_dt(2026, 5, 30, 10, 0)
        sunday_early = self.local_dt(2026, 5, 31, 8, 59)
        self.assertFalse(scheduler.should_run_weekly(saturday, {}, force=False))
        self.assertFalse(scheduler.should_run_weekly(sunday_early, {}, force=False))

    def test_force_is_blocked_during_rth(self):
        rth_et = datetime(2026, 6, 1, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        now = rth_et.astimezone(scheduler.LOCAL_TZ)
        self.assertTrue(scheduler.is_rth(now))
        self.assertFalse(scheduler.should_run_daily(now, {}, force=True))
        self.assertFalse(scheduler.should_run_daily_review(now, {}, force=True))
        self.assertFalse(scheduler.should_run_weekly(now, {}, force=True))

    def test_force_runs_outside_rth(self):
        now = self.local_dt(2026, 5, 29, 12, 0)
        self.assertFalse(scheduler.is_rth(now))
        self.assertTrue(scheduler.should_run_daily(now, {"last_daily_run": {"date": "2026-05-29", "success": True}}, force=True))
        self.assertTrue(scheduler.should_run_daily_review(now, {"last_daily_review": {"date": "2026-05-29", "success": True}}, force=True))
        self.assertTrue(scheduler.should_run_weekly(now, {"last_weekly_run": {"iso_year": 2026, "iso_week": 22, "success": True}}, force=True))

    def test_weekly_deep_dry_run_uses_deep_miner_without_extra_telegram(self):
        state = {}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            scheduler.run_weekly_pipeline(state, "test", dry_run=True, deep=True)
        text = buf.getvalue()

        self.assertIn("--trials 200", text)
        self.assertIn("--seeds", text)
        self.assertNotIn("--telegram", text)
        self.assertEqual(state, {})


if __name__ == "__main__":
    unittest.main()
