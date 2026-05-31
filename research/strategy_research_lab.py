"""
MagicQuant Strategy Research Lab.
VERSION : v1.0.0
DEPENDS : argparse, csv, dataclasses, datetime, json, pathlib, statistics, typing,
          config.settings

Purpose / 用途:
Generate observation-first research reports from existing RKLB/RKLX/RKLZ
history and Arena trial records. This lab does not generate strategies,
modify parameters, optimize, mutate, trade, or change Arena scoring.
基于已有 RKLB/RKLX/RKLZ 历史数据与 Arena 试验记录生成先观察后优化的研究报告；
本实验室不生成策略、不修改参数、不优化、不变异、不交易、不修改 Arena 评分。
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, time
import json
from pathlib import Path
from statistics import mean
import sys
from typing import Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RTH_START = time(9, 30)
RTH_END = time(16, 0)
CAPITAL_UNIT = 100.0


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def default_paths() -> dict[str, Path]:
    base = _base_dir()
    return {
        "rklb": base / "data" / "historical" / "RKLB_1m.csv",
        "rklx": base / "data" / "historical" / "RKLX_1m.csv",
        "rklz": base / "data" / "historical" / "RKLZ_1m.csv",
        "trial": base / "data" / "arena" / "historical_trial_results.jsonl",
        "out": base / "reports" / "research",
    }


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")


def _load_bars(path: Path, keep_all_sessions: bool = False) -> Dict[str, List[Bar]]:
    days: Dict[str, List[Bar]] = {}
    if not path.exists():
        return days
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                ts = _parse_time(row["time_key"])
                if not keep_all_sessions and not (RTH_START <= ts.time() < RTH_END):
                    continue
                bar = Bar(
                    ts,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row.get("volume", 0) or 0),
                )
            except (KeyError, ValueError):
                continue
            days.setdefault(ts.strftime("%Y-%m-%d"), []).append(bar)
    return {day: bars for day, bars in days.items() if bars}


def _pct(entry: float, exit_price: float) -> float:
    return (exit_price - entry) / entry if entry > 0 else 0.0


def _signal_pnl(direction: str, entry: float, close: float) -> float:
    value = str(direction).lower()
    move = _pct(entry, close)
    if value in {"bull", "long", "buy"}:
        return move * 2.0 * CAPITAL_UNIT
    if value in {"bear", "short", "sell"}:
        return -move * 2.0 * CAPITAL_UNIT
    return 0.0


def _pf(values: Iterable[float]) -> Optional[float]:
    rows = list(values)
    wins = sum(value for value in rows if value > 0)
    losses = abs(sum(value for value in rows if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return wins / losses


def _win_rate(values: Iterable[float]) -> Optional[float]:
    active = [value for value in values if value != 0]
    if not active:
        return None
    return sum(1 for value in active if value > 0) / len(active)


def _max_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if value == float("inf"):
        return "inf"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _metric_line(values: List[float]) -> str:
    wr = _win_rate(values)
    return (
        f"Count {len(values)}, PnL {_fmt(sum(values))}, PF {_fmt(_pf(values))}, "
        f"Win Rate {_fmt(wr * 100 if wr is not None else None)}%, Max DD {_fmt(_max_drawdown(values))}"
    )


def _norm_direction(value: str) -> str:
    text = str(value or "").upper()
    if text in {"BULL", "BUY", "LONG"}:
        return "LONG"
    if text in {"BEAR", "SELL", "SHORT"}:
        return "SHORT"
    return "HOLD"


def _vote(row: dict, member_id: str) -> Optional[dict]:
    for vote in row.get("strategy_votes") or []:
        if vote.get("member_id") == member_id:
            return vote
    return None


def _reason_float(reason: str, key: str) -> Optional[float]:
    marker = key + "="
    if marker not in reason:
        return None
    tail = reason.split(marker, 1)[1].split()[0]
    try:
        return float(tail)
    except ValueError:
        return None


def _session_for_time(value: str) -> str:
    try:
        ts = _parse_time(value)
    except Exception:
        return "Unknown"
    minutes = ts.hour * 60 + ts.minute
    if 9 * 60 + 30 <= minutes < 10 * 60:
        return "Opening 30m"
    if 10 * 60 <= minutes < 12 * 60:
        return "Morning"
    if 12 * 60 <= minutes < 14 * 60:
        return "Midday"
    if 14 * 60 <= minutes <= 16 * 60:
        return "Closing"
    return "Other"


def _day_regime(bars: List[Bar]) -> str:
    if not bars:
        return "Unknown"
    day_ret = _pct(bars[0].open, bars[-1].close)
    intraday_range = (max(bar.high for bar in bars) - min(bar.low for bar in bars)) / bars[0].open
    if day_ret >= 0.02:
        return "Uptrend Day"
    if day_ret <= -0.02:
        return "Downtrend Day"
    if intraday_range >= 0.05:
        return "Choppy Wide Range"
    return "Range Day"


def _vwap(bars: List[Bar]) -> float:
    total_vol = sum(bar.volume for bar in bars)
    if total_vol <= 0:
        return bars[-1].close if bars else 0.0
    return sum(((bar.high + bar.low + bar.close) / 3.0) * bar.volume for bar in bars) / total_vol


def _table(headers: List[str], rows: List[List[str]]) -> List[str]:
    if not rows:
        return ["No data."]
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
        *["| " + " | ".join(row) + " |" for row in rows],
    ]


def _report(title: str, summary: List[str], findings: List[str], data: List[str], risks: List[str], followups: List[str]) -> str:
    lines = [
        f"# {title}",
        "",
        "## Executive Summary",
        *[f"- {item}" for item in summary],
        "",
        "## Key Findings",
        *[f"- {item}" for item in findings],
        "",
        "## Supporting Data",
        *data,
        "",
        "## Risks",
        *[f"- {item}" for item in risks],
        "",
        "## Suggested Follow-up Research",
        *[f"- {item}" for item in followups],
        "",
        "Research Queue Status: WAITING_FOR_HUMAN_REVIEW",
        "",
    ]
    return "\n".join(lines)


class ResearchLab:
    def __init__(self, rklb: Dict[str, List[Bar]], rklx: Dict[str, List[Bar]], rklz: Dict[str, List[Bar]], records: List[dict]):
        self.rklb = rklb
        self.rklx = rklx
        self.rklz = rklz
        self.records = records[-90:]

    def volume_breakout(self) -> str:
        pnls, by_bucket = [], {"<0.8x": [], "0.8-1.2x": [], "1.2-1.8x": [], ">1.8x": []}
        active = 0
        for row in self.records:
            vote = _vote(row, "h3_volume_breakout")
            if not vote:
                continue
            ratio = _reason_float(str(vote.get("reason", "")), "volume_ratio") or 0.0
            pnl = _signal_pnl(vote.get("direction", "neutral"), row.get("entry_price", 0), row.get("close_price", 0))
            pnls.append(pnl)
            if pnl != 0:
                active += 1
            bucket = "<0.8x" if ratio < 0.8 else "0.8-1.2x" if ratio < 1.2 else "1.2-1.8x" if ratio < 1.8 else ">1.8x"
            by_bucket[bucket].append(pnl)
        rows = [[bucket, _metric_line(values)] for bucket, values in by_bucket.items()]
        return _report(
            "MQ-RESEARCH-001 Volume Breakout Deep Dive",
            [f"Volume Breakout was active on {active} of {len(self.records)} reconstructed days.", "This is an observation report only; no volume threshold was changed."],
            ["Best/worst zones are read from historical realized vote outcomes.", "If active count is low, conclusions should be treated as weak evidence."],
            _table(["Volume Ratio Bucket", "Observed Result"], rows),
            ["Historical proxy votes may under-represent real-time volume context.", "Low trade count can make PF unstable."],
            ["Review volume traps separately from clean expansion days.", "Compare RKLX/RKLZ execution slippage around active volume events."],
        )

    def trend_family(self) -> str:
        by_regime: Dict[str, List[float]] = {}
        for row in self.records:
            day = row.get("date")
            vote = _vote(row, "h1_trend")
            bars = self.rklb.get(day, [])
            if not vote or not bars:
                continue
            regime = _day_regime(bars)
            by_regime.setdefault(regime, []).append(_signal_pnl(vote.get("direction", "neutral"), row.get("entry_price", 0), row.get("close_price", 0)))
        rows = [[regime, _metric_line(values)] for regime, values in sorted(by_regime.items())]
        return _report(
            "MQ-RESEARCH-002 Trend Family Deep Dive",
            ["Trend Family behavior was split across uptrend, downtrend, wide-range, and range days."],
            ["Trend edge should be judged by regime, not aggregate score alone.", "Range days are the likely stress case for trend following."],
            _table(["Market Regime", "Trend Vote Result"], rows),
            ["Regime labels are descriptive, not a new Regime Engine.", "Using close-to-close day labels can hide intraday reversals."],
            ["Study trend failure after large opening gaps.", "Compare trend vote with VWAP position at signal time."],
        )

    def vwap_reversal(self) -> str:
        buckets = {"Below VWAP >1%": [], "Near VWAP": [], "Above VWAP >1%": []}
        for row in self.records:
            bars = self.rklb.get(row.get("date"), [])
            if len(bars) < 62:
                continue
            signal_bars = bars[:61]
            vwap = _vwap(signal_bars)
            price = signal_bars[-1].close
            deviation = _pct(vwap, price)
            close = bars[-1].close
            reversal_pnl = -_pct(price, close) * CAPITAL_UNIT if deviation > 0 else _pct(price, close) * CAPITAL_UNIT
            bucket = "Below VWAP >1%" if deviation < -0.01 else "Above VWAP >1%" if deviation > 0.01 else "Near VWAP"
            buckets[bucket].append(reversal_pnl)
        return _report(
            "MQ-RESEARCH-003 VWAP Reversal Deep Dive",
            ["VWAP reversal was studied as an observational condition, not added as a strategy."],
            ["The key question is whether distance from VWAP creates mean-reversion pressure before close."],
            _table(["VWAP Condition", "Observed Reversal Result"], [[k, _metric_line(v)] for k, v in buckets.items()]),
            ["VWAP condition is computed from historical bars and may differ from live cached VWAP.", "No execution spread or slippage is modeled."],
            ["Split VWAP reversal by opening gap direction.", "Check whether reversal works better after high-volume exhaustion bars."],
        )

    def opening_session(self) -> str:
        open_pnls, champion_when_morning = [], []
        for row in self.records:
            bars = self.rklb.get(row.get("date"), [])
            if len(bars) < 31:
                continue
            open_pnls.append(_pct(bars[0].open, bars[30].close) * CAPITAL_UNIT)
            if _session_for_time(row.get("signal_time", "")) in {"Opening 30m", "Morning"}:
                champion_when_morning.append(float(row.get("champion_pnl") or 0.0))
        return _report(
            "MQ-RESEARCH-004 Opening Session Study",
            ["Opening-session movement and Arena morning decisions were measured separately."],
            ["Open Edge exists only if early movement converts into positive later PnL, not merely volatility."],
            ["Opening 30m RKLB move: " + _metric_line(open_pnls), "Arena morning decisions: " + _metric_line(champion_when_morning)],
            ["Arena historical signal currently fires around 10:30, so pure 9:30-10:00 edge is indirect.", "Premarket/overnight context is not fully separated here."],
            ["Run a dedicated 9:30, 10:00, 10:30 decision-time comparison.", "Separate gap-up fade from gap-up continuation."],
        )

    def closing_session(self) -> str:
        closing = []
        for row in self.records:
            bars = self.rklb.get(row.get("date"), [])
            if len(bars) < 120:
                continue
            closing.append(_pct(bars[-60].open, bars[-1].close) * CAPITAL_UNIT)
        return _report(
            "MQ-RESEARCH-005 Closing Session Study",
            ["Closing hour value was measured as a standalone market behavior."],
            ["This report does not recommend adding a closing strategy; it only measures tail-session behavior."],
            ["Last 60 minutes RKLB move: " + _metric_line(closing)],
            ["Closing dynamics may be dominated by news, option expiry, or liquidity effects not labeled here."],
            ["Compare closing move with same-day Arena direction.", "Study whether losing morning signals recover or worsen into close."],
        )

    def losing_autopsy(self) -> str:
        losses = [row for row in self.records if float(row.get("champion_pnl") or 0) < 0]
        categories: Dict[str, List[float]] = {"False Breakout": [], "Gap Reversal": [], "News/Sharp Reversal": [], "Volume Trap": [], "Other": []}
        for row in losses:
            pnl = float(row.get("champion_pnl") or 0)
            h3 = _vote(row, "h3_volume_breakout")
            h1 = _vote(row, "h1_trend")
            ratio = _reason_float(str((h3 or {}).get("reason", "")), "volume_ratio") or 0.0
            benchmark = float(row.get("benchmark_a_pnl") or 0)
            if h3 and h3.get("direction") != "neutral" and ratio >= 1.2:
                categories["Volume Trap"].append(pnl)
            elif h1 and h1.get("direction") != "neutral" and benchmark * pnl < 0:
                categories["False Breakout"].append(pnl)
            elif abs(benchmark) >= 3:
                categories["Gap Reversal"].append(pnl)
            elif abs(pnl) >= 8:
                categories["News/Sharp Reversal"].append(pnl)
            else:
                categories["Other"].append(pnl)
        return _report(
            "MQ-RESEARCH-006 Losing Trades Autopsy",
            [f"Found {len(losses)} losing Champion Portfolio days in the 90-day reconstruction."],
            ["Losses are classified by observable historical symptoms, not by assumed intent.", "Large single-day losses deserve separate review before any parameter change."],
            _table(["Loss Category", "Observed Loss Result"], [[k, _metric_line(v)] for k, v in categories.items()]),
            ["Category labels are heuristic and require human review.", "News reversals are inferred from price behavior, not a news feed."],
            ["Manually inspect the five largest losing days.", "Add news/event tags only after human review approves the taxonomy."],
        )

    def winning_autopsy(self) -> str:
        wins = [row for row in self.records if float(row.get("champion_pnl") or 0) > 0]
        by_direction: Dict[str, List[float]] = {"LONG": [], "SHORT": [], "HOLD": []}
        for row in wins:
            by_direction.setdefault(str(row.get("champion_signal") or "HOLD"), []).append(float(row.get("champion_pnl") or 0))
        return _report(
            "MQ-RESEARCH-007 Winning Trades Autopsy",
            [f"Found {len(wins)} winning Champion Portfolio days in the 90-day reconstruction."],
            ["Winning days are split by Arena direction to identify where positive expectancy actually came from."],
            _table(["Champion Direction", "Observed Win Result"], [[k, _metric_line(v)] for k, v in by_direction.items()]),
            ["Winning classifications do not prove repeatability.", "Direction-level wins can mask poor entry timing."],
            ["Break winning days into trend-continuation vs reversion wins.", "Review whether winners cluster around specific market sessions."],
        )

    def ai_signal_study(self) -> str:
        rows = []
        for member in ["gpt", "claude", "deepseek", "kimi"]:
            pnls, agree, active = [], 0, 0
            for row in self.records:
                vote = _vote(row, member)
                if not vote:
                    continue
                direction = vote.get("direction", "neutral")
                pnl = _signal_pnl(direction, row.get("entry_price", 0), row.get("close_price", 0))
                pnls.append(pnl)
                if direction != "neutral":
                    active += 1
                if _norm_direction(direction) == _norm_direction(str(row.get("champion_signal") or "HOLD")):
                    agree += 1
            rows.append([member, str(active), _metric_line(pnls), _fmt(agree / len(self.records) * 100 if self.records else 0) + "%"])
        return _report(
            "MQ-RESEARCH-008 AI Signal Study",
            ["GPT, Claude, DeepSeek, and Kimi were evaluated from existing historical proxy votes."],
            ["The goal is contribution diagnosis, not changing AI weights.", "Low-activity AI members can still be valuable if they avoid bad trades."],
            _table(["AI Member", "Active Days", "Standalone Vote Result", "Champion Agreement"], rows),
            ["Historical proxy votes are not fresh model calls.", "Agreement with Champion Portfolio is not the same as accuracy."],
            ["Compare AI votes only on high-conviction days.", "Study AI disagreement days separately."],
        )

    def parameter_surface(self) -> str:
        thresholds = [1.5, 1.8, 2.0, 2.2, 2.5]
        rows = []
        for threshold in thresholds:
            pnls = []
            for row in self.records:
                vote = _vote(row, "h3_volume_breakout")
                if not vote:
                    continue
                ratio = _reason_float(str(vote.get("reason", "")), "volume_ratio") or 0.0
                if ratio >= threshold:
                    pnls.append(_signal_pnl(vote.get("direction", "neutral"), row.get("entry_price", 0), row.get("close_price", 0)))
            rows.append([f"{threshold:.1f}x", _metric_line(pnls)])
        return _report(
            "MQ-RESEARCH-009 Parameter Surface Analysis",
            ["Volume threshold surface was mapped for observation only.", "No threshold was changed by this report."],
            ["Sparse activation at high thresholds means the map can be more informative than aggregate score."],
            _table(["Volume Threshold", "Observed Historical Surface"], rows),
            ["This is not an optimizer and must not be treated as auto-tuning.", "Results depend on current historical proxy signal construction."],
            ["Add confidence bands before considering any parameter review.", "Require human approval before any threshold experiment."],
        )

    def arena_meta(self) -> str:
        by_family: Dict[str, List[float]] = {}
        by_session: Dict[str, List[float]] = {}
        by_direction: Dict[str, List[float]] = {}
        for row in self.records:
            pnl = float(row.get("champion_pnl") or 0)
            by_session.setdefault(_session_for_time(row.get("signal_time", "")), []).append(pnl)
            by_direction.setdefault(str(row.get("champion_signal") or "HOLD"), []).append(pnl)
            for family, value in (row.get("family_contributions") or {}).items():
                by_family.setdefault(family, []).append(float(value))
        data = []
        data.extend(_table(["Family", "Contribution"], [[k, _metric_line(v)] for k, v in sorted(by_family.items())]))
        data.append("")
        data.extend(_table(["Session", "Champion Result"], [[k, _metric_line(v)] for k, v in sorted(by_session.items())]))
        data.append("")
        data.extend(_table(["Direction", "Champion Result"], [[k, _metric_line(v)] for k, v in sorted(by_direction.items())]))
        return _report(
            "MQ-RESEARCH-010 Arena Meta Study",
            ["Arena meta edge was decomposed by family, session, and direction using the 90-day reconstruction."],
            ["The current sample should be used to prioritize questions, not to authorize automatic optimization."],
            data,
            ["Family contribution inherits the current vote attribution method.", "One 90-day period can overstate temporary market structure."],
            ["Cross-check this report after another 30 trading days.", "Compare meta findings against Contender Board successors."],
        )

    def build_all(self) -> Dict[str, str]:
        return {
            "REPORT_VOLUME_BREAKOUT.md": self.volume_breakout(),
            "REPORT_TREND_FAMILY.md": self.trend_family(),
            "REPORT_VWAP_REVERSAL.md": self.vwap_reversal(),
            "REPORT_OPENING_SESSION.md": self.opening_session(),
            "REPORT_CLOSING_SESSION.md": self.closing_session(),
            "REPORT_LOSS_AUTOPSY.md": self.losing_autopsy(),
            "REPORT_WIN_AUTOPSY.md": self.winning_autopsy(),
            "REPORT_AI_SIGNAL_STUDY.md": self.ai_signal_study(),
            "REPORT_PARAMETER_SURFACE.md": self.parameter_surface(),
            "REPORT_ARENA_META.md": self.arena_meta(),
        }


def build_research_queue(report_names: Iterable[str]) -> str:
    lines = [
        "# Research Queue",
        "",
        "Status: WAITING_FOR_HUMAN_REVIEW",
        "",
        "Rules:",
        "- Observation First, Optimization Later.",
        "- No strategy changes are approved by these reports.",
        "- No parameter changes are approved by these reports.",
        "- Human review is required before any experiment proposal.",
        "",
        "Reports:",
    ]
    for name in report_names:
        lines.append(f"- {name}: WAITING_FOR_HUMAN_REVIEW")
    lines.append("")
    return "\n".join(lines)


def generate_reports(out_dir: Path | None = None) -> Dict[str, Path]:
    paths = default_paths()
    out = out_dir or paths["out"]
    out.mkdir(parents=True, exist_ok=True)
    lab = ResearchLab(
        _load_bars(paths["rklb"]),
        _load_bars(paths["rklx"]),
        _load_bars(paths["rklz"]),
        _load_jsonl(paths["trial"]),
    )
    reports = lab.build_all()
    written: Dict[str, Path] = {}
    for name, content in reports.items():
        path = out / name
        path.write_text(content, encoding="utf-8")
        written[name] = path
    queue = out / "RESEARCH_QUEUE.md"
    queue.write_text(build_research_queue(reports), encoding="utf-8")
    written["RESEARCH_QUEUE.md"] = queue
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate observation-first Arena research reports.")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    written = generate_reports(Path(args.out_dir) if args.out_dir else None)
    print(f"[research_lab] wrote {len(written)} files")
    for path in written.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
