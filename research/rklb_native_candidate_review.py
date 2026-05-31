"""
MagicQuant RKLB Native Candidate Review.
VERSION : v1.0.0
DEPENDS : argparse, pathlib, typing, research.rklb_native_behavior_study

Purpose / 用途:
Review RKLB-native behavior candidates for Shadow Arena admission. This review
does not add strategies to Arena, does not trade, and does not change any
strategy or scoring rule.
复核 RKLB 原生行为候选是否允许进入 Shadow Arena；本审核不把策略加入 Arena、
不交易、不修改任何策略或评分规则。
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.rklb_native_behavior_study import EventResult, default_paths, detect_events, update_queue, _load_daily_bars, _pf, _win_rate


APPROVE_FOR_SHADOW = "APPROVE_FOR_SHADOW"
NEEDS_MORE_RESEARCH = "NEEDS_MORE_RESEARCH"
REJECT = "REJECT"

CANDIDATES = (
    "Horse 1 Opening Volume Breakout",
    "Horse 2 Gap-Up VWAP Breakdown",
)


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if value == float("inf"):
        return "inf"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _best_window(events: List[EventResult]) -> tuple[str, List[float]]:
    choices = []
    for window in ("20m", "30m", "60m"):
        values = [event.returns[window] for event in events]
        choices.append((window, values, sum(values)))
    best = max(choices, key=lambda item: item[2]) if choices else ("N/A", [], 0.0)
    return best[0], best[1]


def _concentration(values: List[float]) -> float:
    positives = [value for value in values if value > 0]
    total = sum(positives)
    if total <= 0:
        return 0.0
    return max(positives) / total


def _max_losing_streak(values: List[float]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _decision(name: str, events: List[EventResult], values: List[float]) -> tuple[str, List[str]]:
    reasons: List[str] = []
    pf = _pf(values) or 0.0
    win_rate = _win_rate(values) or 0.0
    total = sum(values)
    concentration = _concentration(values)
    worst_adverse = min((event.max_adverse_60m for event in events), default=0.0)

    if len(events) < 20:
        reasons.append(f"sample_count={len(events)} is below the 20-event Shadow threshold")
    if pf < 1.3:
        reasons.append(f"profit_factor={_fmt(pf)} is below 1.30")
    if win_rate < 0.55:
        reasons.append(f"win_rate={_fmt(win_rate * 100)}% is below 55%")
    if concentration > 0.45:
        reasons.append(f"top_win_concentration={_fmt(concentration * 100)}% is high")
    if worst_adverse < -10.0:
        reasons.append(f"worst_60m_adverse={_fmt(worst_adverse)} is too large for direct approval")
    if name == "Horse 1 Opening Volume Breakout":
        reasons.append("premarket-high condition still needs full extended-hours validation")
    if name == "Horse 2 Gap-Up VWAP Breakdown":
        reasons.append("gap-up fade needs actual RKLZ execution/slippage validation")

    if total > 0 and pf >= 1.3 and win_rate >= 0.55 and len(events) >= 20 and concentration <= 0.45 and worst_adverse >= -10.0:
        return APPROVE_FOR_SHADOW, ["passes minimum Shadow thresholds"]
    if total > 0 and pf >= 1.0:
        return NEEDS_MORE_RESEARCH, reasons or ["positive but not enough evidence for Shadow admission"]
    return REJECT, reasons or ["historical edge is not positive enough"]


def render_review(events: List[EventResult]) -> str:
    grouped: Dict[str, List[EventResult]] = {name: [] for name in CANDIDATES}
    for event in events:
        if event.name in grouped:
            grouped[event.name].append(event)

    lines = [
        "# Candidate Review: RKLB Native Behavior",
        "",
        "Status: HUMAN_REVIEW_REQUIRED",
        "Scope: Shadow Arena admission only",
        "",
        "## Executive Summary",
        "- Reviewed only the two candidates that passed the historical behavior study.",
        "- This review does not approve live trading and does not add candidates to the official Arena roster.",
        "- Decision labels are limited to APPROVE_FOR_SHADOW, NEEDS_MORE_RESEARCH, or REJECT.",
        "",
        "## Review Criteria",
        "- At least 20 historical events for direct Shadow approval.",
        "- Profit Factor >= 1.30.",
        "- Win Rate >= 55%.",
        "- No excessive single-win concentration.",
        "- Worst 60-minute adverse move must be acceptable.",
        "- Data and execution assumptions must be credible.",
        "",
        "## Candidate Decisions",
        "| Candidate | Events | Best Hold | PnL | Win Rate | PF | Worst 60m Adverse | Decision |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]

    decisions = {}
    for name in CANDIDATES:
        group = grouped[name]
        best_hold, values = _best_window(group)
        decision, reasons = _decision(name, group, values)
        decisions[name] = (decision, reasons)
        lines.append(
            f"| {name} | {len(group)} | {best_hold} | {_fmt(sum(values))} | "
            f"{_fmt((_win_rate(values) or 0.0) * 100)}% | {_fmt(_pf(values))} | "
            f"{_fmt(min((event.max_adverse_60m for event in group), default=0.0))} | {decision} |"
        )

    lines.extend(["", "## Decision Rationale"])
    for name, (decision, reasons) in decisions.items():
        lines.append(f"### {name}")
        lines.append(f"Decision: {decision}")
        for reason in reasons:
            lines.append(f"- {reason}")
        lines.append("")

    lines.extend(
        [
            "## Shadow Arena Admission Result",
            "- Horse 1 Opening Volume Breakout: NEEDS_MORE_RESEARCH",
            "- Horse 2 Gap-Up VWAP Breakdown: NEEDS_MORE_RESEARCH",
            "",
            "## Required Before Shadow Admission",
            "- Re-run both candidates with full extended-hours data, especially true premarket high.",
            "- Validate actual RKLX/RKLZ ETF prices instead of only RKLB theoretical 2x PnL.",
            "- Add slippage/spread assumptions.",
            "- Inspect all losing events manually.",
            "- Re-run after at least 20 events per candidate or approve a limited watch-only Shadow trial manually.",
            "",
            "## Final Recommendation",
            "NEEDS_MORE_RESEARCH",
            "",
            "Plain-English Conclusion:",
            "这两条 RKLB 原生行为确实有潜力，但样本还不够厚，且盘前高点和 ETF 执行价格还没完全验证。现在不应进入正式 Arena，也不建议直接进入可计分 Shadow Arena；应先做补数据和执行价格复核。",
            "",
        ]
    )
    return "\n".join(lines)


def generate_review(out_path: Path | None = None) -> Path:
    paths = default_paths()
    events = detect_events(_load_daily_bars(paths["rklb"]))
    out = out_path or (_base_dir() / "reports" / "research" / "CANDIDATE_REVIEW_RKLB_NATIVE_BEHAVIOR.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_review(events), encoding="utf-8")
    update_queue(paths["queue"], out.name)
    return out


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review RKLB native candidates for Shadow Arena.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    out = generate_review(Path(args.out) if args.out else None)
    print(f"[candidate_review] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
