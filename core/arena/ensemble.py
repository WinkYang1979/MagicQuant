"""
MagicQuant Arena Lite champion portfolio voting.
VERSION : v1.0.0
DEPENDS : dataclasses, pathlib, typing, config.settings, core.arena.roster

Purpose / 用途:
Collect fixed-roster signals, cluster same-kind duplicate signals, and produce
one Champion Portfolio action. No single champion, no auto-trading.
收集固定名单信号，聚合同类重复信号，并输出冠军组合动作；不设单冠军，不自动交易。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.arena.roster import roster_by_id, validate_equal_weight

BULL = "bull"
BEAR = "bear"
NEUTRAL = "neutral"

LONG = "LONG"
SHORT = "SHORT"
HOLD = "HOLD"

RKLX = "RKLX"
RKLZ = "RKLZ"
CASH = "Cash"

VALID_DIRECTIONS = {BULL, BEAR, NEUTRAL}


@dataclass(frozen=True)
class ArenaSignal:
    """One contestant signal. / 单个参赛者信号。"""

    member_id: str
    direction: str
    reason: str = ""
    cluster_key: Optional[str] = None


@dataclass(frozen=True)
class ClusterVote:
    """One deduplicated cluster vote. / 一个去重后的聚类投票。"""

    cluster_key: str
    direction: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class ChampionDecision:
    """Champion Portfolio decision snapshot. / 冠军组合决策快照。"""

    action: str
    preferred_instrument: str
    bull_votes: int
    bear_votes: int
    neutral_votes: int
    net_score: int
    cluster_votes: tuple[ClusterVote, ...]


def _normalize_direction(direction: str) -> str:
    value = (direction or "").strip().lower()
    aliases = {
        "long": BULL,
        "buy": BULL,
        "short": BEAR,
        "sell": BEAR,
        "flat": NEUTRAL,
        "hold": NEUTRAL,
        "cash": NEUTRAL,
    }
    value = aliases.get(value, value)
    if value not in VALID_DIRECTIONS:
        raise ValueError(f"unknown Arena signal direction: {direction!r}")
    return value


def _default_cluster_key(signal: ArenaSignal) -> str:
    # Default keeps equal member votes; explicit cluster_key deduplicates same-kind signals.
    # 默认保留成员等权；显式 cluster_key 用于同类信号去重。
    return signal.cluster_key or signal.member_id


def cluster_signals(signals: Iterable[ArenaSignal], allowed_member_ids: Iterable[str] | None = None) -> List[ClusterVote]:
    """Collapse duplicate same-kind signals into one vote per cluster. / 同类信号每簇只记一票。"""

    if allowed_member_ids is None:
        roster = roster_by_id()
        validate_equal_weight(list(roster.values()))
        allowed_ids = set(roster)
    else:
        allowed_ids = set(allowed_member_ids)
        if not allowed_ids:
            raise ValueError("allowed_member_ids cannot be empty")
    grouped: Dict[str, Dict[str, object]] = {}
    for signal in signals:
        if signal.member_id not in allowed_ids:
            raise ValueError(f"unknown Arena member_id: {signal.member_id!r}")
        direction = _normalize_direction(signal.direction)
        key = _default_cluster_key(signal)
        bucket = grouped.setdefault(key, {"members": [], "counts": {BULL: 0, BEAR: 0, NEUTRAL: 0}})
        bucket["members"].append(signal.member_id)
        bucket["counts"][direction] += 1

    votes: List[ClusterVote] = []
    rank = {BULL: 2, BEAR: 1, NEUTRAL: 0}
    for key in sorted(grouped):
        bucket = grouped[key]
        counts = bucket["counts"]
        direction = max((BULL, BEAR, NEUTRAL), key=lambda item: (counts[item], rank[item]))
        votes.append(ClusterVote(key, direction, tuple(bucket["members"])))
    return votes


def decide_champion_portfolio(
    signals: Iterable[ArenaSignal],
    allowed_member_ids: Iterable[str] | None = None,
) -> ChampionDecision:
    """Produce LONG, SHORT, or HOLD from clustered votes. / 从聚类投票输出 LONG、SHORT 或 HOLD。"""

    cluster_votes = tuple(cluster_signals(signals, allowed_member_ids=allowed_member_ids))
    bull_votes = sum(1 for vote in cluster_votes if vote.direction == BULL)
    bear_votes = sum(1 for vote in cluster_votes if vote.direction == BEAR)
    neutral_votes = sum(1 for vote in cluster_votes if vote.direction == NEUTRAL)
    net_score = bull_votes - bear_votes

    if net_score > 0:
        action = LONG
        preferred = RKLX
    elif net_score < 0:
        action = SHORT
        preferred = RKLZ
    else:
        action = HOLD
        preferred = CASH

    return ChampionDecision(
        action=action,
        preferred_instrument=preferred,
        bull_votes=bull_votes,
        bear_votes=bear_votes,
        neutral_votes=neutral_votes,
        net_score=net_score,
        cluster_votes=cluster_votes,
    )


def render_daily_champion_report(date: str, decision: ChampionDecision, benchmarks: Dict[str, str] | None = None) -> str:
    """Render today_champion.md content. / 生成 today_champion.md 内容。"""

    bench = benchmarks or {}
    return "\n".join(
        [
            "# Daily Champion Report",
            "",
            f"Date: {date}",
            f"Champion Portfolio Signal: {decision.action}",
            f"Bull Votes: {decision.bull_votes}",
            f"Bear Votes: {decision.bear_votes}",
            f"Net Score: {decision.net_score}",
            f"Preferred Instrument: {decision.preferred_instrument}",
            "",
            "Instruments:",
            "- RKLX: long exposure candidate",
            "- RKLZ: short exposure candidate",
            "- Cash: no-trade benchmark",
            "",
            "Benchmark Status:",
            f"- Buy & Hold RKLB: {bench.get('buy_hold_rklb', 'pending')}",
            f"- Current Main Strategy: {bench.get('current_main_strategy', 'pending')}",
            f"- No Trade: {bench.get('no_trade', 'pending')}",
            "",
        ]
    )


def write_daily_champion_report(
    date: str,
    decision: ChampionDecision,
    benchmarks: Dict[str, str] | None = None,
    out_path: str | Path | None = None,
) -> Path:
    """Write today_champion.md under BASE_DIR/data/arena by default. / 默认写入 BASE_DIR/data/arena。"""

    if out_path is None:
        from config.settings import BASE_DIR

        out = Path(BASE_DIR) / "data" / "arena" / "today_champion.md"
    else:
        out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_daily_champion_report(date, decision, benchmarks), encoding="utf-8")
    return out
