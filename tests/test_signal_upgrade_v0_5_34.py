"""
VERSION : v0.5.34-test
DEPENDS : core.focus.context, core.focus.swing_detector

回放 2026-05-14 / 2026-05-16 的真实 triggers.json, 锁定 v0.5.34 信号升级。
Replay real review fixtures and verify the v0.5.34 alert gates.
"""

import json
import sys
import time
import unittest
import importlib.util
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
MASTER = "US.RKLB"
FOLLOWERS = ["US.RKLX", "US.RKLZ"]


def _load_module(name, rel_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


context_mod = _load_module("mq_focus_context_v0534", "core/focus/context.py")
sd = _load_module("mq_swing_detector_v0534", "core/focus/swing_detector.py")
FocusSession = context_mod.FocusSession
data_quality = _load_module("mq_data_quality_v0535", "core/focus/data_quality.py")
kline_display = _load_module("mq_kline_display_v0535", "core/focus/kline_display.py")
pusher = _load_module("mq_pusher_v0535", "core/focus/pusher.py")


def _load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _indicators(record):
    dc = record.get("decision_context") or {}
    raw = dc.get("indicators_raw") or {}
    bars = (dc.get("kline_data") or {}).get("bars") or []
    return {
        "data_ok": bool(raw.get("data_ok", True)),
        "is_today": raw.get("is_today", True),
        "rsi_5m": raw.get("rsi_14"),
        "rsi_history": raw.get("rsi_history"),
        "vwap": raw.get("vwap"),
        "vol_ratio": raw.get("vol_ratio"),
        "session_high": raw.get("session_high"),
        "session_low": raw.get("session_low"),
        "dist_high": raw.get("dist_high"),
        "dist_low": raw.get("dist_low"),
        "candle": raw.get("candle") or {},
        "kline_bars": bars,
    }


def _sync_session(session, record):
    prices = record.get("prices") or {}
    for short, price in prices.items():
        ticker = "US." + short
        if price:
            session.update_price(ticker, float(price))

    for ticker in [MASTER] + FOLLOWERS:
        day_chg = None
        if ticker == record.get("ticker"):
            day_chg = (record.get("data") or {}).get("day_change_pct")
        if ticker == MASTER:
            day_chg = day_chg if day_chg is not None else ((record.get("decision_context") or {})
                      .get("price_context") or {}).get("day_change_pct")
        if day_chg is not None:
            session.quote_snapshot[ticker] = {"change_pct": day_chg}

    session.cash_available = record.get("cash_available")
    session.positions_snapshot = {}
    for short, pos in (record.get("positions") or {}).items():
        ticker = "US." + short
        if isinstance(pos, dict):
            session.positions_snapshot[ticker] = pos


def _replay_v0534(records):
    """只回放本次升级涉及的降噪门 / replay only gates changed in v0.5.34."""
    session = FocusSession(MASTER, FOLLOWERS)
    kept = []
    near_support_last_ts = {}
    target_last_ts = {}
    strong_long_count = 0
    trend_hold_locked = False

    for record in records:
        _sync_session(session, record)
        ind = _indicators(record)
        trigger = record.get("trigger")
        ticker = record.get("ticker")
        ts = datetime.strptime(record["ts"], "%Y-%m-%d %H:%M:%S").timestamp()

        ind.pop("_stale_checked", None)
        stale = sd._update_indicator_stale(session, ind, sd.DEFAULT_PARAMS)
        if stale and trigger != "stop_loss_warning":
            continue

        if trigger == "rapid_move" and ticker in FOLLOWERS:
            continue

        if trigger == "direction_trend":
            if record.get("direction") == "long" and record.get("strength") == "STRONG":
                strong_long_count += 1
                if strong_long_count >= sd.DEFAULT_PARAMS["trend_lock_required_hits"]:
                    trend_hold_locked = True
            elif record.get("direction") == "short":
                strong_long_count = 0

        if trigger == "swing_bottom":
            if record.get("strength") == "WEAK":
                continue
            count, _ = sd._strong_bottom_confirmations(session, ticker, ind, sd.DEFAULT_PARAMS)
            if count < sd.DEFAULT_PARAMS["swing_bottom_weak_confirm_required"]:
                continue

        if trigger == "near_support":
            last = near_support_last_ts.get(ticker)
            if last is not None and ts - last < sd.DEFAULT_PARAMS["near_support_cooldown"]:
                continue
            near_support_last_ts[ticker] = ts

        if trigger == "profit_target_hit":
            data = record.get("data") or {}
            trend_hold = trend_hold_locked or sd._is_strong_market(session, MASTER, ind, sd.DEFAULT_PARAMS)
            if trend_hold and data.get("sub_reason") not in ("overbought_surge", "drawdown", "volume_dry"):
                continue

        if trigger == "target_advance":
            last = target_last_ts.get(ticker)
            cooldown = sd.DEFAULT_PARAMS["target_advance_trend_cooldown"]
            if last is not None and ts - last < cooldown:
                continue
            target_last_ts[ticker] = ts

        kept.append(record)
    return kept


class TestSignalUpgradeV0534(unittest.TestCase):
    def test_direction_skip_right_when_down_gap_has_no_intraday_trend(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session._disable_review_log = True
        now = time.time()
        session.prices[MASTER] = [
            (now - 900, 127.0),
            (now - 600, 127.2),
            (now - 300, 126.9),
            (now, 127.05),
        ]
        session.quote_snapshot[MASTER] = {"change_pct": -3.1}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 52.0,
            "vol_ratio": 0.65,
            "vwap": 127.0,
        }

        self.assertIsNone(sd.check_direction_trend(session, MASTER, indicators, sd.DEFAULT_PARAMS))
        skips = getattr(session, "_direction_skips", [])
        self.assertEqual(skips[-1]["blocked_by"], "rsi_too_high_for_short")
        self.assertEqual(skips[-1]["skip_class"], "right_skip")

    def test_direction_skip_wrong_when_short_guard_blocks_real_downtrend(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session._disable_review_log = True
        now = time.time()
        session.prices[MASTER] = [
            (now - 850, 100.0),
            (now - 600, 99.0),
            (now - 300, 98.4),
            (now, 98.0),
        ]
        session.quote_snapshot[MASTER] = {"change_pct": -4.5}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 52.0,
            "vol_ratio": 1.2,
            "vwap": 98.8,
        }

        self.assertIsNone(sd.check_direction_trend(session, MASTER, indicators, sd.DEFAULT_PARAMS))
        skips = getattr(session, "_direction_skips", [])
        self.assertEqual(skips[-1]["blocked_by"], "rsi_too_high_for_short")
        self.assertEqual(skips[-1]["skip_class"], "wrong_skip")

    def test_direction_skip_extreme_oversold_guard_is_right_skip(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session._disable_review_log = True
        now = time.time()
        session.prices[MASTER] = [
            (now - 850, 100.0),
            (now - 600, 98.9),
            (now - 300, 98.2),
            (now, 97.9),
        ]
        session.quote_snapshot[MASTER] = {"change_pct": -5.0}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 25.0,
            "vol_ratio": 2.0,
            "vwap": 99.0,
        }

        self.assertIsNone(sd.check_direction_trend(session, MASTER, indicators, sd.DEFAULT_PARAMS))
        skips = getattr(session, "_direction_skips", [])
        self.assertEqual(skips[-1]["blocked_by"], "rsi_oversold_guard")
        self.assertEqual(skips[-1]["skip_class"], "right_skip")
        self.assertEqual(skips[-1].get("skip_note"), "extreme_oversold_guard")

    def test_rebound_delay_logs_missing_and_produced_events(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session._disable_review_log = True
        now = time.time()
        session.prices[MASTER] = [(now - 120, 100.5), (now, 101.0)]
        session.quote_snapshot[MASTER] = {"change_pct": -6.0}
        base = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 45.0,
            "vol_ratio": 1.0,
            "vwap": 102.0,
            "session_low": 100.0,
        }

        self.assertIsNone(sd.check_crash_rebound_watch(session, MASTER, dict(base), sd.DEFAULT_PARAMS))
        events = getattr(session, "_rebound_delay_events", [])
        self.assertEqual(events[-1]["source"], "crash_rebound_watch")
        self.assertEqual(events[-1]["outcome"], "not_produced")
        self.assertEqual(events[-1]["primary_reason"], "low_rebound_below_min")

        session = FocusSession(MASTER, FOLLOWERS)
        session._disable_review_log = True
        now = time.time()
        session.prices[MASTER] = [(now - 120, 101.5), (now, 102.2)]
        session.quote_snapshot[MASTER] = {"change_pct": -6.0}
        produced = {
            **base,
            "vwap": 103.0,
            "session_low": 100.0,
        }
        hit = sd.check_crash_rebound_watch(session, MASTER, produced, sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        events = getattr(session, "_rebound_delay_events", [])
        self.assertEqual(events[-1]["outcome"], "produced_weak")

    def test_indicator_stale_silences_noise_but_allows_stop_loss(self):
        session = FocusSession(MASTER, FOLLOWERS)
        ind = {"data_ok": True, "is_today": True, "vol_ratio": 1.23, "rsi_5m": 50}
        params = {**sd.DEFAULT_PARAMS, "indicator_stale_repeat": 3}

        self.assertFalse(sd._update_indicator_stale(session, dict(ind), params))
        self.assertFalse(sd._update_indicator_stale(session, dict(ind), params))
        stale_ind = dict(ind)
        self.assertTrue(sd._update_indicator_stale(session, stale_ind, params))
        self.assertTrue(stale_ind["indicator_stale"])

    def test_indicator_stale_does_not_count_same_5m_bar(self):
        session = FocusSession(MASTER, FOLLOWERS)
        params = {**sd.DEFAULT_PARAMS, "indicator_stale_repeat": 3}
        ind = {
            "data_ok": True,
            "is_today": True,
            "vol_ratio": 1.23,
            "rsi_5m": 50,
            "last_bar_time": "2026-05-18 09:55:00",
        }

        self.assertFalse(sd._update_indicator_stale(session, dict(ind), params))
        self.assertFalse(sd._update_indicator_stale(session, dict(ind), params))
        self.assertFalse(sd._update_indicator_stale(session, dict(ind), params))

    def test_weak_market_support_and_bottom_filters(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.update_price(MASTER, 100.0)
        session.quote_snapshot[MASTER] = {"change_pct": -3.2}
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 44,
            "rsi_history": [34, 34, 34, 34, 34],
            "vwap": 101.0,
            "vol_ratio": 1.0,
            "session_low": 98.0,
            "dist_low": 1.1,
            "candle": {},
            "kline_bars": [{"close": 100.0}, {"close": 99.8}, {"close": 99.9}],
        }
        self.assertTrue(sd._is_weak_market(session, MASTER, ind, sd.DEFAULT_PARAMS))
        self.assertIsNone(sd.check_swing_bottom(session, MASTER, dict(ind), sd.DEFAULT_PARAMS))

        hit = sd.check_near_support(session, MASTER, dict(ind), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["direction"], "neutral")
        self.assertTrue(hit["data"]["weak_market"])

    def test_intraday_reversal_down_after_big_high_pullback(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.update_price(MASTER, 128.62)
        session.quote_snapshot[MASTER] = {"change_pct": 3.09}
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 41.7,
            "vwap": 132.69,
            "vol_ratio": 2.98,
            "session_high": 138.29,
            "session_low": 127.30,
            "last_bar_time": "2026-05-18 09:50:00",
        }

        hit = sd.check_intraday_reversal(session, MASTER, dict(ind), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "intraday_reversal")
        self.assertEqual(hit["direction"], "short")

    def test_intraday_reversal_does_not_chase_overbought_uptrend(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.update_price(MASTER, 136.65)
        session.quote_snapshot[MASTER] = {"change_pct": 9.52}
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 85.0,
            "vwap": 133.62,
            "vol_ratio": 37.9,
            "session_high": 138.29,
            "session_low": 130.82,
            "last_bar_time": "2026-05-18 09:40:00",
        }

        self.assertIsNone(sd.check_intraday_reversal(session, MASTER, dict(ind), sd.DEFAULT_PARAMS))

    def test_intraday_reversal_short_does_not_require_bounce_from_low(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.update_price(MASTER, 129.0)
        session.quote_snapshot[MASTER] = {"change_pct": 2.4}
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 52.0,
            "vwap": 132.0,
            "vol_ratio": 0.82,
            "session_high": 138.0,
            "session_low": 128.9,
            "last_bar_time": "2026-05-18 10:15:00",
        }

        hit = sd.check_intraday_reversal(session, MASTER, dict(ind), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["direction"], "short")

    def test_breakdown_warning_fires_on_fresh_open_breakdown(self):
        session = FocusSession(MASTER, FOLLOWERS)
        now = time.time()
        session.prices[MASTER] = [(now - 130, 126.5), (now, 123.0)]
        session.quote_snapshot[MASTER] = {"change_pct": -6.17}
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 11.7,
            "vwap": 124.52,
            "vol_ratio": 52.51,
            "last_bar_time": "2026-05-19 09:35:00",
        }

        hit = sd.check_breakdown_warning(session, MASTER, dict(ind), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "breakdown_warning")
        self.assertEqual(hit["direction"], "short")
        self.assertEqual(hit["strength"], "STRONG")

        msg = pusher.format_trigger_message(hit, session)
        self.assertIsNotNone(msg)
        self.assertIn("方向破位", msg["text"])
        self.assertIn("多头失效", msg["text"])
        flattened = [
            btn.get("callback_data", "")
            for row in (msg.get("buttons") or [])
            for btn in row
            if isinstance(btn, dict)
        ]
        self.assertFalse(any(v.startswith("focus_order_") for v in flattened))

    def test_breakdown_warning_is_fresh_data_trigger(self):
        self.assertTrue(data_quality.trigger_requires_fresh_data("breakdown_warning"))

    def test_structural_breakdown_fires_even_after_short_rebound(self):
        session = FocusSession(MASTER, FOLLOWERS)
        now = time.time()
        session.prices[MASTER] = [(now - 130, 116.0), (now, 117.2)]
        session.quote_snapshot[MASTER] = {"change_pct": -10.6}
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 12.3,
            "vwap": 122.55,
            "vol_ratio": 1.31,
            "session_high": 131.16,
            "last_bar_time": "2026-05-19 10:10:00",
        }

        hit = sd.check_breakdown_warning(session, MASTER, dict(ind), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "breakdown_warning")
        self.assertEqual(hit["data"]["breakdown_kind"], "structural")

    def test_early_breakdown_fires_before_extreme_volume(self):
        session = FocusSession(MASTER, FOLLOWERS)
        now = time.time()
        session.prices[MASTER] = [(now - 130, 128.9), (now, 128.1)]
        session.quote_snapshot[MASTER] = {"change_pct": -2.8}
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 42.0,
            "vwap": 129.2,
            "vol_ratio": 1.05,
            "session_high": 131.0,
            "last_bar_time": "2026-05-29 09:55:00",
        }

        hit = sd.check_breakdown_warning(session, MASTER, dict(ind), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "breakdown_warning")
        self.assertEqual(hit["data"]["breakdown_kind"], "early")

    def test_capitulation_bottom_watch_observes_without_entry_button(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.update_price(MASTER, 116.57)
        session.quote_snapshot[MASTER] = {"change_pct": -11.12}
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 13.1,
            "rsi_history": [14.9, 13.0, 12.0, 11.9, 13.1],
            "vwap": 120.94,
            "vol_ratio": 0.97,
            "session_low": 115.23,
            "dist_low": 1.16,
            "candle": {"type": "bullish", "name": "hammer"},
            "last_bar_time": "2026-05-19 10:25:00",
        }

        hit = sd.check_capitulation_bottom_watch(session, MASTER, dict(ind), sd.DEFAULT_PARAMS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "capitulation_bottom_watch")
        self.assertEqual(hit["direction"], "neutral")
        msg = pusher.format_trigger_message(hit, session)
        self.assertIsNotNone(msg)
        self.assertIn("恐慌底部观察", msg["text"])
        flattened = [
            btn.get("callback_data", "")
            for row in (msg.get("buttons") or [])
            for btn in row
            if isinstance(btn, dict)
        ]
        self.assertFalse(any(v.startswith("focus_order_") for v in flattened))

    def test_fixtures_replay_0514_trend_day_profit_noise_reduced(self):
        records = _load_fixture("review_2026_05_14_triggers.json")
        kept = _replay_v0534(records)
        noisy = [r for r in kept if r["trigger"] in ("target_advance", "profit_target_hit")]
        self.assertLessEqual(len(noisy), 12)

    def test_fixtures_replay_0516_weak_day_buy_noise_under_30_percent(self):
        records = _load_fixture("review_2026_05_16_triggers.json")
        kept = _replay_v0534(records)
        buy_noise = [r for r in kept if r["trigger"] in ("near_support", "swing_bottom")]
        self.assertLess(len(buy_noise) / len(records), 0.30)

    def test_0518_first_bad_direction_signal_is_blocked_by_quality_gate(self):
        records = _load_fixture("review_2026_05_18_triggers.json")
        first = records[0]
        self.assertEqual(first["trigger"], "direction_trend")
        session = FocusSession(MASTER, FOLLOWERS)
        _sync_session(session, first)
        ind = _indicators(first)
        now = datetime.strptime(first["ts"], "%Y-%m-%d %H:%M:%S")

        quality = data_quality.evaluate_data_quality(session, ind, now=now, update_repeat=False)
        self.assertFalse(quality.ok)
        self.assertFalse(quality.can_direction)
        self.assertIn("current", quality.reason)

        hits = sd.run_all_triggers(session, MASTER, FOLLOWERS, ind, sd.DEFAULT_PARAMS)
        self.assertFalse(
            any(h["trigger"] == "direction_trend" for h in hits),
            "05-18 first stale-K direction signal must be blocked",
        )

    def test_known_frozen_rsi_vol_pair_is_blocked(self):
        session = FocusSession(MASTER, FOLLOWERS)
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 43.1,
            "vol_ratio": 4.94,
        }

        quality = data_quality.evaluate_data_quality(session, ind, update_repeat=False)
        self.assertFalse(quality.ok)
        self.assertFalse(quality.can_direction)
        self.assertIn("known frozen", quality.reason)

    def test_natural_rsi_vol_pair_is_not_blacklisted(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session._last_data_quality = {
            "last_bar_time": "2026-05-18 10:00:00",
            "last_bar_age_sec": 60,
            "is_current_trading_day": True,
        }
        ind = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 57.9,
            "vol_ratio": 6.58,
            "last_bar_time": "2026-05-18 10:00:00",
        }
        now = datetime.strptime("2026-05-18 10:01:00", "%Y-%m-%d %H:%M:%S")

        quality = data_quality.evaluate_data_quality(session, ind, now=now, update_repeat=False)
        self.assertTrue(quality.ok, quality.reason)
        self.assertTrue(quality.can_direction)

    def test_0518_pusher_final_gate_blocks_order_buttons(self):
        records = _load_fixture("review_2026_05_18_triggers.json")
        first = records[0]
        session = FocusSession(MASTER, FOLLOWERS)
        _sync_session(session, first)
        session._last_indicators_cache = _indicators(first)

        msg = pusher.format_trigger_message(first, session)
        self.assertIsNone(msg)

    def test_bad_data_stop_loss_passes_without_buttons(self):
        records = _load_fixture("review_2026_05_18_triggers.json")
        stop = next(r for r in records if r["trigger"] == "stop_loss_warning")
        session = FocusSession(MASTER, FOLLOWERS)
        _sync_session(session, stop)
        session._last_indicators_cache = _indicators(stop)

        msg = pusher.format_trigger_message(stop, session)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.get("buttons"), [])
        self.assertIn("技术指标数据不可用", msg["text"])


    def test_bad_data_stop_loss_uses_pure_loss_only(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.update_price("US.RKLZ", 2.62)
        session.positions_snapshot = {
            "US.RKLZ": {
                "ticker": "US.RKLZ",
                "qty": 500,
                "cost_price": 2.70,
                "current_price": 2.62,
                "pl_val": -40.0,
                "pl_pct": -3.0,
            }
        }

        hit = sd.check_stop_loss_warning(session, "US.RKLZ", bad_data_mode=True)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "stop_loss_warning")
        self.assertEqual(hit["level"], "WARN")
        self.assertTrue(hit["data"]["bad_data_mode"])
        self.assertIsNone(hit["data"]["stop"])

    def test_warmup_removes_one_click_order_buttons(self):
        from config import settings
        old_warmup = settings.ONE_CLICK_BUTTON_WARMUP_SEC
        settings.ONE_CLICK_BUTTON_WARMUP_SEC = 900
        session = FocusSession(MASTER, FOLLOWERS)
        try:
            session.start_time = time.time()
            session.update_cash(3000)
            session.update_price(MASTER, 100.0)
            session.update_price("US.RKLX", 50.0)
            session.update_price("US.RKLZ", 3.0)
            session._last_data_quality = {"last_bar_time": "2026-05-18 08:40:00"}
            hit = {
                "trigger": "direction_trend",
                "level": "URGENT",
                "style": "A",
                "ticker": MASTER,
                "direction": "long",
                "strength": "STRONG",
                "data": {
                    "current": 100.0,
                    "day_chg": 2.8,
                    "rsi": 58,
                    "vol_ratio": 1.5,
                    "has_indicators": True,
                },
                "title": "RKLB direction long",
            }

            msg = pusher.format_trigger_message(hit, session)
            self.assertIsNotNone(msg)
            flattened = [
                btn.get("callback_data", "")
                for row in (msg.get("buttons") or [])
                for btn in row
                if isinstance(btn, dict)
            ]
            self.assertFalse(any(v.startswith("focus_order_") for v in flattened))
            self.assertIn("防御模式", msg["text"])
            self.assertIn("方向可信度", msg["text"])
            self.assertIn("方向倾向", msg["text"])
            self.assertIn("K_5M last: 2026-05-18 08:40", msg["text"])
            self.assertNotIn("不是自动下单建议", msg["text"])
            self.assertNotIn("暂不作为入场依据", msg["text"])
            self.assertNotIn("适合做多", msg["text"])
        finally:
            settings.ONE_CLICK_BUTTON_WARMUP_SEC = old_warmup
        self.assertNotIn("淇", msg["text"])

    def test_signal_copy_does_not_claim_data_missing_when_indicators_exist(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.start_time = time.time() - 3600
        session.update_cash(3000)
        session.update_price(MASTER, 130.0)
        session.update_price("US.RKLZ", 2.4)
        hit = {
            "trigger": "swing_top",
            "level": "WARN",
            "style": "B",
            "ticker": MASTER,
            "direction": "short",
            "strength": "WEAK",
            "data": {
                "current": 130.0,
                "rsi": 71.5,
                "vol_ratio": 0.66,
            },
            "title": "RKLB swing top",
        }

        msg = pusher.format_trigger_message(hit, session)
        self.assertIsNotNone(msg)
        self.assertNotIn("行情: 数据不足", msg["text"])
        self.assertNotIn("适合做空", msg["text"])

    def test_premarket_low_volume_long_is_downgraded_to_medium(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.start_time = time.time() - 3600
        session.market_status = "pre"
        session.update_cash(3000)
        session.update_price(MASTER, 128.54)
        session.update_price("US.RKLX", 85.39)
        session._last_data_quality = {"last_bar_time": "2026-05-19 07:05:00"}
        hit = {
            "trigger": "direction_trend",
            "level": "URGENT",
            "style": "A",
            "ticker": MASTER,
            "direction": "long",
            "strength": "STRONG",
            "data": {
                "current": 128.54,
                "day_change_pct": 3.02,
                "rsi": 52.3,
                "vol_ratio": 0.51,
                "vwap": 129.14,
                "has_indicators": True,
            },
            "title": "RKLB direction long",
        }

        msg = pusher.format_trigger_message(hit, session)
        self.assertIsNotNone(msg)
        text = msg["text"]
        self.assertIn("[中等]", text)
        self.assertIn("盘前低量", text)
        self.assertIn("降为中等信心", text)
        self.assertIn("方向可信度: 65%｜中", text)
        self.assertNotIn("[强烈]", text)

    def test_premarket_high_volume_long_is_not_downgraded(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.start_time = time.time() - 3600
        session.market_status = "pre"
        session.update_cash(3000)
        session.update_price(MASTER, 128.54)
        session.update_price("US.RKLX", 85.39)
        session._last_data_quality = {"last_bar_time": "2026-05-19 07:05:00"}
        hit = {
            "trigger": "direction_trend",
            "level": "URGENT",
            "style": "A",
            "ticker": MASTER,
            "direction": "long",
            "strength": "STRONG",
            "data": {
                "current": 128.54,
                "day_change_pct": 3.02,
                "rsi": 52.3,
                "vol_ratio": 1.2,
                "vwap": 129.14,
                "has_indicators": True,
            },
            "title": "RKLB direction long [强烈]",
        }

        msg = pusher.format_trigger_message(hit, session)
        self.assertIsNotNone(msg)
        text = msg["text"]
        self.assertIn("[强烈]", text)
        self.assertNotIn("盘前低量", text)
        self.assertNotIn("降为中等信心", text)

    def test_short_rklb_uses_long_targets_for_rklz(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.start_time = time.time() - 3600
        session.update_cash(3000)
        for px in [2.46, 2.48, 2.49, 2.50, 2.51, 2.52, 2.53]:
            session.update_price("US.RKLZ", px)
        for px in [126.9, 126.8, 126.7, 126.77]:
            session.update_price(MASTER, px)
        session._last_data_quality = {"last_bar_time": "2026-05-20 04:35:00"}
        hit = {
            "trigger": "swing_top",
            "level": "WARN",
            "style": "B",
            "ticker": MASTER,
            "direction": "short",
            "strength": "STRONG",
            "data": {
                "current": 126.77,
                "rsi": 72.9,
                "vol_ratio": 0.33,
            },
            "title": "RKLB swing top",
        }

        old_long = pusher.get_long_tools
        old_short = pusher.get_short_tools
        old_classify = pusher.classify_follower
        pusher.get_long_tools = lambda _master: ["US.RKLX"]
        pusher.get_short_tools = lambda _master: ["US.RKLZ"]
        pusher.classify_follower = lambda _master, follower: (
            "short" if follower == "US.RKLZ" else "long"
        )
        try:
            msg = pusher.format_trigger_message(hit, session)
        finally:
            pusher.get_long_tools = old_long
            pusher.get_short_tools = old_short
            pusher.classify_follower = old_classify

        self.assertIsNotNone(msg)
        text = msg["text"]
        self.assertIn("参考入场", text)
        self.assertIn("RKLZ", text)
        self.assertRegex(text, r"RKLZ 目标 T1 \$2\.(?:5[4-9]|6[0-9])")
        self.assertRegex(text, r"RKLZ 失效价 \$2\.4[0-9]")
        self.assertNotIn("RKLZ 目标 T1 $2.51", text)
        self.assertNotIn("RKLZ 失效价 $2.54", text)

    def test_low_price_follower_target_does_not_jump_to_five_dollars(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.start_time = time.time() - 3600
        for px in [2.44, 2.45, 2.46, 2.47, 2.48]:
            session.update_price("US.RKLZ", px)

        targets = pusher._calc_price_targets(session, "US.RKLZ", "long", 2.48)

        self.assertIsNotNone(targets.get("t1"))
        self.assertLess(targets.get("t1"), 3.0)
        if targets.get("t2") is not None:
            self.assertLess(targets.get("t2"), 3.0)
        self.assertNotEqual(targets.get("t2"), 5.0)
        self.assertNotEqual(targets.get("t2_label"), "整数关口")

    def test_follower_targets_use_kline_atr_not_tick_jitter(self):
        import pandas as pd

        session = FocusSession(MASTER, FOLLOWERS)
        session.start_time = time.time() - 3600
        base_ts = datetime(2026, 5, 21, 9, 30)
        rows = []
        close = 125.0
        for idx in range(20):
            close += 0.2
            rows.append({
                "time_key": base_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "open": close - 0.3,
                "high": close + 0.8,
                "low": close - 0.9,
                "close": close,
                "volume": 1000 + idx,
            })
        session._last_kline_cache = pd.DataFrame(rows)
        session.update_price(MASTER, 129.0)
        for px in [79.94, 79.95, 79.96, 79.97, 79.96, 79.95]:
            session.update_price("US.RKLX", px)

        old_daily = pusher._daily_atr_pct_from_local_history
        pusher._daily_atr_pct_from_local_history = lambda ticker, period=14: (0.0, "test no daily")
        try:
            targets = pusher._calc_price_targets(session, "US.RKLX", "long", 79.96)
        finally:
            pusher._daily_atr_pct_from_local_history = old_daily

        self.assertEqual(targets.get("atr_source"), "RKLB K_5M ATR x2")
        self.assertLessEqual(targets.get("stop"), 78.40)
        self.assertGreaterEqual(targets.get("t1"), 81.20)

    def test_follower_targets_use_daily_atr_floor_for_real_loss_case(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.start_time = time.time() - 3600
        for px in [79.94, 79.95, 79.96, 79.97, 79.96, 79.95]:
            session.update_price("US.RKLX", px)

        old_daily = pusher._daily_atr_pct_from_local_history
        pusher._daily_atr_pct_from_local_history = lambda ticker, period=14: (4.2, "daily ATR")
        try:
            targets = pusher._calc_price_targets(session, "US.RKLX", "long", 79.96)
        finally:
            pusher._daily_atr_pct_from_local_history = old_daily

        self.assertEqual(targets.get("atr_source"), "daily ATR")
        self.assertLessEqual(targets.get("stop"), 78.00)
        self.assertGreaterEqual((targets.get("t1") - 79.96) / 79.96 * 100, 1.5)

    def test_target_floor_fallback_does_not_use_short_tick_jitter(self):
        session = FocusSession(MASTER, FOLLOWERS)
        for px in [79.95, 79.96, 79.95, 79.96, 79.95]:
            session.update_price("US.RKLX", px)

        old_daily = pusher._daily_atr_pct_from_local_history
        pusher._daily_atr_pct_from_local_history = lambda ticker, period=14: (0.0, "test no daily")
        try:
            targets = pusher._calc_price_targets(session, "US.RKLX", "long", 79.96)
        finally:
            pusher._daily_atr_pct_from_local_history = old_daily

        self.assertEqual(targets.get("atr_source"), "floor fallback")
        self.assertLessEqual(targets.get("stop"), round(79.96 * 0.975, 2))
        self.assertGreaterEqual((targets.get("t1") - 79.96) / 79.96 * 100, 1.5)

    def test_new_snapshot_position_blocks_stale_deal_time(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.update_positions({
            "US.RKLX": {"ticker": "US.RKLX", "qty": 38, "cost_price": 79.9584}
        })
        first_seen = session._position_first_seen["US.RKLX"]

        session.set_position_open_time("US.RKLX", first_seen - 3600)

        self.assertNotIn("US.RKLX", session._position_open_time)
        self.assertLess(session.get_position_age_sec("US.RKLX"), 5)

    def test_diagnose_distance_uses_observation_copy(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session.quote_snapshot[MASTER] = {"change_pct": -2.6}
        indicators = {"data_ok": True, "rsi_5m": 56.3}

        diag = sd.diagnose_distance(session, MASTER, indicators)
        text = "\n".join(diag["distances"])

        self.assertIn("RKLB", text)
        self.assertIn("较昨收跌幅触发", text)
        self.assertIn("等待: 站稳", text)
        self.assertIn("关键位后再看", text)
        self.assertNotIn("看空已满足", text)

    def test_panic_rebound_fires_after_crash_bounce(self):
        session = FocusSession(MASTER, FOLLOWERS)
        now = time.time()
        session.prices[MASTER] = [(now - 130, 115.50), (now, 116.57)]
        session.session_low[MASTER] = 115.50
        session.session_high[MASTER] = 131.16
        session.quote_snapshot[MASTER] = {"change_pct": -11.0}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 13.1,
            "vwap": 120.0,
            "vol_ratio": 0.97,
            "session_low": 115.50,
            "indicator_stale": False,
        }

        hit = sd.check_panic_rebound(session, MASTER, indicators)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "panic_rebound")
        self.assertEqual(hit["direction"], "long")
        self.assertGreaterEqual(hit["data"]["low_rebound_pct"], 0.6)

        msg = pusher.format_trigger_message(hit, session)
        self.assertIsNotNone(msg)
        callbacks = [
            btn.get("callback_data", "")
            for row in (msg.get("buttons") or [])
            for btn in row
            if isinstance(btn, dict)
        ]
        self.assertFalse(any(cb.startswith("focus_order_") for cb in callbacks))

    def test_crash_rebound_watch_fires_before_full_reversal_confirmation(self):
        session = FocusSession(MASTER, FOLLOWERS)
        now = time.time()
        session.prices[MASTER] = [(now - 130, 115.50), (now, 118.10)]
        session.session_low[MASTER] = 115.50
        session.session_high[MASTER] = 131.16
        session.quote_snapshot[MASTER] = {"change_pct": -9.2}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 45.0,
            "vwap": 119.8,
            "vol_ratio": 0.62,
            "session_low": 115.50,
            "indicator_stale": False,
        }

        hit = sd.check_crash_rebound_watch(session, MASTER, indicators)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "crash_rebound_watch")
        self.assertEqual(hit["direction"], "long")
        self.assertGreaterEqual(hit["data"]["low_rebound_pct"], 2.0)

        msg = pusher.format_trigger_message(hit, session)
        self.assertIsNotNone(msg)
        self.assertIn("暴跌反弹观察", msg["text"])
        callbacks = [
            btn.get("callback_data", "")
            for row in (msg.get("buttons") or [])
            for btn in row
            if isinstance(btn, dict)
        ]
        self.assertFalse(any(cb.startswith("focus_order_") for cb in callbacks))

    def test_crash_rebound_watch_fires_on_early_rebound(self):
        session = FocusSession(MASTER, FOLLOWERS)
        now = time.time()
        session.prices[MASTER] = [(now - 130, 123.60), (now, 124.00)]
        session.session_low[MASTER] = 122.50
        session.quote_snapshot[MASTER] = {"change_pct": -4.4}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 51.0,
            "vwap": 124.80,
            "vol_ratio": 0.38,
            "session_low": 122.50,
            "indicator_stale": False,
        }

        hit = sd.check_crash_rebound_watch(session, MASTER, indicators)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["trigger"], "crash_rebound_watch")
        self.assertEqual(hit["direction"], "long")
        self.assertGreaterEqual(hit["data"]["low_rebound_pct"], 1.2)

    def test_targeted_breakdown_shadow_records_without_push_hit(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session._disable_review_log = True
        now = time.time()
        session.prices[MASTER] = [
            (now - 901, 144.00),
            (now - 301, 143.50),
            (now, 142.80),
        ]
        session.session_high[MASTER] = 145.00
        session.session_low[MASTER] = 142.80
        session.quote_snapshot[MASTER] = {"change_pct": -1.5}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 50.0,
            "vwap": 143.20,
            "vol_ratio": 0.50,
            "session_high": 145.00,
            "session_low": 142.80,
            "indicator_stale": False,
        }

        record = sd.check_targeted_breakdown_shadow(session, MASTER, indicators)

        self.assertIsNotNone(record)
        self.assertEqual(record["profile"], "D_TARGETED_BREAKDOWN")
        self.assertTrue(record["shadow_only"])
        self.assertEqual(record["trigger"], "shadow_targeted_breakdown")
        self.assertEqual(record["direction"], "short")
        self.assertEqual(len(session._shadow_signals), 1)

        hits = sd.run_all_triggers(session, MASTER, FOLLOWERS, dict(indicators), sd.DEFAULT_PARAMS)
        self.assertFalse(any(h.get("trigger", "").startswith("shadow_") for h in hits))

    def test_shadow_wave_alert_promotes_only_confirmed_watch_without_buttons(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session._disable_review_log = True
        now = time.time()
        session.prices[MASTER] = [
            (now - 901, 145.00),
            (now - 301, 144.70),
            (now, 144.30),
        ]
        session.session_high[MASTER] = 146.00
        session.session_low[MASTER] = 144.30
        session.quote_snapshot[MASTER] = {"change_pct": -1.5}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 45.0,
            "vwap": 144.80,
            "vol_ratio": 1.10,
            "session_high": 146.00,
            "session_low": 144.30,
            "indicator_stale": False,
        }

        params = {**sd.DEFAULT_PARAMS, "shadow_tg_enabled": True}
        record = sd.check_targeted_breakdown_shadow(session, MASTER, dict(indicators), params)
        wave = sd._shadow_record_to_wave_alert(session, record, dict(indicators), params)
        self.assertIsNotNone(wave)
        self.assertEqual(wave["direction"], "short")
        msg = pusher.format_trigger_message(wave, session)
        self.assertIsNotNone(msg)
        self.assertIn("波峰回落时刻", msg["text"])
        self.assertIn("无下单按钮", msg["text"])
        self.assertEqual(msg.get("buttons"), [])

    def test_shadow_wave_default_records_forward_case_without_push(self):
        session = FocusSession(MASTER, FOLLOWERS)
        session._disable_review_log = True
        now = time.time()
        session.prices[MASTER] = [
            (now - 901, 145.00),
            (now - 301, 144.70),
            (now, 144.30),
        ]
        session.session_high[MASTER] = 146.00
        session.session_low[MASTER] = 144.30
        session.quote_snapshot[MASTER] = {"change_pct": -1.5}
        indicators = {
            "data_ok": True,
            "is_today": True,
            "rsi_5m": 45.0,
            "vwap": 144.80,
            "vol_ratio": 1.10,
            "session_high": 146.00,
            "session_low": 144.30,
            "indicator_stale": False,
        }

        hits = sd.run_all_triggers(session, MASTER, FOLLOWERS, dict(indicators), sd.DEFAULT_PARAMS)

        self.assertFalse(any(h["trigger"] == "wave_peak_rollover" for h in hits))
        cases = getattr(session, "_wave_forward_cases", [])
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["source_trigger"], "shadow_targeted_breakdown")
        self.assertEqual(cases[0]["entry_price"], 144.30)
        self.assertEqual(cases[0]["status"], "open")

    def test_kline_source_line_marks_old_data(self):
        line = kline_display.format_kline_source_line(
            indicators={"kline_bars": [{"time": "2026-05-15 16:00:00"}]}
        )
        self.assertIn("K_5M last: 2026-05-15 16:00", line)
        self.assertIn("数据过期", line)


if __name__ == "__main__":
    unittest.main()
