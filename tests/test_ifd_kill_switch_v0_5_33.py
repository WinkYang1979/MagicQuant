"""
tests/test_ifd_kill_switch_v0_5_33.py — v0.5.33 P0 kill switch 回归

锁定: 默认 _IFD_DISABLED=True 时 detector 不进入任何冻结状态机分支,
保证线上告警刷屏被切断。周末修复 detector 逻辑前, 此开关必须保留 True。

run: PYTHONIOENCODING=utf-8 python tests/test_ifd_kill_switch_v0_5_33.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.focus import focus_manager as fm  # noqa: E402
from core.focus.focus_manager import IndicatorFreezeDetector  # noqa: E402


def _assert(cond, name):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}")
    if not cond:
        sys.exit(1)


def test_default_disabled():
    """模块加载默认 _IFD_DISABLED=True"""
    # 模块刚加载时应该是 True (周末修复前必须保持)
    # 注意: 其他测试文件会改这个标志, 这里强制读模块源
    import importlib
    fresh = importlib.reload(fm)
    _assert(fresh._IFD_DISABLED is True,
            "模块加载默认 _IFD_DISABLED=True (kill switch 激活)")


def test_disabled_update_always_returns_ok():
    """禁用时 update() 不论输入永远返回 'ok'"""
    fm._IFD_DISABLED = True
    try:
        d = IndicatorFreezeDetector(threshold=3)
        # 即使 5 次完全相同,也不应进入 frozen
        for i in range(10):
            result = d.update(50.0, 1.0, now=i * 30.0)
            _assert(result == "ok", f"第 {i+1} 次禁用态 update 应返回 ok, got {result}")
        _assert(not d.frozen, "禁用态不应进入 frozen")
        _assert(d.sig_repeat == 0, "禁用态 sig_repeat 保持 0 (未进入状态机)")
    finally:
        fm._IFD_DISABLED = True  # 保持禁用


def test_kill_switch_can_be_disabled_for_tests():
    """单测能临时打开 kill switch 验证状态机"""
    fm._IFD_DISABLED = False
    try:
        d = IndicatorFreezeDetector(threshold=3)
        d.update(50.0, 1.0, now=0)
        d.update(50.0, 1.0, now=30)
        result = d.update(50.0, 1.0, now=60)
        _assert(result == "freeze_started",
                f"打开 kill switch 后状态机应正常工作, got {result}")
    finally:
        fm._IFD_DISABLED = True  # 恢复禁用


def test_disabled_state_does_not_pollute_history():
    """禁用态不写 history (避免日志混乱)"""
    fm._IFD_DISABLED = True
    try:
        d = IndicatorFreezeDetector()
        for i in range(5):
            d.update(50.0, 1.0, now=i * 30.0)
        _assert(len(d.history) == 0, "禁用态 history 应保持空")
    finally:
        fm._IFD_DISABLED = True


def main():
    print("=" * 60)
    print("v0.5.33 P0 IFD kill switch 回归")
    print("=" * 60)
    print("\n[1/4] 默认禁用")
    test_default_disabled()
    print("\n[2/4] 禁用态 update() 永远 ok")
    test_disabled_update_always_returns_ok()
    print("\n[3/4] kill switch 可临时打开 (单测用)")
    test_kill_switch_can_be_disabled_for_tests()
    print("\n[4/4] 禁用态 history 不污染")
    test_disabled_state_does_not_pollute_history()
    print("\n" + "=" * 60)
    print("✅ kill switch 已锁定 — 周末修复前 _IFD_DISABLED 必须保持 True")
    print("=" * 60)


if __name__ == "__main__":
    main()
