"""
MagicQuant Risk Engine — Severity 定义
Dare to dream. Data to win.

严重度排序: block > warn > advisory > pass
"""

from enum import Enum


class Severity(str, Enum):
    PASS     = "pass"       # 通过,无任何问题
    ADVISORY = "advisory"   # 仅提醒,不影响流程
    WARN     = "warn"       # 警告,可用户覆盖继续
    BLOCK    = "block"      # 拦截,硬阻止


# 排序权重(数字越大越严重)
SEVERITY_WEIGHT = {
    Severity.PASS:     0,
    Severity.ADVISORY: 10,
    Severity.WARN:     50,
    Severity.BLOCK:    100,
}


def max_severity(severities: list) -> Severity:
    """取一组 severity 中最严重的"""
    if not severities:
        return Severity.PASS
    return max(severities, key=lambda s: SEVERITY_WEIGHT.get(s, 0))


def severity_emoji(severity: str) -> str:
    """给 TG 推送用"""
    return {
        "pass":     "✅",
        "advisory": "💡",
        "warn":     "⚠️",
        "block":    "❌",
    }.get(severity, "❓")


def is_blocking(severity: str) -> bool:
    """block 级别才真正拦截"""
    return severity == Severity.BLOCK.value
