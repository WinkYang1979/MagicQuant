"""
MagicQuant universe configuration.
VERSION : v1.0.0
DEPENDS : typing

Purpose / 用途:
Prepare a multi-symbol interface while keeping Arena Trial defaulted to RKLB.
预留多标的接口，但 Arena Trial 默认只运行 RKLB。
"""
from __future__ import annotations

from typing import Iterable, Tuple


DEFAULT_SYMBOL = "RKLB"
UNIVERSE: Tuple[str, ...] = ("RKLB",)
RESERVED_SYMBOLS: Tuple[str, ...] = ("ASTS", "LUNR", "RDW", "ACHR", "JOBY", "PL")


def get_universe() -> Tuple[str, ...]:
    """Return enabled Arena symbols. / 返回当前启用的 Arena 标的。"""

    return UNIVERSE


def validate_symbol(symbol: str, enabled: Iterable[str] | None = None) -> None:
    """Reject symbols outside the enabled universe. / 拒绝未启用标的。"""

    allowed = tuple(enabled) if enabled is not None else UNIVERSE
    if symbol not in allowed:
        raise ValueError(f"symbol {symbol!r} is not enabled for Arena Trial; enabled={allowed}")
