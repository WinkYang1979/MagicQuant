"""
tests/test_compute_rr_v0_5_33.py — v0.5.33 P0 R/R 闸门修复回归

锁定: _compute_rr 在 reward 微小 (< entry × 0.5%) 时返回 None,
让闸门放行而不是用近似 0 的 R/R 拦截 swing_bottom 等底部信号。

线上证据: 2026-05-16 ET 10:40 swing_bottom RKLB R/R 0.00:1 被拦,
         2026-05-15 ET 全天 248 条 trigger 中 0 条 swing_bottom。

run: PYTHONIOENCODING=utf-8 python tests/test_compute_rr_v0_5_33.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.focus.pusher import _compute_rr  # noqa: E402


def _assert(cond, name):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}")
    if not cond:
        sys.exit(1)


# ── 正常 R/R 情况 ──────────────────────────────────────────

def test_normal_rr_long():
    """正常 LONG: entry=100, t1=110, stop=95 → R/R = 10/5 = 2.0"""
    rr = _compute_rr({"t1": 110.0, "stop": 95.0}, 100.0)
    _assert(rr is not None and abs(rr - 2.0) < 0.001, f"R/R 应=2.0, got {rr}")


def test_normal_rr_short():
    """正常 SHORT: entry=100, t1=90 (向下), stop=105 → R/R = 10/5 = 2.0"""
    rr = _compute_rr({"t1": 90.0, "stop": 105.0}, 100.0)
    _assert(rr is not None and abs(rr - 2.0) < 0.001, f"R/R 应=2.0, got {rr}")


def test_rr_below_gate():
    """R/R = 0.5: entry=100, t1=101, stop=98 → reward=1, risk=2, R/R=0.5"""
    rr = _compute_rr({"t1": 101.0, "stop": 98.0}, 100.0)
    _assert(rr is not None and abs(rr - 0.5) < 0.001, f"R/R 应=0.5, got {rr}")


# ── v0.5.33 P0 修复: 微小 reward 放行 ──────────────────────

def test_tiny_reward_returns_none():
    """
    线上 reproducer: entry=$126.47, t1=$126.48 (大 0.01),
    reward=0.01 < entry×0.005=0.6325 → 应返回 None (放行)
    """
    rr = _compute_rr({"t1": 126.48, "stop": 125.0}, 126.47)
    _assert(rr is None,
            f"reward 0.01 < entry×0.5%=0.63, 应返回 None, got {rr}")


def test_swing_bottom_rklb_reproducer():
    """
    swing_bottom on RKLB at ~$126: 若 ATR≈0 → t1 ≈ entry+0.05,
    reward 0.05 < 126×0.005=0.63 → 放行 (修复前 R/R≈0.04 被拦)
    """
    rr = _compute_rr({"t1": 126.30, "stop": 124.50}, 126.25)
    _assert(rr is None,
            f"线上 reproducer 应放行 (return None), got {rr}")


def test_reward_exactly_at_boundary():
    """边界: reward == entry × 0.5% 应该走正常 R/R 计算 (不放行)"""
    entry = 100.0
    reward = entry * 0.005  # 正好 0.5
    rr = _compute_rr({"t1": entry + reward, "stop": entry - 5.0}, entry)
    # reward 不严格 < entry × 0.005 → 不放行, 走正常计算 = 0.5/5 = 0.1
    _assert(rr is not None and abs(rr - 0.1) < 0.001,
            f"边界 reward 正好 0.5% 应走正常计算 R/R=0.1, got {rr}")


def test_reward_just_below_boundary():
    """边界: reward < entry × 0.5% (差 0.001) 应放行"""
    entry = 100.0
    reward = entry * 0.005 - 0.001  # 0.499
    rr = _compute_rr({"t1": entry + reward, "stop": entry - 5.0}, entry)
    _assert(rr is None, f"reward 略低于边界应放行, got {rr}")


# ── 既有契约保留 ──────────────────────────────────────────

def test_missing_t1_returns_none():
    rr = _compute_rr({"t1": None, "stop": 95.0}, 100.0)
    _assert(rr is None, "缺 t1 应返回 None")


def test_missing_stop_returns_none():
    rr = _compute_rr({"t1": 110.0, "stop": None}, 100.0)
    _assert(rr is None, "缺 stop 应返回 None")


def test_zero_risk_returns_none():
    """stop == entry → risk=0 → 返回 None"""
    rr = _compute_rr({"t1": 110.0, "stop": 100.0}, 100.0)
    _assert(rr is None, "risk=0 应返回 None")


def test_missing_entry_returns_none():
    rr = _compute_rr({"t1": 110.0, "stop": 95.0}, None)
    _assert(rr is None, "缺 entry 应返回 None")


def test_invalid_types_returns_none():
    rr = _compute_rr({"t1": "abc", "stop": 95.0}, 100.0)
    _assert(rr is None, "type error 应返回 None")


def main():
    print("=" * 60)
    print("v0.5.33 P0 _compute_rr 闸门修复回归")
    print("=" * 60)
    print("\n[1/4] 正常 R/R 计算")
    test_normal_rr_long()
    test_normal_rr_short()
    test_rr_below_gate()
    print("\n[2/4] v0.5.33 P0: 微小 reward 放行")
    test_tiny_reward_returns_none()
    test_swing_bottom_rklb_reproducer()
    test_reward_exactly_at_boundary()
    test_reward_just_below_boundary()
    print("\n[3/4] 既有 None 契约保留")
    test_missing_t1_returns_none()
    test_missing_stop_returns_none()
    test_zero_risk_returns_none()
    test_missing_entry_returns_none()
    test_invalid_types_returns_none()
    print("\n" + "=" * 60)
    print("✅ swing_bottom R/R=0 误拦修复 — 锁定: reward<0.5%时 None 放行")
    print("=" * 60)


if __name__ == "__main__":
    main()
