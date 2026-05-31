"""
MagicQuant Historical Arena Reconstruction.
VERSION : v1.0.0
DEPENDS : argparse, csv, dataclasses, datetime, json, pathlib, statistics, typing,
          config.settings, core.arena.ensemble

Purpose / 用途:
Rebuild historical Arena samples from existing RKLB 1m history. This is a data
backfill only: no new strategy, no AI generation, no mutation, no regime, and
no live trading logic changes.
仅使用已有 RKLB 1m 历史数据重建 Arena 样本；这是数据补齐脚本，不新增策略、
不生成 AI、不变异、不引入 Regime、不改实盘交易逻辑。
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, time
import json
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional

from core.arena.ensemble import ArenaSignal, decide_champion_portfolio


RTH_START = time(9, 30)
RTH_END = time(16, 0)
DEFAULT_DAYS = 90
CAPITAL_UNIT = 100.0


@dataclass(frozen=True)
class DailyArenaBackfill:
    date: str
    champion_id: str
    signal_time: str
    entry_price: float
    close_price: float
    champion_signal: str
    preferred_instrument: str
    champion_members: tuple[str, ...]
    bull_votes: int
    bear_votes: int
    neutral_votes: int
    net_score: int
    strategy_votes: tuple[dict, ...]
    ai_votes: dict
    family_contributions: dict
    champion_pnl: float
    benchmark_a_pnl: float
    benchmark_b_pnl: float
    benchmark_c_pnl: float
    actual_result: dict


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def _historical_path() -> Path:
    return _base_dir() / "data" / "historical" / "RKLB_1m.csv"


def _out_dir() -> Path:
    return _base_dir() / "data" / "arena"


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")


def _load_daily_bars(path: Path) -> Dict[str, List[dict]]:
    days: Dict[str, List[dict]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                dt = _parse_time(row["time_key"])
                if not (RTH_START <= dt.time() < RTH_END):
                    continue
                bar = {
                    "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0) or 0),
                }
            except (KeyError, ValueError):
                continue
            days.setdefault(dt.strftime("%Y-%m-%d"), []).append(bar)
    return {day: bars for day, bars in days.items() if len(bars) >= 180}


def _pct(entry: float, exit_price: float) -> float:
    return (exit_price - entry) / entry if entry > 0 else 0.0


def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) <= period:
        return None
    gains, losses = [], []
    for idx in range(-period, 0):
        diff = closes[idx] - closes[idx - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = mean(gains) / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _direction_from_score(score: float, threshold: float = 0.002) -> str:
    if score > threshold:
        return "bull"
    if score < -threshold:
        return "bear"
    return "neutral"


def _vote_rows(day: str, bars: List[dict], signal_idx: int) -> List[dict]:
    history = bars[: signal_idx + 1]
    first = bars[0]
    current = bars[signal_idx]
    closes = [bar["close"] for bar in history]
    volumes = [bar["volume"] for bar in history]
    day_return = _pct(first["open"], current["close"])
    short_return = _pct(history[max(0, len(history) - 15)]["close"], current["close"])
    rsi = _rsi(closes) or 50.0
    avg_volume = mean(volumes[:-1]) if len(volumes) > 1 else current["volume"]
    volume_ratio = current["volume"] / avg_volume if avg_volume > 0 else 1.0
    recent_high = max(bar["high"] for bar in history[-30:])
    recent_low = min(bar["low"] for bar in history[-30:])

    trend = _direction_from_score(day_return)
    reversion = "bear" if rsi >= 72 else "bull" if rsi <= 35 else "neutral"
    volume = "bull" if current["close"] >= recent_high * 0.998 and volume_ratio >= 1.25 else "bear" if current["close"] <= recent_low * 1.002 and volume_ratio >= 1.25 else "neutral"

    # AI proxy votes are deterministic historical proxies, not model calls.
    # AI 代理票是确定性历史代理，不调用模型。
    gpt = trend
    claude = trend if abs(day_return) >= 0.006 else "neutral"
    deepseek = reversion
    kimi = volume if volume != "neutral" else _direction_from_score(short_return, 0.0015)

    return [
        {"member_id": "h1_trend", "direction": trend, "family": "Trend Family", "reason": f"day_return={day_return:.4f}"},
        {"member_id": "h2_mean_reversion", "direction": reversion, "family": "Mean Reversion Family", "reason": f"rsi={rsi:.1f}"},
        {"member_id": "h3_volume_breakout", "direction": volume, "family": "Volume Family", "reason": f"volume_ratio={volume_ratio:.2f}"},
        {"member_id": "gpt", "direction": gpt, "family": "AI Family", "reason": "historical trend proxy"},
        {"member_id": "claude", "direction": claude, "family": "AI Family", "reason": "historical risk-balanced proxy"},
        {"member_id": "deepseek", "direction": deepseek, "family": "AI Family", "reason": "historical reversion proxy"},
        {"member_id": "kimi", "direction": kimi, "family": "AI Family", "reason": "historical volume proxy"},
    ]


def _signal_to_pnl(signal: str, entry: float, close: float) -> float:
    move = _pct(entry, close)
    if signal == "LONG":
        return round(move * 2.0 * CAPITAL_UNIT, 4)
    if signal == "SHORT":
        return round(-move * 2.0 * CAPITAL_UNIT, 4)
    return 0.0


def _family_contributions(votes: List[dict], champion_pnl: float) -> dict:
    active = [vote for vote in votes if vote["direction"] != "neutral"]
    if not active or champion_pnl == 0:
        return {}
    counts: Dict[str, int] = {}
    for vote in active:
        counts[vote["family"]] = counts.get(vote["family"], 0) + 1
    total = sum(counts.values())
    return {family: round(champion_pnl * count / total, 4) for family, count in counts.items()}


def _max_drawdown(values: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return round(worst, 4)


def _pf(values: List[float]) -> Optional[float]:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None if wins == 0 else float("inf")
    return round(wins / losses, 4)


def _win_rate(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(1 for value in values if value > 0) / len(values), 4)


def reconstruct(days: int = DEFAULT_DAYS, historical_path: Path | None = None) -> List[DailyArenaBackfill]:
    daily = _load_daily_bars(historical_path or _historical_path())
    selected_days = sorted(daily)[-days:]
    records: List[DailyArenaBackfill] = []
    for day in selected_days:
        bars = daily[day]
        signal_idx = min(60, len(bars) - 2)
        entry = bars[signal_idx]["close"]
        close = bars[-1]["close"]
        votes = _vote_rows(day, bars, signal_idx)
        signals = [ArenaSignal(vote["member_id"], vote["direction"], reason=vote["reason"]) for vote in votes]
        decision = decide_champion_portfolio(signals)
        champion_pnl = _signal_to_pnl(decision.action, entry, close)
        benchmark_a = round(_pct(bars[0]["open"], close) * CAPITAL_UNIT, 4)
        # Current Main Strategy proxy: H1 trend only, applied from the same signal time.
        benchmark_b = _signal_to_pnl("LONG" if votes[0]["direction"] == "bull" else "SHORT" if votes[0]["direction"] == "bear" else "HOLD", entry, close)
        benchmark_c = 0.0
        ai_votes = {vote["member_id"]: vote["direction"] for vote in votes if vote["family"] == "AI Family"}
        records.append(
            DailyArenaBackfill(
                date=day,
                champion_id="Champion Portfolio",
                signal_time=bars[signal_idx]["time"],
                entry_price=round(entry, 4),
                close_price=round(close, 4),
                champion_signal=decision.action,
                preferred_instrument=decision.preferred_instrument,
                champion_members=tuple(member for vote in decision.cluster_votes for member in vote.members),
                bull_votes=decision.bull_votes,
                bear_votes=decision.bear_votes,
                neutral_votes=decision.neutral_votes,
                net_score=decision.net_score,
                strategy_votes=tuple(votes),
                ai_votes=ai_votes,
                family_contributions=_family_contributions(votes, champion_pnl),
                champion_pnl=champion_pnl,
                benchmark_a_pnl=benchmark_a,
                benchmark_b_pnl=benchmark_b,
                benchmark_c_pnl=benchmark_c,
                actual_result={
                    "champion_pnl": champion_pnl,
                    "benchmark_a_pnl": benchmark_a,
                    "benchmark_b_pnl": benchmark_b,
                    "benchmark_c_pnl": benchmark_c,
                    "champion_max_drawdown": min(0.0, champion_pnl),
                    "benchmark_b_max_drawdown": min(0.0, benchmark_b),
                },
            )
        )
    return records


def _write_jsonl(path: Path, rows: Iterable[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    return path


def write_outputs(records: List[DailyArenaBackfill], out_dir: Path | None = None) -> dict[str, Path]:
    out = out_dir or _out_dir()
    record_dicts = [asdict(record) for record in records]
    champion_pnls = [record.champion_pnl for record in records]
    fitness_rows = []
    for idx, record in enumerate(records):
        sample = champion_pnls[max(0, idx - 19) : idx + 1]
        fitness_rows.append(
            {
                "date": record.date,
                "strategy_id": "Champion Portfolio",
                "profit_factor": _pf(sample),
                "win_rate": _win_rate(sample),
                "max_drawdown": _max_drawdown(sample),
                "pnl": record.champion_pnl,
            }
        )
    champion_history = [
        {
            "date": record.date,
            "champion_id": "Champion Portfolio",
            "champion_portfolio": record.champion_signal,
            "dominant_signal_source": record.champion_members[0] if record.champion_members else "none",
            "daily_result": record.champion_pnl,
            "max_drawdown_record": min(0.0, record.champion_pnl),
        }
        for record in records
    ]
    paths = {
        "champion_history": _write_jsonl(out / "champion_history.jsonl", champion_history),
        "arena_decisions": _write_jsonl(out / "arena_decisions.jsonl", record_dicts),
        "historical_trial_results": _write_jsonl(out / "historical_trial_results.jsonl", record_dicts),
        "fitness_scores": _write_jsonl(out / "fitness_scores.jsonl", fitness_rows),
    }
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill historical Arena samples from RKLB 1m history.")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--historical-path", default=None)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    records = reconstruct(args.days, Path(args.historical_path) if args.historical_path else None)
    paths = write_outputs(records, Path(args.out_dir) if args.out_dir else None)
    print(f"[arena_backfill] reconstructed {len(records)} trading days")
    for name, path in paths.items():
        print(f"[arena_backfill] {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
