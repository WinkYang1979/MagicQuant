"""
VERSION : v0.5.36-test
DEPENDS : core.focus.context, core.focus.position_followup, core.focus.pusher

Regression tests for held-position follow-up and confidence caps.
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.focus.context import FocusSession
from core.focus.position_followup import check_position_followup
from core.focus.pusher import _confidence_score, _fmt_position_followup


def make_session(cost=97.0, current=96.9):
    session = FocusSession("US.RKLB", ["US.RKLX", "US.RKLZ"])
    for price in [97.0, 95.0, 93.4, 94.2, 95.7, current]:
        session.update_price("US.RKLX", price)
    session.positions_snapshot = {
        "US.RKLX": {
            "qty": 34,
            "cost_price": cost,
            "current_price": current,
            "pl_val": round((current - cost) * 34, 2),
            "pl_pct": round((current - cost) / cost * 100, 2),
        }
    }
    session._target_state = {
        "US.RKLX": {
            "direction": "long",
            "t1": 101.2,
            "t2": 104.0,
            "stop": 93.5,
            "set_at_price": cost,
            "set_at_ts": time.time() - 900,
        }
    }
    return session


class TestPositionFollowupV0536(unittest.TestCase):
    def test_cost_retest_after_adverse_move_is_single_shot(self):
        session = make_session(current=96.9)
        hit = check_position_followup(session, "US.RKLX")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "position_followup")
        self.assertEqual(hit["data"]["state"], "COST_RETEST")
        text = _fmt_position_followup(hit, session)["text"]
        self.assertIn("回到成本", text)

        self.assertIsNone(check_position_followup(session, "US.RKLX"))

    def test_invalidated_uses_existing_atr_stop(self):
        session = make_session(current=93.4)
        hit = check_position_followup(session, "US.RKLX")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["data"]["state"], "INVALIDATED")
        self.assertEqual(hit["data"]["stop"], 93.5)

    def test_invalidated_is_one_shot_until_new_lower_stage(self):
        session = make_session(current=93.4)
        first = check_position_followup(session, "US.RKLX")
        self.assertIsNotNone(first)
        self.assertEqual(first["data"]["state"], "INVALIDATED")

        session.last_trigger_time["position_followup_invalidated_US.RKLX"] = 0
        session.update_price("US.RKLX", 93.2)
        second = check_position_followup(session, "US.RKLX")
        self.assertIsNone(second)

        session.update_price("US.RKLX", 90.4)
        third = check_position_followup(session, "US.RKLX")
        self.assertIsNotNone(third)
        self.assertEqual(third["data"]["state"], "INVALIDATED")

    def test_rsi_rollover_removes_good_zone_bonus(self):
        hit = {
            "trigger": "direction_trend",
            "direction": "long",
            "strength": "STRONG",
            "data": {
                "rsi": 58,
                "rsi_history": [66, 62, 58],
                "vol_ratio": 1.0,
            },
        }
        score = _confidence_score(hit)
        self.assertLessEqual(score, 70)
        self.assertIn("rsi_rolling_over", hit["data"]["cap_reasons"])

    def test_post_top_warning_confidence_cap(self):
        hit = {
            "trigger": "direction_trend",
            "direction": "long",
            "strength": "STRONG",
            "data": {
                "rsi": 58,
                "rsi_history": [56, 57, 58],
                "vol_ratio": 1.5,
                "confidence_cap": 65,
            },
        }
        self.assertEqual(_confidence_score(hit), 65)
        self.assertIn("post_top_warning_cap", hit["data"]["cap_reasons"])

    # ── v0.5.36 hotfix 后续(claude review fixes)──

    def test_rsi_rollover_threshold_lowered_to_50_catches_54_5(self):
        """11:02 那笔 RSI 54.5 滚自 66.7,旧阈值 r>=55 漏掉;新阈值 r>=50 应抓住。"""
        hit = {
            "trigger": "direction_trend",
            "direction": "long",
            "strength": "STRONG",
            "data": {
                "rsi": 54.5,
                "rsi_history": [66.7, 60.0, 54.5],   # 明显滚下来
                "vol_ratio": 1.0,
            },
        }
        score = _confidence_score(hit)
        self.assertIn("rsi_rolling_over", hit["data"]["cap_reasons"])
        # 旧版会给 +15 → ~85;新版不给 → 50+20+0+0 = 70 左右
        self.assertLessEqual(score, 75)

    def test_mark_top_warning_wires_through_to_recent_top_warning(self):
        """端到端 wire:swing_detector._mark_top_warning 写入后,_recent_top_warning 应读到。
        这条防止 v0.5.36 那种"helper 定义但没人调"的死代码再次出现。"""
        from core.focus import swing_detector as sd
        session = make_session()
        sd._mark_top_warning(session, "US.RKLB", "near_resistance")
        info = sd._recent_top_warning(session, "US.RKLB", window_sec=300)
        self.assertIsNotNone(info)
        self.assertEqual(info["trigger"], "near_resistance")
        # 超时后应失效
        info = sd._recent_top_warning(session, "US.RKLB", window_sec=0)
        self.assertIsNone(info)

    def test_top_watch_fires_after_recent_top_warning(self):
        """持仓中 + session 有最近顶部风险标记 → TOP_WATCH 应触发(接管被压制的 near_resistance 等)。"""
        from core.focus import swing_detector as sd
        # 不让它进 COST_RETEST 路径:price 远离成本
        session = make_session(cost=97.0, current=99.5)
        # 触发顶部风险标记
        sd._mark_top_warning(session, "US.RKLX", "near_resistance")
        # 清掉 trough 状态防止 cost_retest 干扰
        session.trough_price = {"US.RKLX": 99.0}
        hit = check_position_followup(session, "US.RKLX",
                                      indicators={"rsi_5m": 55, "vwap": 99.0})
        self.assertIsNotNone(hit)
        self.assertEqual(hit["data"]["state"], "TOP_WATCH")
        self.assertIn("recent_near_resistance", hit["data"]["reason"])

    def test_structural_invalidated_without_prior_cost_retest(self):
        """5m 结构破位 + 浮亏 ≥ 1.5%,即使没经过 COST_RETEST 也应判定 INVALIDATED(structural)。"""
        session = make_session(cost=97.0, current=94.5)   # adverse from cost ~2.5%
        # 5m bars 显示破位:close[-1] < vwap & close 递降
        indicators = {
            "rsi_5m": 45, "vwap": 95.5,
            "bars": [
                {"close": 96.0, "high": 96.5, "low": 95.8},
                {"close": 95.0, "high": 95.5, "low": 94.6},
                {"close": 94.5, "high": 94.9, "low": 94.3},
            ],
        }
        # 让 trough 比 cost 低 2.5%,触发 adverse_pct >= 1.5
        session.trough_price = {"US.RKLX": 94.5}
        hit = check_position_followup(session, "US.RKLX", indicators=indicators)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["data"]["state"], "INVALIDATED")
        self.assertEqual(hit["data"]["reason"], "structural_breakdown")


if __name__ == "__main__":
    unittest.main()
