"""
MagicQuant Arena Lite champion validation layer.
VERSION : v1.0.0
DEPENDS : dataclasses, json, pathlib, statistics, typing, config.settings

Purpose / 用途:
Validate whether the current champion is stable or merely lucky. This layer
does not add strategies, call AI generation, mutate parameters, or use regimes.
验证当前冠军是稳定冠军还是幸运冠军；不新增策略、不调用 AI 生成、不变异参数、不使用 Regime。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional


TRUE_CHAMPION = "TRUE_CHAMPION"
LUCKY_CHAMPION = "LUCKY_CHAMPION"


@dataclass(frozen=True)
class ChampionRecord:
    """One replayed or live paper week for a champion. / 冠军的一周回放或纸面实盘记录。"""

    week_start: str
    champion_id: str
    champion_pnl: float
    champion_profit_factor: float
    champion_max_drawdown: float
    current_main_strategy_pnl: float
    buy_hold_rklb_pnl: float = 0.0
    no_trade_pnl: float = 0.0


@dataclass(frozen=True)
class StabilityScore:
    """Cross-week stability summary. / 跨周稳定性摘要。"""

    weeks: int
    positive_weeks: int
    beat_main_weeks: int
    pf_pass_weeks: int
    average_pnl: float
    pnl_volatility: float
    worst_drawdown: float
    stability_score: float


@dataclass(frozen=True)
class ValidationResult:
    """Final champion validation result. / 冠军验证最终结果。"""

    champion_id: str
    verdict: str
    stability: StabilityScore
    reasons: tuple[str, ...]


def compute_stability_score(records: Iterable[ChampionRecord]) -> StabilityScore:
    """Score whether performance is repeatable across weeks. / 评分表现是否跨周可重复。"""

    rows = list(records)
    if not rows:
        return StabilityScore(0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0)

    pnls = [row.champion_pnl for row in rows]
    positive_weeks = sum(1 for row in rows if row.champion_pnl > 0)
    beat_main_weeks = sum(1 for row in rows if row.champion_pnl > row.current_main_strategy_pnl)
    pf_pass_weeks = sum(1 for row in rows if row.champion_profit_factor > 1.0)
    worst_drawdown = min(row.champion_max_drawdown for row in rows)
    average_pnl = mean(pnls)
    pnl_volatility = pstdev(pnls) if len(pnls) > 1 else 0.0

    repeatability = (positive_weeks / len(rows)) * 30.0
    benchmark_edge = (beat_main_weeks / len(rows)) * 35.0
    pf_quality = (pf_pass_weeks / len(rows)) * 25.0
    volatility_penalty = min(pnl_volatility / max(abs(average_pnl), 1.0), 3.0) * 5.0
    drawdown_penalty = abs(worst_drawdown) * 100.0
    score = repeatability + benchmark_edge + pf_quality - volatility_penalty - drawdown_penalty

    return StabilityScore(
        weeks=len(rows),
        positive_weeks=positive_weeks,
        beat_main_weeks=beat_main_weeks,
        pf_pass_weeks=pf_pass_weeks,
        average_pnl=round(average_pnl, 4),
        pnl_volatility=round(pnl_volatility, 4),
        worst_drawdown=round(worst_drawdown, 4),
        stability_score=round(score, 4),
    )


def validate_champion(
    champion_id: str,
    records: Iterable[ChampionRecord],
    min_weeks: int = 6,
    min_stability_score: float = 70.0,
) -> ValidationResult:
    """Classify champion as TRUE_CHAMPION or LUCKY_CHAMPION. / 判定真冠军或幸运冠军。"""

    rows = [row for row in records if row.champion_id == champion_id]
    stability = compute_stability_score(rows)
    reasons: List[str] = []

    if stability.weeks < min_weeks:
        reasons.append(f"only {stability.weeks} weeks validated; need {min_weeks}")
    if stability.beat_main_weeks < stability.weeks:
        reasons.append("did not beat Current Main Strategy every validated week")
    if stability.pf_pass_weeks < stability.weeks:
        reasons.append("Profit Factor was not above 1 every validated week")
    if stability.stability_score < min_stability_score:
        reasons.append(f"stability_score {stability.stability_score} below {min_stability_score}")

    verdict = TRUE_CHAMPION if not reasons else LUCKY_CHAMPION
    if not reasons:
        reasons.append("beat main benchmark every week with PF > 1 and stable cross-week profile")
    return ValidationResult(champion_id, verdict, stability, tuple(reasons))


def replay_champion_history(records: Iterable[ChampionRecord]) -> Dict[str, ValidationResult]:
    """Replay stored champion history and validate each champion ID. / 回放冠军历史并验证每个冠军 ID。"""

    rows = list(records)
    champion_ids = sorted({row.champion_id for row in rows})
    return {champion_id: validate_champion(champion_id, rows) for champion_id in champion_ids}


def append_champion_history(
    record: ChampionRecord,
    history_path: str | Path | None = None,
) -> Path:
    """Append one champion record as JSONL. / 以 JSONL 追加一条冠军历史。"""

    if history_path is None:
        from config.settings import BASE_DIR

        path = Path(BASE_DIR) / "data" / "arena" / "champion_history.jsonl"
    else:
        path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def load_champion_history(history_path: str | Path) -> List[ChampionRecord]:
    """Load champion JSONL history. / 读取冠军 JSONL 历史。"""

    path = Path(history_path)
    if not path.exists():
        return []
    records: List[ChampionRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(ChampionRecord(**json.loads(line)))
    return records


def render_validation_report(result: ValidationResult) -> str:
    """Render champion validation report. / 生成冠军验证报告。"""

    stability = result.stability
    lines = [
        "# Arena Champion Validation",
        "",
        f"Champion: {result.champion_id}",
        f"Verdict: {result.verdict}",
        "",
        "Stability Score:",
        f"- Weeks: {stability.weeks}",
        f"- Positive Weeks: {stability.positive_weeks}",
        f"- Beat Current Main Strategy Weeks: {stability.beat_main_weeks}",
        f"- PF > 1 Weeks: {stability.pf_pass_weeks}",
        f"- Average PnL: {stability.average_pnl}",
        f"- PnL Volatility: {stability.pnl_volatility}",
        f"- Worst Drawdown: {stability.worst_drawdown}",
        f"- Stability Score: {stability.stability_score}",
        "",
        "Reasons:",
    ]
    lines.extend(f"- {reason}" for reason in result.reasons)
    return "\n".join(lines)


def write_validation_report(
    result: ValidationResult,
    out_path: str | Path | None = None,
) -> Path:
    """Write champion_validation.md under BASE_DIR/data/arena by default. / 默认写入冠军验证报告。"""

    if out_path is None:
        from config.settings import BASE_DIR

        path = Path(BASE_DIR) / "data" / "arena" / "champion_validation.md"
    else:
        path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_validation_report(result), encoding="utf-8")
    return path
