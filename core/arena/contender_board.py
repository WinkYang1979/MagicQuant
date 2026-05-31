"""
MagicQuant Arena Contender Board.
VERSION : v1.0.0
DEPENDS : argparse, dataclasses, json, pathlib, typing, config.settings,
          core.arena.promotion_system

Purpose / 用途:
Build a contender league table and promotion watchlist from existing Arena
history only. This module does not discover, mutate, add strategies, change
Champion logic, change Fitness scoring, or trade.
只用已有 Arena 历史生成挑战者联赛榜和晋升观察名单；本模块不发现、
不变异、不新增策略、不修改冠军逻辑、不修改 Fitness 评分、不交易。
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.arena.promotion_system import (
    DEMOTION_WATCH,
    KEEP,
    PROMOTE,
    WATCH,
    decide_promotion,
    demotion_watchlist,
)


RISING = "RISING"
STABLE = "STABLE"
DECLINING = "DECLINING"
CHAMPION = "CHAMPION"
CONTENDER = "CONTENDER"
NO_SUCCESSOR = "NONE"
CAPITAL_UNIT = 100.0


@dataclass(frozen=True)
class StrategyLeagueRow:
    """One strategy row on the contender board. / 挑战者榜单中的单个策略。"""

    rank: int
    strategy_id: str
    family: str
    pnl: float
    profit_factor: Optional[float]
    win_rate: Optional[float]
    max_drawdown: float
    fitness_score: float
    health_score: int
    consistency_score: int
    momentum_score: int
    momentum_status: str
    contender_score: int
    current_status: str
    pf_declining: bool


@dataclass(frozen=True)
class ContenderBoardAnalysis:
    """Final contender board result. / 最终挑战者看板结果。"""

    current_champion: str
    champion_health: int
    threat_level: str
    top_strategies: tuple[StrategyLeagueRow, ...]
    promotion_watchlist: tuple[StrategyLeagueRow, ...]
    demotion_watchlist: tuple[str, ...]
    recommended_successor: str
    final_recommendation: str


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def default_paths() -> dict[str, Path]:
    base = _base_dir()
    return {
        "trial_records": base / "data" / "arena" / "historical_trial_results.jsonl",
        "champion_stability": base / "data" / "champion_stability" / "latest.json",
        "report": base / "reports" / "contenders" / "contender_board.md",
        "latest": base / "data" / "contenders" / "latest.json",
    }


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _float(row: dict, *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = row.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
    return default


def _signal_to_pnl(direction: str, entry: float, close: float) -> float:
    if entry <= 0:
        return 0.0
    move = (close - entry) / entry
    value = str(direction).upper()
    if value in {"LONG", "BULL", "BUY"}:
        return move * 2.0 * CAPITAL_UNIT
    if value in {"SHORT", "BEAR", "SELL"}:
        return -move * 2.0 * CAPITAL_UNIT
    return 0.0


def _pf(values: List[float]) -> Optional[float]:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _win_rate(values: List[float]) -> Optional[float]:
    active = [value for value in values if value != 0]
    if not active:
        return None
    return sum(1 for value in active if value > 0) / len(active)


def _max_drawdown(values: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _score(value: float, low: float, high: float) -> int:
    if high <= low:
        return 0
    return int(round(max(0.0, min(1.0, (value - low) / (high - low))) * 100.0))


def _normalize(value: float, low: float, high: float) -> int:
    if high <= low:
        return 50
    return _score(value, low, high)


def _fitness_score(values: List[float]) -> float:
    pf = _pf(values) or 0.0
    win_rate = _win_rate(values) or 0.0
    expectancy = _avg(values)
    drawdown = abs(_max_drawdown(values))
    pf_component = min(pf, 3.0) * 25.0
    win_component = win_rate * 20.0
    drawdown_penalty = drawdown
    return round(pf_component + win_component + expectancy - drawdown_penalty, 4)


def _consistency_score(values: List[float]) -> int:
    if not values:
        return 0
    non_zero = [value for value in values if value != 0]
    if not non_zero:
        return 0
    positive = sum(1 for value in non_zero if value > 0) / len(non_zero)
    participation = len(non_zero) / len(values)
    return int(round((positive * 0.7 + participation * 0.3) * 100.0))


def _health_score(values: List[float]) -> int:
    pf = _pf(values) or 0.0
    win_rate = _win_rate(values) or 0.0
    drawdown_score = 1.0 - min(abs(_max_drawdown(values)) / 40.0, 1.0)
    consistency = _consistency_score(values) / 100.0
    score = min(pf, 2.0) / 2.0 * 35.0 + win_rate * 25.0 + drawdown_score * 25.0 + consistency * 15.0
    return int(round(max(0.0, min(100.0, score))))


def _momentum(values: List[float]) -> tuple[int, str]:
    if len(values) < 5:
        return 50, STABLE
    avg_5 = _avg(values[-5:])
    avg_10 = _avg(values[-10:]) if len(values) >= 10 else avg_5
    avg_20 = _avg(values[-20:]) if len(values) >= 20 else _avg(values)
    delta = (avg_5 - avg_20) + 0.5 * (avg_10 - avg_20)
    if delta > 0.2:
        return min(100, 60 + _score(delta, 0.2, 2.0) // 2), RISING
    if delta < -0.2:
        return max(0, 40 - _score(abs(delta), 0.2, 2.0) // 2), DECLINING
    return 50, STABLE


def _pf_declining(values: List[float]) -> bool:
    if len(values) < 20:
        return False
    pf20 = _pf(values[-20:]) or 0.0
    pf10 = _pf(values[-10:]) or 0.0
    pf5 = _pf(values[-5:]) or 0.0
    return pf20 > pf10 >= pf5


def _family_for_member(member_id: str, vote: dict | None = None) -> str:
    if vote and vote.get("family"):
        return str(vote["family"])
    key = member_id.lower()
    if "trend" in key or key.startswith("h1"):
        return "Trend Family"
    if "reversion" in key or "mean" in key or key.startswith("h2"):
        return "Mean Reversion Family"
    if "volume" in key or "breakout" in key or key.startswith("h3"):
        return "Volume Family"
    if key in {"gpt", "claude", "deepseek", "kimi"}:
        return "AI Family"
    return "Event Family"


def _strategy_daily_pnls(records: Iterable[dict]) -> tuple[Dict[str, List[float]], Dict[str, str]]:
    pnls: Dict[str, List[float]] = {}
    families: Dict[str, str] = {}
    for row in records:
        entry = _float(row, "entry_price")
        close = _float(row, "close_price")
        champion_id = str(row.get("champion_id") or "Champion Portfolio")
        champion_pnl = _float(row.get("actual_result") or {}, "champion_pnl", default=_float(row, "champion_pnl"))
        pnls.setdefault(champion_id, []).append(champion_pnl)
        families.setdefault(champion_id, "Portfolio")
        for vote in row.get("strategy_votes") or []:
            member_id = str(vote.get("member_id") or "")
            if not member_id:
                continue
            direction = str(vote.get("direction") or "neutral")
            pnls.setdefault(member_id, []).append(_signal_to_pnl(direction, entry, close))
            families.setdefault(member_id, _family_for_member(member_id, vote))
    return pnls, families


def _build_rows(records: Iterable[dict], current_champion: str) -> List[StrategyLeagueRow]:
    pnls, families = _strategy_daily_pnls(records)
    base_rows = []
    for strategy_id, values in pnls.items():
        if not values:
            continue
        momentum_score, momentum_status = _momentum(values)
        base_rows.append(
            {
                "strategy_id": strategy_id,
                "family": families.get(strategy_id, "Event Family"),
                "pnl": round(sum(values), 4),
                "profit_factor": _pf(values),
                "win_rate": _win_rate(values),
                "max_drawdown": _max_drawdown(values),
                "fitness_score": _fitness_score(values),
                "health_score": _health_score(values),
                "consistency_score": _consistency_score(values),
                "momentum_score": momentum_score,
                "momentum_status": momentum_status,
                "pf_declining": _pf_declining(values),
            }
        )
    if not base_rows:
        return []

    scores = [row["fitness_score"] for row in base_rows]
    low, high = min(scores), max(scores)
    output = []
    for row in base_rows:
        fitness_norm = _normalize(row["fitness_score"], low, high)
        contender_score = int(round(
            fitness_norm * 0.4
            + row["health_score"] * 0.3
            + row["consistency_score"] * 0.2
            + row["momentum_score"] * 0.1
        ))
        output.append((row, contender_score))
    output.sort(key=lambda item: (-item[0]["fitness_score"], -item[1], item[0]["strategy_id"]))

    ranked = []
    for rank, (row, contender_score) in enumerate(output, 1):
        status = CHAMPION if row["strategy_id"] == current_champion else CONTENDER
        if row["pf_declining"] and row["momentum_status"] == DECLINING and row["health_score"] < 60:
            status = f"{CHAMPION} / {DEMOTION_WATCH}" if row["strategy_id"] == current_champion else DEMOTION_WATCH
        ranked.append(
            StrategyLeagueRow(
                rank,
                row["strategy_id"],
                row["family"],
                row["pnl"],
                None if row["profit_factor"] is None else round(row["profit_factor"], 4),
                None if row["win_rate"] is None else round(row["win_rate"], 4),
                round(row["max_drawdown"], 4),
                row["fitness_score"],
                row["health_score"],
                row["consistency_score"],
                row["momentum_score"],
                row["momentum_status"],
                contender_score,
                status,
                row["pf_declining"],
            )
        )
    return ranked


def analyze_contenders(
    trial_records: Iterable[dict],
    champion_stability: dict | None = None,
    top_n: int = 10,
) -> ContenderBoardAnalysis:
    """Build contender board from existing Arena records. / 从已有 Arena 记录生成挑战者榜。"""

    records = list(trial_records)
    stability = champion_stability or {}
    current_champion = str(stability.get("current_champion") or (records[-1].get("champion_id") if records else "UNKNOWN"))
    champion_health = int(stability.get("health_score") or 0)
    if not records:
        return ContenderBoardAnalysis("UNKNOWN", 0, "LOW", tuple(), tuple(), tuple(), NO_SUCCESSOR, KEEP)

    rows = _build_rows(records, current_champion)
    top_rows = tuple(rows[:top_n])
    contenders = [row for row in rows if row.strategy_id != current_champion]
    promotion_watch = tuple(sorted(contenders, key=lambda row: (-row.contender_score, row.strategy_id))[:3])
    champion_row = next((row for row in rows if row.strategy_id == current_champion), None)
    champion_score = champion_row.contender_score if champion_row else champion_health
    decision = decide_promotion(current_champion, champion_score, champion_health, rows)
    demotions = demotion_watchlist(rows)
    return ContenderBoardAnalysis(
        current_champion,
        champion_health,
        decision.threat_level,
        top_rows,
        promotion_watch,
        demotions,
        decision.recommended_successor,
        decision.recommendation,
    )


def load_and_analyze(
    trial_records_path: Path | None = None,
    champion_stability_path: Path | None = None,
    top_n: int = 10,
) -> ContenderBoardAnalysis:
    """Load existing files and analyze contenders. / 读取既有文件并分析挑战者。"""

    paths = default_paths()
    return analyze_contenders(
        _load_jsonl(trial_records_path or paths["trial_records"]),
        _load_json(champion_stability_path or paths["champion_stability"]),
        top_n=top_n,
    )


def render_report(analysis: ContenderBoardAnalysis) -> str:
    """Render reports/contenders/contender_board.md. / 生成挑战者报告。"""

    lines = [
        "# Contender Board",
        "",
        f"Current Champion: {analysis.current_champion}",
        f"Champion Health: {analysis.champion_health}",
        f"Threat Level: {analysis.threat_level}",
        "",
        "Top 10 Contenders:",
        "| Rank | Strategy | Family | PF | Win Rate | Health | Momentum | Contender Score | Status |",
        "| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for row in analysis.top_strategies:
        lines.append(
            f"| {row.rank} | {row.strategy_id} | {row.family} | {row.profit_factor} | "
            f"{row.win_rate} | {row.health_score} | {row.momentum_status} | "
            f"{row.contender_score} | {row.current_status} |"
        )
    lines.extend(["", "Promotion Watchlist:"])
    if analysis.promotion_watchlist:
        for idx, row in enumerate(analysis.promotion_watchlist, 1):
            lines.append(f"- {idx}. {row.strategy_id} | Score {row.contender_score} | {row.momentum_status}")
    else:
        lines.append("- None")
    lines.extend(["", "Demotion Watchlist:"])
    if analysis.demotion_watchlist:
        for strategy_id in analysis.demotion_watchlist:
            lines.append(f"- {strategy_id}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            f"Recommended Successor: {analysis.recommended_successor}",
            f"Final Recommendation: {analysis.final_recommendation}",
            "",
            "Plain-English Decision:",
            _plain_decision(analysis),
            "",
        ]
    )
    return "\n".join(lines)


def _plain_decision(analysis: ContenderBoardAnalysis) -> str:
    if analysis.final_recommendation == PROMOTE:
        return f"冠军健康度偏弱，{analysis.recommended_successor} 已经具备接班优先级。"
    if analysis.final_recommendation == WATCH:
        return f"冠军仍可观察，但威胁等级为 {analysis.threat_level}，需要重点盯住前三挑战者。"
    return "冠军暂时守住位置，挑战者还没有形成足够压力。"


def render_telegram_summary(analysis: ContenderBoardAnalysis) -> str:
    """Chinese dashboard notification text. / 中文 Dashboard 通知文本。"""

    top = analysis.promotion_watchlist[0] if analysis.promotion_watchlist else None
    challenger = top.strategy_id if top else "暂无"
    score = top.contender_score if top else 0
    return "\n".join(
        [
            "Arena 挑战者看板",
            f"当前冠军: {analysis.current_champion}（健康度 {analysis.champion_health}）",
            f"最强挑战者: {challenger}（挑战分 {score}）",
            f"冠军威胁等级: {analysis.threat_level}",
            f"接班建议: {analysis.final_recommendation}",
            "",
            f"结论: {_plain_decision(analysis)}",
        ]
    )


def write_outputs(
    analysis: ContenderBoardAnalysis,
    report_path: Path | None = None,
    latest_path: Path | None = None,
) -> tuple[Path, Path]:
    """Write report and dashboard JSON. / 写报告和 Dashboard JSON。"""

    paths = default_paths()
    report_out = report_path or paths["report"]
    latest_out = latest_path or paths["latest"]
    report_out.parent.mkdir(parents=True, exist_ok=True)
    latest_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(render_report(analysis), encoding="utf-8")
    latest_out.write_text(json.dumps(asdict(analysis), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report_out, latest_out


def _send_telegram(text: str) -> bool:
    try:
        from core.sim_weekly.tg_format import send_private
    except Exception:
        return False
    return bool(send_private(text))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Arena contender board.")
    parser.add_argument("--trial-records", default=None)
    parser.add_argument("--champion-stability", default=None)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--telegram", action="store_true", help="Send Chinese Telegram summary.")
    args = parser.parse_args()
    analysis = load_and_analyze(
        Path(args.trial_records) if args.trial_records else None,
        Path(args.champion_stability) if args.champion_stability else None,
        top_n=args.top_n,
    )
    report, latest = write_outputs(analysis)
    print(f"[contender_board] wrote {report} and {latest}")
    if args.telegram:
        print(f"[contender_board] telegram sent={_send_telegram(render_telegram_summary(analysis))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
