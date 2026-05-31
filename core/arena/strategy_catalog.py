"""
MagicQuant Arena Lite strategy catalog.
VERSION : v1.0.0
DEPENDS : dataclasses, typing

Purpose / 用途:
Standardize strategy intake by family. This is a controlled catalog, not a
Discovery Agent: it does not generate, mutate, trade, or auto-promote horses.
按家族标准化策略准入；这是受控目录，不是 Discovery Agent：不生成、不变异、不交易、不自动晋级。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


TREND_FAMILY = "Trend Family"
MEAN_REVERSION_FAMILY = "Mean Reversion Family"
VOLUME_FAMILY = "Volume Family"
EVENT_FAMILY = "Event Family"
AI_FAMILY = "AI Family"

ALLOWED_FAMILIES = {
    TREND_FAMILY,
    MEAN_REVERSION_FAMILY,
    VOLUME_FAMILY,
    EVENT_FAMILY,
    AI_FAMILY,
}

MIN_FAMILY_CANDIDATES = 3
MAX_FAMILY_CANDIDATES = 5
MAX_ARENA_STRATEGIES = 20

STATUS_CANDIDATE = "candidate"
STATUS_ACTIVE = "active"
STATUS_FROZEN = "frozen"
STATUS_REJECTED = "rejected"

ALLOWED_STATUSES = {
    STATUS_CANDIDATE,
    STATUS_ACTIVE,
    STATUS_FROZEN,
    STATUS_REJECTED,
}


@dataclass(frozen=True)
class StrategyCatalogEntry:
    """One controlled Arena horse. / 一匹受控 Arena 候选马。"""

    strategy_id: str
    family: str
    description: str
    status: str
    fitness_score: float


def _active_entries(entries: Iterable[StrategyCatalogEntry]) -> List[StrategyCatalogEntry]:
    return [entry for entry in entries if entry.status in {STATUS_CANDIDATE, STATUS_ACTIVE}]


def validate_catalog(entries: Iterable[StrategyCatalogEntry]) -> None:
    """Enforce family, size, status, and id rules. / 强制家族、规模、状态和 ID 规则。"""

    rows = list(entries)
    active_rows = _active_entries(rows)
    if len(active_rows) > MAX_ARENA_STRATEGIES:
        raise ValueError(f"Arena catalog cannot exceed {MAX_ARENA_STRATEGIES} active strategies")

    seen_ids = set()
    by_family: Dict[str, int] = {}
    for entry in rows:
        if not entry.strategy_id or entry.strategy_id in seen_ids:
            raise ValueError(f"duplicate or empty strategy_id: {entry.strategy_id!r}")
        seen_ids.add(entry.strategy_id)
        if entry.family not in ALLOWED_FAMILIES:
            raise ValueError(f"strategy {entry.strategy_id!r} has unknown family: {entry.family!r}")
        if entry.status not in ALLOWED_STATUSES:
            raise ValueError(f"strategy {entry.strategy_id!r} has unknown status: {entry.status!r}")
        if entry.status in {STATUS_CANDIDATE, STATUS_ACTIVE}:
            by_family[entry.family] = by_family.get(entry.family, 0) + 1

    for family, count in by_family.items():
        if count > MAX_FAMILY_CANDIDATES:
            raise ValueError(f"{family} cannot exceed {MAX_FAMILY_CANDIDATES} active candidates, got {count}")


def group_by_family(entries: Iterable[StrategyCatalogEntry]) -> Dict[str, List[StrategyCatalogEntry]]:
    """Return active candidates grouped by family. / 返回按家族分组的有效候选。"""

    validate_catalog(entries)
    grouped: Dict[str, List[StrategyCatalogEntry]] = {family: [] for family in ALLOWED_FAMILIES}
    for entry in _active_entries(entries):
        grouped[entry.family].append(entry)
    for family_entries in grouped.values():
        family_entries.sort(key=lambda entry: (-entry.fitness_score, entry.strategy_id))
    return grouped


def select_family_champions(entries: Iterable[StrategyCatalogEntry]) -> Dict[str, StrategyCatalogEntry]:
    """Select one champion per family by fitness score. / 按 fitness_score 选出每个家族冠军。"""

    grouped = group_by_family(entries)
    champions: Dict[str, StrategyCatalogEntry] = {}
    for family, family_entries in grouped.items():
        if family_entries:
            champions[family] = family_entries[0]
    return champions


def champion_strategy_ids(entries: Iterable[StrategyCatalogEntry]) -> Tuple[str, ...]:
    """Return stable strategy IDs allowed to vote in Champion Portfolio. / 返回可投票冠军 ID。"""

    champions = select_family_champions(entries)
    return tuple(champions[family].strategy_id for family in sorted(champions))


def render_family_champion_report(entries: Iterable[StrategyCatalogEntry]) -> str:
    """Render required family champion output. / 生成要求的家族冠军输出。"""

    champions = select_family_champions(entries)
    labels = [
        (TREND_FAMILY, "Trend Champion"),
        (MEAN_REVERSION_FAMILY, "Reversion Champion"),
        (VOLUME_FAMILY, "Volume Champion"),
        (EVENT_FAMILY, "Event Champion"),
        (AI_FAMILY, "AI Champion"),
    ]
    lines = ["# Arena Family Champions", ""]
    for family, label in labels:
        champion = champions.get(family)
        if champion is None:
            lines.append(f"- {label}: pending")
        else:
            lines.append(f"- {label}: {champion.strategy_id} ({champion.fitness_score})")
    lines.append("")
    lines.append("Champion Portfolio voting must use these family champions only.")
    return "\n".join(lines)
