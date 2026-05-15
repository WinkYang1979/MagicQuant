"""
tests/test_indicator_freeze_v0_5_32.py — v0.5.32 P0 #1 IndicatorFreezeDetector

锁定指标数值冻结检测的状态机行为。
关键：30s 拉取 × 5 = ~150s 后才告警；恢复必须发出 recovered 事件。

run: PYTHONIOENCODING=utf-8 python -m pytest tests/test_indicator_freeze_v0_5_32.py -v
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# 仅 import 类，不触发 focus_manager 启动副作用
from core.focus import focus_manager as _fm  # noqa: E402
from core.focus.focus_manager import IndicatorFreezeDetector  # noqa: E402

# v0.5.33 P0: 生产线上 detector 已禁用; 单测打开 kill switch 测状态机逻辑
_fm._IFD_DISABLED = False


def test_changing_values_never_freeze():
    """正常变化 — 永远 ok"""
    d = IndicatorFreezeDetector(threshold=5)
    assert d.update(57.9, 1.10, now=100.0) == "ok"
    assert d.update(58.1, 1.11, now=130.0) == "ok"
    assert d.update(58.5, 1.13, now=160.0) == "ok"
    assert not d.frozen


def test_five_identical_triggers_freeze():
    """5 次相同 → freeze_started"""
    d = IndicatorFreezeDetector(threshold=5)
    assert d.update(57.9, 6.58, now=100.0) == "ok"
    assert d.update(57.9, 6.58, now=130.0) == "ok"
    assert d.update(57.9, 6.58, now=160.0) == "ok"
    assert d.update(57.9, 6.58, now=190.0) == "ok"
    assert d.update(57.9, 6.58, now=220.0) == "freeze_started"
    assert d.frozen


def test_freeze_continues_silently():
    """冻结后继续相同 → freeze_ongoing,不重复告警"""
    d = IndicatorFreezeDetector(threshold=5)
    for t in (100.0, 130.0, 160.0, 190.0, 220.0):
        d.update(57.9, 6.58, now=t)
    assert d.frozen
    assert d.update(57.9, 6.58, now=250.0) == "freeze_ongoing"
    assert d.update(57.9, 6.58, now=280.0) == "freeze_ongoing"


def test_recovery_after_freeze():
    """冻结后数值变化 → recovered"""
    d = IndicatorFreezeDetector(threshold=5)
    for t in (100.0, 130.0, 160.0, 190.0, 220.0):
        d.update(57.9, 6.58, now=t)
    assert d.frozen
    # 数值变了 → 恢复
    assert d.update(58.4, 6.71, now=400.0) == "recovered"
    assert not d.frozen


def test_freeze_minutes_zero_when_not_frozen():
    d = IndicatorFreezeDetector(threshold=5)
    assert d.freeze_minutes(now=999.0) == 0


def test_freeze_minutes_reflects_duration():
    d = IndicatorFreezeDetector(threshold=5)
    for t in (100.0, 130.0, 160.0, 190.0, 220.0):
        d.update(57.9, 6.58, now=t)
    # 冻结起点是 now=220 (5th identical), 现在过了 6 min
    assert d.freeze_minutes(now=220.0 + 6 * 60) >= 6


def test_threshold_3_for_aggressive_test():
    """阈值参数化，便于覆盖不同灵敏度"""
    d = IndicatorFreezeDetector(threshold=3)
    assert d.update(50.0, 1.0, now=0) == "ok"
    assert d.update(50.0, 1.0, now=30) == "ok"
    assert d.update(50.0, 1.0, now=60) == "freeze_started"


def test_partial_changes_reset_counter():
    """RSI 变 vol 不变 → 重置(都是签名一部分)"""
    d = IndicatorFreezeDetector(threshold=5)
    for t in (0, 30, 60, 90):
        d.update(57.9, 6.58, now=t)
    # 第 5 次 vol_ratio 变了 → 应该 ok 而非 freeze_started
    assert d.update(57.9, 6.59, now=120) == "ok"
    assert not d.frozen


def test_none_values_dont_break_state():
    """data_ok=False 时 RSI/vol 是 None,不应影响累积"""
    d = IndicatorFreezeDetector(threshold=3)
    assert d.update(57.9, 6.58, now=0) == "ok"
    assert d.update(57.9, 6.58, now=30) == "ok"
    # 中途数据缺失 → 不增不减,保持 sig_repeat=2
    assert d.update(None, None, now=60) == "ok"
    assert d.sig_repeat == 2  # 没增长也没重置
    assert d.update(57.9, 6.58, now=90) == "freeze_started"


def test_recovery_with_threshold_3():
    """阈值 3 + 恢复路径"""
    d = IndicatorFreezeDetector(threshold=3)
    for t in (0, 30, 60):
        d.update(60.0, 2.5, now=t)
    assert d.frozen
    assert d.update(60.5, 2.5, now=90) == "recovered"
    assert not d.frozen
    # 恢复后再次变化 → 普通 ok,不是再次 recovered
    assert d.update(61.0, 2.6, now=120) == "ok"


def test_reset_clears_all_state():
    """v0.5.32 P0 #1.1: reset() 清除全部状态(给盘前/盘后跳过用)"""
    d = IndicatorFreezeDetector(threshold=3)
    for t in (0, 30, 60):
        d.update(60.0, 2.5, now=t)
    assert d.frozen
    d.reset()
    assert d.sig_last is None
    assert d.sig_repeat == 0
    assert not d.frozen
    assert d.freeze_started_ts == 0.0
    # reset 后,从新一轮开始累积
    assert d.update(60.0, 2.5, now=120) == "ok"
    assert d.sig_repeat == 1


def test_reset_avoids_carryover_across_premarket():
    """
    模拟场景: 盘前累积到 frozen,盘前 reset(),开盘后 RSI 跳变 → 不该被
    判为 recovered (因为根本没真冻结过)
    """
    d = IndicatorFreezeDetector(threshold=3)
    # 盘前累积冻结
    for t in (0, 30, 60):
        d.update(57.9, 5.87, now=t)
    assert d.frozen
    # 盘前 reset
    d.reset()
    # 开盘第一次更新 — 应该是 ok,而非 recovered
    assert d.update(58.4, 6.71, now=600) == "ok"


if __name__ == "__main__":
    # 简易自跑(不依赖 pytest)
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
