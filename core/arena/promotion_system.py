"""
MagicQuant Arena Promotion System.
VERSION : v1.0.0
DEPENDS : dataclasses, typing

Purpose / 用途:
Evaluate champion threat, promotion, and demotion decisions from existing
Arena contender metrics. This module does not create strategies, change
scoring, mutate parameters, run regime logic, or trade.
根据已有 Arena 挑战者指标判断威胁、晋升与降级；本模块不新增策略、
不修改评分、不变异参数、不引入 Regime、不交易。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"

KEEP = "KEEP"
PROMOTE = "PROMOTE"
WATCH = "WATCH"

DEMOTION_WATCH = "DEMOTION WATCH"


class StrategyLike(Protocol):
    strategy_id: str
    contender_score: int
    health_score: int
    momentum_status: str
    pf_declining: bool


@dataclass(frozen=True)
class PromotionDecision:
    """Promotion engine output. / 晋升引擎输出。"""

    threat_level: str
    recommended_successor: str
    recommendation: str


def champion_threat_level(champion_score: int, challenger_score: int | None) -> str:
    """Return threat level from champion-vs-runner-up gap. / 根据分差判断冠军威胁。"""

    if challenger_score is None:
        return LOW
    gap = champion_score - challenger_score
    if gap <= 5:
        return HIGH
    if gap <= 15:
        return MEDIUM
    return LOW


def promotion_recommendation(champion_health: int, challenger_score: int | None, threat_level: str) -> str:
    """Return KEEP/PROMOTE/WATCH. / 返回 KEEP、PROMOTE 或 WATCH。"""

    if challenger_score is None:
        return KEEP if champion_health >= 60 else WATCH
    if champion_health < 60 and challenger_score >= 65:
        return PROMOTE
    if champion_health < 70 and challenger_score >= 75:
        return PROMOTE
    if threat_level == HIGH or champion_health < 85:
        return WATCH
    return KEEP


def demotion_watchlist(strategies: Iterable[StrategyLike]) -> tuple[str, ...]:
    """Return strategies with persistent deterioration. / 返回持续恶化的策略。"""

    rows = []
    for item in strategies:
        if item.pf_declining and item.momentum_status == "DECLINING" and item.health_score < 60:
            rows.append(item.strategy_id)
    return tuple(rows)


def decide_promotion(
    champion_id: str,
    champion_score: int,
    champion_health: int,
    contenders: Iterable[StrategyLike],
) -> PromotionDecision:
    """Pick successor and final promotion decision. / 选择接班人并给出最终建议。"""

    rows = [row for row in contenders if row.strategy_id != champion_id]
    rows.sort(key=lambda row: (-row.contender_score, row.strategy_id))
    successor = rows[0].strategy_id if rows else "NONE"
    challenger_score = rows[0].contender_score if rows else None
    threat = champion_threat_level(champion_score, challenger_score)
    recommendation = promotion_recommendation(champion_health, challenger_score, threat)
    return PromotionDecision(threat, successor, recommendation)
