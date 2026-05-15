"""
tests/smoke_data_alert_v0_5_33.py — v0.5.33 数据异常告警冒烟测试

验证：
  1. K_5M 订阅失败 mock → Telegram 告警发出, 格式统一
  2. 同类告警 30 min 内只推一次 (cooldown 节流)
  3. 不同类型告警互不节流 (各自 warn_key)
  4. 5 类告警 (kline_sub / no_indicators / indicator_freeze /
     futu_conn / futu_conn_128) 都能从 _push_system_warning 发出

Windows 运行: PYTHONIOENCODING=utf-8 python tests/smoke_data_alert_v0_5_33.py
"""
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.focus import focus_manager as fm  # noqa: E402


def _make_capture():
    """收集 send_tg_fn 调用的 mock。"""
    captured = []

    def _capture(msg, *args, **kwargs):
        captured.append(str(msg))

    return _capture, captured


def _assert(cond, name):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}")
    if not cond:
        sys.exit(1)


def test_kline_sub_alert():
    print("\n[1/4] K_5M 订阅失败 dry-run")
    capture, captured = _make_capture()
    fm._send_tg_ref = capture
    fm._tg_warn_last.clear()  # 清节流状态

    fm._push_system_warning(
        "kline_sub", "K_5M 订阅失败",
        "US.RKLB ret=-1: connection refused",
        impact="信号已暂停 (拿不到 5m K 线)",
        suggestion="检查 Futu OpenD / 重启系统",
    )

    _assert(len(captured) == 1, "TG 收到 1 条告警")
    msg = captured[0]
    _assert("MagicQuant 数据异常告警" in msg, "标题正确")
    _assert("错误类型: K_5M 订阅失败" in msg, "错误类型字段")
    _assert("影响: 信号已暂停" in msg, "影响字段")
    _assert("建议: 检查 Futu OpenD" in msg, "建议字段")
    _assert("详情: US.RKLB ret=-1" in msg, "详情字段保留 ticker/ret")
    print(f"\n--- 告警全文 ---\n{msg}\n----------------")


def test_cooldown_30min():
    print("\n[2/4] 同类告警 30 min 冷却")
    capture, captured = _make_capture()
    fm._send_tg_ref = capture
    fm._tg_warn_last.clear()

    fm._push_system_warning("kline_sub", "K_5M 订阅失败", "A")
    fm._push_system_warning("kline_sub", "K_5M 订阅失败", "B")  # 应被节流
    fm._push_system_warning("kline_sub", "K_5M 订阅失败", "C")  # 应被节流

    _assert(len(captured) == 1, "30 min 内只推 1 条 (节流生效)")
    _assert("A" in captured[0], "首条详情透出")
    _assert(fm._TG_WARN_INTERVAL == 30 * 60, "_TG_WARN_INTERVAL = 30 min")

    # 模拟"31 分钟后" → 应重新允许
    fm._tg_warn_last["kline_sub"] = time.time() - 31 * 60
    fm._push_system_warning("kline_sub", "K_5M 订阅失败", "D")
    _assert(len(captured) == 2, "31 min 后允许第 2 条")


def test_cross_type_independence():
    print("\n[3/4] 不同类型告警互不节流")
    capture, captured = _make_capture()
    fm._send_tg_ref = capture
    fm._tg_warn_last.clear()

    fm._push_system_warning("kline_sub", "K_5M 订阅失败", "x")
    fm._push_system_warning("no_indicators", "has_indicators 失效", "y",
                            duration_min=12)
    fm._push_system_warning("indicator_freeze", "指标冻结", "z",
                            duration_min=2)
    fm._push_system_warning("futu_conn", "Futu 连接断开", "w")
    fm._push_system_warning("futu_conn_128", "Futu 连接数超 128", "v")

    _assert(len(captured) == 5, "5 个不同 warn_key 各发 1 条")
    types = [
        "K_5M 订阅失败", "has_indicators 失效", "指标冻结",
        "Futu 连接断开", "Futu 连接数超 128",
    ]
    for t in types:
        _assert(any(t in m for m in captured), f"包含 [{t}] 告警")


def test_duration_format():
    print("\n[4/4] 持续时间字段格式化")
    capture, captured = _make_capture()
    fm._send_tg_ref = capture
    fm._tg_warn_last.clear()

    fm._push_system_warning("no_indicators", "has_indicators 失效", "",
                            duration_min=12)
    fm._push_system_warning("indicator_freeze", "指标冻结", "",
                            duration_min=2)
    fm._push_system_warning("futu_conn", "Futu 连接断开", "")  # duration=0

    _assert("持续时间: 12 分钟" in captured[0], "duration=12 → '12 分钟'")
    _assert("持续时间: 2 分钟" in captured[1], "duration=2 → '2 分钟'")
    _assert("持续时间: 刚发生" in captured[2], "duration=0 → '刚发生'")


def main():
    print("=" * 60)
    print("v0.5.33 数据异常告警 — dry-run 冒烟测试")
    print("=" * 60)
    test_kline_sub_alert()
    test_cooldown_30min()
    test_cross_type_independence()
    test_duration_format()
    print("\n" + "=" * 60)
    print("✅ 全部通过 — 5 类告警 + 30min cooldown + 统一格式")
    print("=" * 60)


if __name__ == "__main__":
    main()
