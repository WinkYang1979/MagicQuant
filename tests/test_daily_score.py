import unittest
from datetime import date
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = PROJECT_ROOT / "research" / "vectorbt_lab"
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))

import daily_score
from daily_rklb_review import Wave


class DailyScoreTests(unittest.TestCase):
    def make_bars(self):
        ts = pd.date_range("2026-05-28 13:30:00Z", periods=60, freq="1min")
        close = [100 + i * 0.05 for i in range(60)]
        return pd.DataFrame({
            "timestamp": ts,
            "open": close,
            "high": [v + 0.05 for v in close],
            "low": [v - 0.05 for v in close],
            "close": close,
            "volume": [1000] * 60,
            "symbol": ["RKLB"] * 60,
        })

    def test_long_signal_scores_correct(self):
        bars = self.make_bars()
        record = {
            "trigger": "direction_trend",
            "direction": "long",
            "strength": "STRONG",
            "confidence": 85,
            "data": {"current": 100.0, "data_quality": {"last_bar_time": "2026-05-28 09:30:00"}},
        }
        scored = daily_score.score_signal(record, bars)
        self.assertIsNotNone(scored)
        self.assertEqual(scored.outcome, "correct")

    def test_daily_score_counts_miss_and_suggestion(self):
        bars = self.make_bars()
        waves = [Wave(bars["timestamp"].iloc[0], bars["timestamp"].iloc[-1], "UP", 100.0, 103.0, 3.0)]
        score = daily_score.build_daily_score(date(2026, 5, 28), bars, waves, [])
        self.assertEqual(score["miss"], 1)
        self.assertTrue(any("上涨" in item or "反弹" in item for item in score["suggestions"]))


if __name__ == "__main__":
    unittest.main()
