"""
MagicQuant Arena Edge Attribution Analyzer.
VERSION : v1.0.0
DEPENDS : argparse, dataclasses, json, pathlib, typing, config.settings

Purpose / 用途:
Explain where Arena Champion Portfolio edge comes from. This module only
analyzes existing experiment records; it does not add strategies, modify
Champion logic, change scoring, discover, mutate, or trade.
解释 Arena 冠军组合收益来源；本模块只分析既有实验记录，不新增策略、不修改冠军逻辑、
不改变评分、不发现、不变异、不交易。
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional


FAMILIES = ("Trend Family", "Mean Reversion Family", "Volume Family", "Event Family", "AI Family")
AI_MEMBERS = ("GPT", "Claude", "DeepSeek", "Kimi")
TIME_BUCKETS = ("Opening Session", "Morning Session", "Midday Session", "Closing Session", "Unknown")
DIRECTIONS = ("LONG", "SHORT", "HOLD")

STRONG = "STRONG"
MODERATE = "MODERATE"
WEAK = "WEAK"

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"


@dataclass(frozen=True)
class AttributionBucket:
    """PnL/win/PF attribution bucket. / 收益、胜率、PF 归因桶。"""

    name: str
    pnl: float
    win_rate: Optional[float]
    profit_factor: Optional[float]
    contribution_pct: float
    count: int


@dataclass(frozen=True)
class AIAttribution:
    """AI member contribution. / AI 成员贡献。"""

    name: str
    participation_count: int
    agreement_rate: Optional[float]
    accuracy: Optional[float]
    contribution_pnl: float
    contribution_pct: float


@dataclass(frozen=True)
class EdgeAttributionAnalysis:
    """Final Edge Attribution result. / 最终 Edge 归因结果。"""

    current_champion: str
    total_pnl: float
    family_attribution: tuple[AttributionBucket, ...]
    time_attribution: tuple[AttributionBucket, ...]
    direction_attribution: tuple[AttributionBucket, ...]
    ai_attribution: tuple[AIAttribution, ...]
    signal_push_attribution: tuple[AttributionBucket, ...]
    edge_concentration_score: int
    concentration_risk: str
    luck_score: int
    edge_status: str
    conclusion: str


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def default_paths() -> dict[str, Path]:
    base = _base_dir()
    return {
        "champion_history": base / "data" / "arena" / "champion_history.jsonl",
        "fitness_scores": base / "data" / "arena" / "fitness_scores.jsonl",
        "strategy_rankings": base / "data" / "arena" / "strategy_rankings.jsonl",
        "benchmark_results": base / "data" / "benchmark" / "benchmark_results.json",
        "trial_records": base / "data" / "trial" / "arena_trial_records.jsonl",
        "report": base / "reports" / "edge" / "champion_edge_report.md",
        "latest": base / "data" / "edge" / "latest.json",
    }


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_json(path: Path):
    if not path.exists():
        return []
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


def _actual(row: dict) -> dict:
    return row.get("actual_result") or {}


def _pnl(row: dict) -> float:
    actual = _actual(row)
    return _float(actual, "champion_pnl", default=_float(row, "pnl", "daily_result", "champion_pnl"))


def _date(row: dict) -> str:
    return str(row.get("date") or row.get("day") or "")


def _champion(row: dict) -> str:
    return str(row.get("champion_id") or row.get("strategy_id") or row.get("current_champion") or row.get("champion_portfolio") or "UNKNOWN")


def _members(row: dict) -> List[str]:
    raw = row.get("champion_members") or row.get("members") or []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [str(item) for item in raw]


def _direction(row: dict) -> str:
    value = str(row.get("direction") or row.get("champion_signal") or row.get("signal") or "HOLD").upper()
    if value in ("BUY", "BULL"):
        return "LONG"
    if value in ("SELL", "BEAR"):
        return "SHORT"
    return value if value in DIRECTIONS else "HOLD"


def _time_bucket_from_value(value: str) -> str:
    if not value:
        return "Unknown"
    if value in TIME_BUCKETS:
        return value
    try:
        hour, minute = [int(part) for part in value[:5].split(":")]
    except Exception:
        return "Unknown"
    minutes = hour * 60 + minute
    if 9 * 60 + 30 <= minutes < 10 * 60 + 30:
        return "Opening Session"
    if 10 * 60 + 30 <= minutes < 12 * 60:
        return "Morning Session"
    if 12 * 60 <= minutes < 14 * 60:
        return "Midday Session"
    if 14 * 60 <= minutes <= 16 * 60:
        return "Closing Session"
    return "Unknown"


def _time_bucket(row: dict) -> str:
    value = str(row.get("time_bucket") or row.get("entry_time") or row.get("signal_time") or row.get("time") or "")
    if value in TIME_BUCKETS:
        return value
    if " " in value and value[:10].count("-") == 2:
        value = value.split(" ", 1)[1]
    return _time_bucket_from_value(value)


def _family_from_member(member: str) -> str:
    key = member.lower()
    if key.startswith("h1") or "trend" in key:
        return "Trend Family"
    if key.startswith("h2") or "reversion" in key or "mean" in key:
        return "Mean Reversion Family"
    if key.startswith("h3") or "volume" in key or "breakout" in key:
        return "Volume Family"
    if "event" in key or "news" in key:
        return "Event Family"
    if key in ("gpt", "claude", "deepseek", "kimi") or "ai" in key:
        return "AI Family"
    return "AI Family" if member in AI_MEMBERS else "Event Family"


def _family_contributions(row: dict) -> Dict[str, float]:
    raw = row.get("family_contributions")
    if isinstance(raw, dict):
        return {str(key): float(value) for key, value in raw.items()}
    members = _members(row)
    pnl = _pnl(row)
    if not members:
        return {"Event Family": pnl}
    family_counts: Dict[str, int] = {}
    for member in members:
        family = _family_from_member(member)
        family_counts[family] = family_counts.get(family, 0) + 1
    total = sum(family_counts.values()) or 1
    return {family: pnl * count / total for family, count in family_counts.items()}


def _ai_votes(row: dict) -> Dict[str, str]:
    def norm_name(value: str) -> str:
        key = str(value).lower()
        if key == "gpt":
            return "GPT"
        if key == "claude":
            return "Claude"
        if key == "deepseek":
            return "DeepSeek"
        if key == "kimi":
            return "Kimi"
        return str(value)

    raw = row.get("ai_votes")
    if isinstance(raw, dict):
        return {norm_name(str(key)): str(value).upper() for key, value in raw.items()}
    votes = {}
    row_direction = _direction(row)
    for member in _members(row):
        title = member[:1].upper() + member[1:] if member.lower() != "gpt" else "GPT"
        if title in AI_MEMBERS:
            votes[title] = row_direction
    return votes


def _bucket_stats(values: Dict[str, List[float]], ordered_names: Iterable[str]) -> tuple[AttributionBucket, ...]:
    total_positive = sum(max(sum(items), 0.0) for items in values.values())
    rows: List[AttributionBucket] = []
    for name in ordered_names:
        pnls = values.get(name, [])
        pnl = sum(pnls)
        wins = [item for item in pnls if item > 0]
        losses = [item for item in pnls if item < 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        pf = gross_win / gross_loss if gross_loss > 0 else (None if gross_win == 0 else float("inf"))
        pct = (max(pnl, 0.0) / total_positive * 100.0) if total_positive > 0 else 0.0
        rows.append(AttributionBucket(name, round(pnl, 4), round(len(wins) / len(pnls), 4) if pnls else None, None if pf is None else round(pf, 4), round(pct, 2), len(pnls)))
    return tuple(rows)


def _concentration(attribution: Iterable[AttributionBucket]) -> tuple[int, str]:
    top = max((bucket.contribution_pct for bucket in attribution), default=0.0)
    score = int(round(top))
    if top >= 75.0:
        return score, HIGH
    if top >= 55.0:
        return score, MEDIUM
    return score, LOW


def _luck_score(pnls: List[float]) -> int:
    positives = [max(item, 0.0) for item in pnls]
    total = sum(positives)
    if total <= 0:
        return 100 if any(item != 0 for item in pnls) else 0
    top = max(positives)
    return int(round(min(100.0, top / total * 100.0)))


def _edge_status(total_pnl: float, concentration_risk: str, luck_score: int) -> str:
    if total_pnl <= 0:
        return WEAK
    if concentration_risk == HIGH or luck_score >= 70:
        return WEAK
    if concentration_risk == MEDIUM or luck_score >= 45:
        return MODERATE
    return STRONG


def _top_bucket_name(attribution: Iterable[AttributionBucket]) -> str:
    buckets = list(attribution)
    if not buckets:
        return "none"
    # Pick the strongest readable source. / 优先选择最有解释力的来源。
    return max(buckets, key=lambda item: (item.contribution_pct, abs(item.pnl), item.count)).name


def analyze_edge(
    champion_history_rows: Iterable[dict],
    fitness_score_rows: Iterable[dict],
    strategy_ranking_rows: Iterable[dict],
    benchmark_results,
    trial_records: Iterable[dict] | None = None,
) -> EdgeAttributionAnalysis:
    """Attribute Arena edge using existing records. / 使用既有记录归因 Arena edge。"""

    rows = list(trial_records or champion_history_rows)
    if not rows:
        empty = tuple(AttributionBucket(name, 0.0, None, None, 0.0, 0) for name in FAMILIES)
        empty_time = tuple(AttributionBucket(name, 0.0, None, None, 0.0, 0) for name in TIME_BUCKETS)
        empty_direction = tuple(AttributionBucket(name, 0.0, None, None, 0.0, 0) for name in DIRECTIONS)
        empty_ai = tuple(AIAttribution(name, 0, None, None, 0.0, 0.0) for name in AI_MEMBERS)
        return EdgeAttributionAnalysis("UNKNOWN", 0.0, empty, empty_time, empty_direction, empty_ai, empty, 0, LOW, 0, WEAK, "No edge data available; Arena edge is unproven.")

    current_champion = _champion(rows[-1])
    family_values: Dict[str, List[float]] = {name: [] for name in FAMILIES}
    time_values: Dict[str, List[float]] = {name: [] for name in TIME_BUCKETS}
    direction_values: Dict[str, List[float]] = {name: [] for name in DIRECTIONS}
    push_values: Dict[str, List[float]] = {name: [] for name in FAMILIES}
    ai_pnls: Dict[str, List[float]] = {name: [] for name in AI_MEMBERS}
    ai_agree: Dict[str, List[bool]] = {name: [] for name in AI_MEMBERS}
    ai_correct: Dict[str, List[bool]] = {name: [] for name in AI_MEMBERS}
    pnls: List[float] = []

    for row in rows:
        pnl = _pnl(row)
        pnls.append(pnl)
        for family, family_pnl in _family_contributions(row).items():
            family_values.setdefault(family, []).append(family_pnl)
            push_values.setdefault(family, []).append(1.0 if abs(family_pnl) > 0 else 0.0)
        time_values.setdefault(_time_bucket(row), []).append(pnl)
        direction_values.setdefault(_direction(row), []).append(pnl)
        final_direction = _direction(row)
        for ai_name, vote in _ai_votes(row).items():
            if ai_name not in ai_pnls:
                continue
            share = pnl / max(len(_ai_votes(row)), 1)
            ai_pnls[ai_name].append(share)
            ai_agree[ai_name].append(vote == final_direction)
            ai_correct[ai_name].append((vote == final_direction and pnl > 0) or (vote != final_direction and pnl < 0))

    family_attr = _bucket_stats(family_values, FAMILIES)
    time_attr = _bucket_stats(time_values, TIME_BUCKETS)
    direction_attr = _bucket_stats(direction_values, DIRECTIONS)
    signal_attr = _bucket_stats(push_values, FAMILIES)
    total_positive_ai = sum(max(sum(items), 0.0) for items in ai_pnls.values())
    ai_rows: List[AIAttribution] = []
    for name in AI_MEMBERS:
        pnl = sum(ai_pnls[name])
        pct = (max(pnl, 0.0) / total_positive_ai * 100.0) if total_positive_ai > 0 else 0.0
        ai_rows.append(
            AIAttribution(
                name,
                len(ai_pnls[name]),
                round(sum(ai_agree[name]) / len(ai_agree[name]), 4) if ai_agree[name] else None,
                round(sum(ai_correct[name]) / len(ai_correct[name]), 4) if ai_correct[name] else None,
                round(pnl, 4),
                round(pct, 2),
            )
        )
    ai_attr = tuple(sorted(ai_rows, key=lambda item: (-item.contribution_pnl, item.name)))
    concentration_score, concentration_risk = _concentration(family_attr)
    luck = _luck_score(pnls)
    total = round(sum(pnls), 4)
    status = _edge_status(total, concentration_risk, luck)
    top_family = _top_bucket_name(family_attr)
    top_time = _top_bucket_name(time_attr)
    top_ai = ai_attr[0].name if ai_attr else "none"
    conclusion = f"Edge Status {status}: main sources are {top_family}, {top_time}, and {top_ai}; concentration risk {concentration_risk}, luck score {luck}."
    return EdgeAttributionAnalysis(current_champion, total, family_attr, time_attr, direction_attr, ai_attr, signal_attr, concentration_score, concentration_risk, luck, status, conclusion)


def load_and_analyze(
    champion_history_path: Path | None = None,
    fitness_scores_path: Path | None = None,
    strategy_rankings_path: Path | None = None,
    benchmark_results_path: Path | None = None,
    trial_records_path: Path | None = None,
) -> EdgeAttributionAnalysis:
    """Load existing Arena data and analyze edge. / 读取既有 Arena 数据并归因 edge。"""

    paths = default_paths()
    champion_path = champion_history_path or paths["champion_history"]
    fitness_path = fitness_scores_path or paths["fitness_scores"]
    ranking_path = strategy_rankings_path or paths["strategy_rankings"]
    benchmark_path = benchmark_results_path or paths["benchmark_results"]
    trial_path = trial_records_path or paths["trial_records"]
    return analyze_edge(_load_jsonl(champion_path), _load_jsonl(fitness_path), _load_jsonl(ranking_path), _load_json(benchmark_path), _load_jsonl(trial_path))


def _bucket_lines(title: str, rows: Iterable[AttributionBucket]) -> List[str]:
    lines = [title, "| Source | PnL | Contribution | Win Rate | PF | Count |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        lines.append(f"| {row.name} | {row.pnl:+.2f} | {row.contribution_pct:.2f}% | {row.win_rate} | {row.profit_factor} | {row.count} |")
    return lines


def render_report(analysis: EdgeAttributionAnalysis) -> str:
    """Render champion edge report. / 生成冠军 edge 报告。"""

    lines = [
        "# Champion Edge Report",
        "",
        f"Current Champion: {analysis.current_champion}",
        f"Current PnL: {analysis.total_pnl:+.2f}",
        "",
    ]
    lines.extend(_bucket_lines("## Strategy Family Attribution", analysis.family_attribution))
    lines.extend([""])
    lines.extend(_bucket_lines("## Time Attribution", analysis.time_attribution))
    lines.extend([""])
    lines.extend(_bucket_lines("## Direction Attribution", analysis.direction_attribution))
    lines.extend(["", "## AI Attribution", "| AI | Participation | Agreement | Accuracy | PnL | Contribution |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in analysis.ai_attribution:
        lines.append(f"| {row.name} | {row.participation_count} | {row.agreement_rate} | {row.accuracy} | {row.contribution_pnl:+.2f} | {row.contribution_pct:.2f}% |")
    lines.extend([""])
    lines.extend(_bucket_lines("## Champion Signal Attribution", analysis.signal_push_attribution))
    lines.extend(
        [
            "",
            "## Edge Concentration",
            f"Edge Concentration Score: {analysis.edge_concentration_score}",
            f"Risk Level: {analysis.concentration_risk}",
            "",
            "## Luck Detection",
            f"Luck Score: {analysis.luck_score}",
            "",
            f"EDGE STATUS: {analysis.edge_status}",
            "",
            "Final Conclusion:",
            analysis.conclusion,
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(analysis: EdgeAttributionAnalysis, report_path: Path | None = None, latest_path: Path | None = None) -> tuple[Path, Path]:
    """Write markdown report and latest JSON. / 写 Markdown 报告和 JSON。"""

    paths = default_paths()
    report_out = report_path or paths["report"]
    latest_out = latest_path or paths["latest"]
    report_out.parent.mkdir(parents=True, exist_ok=True)
    latest_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(render_report(analysis), encoding="utf-8")
    latest_out.write_text(json.dumps(asdict(analysis), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report_out, latest_out


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Arena edge attribution.")
    parser.add_argument("--champion-history", default=None)
    parser.add_argument("--fitness-scores", default=None)
    parser.add_argument("--strategy-rankings", default=None)
    parser.add_argument("--benchmark-results", default=None)
    parser.add_argument("--trial-records", default=None)
    args = parser.parse_args()
    analysis = load_and_analyze(
        Path(args.champion_history) if args.champion_history else None,
        Path(args.fitness_scores) if args.fitness_scores else None,
        Path(args.strategy_rankings) if args.strategy_rankings else None,
        Path(args.benchmark_results) if args.benchmark_results else None,
        Path(args.trial_records) if args.trial_records else None,
    )
    report, latest = write_outputs(analysis)
    print(f"[edge_attribution] wrote {report} and {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
