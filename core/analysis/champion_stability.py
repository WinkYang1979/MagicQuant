"""
MagicQuant Champion Stability Analyzer.
VERSION : v1.0.0
DEPENDS : argparse, dataclasses, json, pathlib, statistics, typing, config.settings

Purpose / 用途:
Analyze whether the current Arena champion is stable or lucky. This module only
reads existing experiment outputs and writes audit reports; it does not create,
modify, mutate, discover, or trade strategies.
分析当前 Arena 冠军是真稳定还是短期幸运；本模块只读取既有实验输出并写审计报告，
不创建、不修改、不变异、不发现、不交易策略。
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional


KEEP = "KEEP"
WATCH = "WATCH"
REPLACE = "REPLACE"

HEALTHY = "HEALTHY"
WATCH_STATUS = "WATCH"
DANGER = "DANGER"

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"

WINDOWS = (5, 10, 20)


@dataclass(frozen=True)
class ChampionDay:
    """Normalized champion history row. / 标准化冠军历史行。"""

    date: str
    champion_id: str
    pnl: float = 0.0
    max_drawdown: float = 0.0


@dataclass(frozen=True)
class FitnessDay:
    """Normalized fitness row. / 标准化 fitness 行。"""

    date: str
    strategy_id: str
    profit_factor: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    pnl: float = 0.0


@dataclass(frozen=True)
class LifetimeStats:
    """Champion lifetime stats. / 冠军寿命统计。"""

    average_lifetime: float
    median_lifetime: float
    max_lifetime: int
    min_lifetime: int
    current_lifetime: int


@dataclass(frozen=True)
class RollingMetrics:
    """Rolling metrics for the current champion. / 当前冠军滚动指标。"""

    profit_factor: Dict[str, Optional[float]]
    win_rate: Dict[str, Optional[float]]
    drawdown: Dict[str, Optional[float]]
    pnl: Dict[str, Optional[float]]


@dataclass(frozen=True)
class FailureSignals:
    """Champion failure warning flags. / 冠军失效预警信号。"""

    pf_declining: bool
    pnl_declining: bool
    drawdown_expanding: bool
    frequent_turnover: bool
    warning_level: str


@dataclass(frozen=True)
class StabilityAnalysis:
    """Final stability analysis. / 最终稳定性分析。"""

    current_champion: str
    health_score: int
    status: str
    current_pf: Optional[float]
    current_win_rate: Optional[float]
    current_drawdown: Optional[float]
    lifetime: LifetimeStats
    turnover_count_30d: int
    turnover_rate: float
    rolling: RollingMetrics
    failure_signals: FailureSignals
    recommendation: str


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
        "report": base / "reports" / "champion_stability" / "champion_stability_report.md",
        "latest": base / "data" / "champion_stability" / "latest.json",
    }


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _float(row: dict, *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = row.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
    return default


def _champion_id(row: dict) -> str:
    return str(
        row.get("champion_id")
        or row.get("strategy_id")
        or row.get("current_champion")
        or row.get("champion")
        or row.get("dominant_signal_source")
        or row.get("champion_portfolio")
        or "UNKNOWN"
    )


def normalize_champion_history(rows: Iterable[dict]) -> List[ChampionDay]:
    """Normalize champion_history.jsonl rows. / 标准化冠军历史行。"""

    days = [
        ChampionDay(
            str(row.get("date") or row.get("day") or ""),
            _champion_id(row),
            _float(row, "daily_result", "pnl", "champion_pnl"),
            _float(row, "max_drawdown_record", "max_drawdown", "champion_max_drawdown"),
        )
        for row in rows
    ]
    return sorted([day for day in days if day.date], key=lambda day: day.date)


def normalize_fitness_scores(rows: Iterable[dict]) -> List[FitnessDay]:
    """Normalize fitness_scores.jsonl rows. / 标准化 fitness 分数行。"""

    def norm_rate(value: float) -> float:
        return round(value / 100.0, 4) if value > 1.0 else value

    def norm_drawdown(value: float) -> float:
        return round(value / 100.0, 4) if abs(value) > 1.0 else value

    days = [
        FitnessDay(
            str(row.get("date") or row.get("day") or ""),
            str(row.get("strategy_id") or row.get("champion_id") or row.get("strategy") or "UNKNOWN"),
            _float(row, "profit_factor", "pf"),
            norm_rate(_float(row, "win_rate", "win_rate_pct")),
            norm_drawdown(_float(row, "max_drawdown", "max_drawdown_pct")),
            _float(row, "pnl", "daily_result", "champion_pnl"),
        )
        for row in rows
    ]
    return sorted([day for day in days if day.date], key=lambda day: day.date)


def lifetime_stats(history: List[ChampionDay]) -> LifetimeStats:
    """Calculate consecutive champion lifetimes. / 计算连续冠军寿命。"""

    if not history:
        return LifetimeStats(0.0, 0.0, 0, 0, 0)
    runs: List[int] = []
    current_id = history[0].champion_id
    current_len = 0
    for day in history:
        if day.champion_id == current_id:
            current_len += 1
        else:
            runs.append(current_len)
            current_id = day.champion_id
            current_len = 1
    runs.append(current_len)
    return LifetimeStats(
        round(sum(runs) / len(runs), 2),
        float(median(runs)),
        max(runs),
        min(runs),
        runs[-1],
    )


def turnover_count(history: List[ChampionDay], window: int = 30) -> int:
    """Count champion switches in the latest window. / 统计最近窗口内冠军切换次数。"""

    rows = history[-window:]
    if len(rows) < 2:
        return 0
    return sum(1 for idx in range(1, len(rows)) if rows[idx].champion_id != rows[idx - 1].champion_id)


def turnover_rate(history: List[ChampionDay], window: int = 30) -> float:
    """Champion switches divided by possible transitions. / 切换次数除以可切换次数。"""

    rows = history[-window:]
    if len(rows) < 2:
        return 0.0
    return round(turnover_count(history, window) / (len(rows) - 1), 4)


def _recent_for_champion(fitness: List[FitnessDay], champion_id: str) -> List[FitnessDay]:
    return [row for row in fitness if row.strategy_id == champion_id]


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def rolling_metrics(fitness: List[FitnessDay], champion_id: str) -> RollingMetrics:
    """Compute 5/10/20 rolling PF, win rate, drawdown, and PnL. / 计算 5/10/20 日滚动指标。"""

    rows = _recent_for_champion(fitness, champion_id)
    pf: Dict[str, Optional[float]] = {}
    wr: Dict[str, Optional[float]] = {}
    dd: Dict[str, Optional[float]] = {}
    pnl: Dict[str, Optional[float]] = {}
    for window in WINDOWS:
        sample = rows[-window:]
        key = f"{window}d"
        pf[key] = _avg([row.profit_factor for row in sample]) if sample else None
        wr[key] = _avg([row.win_rate for row in sample]) if sample else None
        dd[key] = _avg([row.max_drawdown for row in sample]) if sample else None
        pnl[key] = _avg([row.pnl for row in sample]) if sample else None
    return RollingMetrics(pf, wr, dd, pnl)


def _strict_decline(values: List[Optional[float]]) -> bool:
    nums = [value for value in values if value is not None]
    return len(nums) >= 3 and nums[0] > nums[1] > nums[2]


def _drawdown_expanding(values: List[Optional[float]]) -> bool:
    nums = [value for value in values if value is not None]
    return len(nums) >= 3 and abs(nums[0]) < abs(nums[1]) < abs(nums[2])


def detect_failure_signals(rolling: RollingMetrics, turnover: float) -> FailureSignals:
    """Detect champion failure warnings. / 检测冠军失效预警。"""

    pf_declining = _strict_decline([rolling.profit_factor["20d"], rolling.profit_factor["10d"], rolling.profit_factor["5d"]])
    pnl_declining = _strict_decline([rolling.pnl["20d"], rolling.pnl["10d"], rolling.pnl["5d"]])
    drawdown_expanding = _drawdown_expanding([rolling.drawdown["20d"], rolling.drawdown["10d"], rolling.drawdown["5d"]])
    frequent_turnover = turnover >= 0.35
    count = sum([pf_declining, pnl_declining, drawdown_expanding, frequent_turnover])
    warning = HIGH if count >= 3 else MEDIUM if count >= 1 else LOW
    return FailureSignals(pf_declining, pnl_declining, drawdown_expanding, frequent_turnover, warning)


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def champion_health_score(lifetime: LifetimeStats, rolling: RollingMetrics, turnover: float) -> int:
    """Weighted 0-100 health score. / 加权 0-100 健康度。"""

    stability_component = _scale(lifetime.current_lifetime, 1.0, 10.0) * (1.0 - min(turnover, 1.0))
    pf_component = _scale(rolling.profit_factor["5d"] or 0.0, 0.8, 2.0)
    drawdown_component = 1.0 - min(abs(rolling.drawdown["5d"] or 0.0) / 0.20, 1.0)
    consistency_component = (rolling.win_rate["5d"] or 0.0)
    score = (
        stability_component * 40.0
        + pf_component * 30.0
        + drawdown_component * 20.0
        + consistency_component * 10.0
    )
    return int(round(max(0.0, min(100.0, score))))


def _status(score: int) -> str:
    if score >= 85:
        return HEALTHY
    if score >= 60:
        return WATCH_STATUS
    return DANGER


def _recommendation(score: int, warning: str) -> str:
    if warning == HIGH or score < 60:
        return REPLACE
    if warning == MEDIUM or score < 85:
        return WATCH
    return KEEP


def analyze_stability(
    champion_history_rows: Iterable[dict],
    fitness_score_rows: Iterable[dict],
    strategy_ranking_rows: Iterable[dict] | None = None,
    benchmark_results: Iterable[dict] | None = None,
) -> StabilityAnalysis:
    """Analyze champion stability from existing Arena outputs. / 从既有 Arena 输出分析冠军稳定性。"""

    history = normalize_champion_history(champion_history_rows)
    fitness = normalize_fitness_scores(fitness_score_rows)
    if not history:
        empty_lifetime = LifetimeStats(0.0, 0.0, 0, 0, 0)
        empty_rolling = RollingMetrics({f"{w}d": None for w in WINDOWS}, {f"{w}d": None for w in WINDOWS}, {f"{w}d": None for w in WINDOWS}, {f"{w}d": None for w in WINDOWS})
        empty_failure = FailureSignals(False, False, False, False, HIGH)
        return StabilityAnalysis("UNKNOWN", 0, DANGER, None, None, None, empty_lifetime, 0, 0.0, empty_rolling, empty_failure, REPLACE)

    current = history[-1].champion_id
    lifetime = lifetime_stats(history)
    turnover = turnover_rate(history)
    turnover_n = turnover_count(history)
    rolling = rolling_metrics(fitness, current)
    failure = detect_failure_signals(rolling, turnover)
    score = champion_health_score(lifetime, rolling, turnover)
    return StabilityAnalysis(
        current,
        score,
        _status(score),
        rolling.profit_factor["5d"],
        rolling.win_rate["5d"],
        rolling.drawdown["5d"],
        lifetime,
        turnover_n,
        turnover,
        rolling,
        failure,
        _recommendation(score, failure.warning_level),
    )


def load_and_analyze(
    champion_history_path: Path | None = None,
    fitness_scores_path: Path | None = None,
    strategy_rankings_path: Path | None = None,
    benchmark_results_path: Path | None = None,
) -> StabilityAnalysis:
    """Load existing data files and analyze. / 读取既有数据文件并分析。"""

    paths = default_paths()
    champion_path = champion_history_path or paths["champion_history"]
    fitness_path = fitness_scores_path or paths["fitness_scores"]
    ranking_path = strategy_rankings_path or paths["strategy_rankings"]
    benchmark_path = benchmark_results_path or paths["benchmark_results"]
    benchmark_rows = json.loads(benchmark_path.read_text(encoding="utf-8")) if benchmark_path.exists() else []
    return analyze_stability(_load_jsonl(champion_path), _load_jsonl(fitness_path), _load_jsonl(ranking_path), benchmark_rows)


def render_report(analysis: StabilityAnalysis) -> str:
    """Render champion stability report. / 生成冠军稳定性报告。"""

    return "\n".join(
        [
            "# Champion Stability Report",
            "",
            f"Champion: {analysis.current_champion}",
            f"Health Score: {analysis.health_score}",
            f"Status: {analysis.status}",
            f"Current PF: {analysis.current_pf}",
            f"Current Win Rate: {analysis.current_win_rate}",
            f"Current Drawdown: {analysis.current_drawdown}",
            "",
            "Champion Lifetime:",
            f"- Average Lifetime: {analysis.lifetime.average_lifetime}",
            f"- Median Lifetime: {analysis.lifetime.median_lifetime}",
            f"- Max Lifetime: {analysis.lifetime.max_lifetime}",
            f"- Min Lifetime: {analysis.lifetime.min_lifetime}",
            f"- Current Lifetime: {analysis.lifetime.current_lifetime} Days",
            "",
            f"Turnover Count 30D: {analysis.turnover_count_30d}",
            f"Turnover Rate: {analysis.turnover_rate}",
            "",
            "Rolling Metrics:",
            f"- PF 5D/10D/20D: {analysis.rolling.profit_factor['5d']} / {analysis.rolling.profit_factor['10d']} / {analysis.rolling.profit_factor['20d']}",
            f"- Win Rate 5D/10D/20D: {analysis.rolling.win_rate['5d']} / {analysis.rolling.win_rate['10d']} / {analysis.rolling.win_rate['20d']}",
            f"- Drawdown 5D/10D/20D: {analysis.rolling.drawdown['5d']} / {analysis.rolling.drawdown['10d']} / {analysis.rolling.drawdown['20d']}",
            "",
            "Failure Signals:",
            f"- PF Declining: {analysis.failure_signals.pf_declining}",
            f"- PnL Declining: {analysis.failure_signals.pnl_declining}",
            f"- Drawdown Expanding: {analysis.failure_signals.drawdown_expanding}",
            f"- Frequent Turnover: {analysis.failure_signals.frequent_turnover}",
            f"- Warning: {analysis.failure_signals.warning_level}",
            "",
            f"Recommendation: {analysis.recommendation}",
            "",
        ]
    )


def write_outputs(analysis: StabilityAnalysis, report_path: Path | None = None, latest_path: Path | None = None) -> tuple[Path, Path]:
    """Write markdown report and latest dashboard JSON. / 写 Markdown 报告和 dashboard JSON。"""

    paths = default_paths()
    report_out = report_path or paths["report"]
    latest_out = latest_path or paths["latest"]
    report_out.parent.mkdir(parents=True, exist_ok=True)
    latest_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(render_report(analysis), encoding="utf-8")
    latest_out.write_text(json.dumps(asdict(analysis), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report_out, latest_out


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Arena champion stability.")
    parser.add_argument("--champion-history", default=None)
    parser.add_argument("--fitness-scores", default=None)
    parser.add_argument("--strategy-rankings", default=None)
    parser.add_argument("--benchmark-results", default=None)
    args = parser.parse_args()
    analysis = load_and_analyze(
        Path(args.champion_history) if args.champion_history else None,
        Path(args.fitness_scores) if args.fitness_scores else None,
        Path(args.strategy_rankings) if args.strategy_rankings else None,
        Path(args.benchmark_results) if args.benchmark_results else None,
    )
    report, latest = write_outputs(analysis)
    print(f"[champion_stability] wrote {report} and {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
