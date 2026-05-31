"""
MagicQuant test_weekly_dependency_update.py
VERSION : v0.1.0
DEPENDS : scripts.weekly_dependency_update

Tests for the weekend dependency updater state gates.
周末依赖更新器测试：验证周末门禁和每周去重状态。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "weekly_dependency_update.py"


def load_module():
    spec = importlib.util.spec_from_file_location("weekly_dependency_update", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeeklyDependencyUpdateTest(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_weekend_allowed_only_saturday_or_sunday(self):
        saturday = datetime(2026, 5, 30, 10, 0)
        sunday = datetime(2026, 5, 31, 10, 0)
        monday = datetime(2026, 6, 1, 10, 0)
        self.assertTrue(self.mod.weekend_allowed(saturday))
        self.assertTrue(self.mod.weekend_allowed(sunday))
        self.assertFalse(self.mod.weekend_allowed(monday))

    def test_iso_week_key_is_stable(self):
        self.assertEqual(self.mod.iso_week_key(datetime(2026, 5, 30, 10, 0)), "2026-W22")

    def test_already_done_this_week_requires_success(self):
        state = {"last_update": {"iso_week": "2026-W22", "success": True}}
        self.assertTrue(self.mod.already_done_this_week(state, "2026-W22"))
        self.assertFalse(self.mod.already_done_this_week(state, "2026-W23"))
        self.assertFalse(self.mod.already_done_this_week({"last_update": {"iso_week": "2026-W22", "success": False}}, "2026-W22"))

    def test_missing_trading_agents_repo_is_safe_skip(self):
        self.mod.TRADING_AGENTS_DIR = ROOT / "tests" / "__missing_trading_agents__"
        result = self.mod.update_trading_agents(dry_run=True)
        self.assertFalse(result.updated)
        self.assertTrue(result.success)
        self.assertIn("skipped", result.message)


if __name__ == "__main__":
    unittest.main()
