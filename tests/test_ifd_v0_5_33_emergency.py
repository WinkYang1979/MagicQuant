"""
tests/test_ifd_v0_5_33_emergency.py — v0.5.33 IFD 紧急修复回归

锁定的回归场景:
  1. 默认阈值已提升到 30 (避免 bar 内 RSI 恒定误报)
  2. RSI/vol 在变化时绝不触发 freeze (用户线上 reproducer)
  3. history ring buffer 记录最近 N 次采样 (告警诊断)
  4. reset() 同时清空 history
  5. 30 次相同才真冻结 (跨 3 个 5m 柱)

run: PYTHONIOENCODING=utf-8 python tests/test_ifd_v0_5_33_emergency.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.focus import focus_manager as _fm  # noqa: E402
from core.focus.focus_manager import IndicatorFreezeDetector  # noqa: E402

# v0.5.33 P0: 生产线上 detector 已禁用; 单测打开 kill switch 测状态机逻辑
_fm._IFD_DISABLED = False


def test_default_threshold_is_30():
    """v0.5.33: 默认阈值 5→30, 防止 bar 内误报"""
    d = IndicatorFreezeDetector()
    assert d.threshold == 30, f"默认阈值应为 30, 实际 {d.threshold}"


def test_bar_internal_stable_never_freezes_at_default():
    """
    v0.5.33: 5m K 线柱内 30s 拉取 = 最多 10 次相同 (5min/30s),
    用默认阈值 30 不会误报。这是用户线上的 reproducer 场景。
    """
    d = IndicatorFreezeDetector()  # threshold=30
    # 模拟 5m bar 内 10 次完全相同 (bar 还没换柱)
    for i in range(10):
        result = d.update(57.9, 6.58, now=i * 30.0)
        assert result == "ok", f"第 {i+1} 次不该触发 freeze, got {result}"
    assert not d.frozen, "10 次相同不应进入 frozen 状态"
    assert d.sig_repeat == 10


def test_real_freeze_requires_30_samples():
    """30 次相同 = 15 min = 跨 3 个 5m 柱仍不变 → 真冻结"""
    d = IndicatorFreezeDetector()
    for i in range(29):
        assert d.update(57.9, 6.58, now=i * 30.0) == "ok"
    # 第 30 次触发
    assert d.update(57.9, 6.58, now=29 * 30.0) == "freeze_started"
    assert d.frozen


def test_changing_values_user_reproducer():
    """
    用户证据回归:
      23:35 RSI=32.0 vol=4.72
      23:35 RSI=34.1 vol=4.74
      23:36 RSI=31.7 vol=4.82
    明显变化的值绝对不该触发 freeze (即使 threshold=5 也不该)
    """
    d = IndicatorFreezeDetector(threshold=5)
    assert d.update(32.0, 4.72, now=100.0) == "ok"
    assert d.update(34.1, 4.74, now=130.0) == "ok"
    assert d.update(31.7, 4.82, now=160.0) == "ok"
    assert d.update(33.0, 4.80, now=190.0) == "ok"
    assert d.update(32.5, 4.75, now=220.0) == "ok"
    assert not d.frozen, "变化的值不应触发 freeze"
    assert d.sig_repeat == 1, "每次都是新签名,repeat 应一直是 1"


def test_history_records_recent_samples():
    """v0.5.33: history ring buffer 保留诊断信息"""
    d = IndicatorFreezeDetector(threshold=5)
    d.update(50.0, 1.0, now=100.0)
    d.update(50.0, 1.0, now=130.0)
    d.update(51.0, 1.1, now=160.0)
    assert len(d.history) == 3
    # 最后一条是新签名
    ts, rsi, vol, sig, rep = d.history[-1]
    assert rsi == 51.0 and vol == 1.1
    assert rep == 1  # 新签名,repeat 重置


def test_history_dump_includes_repeat_counter():
    """诊断字符串要把 sig_repeat 打出来,便于线上判断是真冻结还是误报"""
    d = IndicatorFreezeDetector(threshold=5)
    d.update(50.0, 1.0, now=100.0)
    d.update(50.0, 1.0, now=130.0)
    d.update(50.0, 1.0, now=160.0)
    dump = d.history_dump()
    assert "repeat=1" in dump
    assert "repeat=2" in dump
    assert "repeat=3" in dump
    assert "rsi=50.00" in dump


def test_history_capped_at_12():
    """ring buffer 上限 12,避免内存膨胀"""
    d = IndicatorFreezeDetector(threshold=50)
    for i in range(20):
        d.update(50.0, 1.0, now=i * 30.0)
    assert len(d.history) == 12


def test_reset_clears_history():
    """v0.5.33: reset() 同时清空 history"""
    d = IndicatorFreezeDetector(threshold=5)
    d.update(50.0, 1.0, now=0)
    d.update(50.0, 1.0, now=30)
    assert len(d.history) == 2
    d.reset()
    assert len(d.history) == 0


def test_history_dump_empty():
    """空 history 返回 '(empty)'"""
    d = IndicatorFreezeDetector()
    assert d.history_dump() == "(empty)"


def test_explicit_threshold_still_overridable():
    """显式传入 threshold 仍生效 (测试和 v0.5.32 老 caller 兼容)"""
    d = IndicatorFreezeDetector(threshold=3)
    assert d.threshold == 3
    d.update(50.0, 1.0, now=0)
    d.update(50.0, 1.0, now=30)
    assert d.update(50.0, 1.0, now=60) == "freeze_started"


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
            print(f"  ERR   {fn.__name__}: {e!r}")
            fail += 1
    print(f"\n{len(fns) - fail}/{len(fns)} passed")
    sys.exit(fail)
