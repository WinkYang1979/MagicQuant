"""
tests/test_rr_gate_v0_5_32.py — v0.5.32 P0 #2 R/R 闸门

锁定 _compute_rr 的边界 + _fmt_signal_with_conflict 在 R/R<1.5 时返回 None
+ R/R 1.5-2 时 conf 被封顶 60。

run: PYTHONIOENCODING=utf-8 python tests/test_rr_gate_v0_5_32.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.focus.pusher import _compute_rr, _fmt_signal_with_conflict


# ── _compute_rr 单元 ──────────────────────────────────────────────

def test_rr_basic():
    """T1=110 entry=100 stop=95 → R/R = 10/5 = 2.0"""
    rr = _compute_rr({"t1": 110.0, "stop": 95.0}, 100.0)
    assert rr is not None and abs(rr - 2.0) < 0.01, rr


def test_rr_short_direction():
    """SHORT: t1=90 entry=100 stop=105 → R/R = 10/5 = 2.0"""
    rr = _compute_rr({"t1": 90.0, "stop": 105.0}, 100.0)
    assert rr is not None and abs(rr - 2.0) < 0.01, rr


def test_rr_low_ratio_03():
    """v0.5.31 11:42 案例: t1=100.6 stop=98 entry=100 → R/R = 0.6/2 = 0.3"""
    rr = _compute_rr({"t1": 100.6, "stop": 98.0}, 100.0)
    assert rr is not None and abs(rr - 0.3) < 0.05, rr


def test_rr_missing_t1_returns_none():
    assert _compute_rr({"stop": 95.0}, 100.0) is None


def test_rr_missing_stop_returns_none():
    assert _compute_rr({"t1": 110.0}, 100.0) is None


def test_rr_missing_entry_returns_none():
    assert _compute_rr({"t1": 110.0, "stop": 95.0}, None) is None


def test_rr_zero_risk_returns_none():
    """stop == entry → risk=0 → 不可计算"""
    assert _compute_rr({"t1": 110.0, "stop": 100.0}, 100.0) is None


def test_rr_empty_targets_returns_none():
    assert _compute_rr({}, 100.0) is None
    assert _compute_rr(None, 100.0) is None


# ── _fmt_signal_with_conflict 集成 ────────────────────────────────

class _StubSession:
    def __init__(self, master_price=100.0, follower_price=None,
                 follower="US.RKLX"):
        self.master = "US.RKLB"
        self.followers = [follower] if follower else []
        self._prices = {"US.RKLB": master_price}
        if follower and follower_price:
            self._prices[follower] = follower_price
        # 用于 _trio_block / pick_target_follower / analyze_position_conflict
        self._follower = follower
        self.snapshot_last_signal = {}
        self.positions = {}
        self.account = {"cash": 5000.0}
        self.activity_profile = None
        self.market_status = "regular"
        self.last_quote = {}

    def get_last_price(self, tk):
        return self._prices.get(tk)

    def get_position(self, tk):
        return self.positions.get(tk)


def _stub_hit(trigger="swing_top", direction="short", strength="STRONG",
              rsi=72, vol_ratio=1.5, ticker="US.RKLB"):
    return {
        "trigger":   trigger,
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


def test_low_rr_blocks_signal():
    """
    构造一个 R/R 一定 <1.5 的场景,期望 _fmt_signal_with_conflict 返回 None。
    我们 monkey-patch _calc_price_targets,因为真函数依赖 ATR/kline。
    """
    from core.focus import pusher as P
    orig_calc = P._calc_price_targets
    P._calc_price_targets = lambda session, ticker, dirn, entry: {
        "t1": entry + (entry * 0.005),    # +0.5%
        "stop": entry - (entry * 0.02),   # -2.0%
    }
    try:
        sess = _StubSession(master_price=100.0, follower_price=50.0)
        hit = _stub_hit()
        # 调 _fmt_signal_with_conflict 直接(绕开 swing_top 包装)
        result = _fmt_signal_with_conflict(
            hit, sess, "long", "🟢 RKLB 测试", "tech line"
        )
        assert result is None, f"R/R≈0.25 应被堵, 但返回 {result}"
    finally:
        P._calc_price_targets = orig_calc


def test_borderline_rr_caps_confidence():
    """
    R/R 1.7 (落在 [1.5, 2)) → conf 应被 cap 到 60
    """
    from core.focus import pusher as P
    orig_calc = P._calc_price_targets
    P._calc_price_targets = lambda session, ticker, dirn, entry: {
        "t1": entry + entry * 0.017,   # +1.7%
        "stop": entry - entry * 0.01,  # -1.0% → R/R = 1.7
    }
    try:
        sess = _StubSession(master_price=100.0, follower_price=50.0)
        # STRONG + RSI 72 + vol 1.5 → 原 conf > 60
        hit = _stub_hit(direction="long", rsi=60, strength="STRONG", vol_ratio=1.5)
        result = _fmt_signal_with_conflict(
            hit, sess, "long", "🟢 RKLB", "tech"
        )
        assert result is not None, "R/R=1.7 不应被堵"
        # conf 文案里出现 60% (因 cap)
        assert "60%" in result["text"] or "60.0%" in result["text"], \
            f"conf 没有被 cap 到 60, text:\n{result['text']}"
    finally:
        P._calc_price_targets = orig_calc


def test_high_rr_passes_normally():
    """R/R 2.5 (>=2) → 信号通过, conf 不被 cap"""
    from core.focus import pusher as P
    orig_calc = P._calc_price_targets
    P._calc_price_targets = lambda session, ticker, dirn, entry: {
        "t1": entry + entry * 0.025,   # +2.5%
        "stop": entry - entry * 0.01,  # -1.0% → R/R = 2.5
    }
    try:
        sess = _StubSession(master_price=100.0, follower_price=50.0)
        hit = _stub_hit(direction="long", rsi=60, strength="STRONG", vol_ratio=1.5)
        result = _fmt_signal_with_conflict(
            hit, sess, "long", "🟢 RKLB", "tech"
        )
        assert result is not None, "R/R=2.5 不应被堵"
        assert "2.5:1" in result["text"], "盈亏比 2.5:1 应该出现在文案里"
    finally:
        P._calc_price_targets = orig_calc


def test_missing_targets_passes_through():
    """
    targets 为空 → R/R 是 None → 信号正常通过(rapid_move 这类)
    """
    from core.focus import pusher as P
    orig_calc = P._calc_price_targets
    P._calc_price_targets = lambda session, ticker, dirn, entry: {}
    try:
        sess = _StubSession(master_price=100.0, follower_price=50.0)
        hit = _stub_hit()
        result = _fmt_signal_with_conflict(
            hit, sess, "short", "🔴 RKLB", "tech"
        )
        assert result is not None, "无 R/R 应放行"
    finally:
        P._calc_price_targets = orig_calc


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
