"""
tests/test_anti_chase_v0_5_32.py — v0.5.32 P0 #3 RKLX/RKLZ 高位追多封顶

锁定 follower ∈ {RKLX, RKLZ} + LONG + day_chg≥10% → conf cap 60 / 强度→一般
+ 警告文案。其他 follower / SHORT 方向 / day_chg<10% 不应触发。

run: PYTHONIOENCODING=utf-8 python tests/test_anti_chase_v0_5_32.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.focus.pusher import _fmt_signal_with_conflict
from core.focus import pusher as P


class _StubSession:
    def __init__(self, master_price=100.0, follower_price=50.0,
                 follower="US.RKLX", follower_day_chg=5.0):
        self.master = "US.RKLB"
        self.followers = [follower] if follower else []
        self._prices = {"US.RKLB": master_price}
        if follower and follower_price:
            self._prices[follower] = follower_price
        self._day_chg = {follower: follower_day_chg} if follower else {}
        self.snapshot_last_signal = {}
        self.positions = {}
        self.account = {"cash": 5000.0}
        self.activity_profile = None
        self.market_status = "regular"
        self.last_quote = {}

    def get_last_price(self, tk):
        return self._prices.get(tk)

    def get_day_change_pct(self, tk):
        return self._day_chg.get(tk)

    def get_position(self, tk):
        return self.positions.get(tk)


def _stub_hit(direction="long", strength="STRONG", rsi=60, vol_ratio=1.5,
              ticker="US.RKLB"):
    return {
        "trigger":   "swing_bottom",
        "ticker":    ticker,
        "direction": direction,
        "strength":  strength,
        "data": {
            "rsi":       rsi,
            "vol_ratio": vol_ratio,
            "candle":    {"name": "锤子线"},
            "cond_rsi":  True, "cond_candle": True, "cond_near": True,
        },
    }


def _setup_targets(rr_target=2.5):
    """monkey-patch _calc_price_targets for stable R/R"""
    P._calc_price_targets = lambda session, ticker, dirn, entry: {
        "t1": entry + entry * 0.025,
        "stop": entry - entry * (0.025 / rr_target),
    }


def test_rklx_long_high_gain_caps_conf():
    """RKLX +13% LONG → conf cap 60, [强烈]→[一般], 追多警告出现"""
    orig = P._calc_price_targets
    _setup_targets()
    try:
        sess = _StubSession(follower="US.RKLX", follower_day_chg=13.45)
        hit  = _stub_hit(direction="long", strength="STRONG")
        result = _fmt_signal_with_conflict(
            hit, sess, "long", "🟢 <b>RKLB</b> [强烈]", "tech"
        )
        assert result is not None
        text = result["text"]
        # 标签从强烈改一般
        assert "[一般]" in text and "[强烈]" not in text, \
            f"strength label not demoted:\n{text}"
        # conf 被 cap 60
        assert "60%" in text, f"conf not capped to 60:\n{text}"
        # 警告语
        assert "已大涨" in text or "谨慎追多" in text, \
            f"chase warning missing:\n{text}"
    finally:
        P._calc_price_targets = orig


def test_rklz_long_high_gain_also_caps():
    """RKLZ 同样规则 — pick_target_follower 默认 long 选 RKLX,需 monkey-patch"""
    orig_calc = P._calc_price_targets
    orig_pick = P.pick_target_follower
    _setup_targets()
    P.pick_target_follower = lambda session, dirn: "US.RKLZ" if dirn == "long" else None
    try:
        sess = _StubSession(follower="US.RKLZ", follower_day_chg=10.5)
        hit  = _stub_hit(direction="long", strength="STRONG")
        result = _fmt_signal_with_conflict(
            hit, sess, "long", "🟢 <b>RKLB</b> [强烈]", "tech"
        )
        assert result is not None
        assert "[一般]" in result["text"], result["text"]
        assert "已大涨" in result["text"], result["text"]
    finally:
        P._calc_price_targets = orig_calc
        P.pick_target_follower = orig_pick


def test_rklx_long_below_threshold_unchanged():
    """day_chg=5% < 10% → 不触发,保持原 conf 和强烈标签"""
    orig = P._calc_price_targets
    _setup_targets()
    try:
        sess = _StubSession(follower="US.RKLX", follower_day_chg=5.0)
        hit  = _stub_hit(direction="long", strength="STRONG")
        result = _fmt_signal_with_conflict(
            hit, sess, "long", "🟢 <b>RKLB</b> [强烈]", "tech"
        )
        assert result is not None
        text = result["text"]
        assert "[强烈]" in text, f"strength should stay STRONG: {text}"
        assert "已大涨" not in text, "chase warn should not appear"
    finally:
        P._calc_price_targets = orig


def test_rklx_short_unaffected():
    """SHORT 方向不受 anti-chase 影响"""
    orig = P._calc_price_targets
    _setup_targets()
    try:
        sess = _StubSession(follower="US.RKLX", follower_day_chg=13.45)
        hit  = _stub_hit(direction="short", strength="STRONG")
        result = _fmt_signal_with_conflict(
            hit, sess, "short", "🔴 <b>RKLB</b> [强烈]", "tech"
        )
        assert result is not None
        assert "[强烈]" in result["text"], "SHORT 方向不应被 cap"
        assert "已大涨" not in result["text"]
    finally:
        P._calc_price_targets = orig


def test_other_follower_unaffected():
    """RKLB master signal but follower=SOXL, +12% → 不触发(只对 RKLX/RKLZ 生效)"""
    orig = P._calc_price_targets
    _setup_targets()
    try:
        # 我们要让 pick_target_follower 返回 SOXL 而非 RKLX/RKLZ
        # 直接 monkey-patch
        orig_pick = P.pick_target_follower
        P.pick_target_follower = lambda session, dirn: "US.SOXL"
        try:
            sess = _StubSession(follower="US.SOXL", follower_day_chg=12.0)
            hit  = _stub_hit(direction="long", strength="STRONG")
            result = _fmt_signal_with_conflict(
                hit, sess, "long", "🟢 <b>RKLB</b> [强烈]", "tech"
            )
            assert result is not None
            assert "[强烈]" in result["text"], \
                "非 RKLX/RKLZ follower 不应被 cap"
            assert "已大涨" not in result["text"]
        finally:
            P.pick_target_follower = orig_pick
    finally:
        P._calc_price_targets = orig


def test_rklx_long_at_exactly_10_pct_caps():
    """day_chg = 10.0 边界: ≥10 触发"""
    orig = P._calc_price_targets
    _setup_targets()
    try:
        sess = _StubSession(follower="US.RKLX", follower_day_chg=10.0)
        hit  = _stub_hit(direction="long", strength="STRONG")
        result = _fmt_signal_with_conflict(
            hit, sess, "long", "🟢 <b>RKLB</b> [强烈]", "tech"
        )
        assert result is not None
        assert "[一般]" in result["text"]
    finally:
        P._calc_price_targets = orig


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    fail = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            fail += 1
        except Exception as e:
            import traceback
            print(f"  ERR   {fn.__name__}: {e!r}")
            traceback.print_exc()
            fail += 1
    print(f"\n{len(fns) - fail}/{len(fns)} passed")
    sys.exit(fail)
