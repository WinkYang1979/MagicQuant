"""
MagicQuant test_strategy_miner_multi_run.py
VERSION : v0.2.0
DEPENDS : research.vectorbt_lab.strategy_miner_multi_run, optuna_strategy_miner
PURPOSE : Verify isolated rolling OOS strategy validation.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "research" / "vectorbt_lab"
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

import optuna_strategy_miner as miner
import strategy_miner_multi_run as multi


def tiny_bars() -> pd.DataFrame:
    ts = pd.date_range("2026-05-01 09:30:00", periods=6, freq="5min", tz=miner.ET)
    rows = []
    for idx, stamp in enumerate(ts):
        rows.append({
            "timestamp": stamp,
            "et_date": stamp.date(),
            "minute": stamp.hour * 60 + stamp.minute,
            "atr_pct": 0.1,
            "rklx_open": 20.0,
            "rklx_high": 20.4,
            "rklx_low": 19.8,
            "rklx_close": 20.1,
            "rklz_open": 10.0 if idx <= 1 else 10.4,
            "rklz_high": 10.9 if idx >= 2 else 10.2,
            "rklz_low": 9.9,
            "rklz_close": 10.7 if idx >= 2 else 10.1,
        })
    return pd.DataFrame(rows)


def multi_day_bars(days: int = 16) -> pd.DataFrame:
    rows = []
    for day in range(days):
        base = pd.Timestamp("2026-05-01 09:30:00", tz=miner.ET) + pd.Timedelta(days=day)
        for step in range(3):
            stamp = base + pd.Timedelta(minutes=5 * step)
            rows.append({
                "timestamp": stamp,
                "et_date": stamp.date(),
                "minute": stamp.hour * 60 + stamp.minute,
                "atr_pct": 0.1,
                "rklx_open": 20.0 + step * 0.1,
                "rklx_high": 21.0,
                "rklx_low": 19.5,
                "rklx_close": 20.6,
                "rklz_open": 10.0,
                "rklz_high": 10.5,
                "rklz_low": 9.8,
                "rklz_close": 10.2,
            })
    return pd.DataFrame(rows)


class StrategyMinerMultiRunTest(unittest.TestCase):
    def test_short_rklb_buys_rklz_and_profit_when_rklz_rises(self):
        original = dict(miner.SIGNAL_FUNCS)
        try:
            miner.SIGNAL_FUNCS["unit_short"] = lambda bars, _params: pd.DataFrame({"direction": [-1, 0, 0, 0, 0, 0]}, index=bars.index)
            summary, trades = miner.simulate(
                tiny_bars(),
                "unit_short",
                {
                    "cooldown_bars": 1,
                    "stop_pct": 2.0,
                    "target_pct": 3.0,
                    "stop_atr_mult": 0.0,
                    "rr_min": 1.0,
                    "max_hold_bars": 5,
                },
                trade_value=1000.0,
            )
        finally:
            miner.SIGNAL_FUNCS.clear()
            miner.SIGNAL_FUNCS.update(original)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["tool"], "RKLZ")
        self.assertGreater(trades[0]["net_pnl"], 0)
        self.assertGreater(summary["fee_adjusted_pnl"], 0)
        self.assertIn("mae_pct", trades[0])
        self.assertIn("mfe_pct", trades[0])
        self.assertIn("bars_to_mae", trades[0])
        self.assertIn("bars_to_mfe", trades[0])

    def test_rolling_holdout_has_no_train_oos_overlap(self):
        bars = multi_day_bars(80)

        folds = multi.rolling_holdout_folds(bars, folds=5, oos_days=10, step_days=5)

        self.assertEqual(len(folds), 5)
        for fold in folds:
            self.assertTrue(fold.train_days.isdisjoint(fold.oos_days))
            self.assertEqual(len(fold.oos_days), 10)

    def test_zero_tool_open_is_skipped_instead_of_crashing(self):
        original = dict(miner.SIGNAL_FUNCS)
        bars = tiny_bars()
        bars.loc[1, "rklz_open"] = 0.0
        try:
            miner.SIGNAL_FUNCS["unit_short"] = lambda frame, _params: pd.DataFrame({"direction": [-1, 0, 0, 0, 0, 0]}, index=frame.index)
            summary, trades = miner.simulate(
                bars,
                "unit_short",
                {
                    "cooldown_bars": 1,
                    "stop_pct": 2.0,
                    "target_pct": 3.0,
                    "stop_atr_mult": 0.0,
                    "rr_min": 1.0,
                    "max_hold_bars": 5,
                },
            )
        finally:
            miner.SIGNAL_FUNCS.clear()
            miner.SIGNAL_FUNCS.update(original)

        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(trades, [])

    def test_cross_seed_oos_matrix_shape(self):
        original = dict(miner.SIGNAL_FUNCS)
        bars = multi_day_bars(20)
        folds = multi.rolling_holdout_folds(bars, folds=2, oos_days=3, step_days=2)
        try:
            miner.SIGNAL_FUNCS["unit_long"] = lambda frame, _params: pd.DataFrame({"direction": [1] + [0] * (len(frame) - 1)}, index=frame.index)
            rows = [
                {"seed": 11, "strategy": "unit_long", "params": '{"cooldown_bars": 1, "stop_pct": 2.0, "target_pct": 3.0, "stop_atr_mult": 0.0, "rr_min": 1.0, "max_hold_bars": 2}'},
                {"seed": 22, "strategy": "unit_long", "params": '{"cooldown_bars": 1, "stop_pct": 2.0, "target_pct": 3.0, "stop_atr_mult": 0.0, "rr_min": 1.0, "max_hold_bars": 2}'},
            ]
            matrix = multi.cross_seed_oos_matrix(rows, bars, folds)
        finally:
            miner.SIGNAL_FUNCS.clear()
            miner.SIGNAL_FUNCS.update(original)

        self.assertEqual(matrix["unit_long"]["total_cells"], 4)

    def test_promotion_gate_rejects_low_trade_count(self):
        best = {
            "cross_positive_cells": 25,
            "median_positive_folds": 5,
            "median_oos_trades": 14,
            "median_profit_factor": 1.5,
            "median_p_value": 0.1,
            "median_trade_sharpe": 1.0,
            "median_signal_density": 0.5,
        }

        ok, _passed, failed = multi.promotion_check(best, live_relevance_passed=True)

        self.assertFalse(ok)
        self.assertIn("median OOS trades >= 15", failed)

    def test_promotion_gate_requires_live_relevance(self):
        aggregate = [{
            "strategy": "breakout",
            "cross_positive_cells": 25,
            "median_positive_folds": 5,
            "median_oos_trades": 20,
            "median_profit_factor": 1.5,
            "median_p_value": 0.1,
            "median_trade_sharpe": 1.0,
            "median_signal_density": 0.5,
        }]

        decision, _reason, _passed, failed = multi.best_decision(aggregate, live_relevance_passed=False)

        self.assertEqual(decision, "research_only_pending_live_relevance")
        self.assertEqual(failed, ["live relevance replay passed"])

    def test_summary_row_accepts_walk_forward_avg_drawdown(self):
        row = multi._summary_row({
            "fee_adjusted_pnl": 10.0,
            "return_pct": 1.0,
            "trade_count": 2,
            "win_rate": 50.0,
            "profit_factor": 1.2,
            "avg_max_drawdown": -3.4,
        }, "train")

        self.assertEqual(row["train_max_drawdown"], -3.4)

    def test_telegram_text_is_generated_without_network(self):
        text = multi.build_telegram_text({
            "report_path": "report.md",
            "decision": "research_only_pending_live_relevance",
            "reason": "needs replay",
            "best": {
                "strategy": "breakout",
                "median_oos_pnl": 100.0,
                "cross_positive_cells": 18,
                "cross_total_cells": 25,
                "median_oos_trades": 20,
                "median_profit_factor": 1.2,
            },
        })

        self.assertIn("VectorBT/Optuna rolling OOS completed", text)
        self.assertIn("research_only_pending_live_relevance", text)


if __name__ == "__main__":
    unittest.main()
