"""
MagicQuant Arena Lite roster.
VERSION : v1.0.0
DEPENDS : dataclasses, typing

Purpose / 用途:
Define the fixed Arena Lite contestants only. This module does not generate,
mutate, rank, or trade strategies.
仅定义 Arena Lite 固定参赛名单；不生成、不变异、不排名、不交易策略。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


MECHANICAL_GROUP = "mechanical"
AI_GROUP = "ai"


@dataclass(frozen=True)
class ArenaMember:
    """Fixed equal-weight contestant. / 固定等权参赛者。"""

    member_id: str
    name: str
    group: str
    style: str
    weight: float = 1.0


DEFAULT_ROSTER: Tuple[ArenaMember, ...] = (
    ArenaMember("h1_trend", "H1 Trend", MECHANICAL_GROUP, "trend_following"),
    ArenaMember("h2_mean_reversion", "H2 Mean Reversion", MECHANICAL_GROUP, "mean_reversion"),
    ArenaMember("h3_volume_breakout", "H3 Volume Breakout", MECHANICAL_GROUP, "volume_breakout"),
    ArenaMember("gpt", "GPT", AI_GROUP, "ai_member"),
    ArenaMember("claude", "Claude", AI_GROUP, "ai_member"),
    ArenaMember("deepseek", "DeepSeek", AI_GROUP, "ai_member"),
    ArenaMember("kimi", "Kimi", AI_GROUP, "ai_member"),
)


def get_roster() -> List[ArenaMember]:
    """Return the approved seven-member roster. / 返回批准的 7 名参赛者。"""

    return list(DEFAULT_ROSTER)


def roster_by_id() -> Dict[str, ArenaMember]:
    """Index roster by stable member id. / 按稳定 ID 索引参赛者。"""

    return {member.member_id: member for member in DEFAULT_ROSTER}


def validate_equal_weight(roster: List[ArenaMember] | None = None) -> None:
    """Fail fast if the MVP equal-weight rule is broken. / 等权规则被破坏时立刻失败。"""

    members = roster if roster is not None else get_roster()
    if len(members) != 7:
        raise ValueError(f"Arena Lite roster must contain 7 members, got {len(members)}")
    weights = {member.weight for member in members}
    if weights != {1.0}:
        raise ValueError(f"Arena Lite members must be equal weight, got {sorted(weights)}")
