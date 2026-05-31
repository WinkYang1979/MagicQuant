"""
MagicQuant - review_signal_coverage tests
VERSION : v0.1.0
DATE    : 2026-05-21
DEPENDS : scripts/review_signal_coverage.py
"""
from datetime import datetime
import unittest

from scripts.review_signal_coverage import (
    Bar,
    Wave,
    detect_major_waves,
    detect_major_waves_segmented,
    evaluate_wave_coverage,
    format_markdown,
    split_bars_by_gap,
    _records_outside_segments,
)


class ReviewSignalCoverageTests(unittest.TestCase):
    def test_detect_major_up_and_down_waves(self):
        bars = [
            Bar(datetime(2026, 5, 21, 9, 0), 100, 100, 99.8, 100),
            Bar(datetime(2026, 5, 21, 9, 5), 100, 103, 100, 102.8),
            Bar(datetime(2026, 5, 21, 9, 10), 102.8, 103.2, 101.8, 102),
            Bar(datetime(2026, 5, 21, 9, 15), 102, 102.1, 99.5, 99.8),
            Bar(datetime(2026, 5, 21, 9, 20), 99.8, 100.2, 97.8, 98),
        ]

        waves = detect_major_waves(bars, threshold_pct=2.0)

        self.assertGreaterEqual(len(waves), 2)
        self.assertEqual(waves[0].direction, "up")
        self.assertEqual(waves[1].direction, "down")

    def test_evaluate_wave_coverage_marks_timely_long(self):
        wave = Wave(
            direction="up",
            start=datetime(2026, 5, 21, 9, 0),
            end=datetime(2026, 5, 21, 9, 40),
            start_price=100,
            end_price=104,
            pct=4.0,
            high=104,
            low=100,
            dur_min=40,
            threshold_pct=2.0,
        )
        records = [
            {
                "ts": "2026-05-21 23:08:00",
                "trigger": "direction_trend",
                "direction": "long",
                "strength": "STRONG",
                "confidence": 80,
            }
        ]

        coverage = evaluate_wave_coverage(wave, records, timely_minutes=15)

        self.assertEqual(coverage["status"], "TIMELY")
        self.assertEqual(coverage["relevant_total"], 1)
        self.assertEqual(coverage["opposite_total"], 0)

    def test_evaluate_wave_coverage_marks_wrong_side(self):
        wave = Wave(
            direction="down",
            start=datetime(2026, 5, 21, 10, 0),
            end=datetime(2026, 5, 21, 10, 30),
            start_price=100,
            end_price=96,
            pct=-4.0,
            high=100,
            low=96,
            dur_min=30,
            threshold_pct=2.0,
        )
        records = [
            {
                "ts": "2026-05-22 00:10:00",
                "trigger": "swing_bottom",
                "direction": "long",
                "strength": "STRONG",
                "confidence": 75,
            }
        ]

        coverage = evaluate_wave_coverage(wave, records)

        self.assertEqual(coverage["status"], "WRONG_SIDE")
        self.assertEqual(coverage["opposite_total"], 1)

    def test_evaluate_wave_coverage_filters_follower_ticker(self):
        wave = Wave(
            direction="up",
            start=datetime(2026, 5, 21, 10, 0),
            end=datetime(2026, 5, 21, 10, 30),
            start_price=100,
            end_price=104,
            pct=4.0,
            high=104,
            low=100,
            dur_min=30,
            threshold_pct=2.0,
        )
        records = [
            {
                "ts": "2026-05-22 00:05:00",
                "ticker": "US.RKLX",
                "trigger": "drawdown_from_peak",
                "direction": "neutral",
                "strength": "STRONG",
                "confidence": 70,
                "data": {"current": 80.0},
            },
            {
                "ts": "2026-05-22 00:08:00",
                "ticker": "US.RKLB",
                "trigger": "direction_trend",
                "direction": "long",
                "strength": "STRONG",
                "confidence": 80,
                "data": {"current": 102.0},
            },
        ]

        coverage = evaluate_wave_coverage(wave, records, target_ticker="RKLB")

        self.assertEqual(coverage["signals_total"], 1)
        self.assertEqual(coverage["relevant_total"], 1)
        self.assertEqual(coverage["opposite_total"], 0)

    def test_wrong_side_strong_is_reported(self):
        wave = Wave(
            direction="down",
            start=datetime(2026, 5, 21, 10, 0),
            end=datetime(2026, 5, 21, 10, 30),
            start_price=100,
            end_price=96,
            pct=-4.0,
            high=100,
            low=96,
            dur_min=30,
            threshold_pct=2.0,
        )
        records = [
            {
                "ts": "2026-05-22 00:05:00",
                "ticker": "US.RKLB",
                "trigger": "direction_trend",
                "direction": "long",
                "strength": "STRONG",
                "confidence": 90,
                "prices": {"RKLB": 99.0},
            }
        ]

        coverage = evaluate_wave_coverage(wave, records, target_ticker="RKLB")

        self.assertEqual(coverage["status"], "WRONG_SIDE")
        self.assertEqual(coverage["opposite_strong_total"], 1)
        self.assertEqual(coverage["worst_opposite_minute"], 5)

    def test_markdown_includes_ticker_filter_and_wrong_strong_summary(self):
        wave = Wave(
            direction="down",
            start=datetime(2026, 5, 21, 10, 0),
            end=datetime(2026, 5, 21, 10, 30),
            start_price=100,
            end_price=96,
            pct=-4.0,
            high=100,
            low=96,
            dur_min=30,
            threshold_pct=2.0,
        )
        record = {
            "ts": "2026-05-22 00:05:00",
            "ticker": "US.RKLB",
            "trigger": "direction_trend",
            "direction": "long",
            "strength": "STRONG",
            "confidence": 90,
            "prices": {"RKLB": 99.0},
        }
        coverage = evaluate_wave_coverage(wave, [record], target_ticker="RKLB")
        markdown = format_markdown({
            "date": "2026-05-21",
            "ticker": "RKLB",
            "bar_source": "test",
            "threshold_pct": 2.0,
            "atr_mult": 1.0,
            "all_records": [record, {"ticker": "US.RKLX"}],
            "records": [record],
            "bars": [],
            "segments": [],
            "out_of_session_records": [],
            "waves": [{"wave": wave, "coverage": coverage}],
        })

        self.assertIn("Trigger records excluded by ticker filter: 1", markdown)
        self.assertIn("Wrong-side STRONG signals: 1", markdown)
        self.assertIn("Highest-confidence opposite signal", markdown)

    def test_split_bars_by_gap_prevents_overnight_wave(self):
        bars = [
            Bar(datetime(2026, 5, 20, 19, 58), 100, 103, 100, 103),
            Bar(datetime(2026, 5, 20, 20, 0), 103, 104, 102, 103),
            Bar(datetime(2026, 5, 21, 4, 1), 103, 103, 99, 100),
            Bar(datetime(2026, 5, 21, 4, 2), 100, 101, 99, 100),
        ]

        segments = split_bars_by_gap(bars, gap_minutes=30)
        wave_items, _ = detect_major_waves_segmented(bars, threshold_pct=2.0, gap_minutes=30)

        self.assertEqual(len(segments), 2)
        for item in wave_items:
            self.assertLessEqual(item["wave"].end, item["segment"]["end"])
            self.assertGreaterEqual(item["wave"].start, item["segment"]["start"])

    def test_gap_signal_is_not_counted_inside_wave(self):
        segments = [
            {
                "id": "S1",
                "start": datetime(2026, 5, 20, 19, 50),
                "end": datetime(2026, 5, 20, 20, 0),
                "bars": [],
                "session": "afterhours",
                "gap_before_min": None,
            },
            {
                "id": "S2",
                "start": datetime(2026, 5, 21, 4, 1),
                "end": datetime(2026, 5, 21, 4, 10),
                "bars": [],
                "session": "premarket",
                "gap_before_min": 481,
            },
        ]
        records = [
            {
                "ts": "2026-05-21 12:30:00",  # local -> 05-20 22:30 ET
                "ticker": "US.RKLB",
                "trigger": "intraday_reversal",
                "direction": "long",
                "strength": "STRONG",
                "confidence": 85,
            }
        ]

        out = _records_outside_segments(records, segments)

        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
