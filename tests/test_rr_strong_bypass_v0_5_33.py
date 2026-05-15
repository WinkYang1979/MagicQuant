"""
tests/test_rr_strong_bypass_v0_5_33.py — v0.5.33 P0 v2 STRONG 信号豁免 R/R 闸门

锁定 _fmt_signal_with_conflict 的闸门路径:
  - STRONG + R/R < 1.5 → bypass, 信号通过
  - WEAK   + R/R < 1.5 → 仍按 P0#2 拦截 return None
  - STRONG/WEAK + R/R ≥ 2.0 → 正常推送 (闸门不动)

直接 monkey-patch _calc_price_targets 控制 t1/stop, 不靠 prices history
推算, 避免触发 v0.5.33 P0 #1 (reward<0.5% 放行)。

run: PYTHONIOENCODING=utf-8 python tests/test_rr_strong_bypass_v0_5_33.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.focus import pusher as _pusher  # noqa: E402


def _assert(cond, name):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}")
    if not cond:
        sys.exit(1)


class FakeSession:
    """最小 stub"""
    def __init__(self, master, master_price):
        self.master = master
        self.followers = []
        self._prices = {master: master_price}
        self.prices = {master: [(0, master_price)] * 20}

    def get_last_price(self, ticker):
        return self._prices.get(ticker)

    def get_day_change_pct(self, ticker):
        return 0.0   # 不触发 chase_warn (≥10%) 分支

    def get_position(self, ticker):
        return None


def _make_hit(trigger, ticker, strength, direction="long"):
    return {
        "trigger": trigger,
        "ticker":  ticker,
        "strength": strength,
        "direction": direction,
        "data": {"current": 100.0, "rsi": 25 if strength == "STRONG" else 35,
                 "candle": {"type": "bullish"}, "vol_ratio": 1.2,
                 "dist_low": 0.5},
        "title": f"test {trigger} {strength}",
    }


def _patched_targets(t1, stop):
    """构造 _calc_price_targets 的返回, 控制 R/R"""
    return {
        "t1": t1, "t1_label": "test", "t2": None, "t2_label": "",
        "stop": stop, "atr": abs(t1 - stop) / 2.0,
        "tech_target": t1, "tech_stop": stop,
        "stat_target": None, "stat_stop": None,
        "stat_samples": 0, "conflict": False,
    }


def _run_format(strength, t1, stop, entry=100.0):
    """通用调用 helper, monkey-patch _calc_price_targets 后还原"""
    orig = _pusher._calc_price_targets
    _pusher._calc_price_targets = lambda *a, **k: _patched_targets(t1, stop)
    try:
        sess = FakeSession("US.RKLB", entry)
        hit = _make_hit("swing_bottom", "US.RKLB", strength)
        return _pusher._fmt_signal_with_conflict(
            hit, sess, "long", "title", "tech")
    finally:
        _pusher._calc_price_targets = orig


# ── Tests ─────────────────────────────────────────────────

def test_strong_bypasses_low_rr():
    """STRONG + R/R = 1.0 (reward 1, risk 1) → 闸门豁免"""
    # entry=100, t1=101, stop=99 → reward=1, risk=1, R/R=1.0
    # reward 1 > entry×0.005=0.5 → 不触发 small-reward 放行, 进入闸门
    result = _run_format("STRONG", t1=101.0, stop=99.0)
    _assert(result is not None,
            f"STRONG R/R=1.0 应豁免闸门, got {result}")
    _assert(isinstance(result, dict) and "text" in result,
            "返回 dict 含 text 字段")


def test_strong_bypasses_user_reproducer():
    """用户线上证据: swing_bottom R/R=1.14 STRONG 应通过"""
    # entry=125, t1=126.5, stop=123.5 → reward=1.5, risk=1.5, R/R=1.0
    # 模拟接近用户报告的 1.14:1
    result = _run_format("STRONG", t1=126.7, stop=123.5, entry=125.0)
    _assert(result is not None, "STRONG 线上 reproducer 应豁免")


def test_weak_still_blocked():
    """WEAK + R/R = 1.0 → 闸门按 P0#2 拦截"""
    result = _run_format("WEAK", t1=101.0, stop=99.0)
    _assert(result is None,
            f"WEAK R/R=1.0 应被闸门拦, got {result}")


def test_normal_rr_strong_passes():
    """STRONG + R/R = 2.0 → 正常通过 (闸门不动)"""
    # entry=100, t1=110, stop=95 → reward=10, risk=5, R/R=2.0
    result = _run_format("STRONG", t1=110.0, stop=95.0)
    _assert(result is not None, "STRONG R/R=2.0 正常通过")


def test_normal_rr_weak_passes():
    """WEAK + R/R = 2.0 → 正常通过 (闸门不动)"""
    result = _run_format("WEAK", t1=110.0, stop=95.0)
    _assert(result is not None, "WEAK R/R=2.0 正常通过")


def test_weak_at_gate_boundary_passes():
    """WEAK + R/R = 1.5 → 边界刚好通过 (rr < 1.5 是严格小于)"""
    # entry=100, t1=103, stop=98 → reward=3, risk=2, R/R=1.5
    result = _run_format("WEAK", t1=103.0, stop=98.0)
    _assert(result is not None, "WEAK R/R=1.5 (边界) 应通过")


def main():
    print("=" * 60)
    print("v0.5.33 P0 v2 — STRONG 信号豁免 R/R 闸门回归")
    print("=" * 60)
    print("\n[1/3] STRONG + R/R<1.5 → 豁免")
    test_strong_bypasses_low_rr()
    test_strong_bypasses_user_reproducer()
    print("\n[2/3] WEAK + R/R<1.5 → 仍拦")
    test_weak_still_blocked()
    test_weak_at_gate_boundary_passes()
    print("\n[3/3] R/R≥2 任意强度都通过")
    test_normal_rr_strong_passes()
    test_normal_rr_weak_passes()
    print("\n" + "=" * 60)
    print("✅ STRONG 豁免锁定 — WEAK 闸门保留 P0#2 设计")
    print("=" * 60)


if __name__ == "__main__":
    main()
