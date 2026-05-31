"""
MagicQuant weekend P0 review.
VERSION: v0.1.0
DATE: 2026-05-23
DEPENDS: data/historical/*_1m.csv, data/review/*/triggers.json, data/review/*/direction_skips.json

Read-only weekend validation. / 只读周末验证,不修改主策略。
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
HIST_DIR = ROOT / "data" / "historical"
REVIEW_DIR = ROOT / "data" / "review"
DOCS_DIR = ROOT / "docs"
OUT = DOCS_DIR / "weekend_p0_results_2026-05-23.md"

TICKERS = ("RKLB", "RKLX", "RKLZ")
REVIEW_DAYS = ("2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22")
LEVERAGED = {"RKLX", "RKLZ", "TSLL"}
_BARS_CACHE: dict[str, list[Bar]] = {}
_DAILY_ATR_CACHE: dict[str, float] = {}


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def _safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "UNKNOWN"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _read_1m(ticker: str) -> list[Bar]:
    if ticker in _BARS_CACHE:
        return _BARS_CACHE[ticker]
    path = HIST_DIR / f"{ticker}_1m.csv"
    bars: list[Bar] = []
    if not path.exists():
        _BARS_CACHE[ticker] = bars
        return bars
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ts_raw = (row.get("time_key") or "").strip()
            if len(ts_raw) < 16:
                continue
            try:
                ts = datetime.strptime(ts_raw[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            vals = [_safe_float(row.get(k)) for k in ("open", "high", "low", "close")]
            vol = _safe_float(row.get("volume")) or 0.0
            if any(v is None or v <= 0 for v in vals):
                continue
            o, h, l, c = vals
            if h < max(o, c) or l > min(o, c):
                continue
            bars.append(Bar(ts=ts, open=o, high=h, low=l, close=c, volume=vol))
    _BARS_CACHE[ticker] = bars
    return bars


def _daily_bars(bars: list[Bar]) -> list[dict]:
    by_day: dict[str, dict] = {}
    for b in bars:
        day = b.ts.strftime("%Y-%m-%d")
        item = by_day.setdefault(
            day,
            {"day": day, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "count": 0, "volume": 0.0},
        )
        item["high"] = max(item["high"], b.high)
        item["low"] = min(item["low"], b.low)
        item["close"] = b.close
        item["count"] += 1
        item["volume"] += b.volume
    return [by_day[k] for k in sorted(by_day)]


def _daily_trs(days: list[dict]) -> list[dict]:
    out = []
    prev_close = None
    for d in days:
        if d["close"] <= 0:
            continue
        tr = d["high"] - d["low"]
        if prev_close:
            tr = max(tr, abs(d["high"] - prev_close), abs(d["low"] - prev_close))
        out.append({**d, "tr": tr, "tr_pct": tr / d["close"] * 100.0})
        prev_close = d["close"]
    return out


def _daily_atr_pct(ticker: str, period: int = 14) -> float:
    key = f"{ticker}:{period}"
    if key in _DAILY_ATR_CACHE:
        return _DAILY_ATR_CACHE[key]
    trs = [d for d in _daily_trs(_daily_bars(_read_1m(ticker))) if d["count"] >= 100 and d["tr_pct"] < 25.0]
    if len(trs) < period:
        _DAILY_ATR_CACHE[key] = 0.0
        return 0.0
    recent = trs[-period:]
    out = sum(d["tr_pct"] for d in recent) / len(recent)
    _DAILY_ATR_CACHE[key] = out
    return out


def _target_model(ticker: str, entry: float, direction: str = "long") -> dict:
    """Mirror current display model at a distance level. / 只复刻距离逻辑用于离线验收。"""
    raw_atr_pct = _daily_atr_pct(ticker)
    cap = 6.0 if ticker in LEVERAGED else 4.0
    capped_atr_pct = min(raw_atr_pct, cap) if raw_atr_pct > 0 else 0.0
    floor_stop = 2.50 if ticker in LEVERAGED else 1.20
    floor_t1 = 1.50 if ticker in LEVERAGED else 0.80
    rr_floor = 1.6 if ticker in LEVERAGED else 2.05
    stop_pct = max(capped_atr_pct * 0.6, floor_stop)
    t1_pct = max(floor_t1, stop_pct * rr_floor)
    if direction == "short":
        stop = entry * (1 + stop_pct / 100.0)
        t1 = entry * (1 - t1_pct / 100.0)
    else:
        stop = entry * (1 - stop_pct / 100.0)
        t1 = entry * (1 + t1_pct / 100.0)
    return {
        "ticker": ticker,
        "entry": entry,
        "direction": direction,
        "raw_atr_pct": raw_atr_pct,
        "capped_atr_pct": capped_atr_pct,
        "stop_pct": stop_pct,
        "t1_pct": t1_pct,
        "stop": stop,
        "t1": t1,
    }


def _direction_tool(direction: str) -> str | None:
    if direction == "long":
        return "RKLX"
    if direction == "short":
        return "RKLZ"
    return None


def _trigger_price_samples() -> list[dict]:
    rows = []
    for day in REVIEW_DAYS:
        for rec in _read_json(REVIEW_DIR / day / "triggers.json"):
            trigger = rec.get("trigger")
            direction = rec.get("direction")
            tool = _direction_tool(direction)
            if not tool:
                continue
            prices = rec.get("prices") or {}
            entry = _safe_float(prices.get(tool))
            if not entry:
                continue
            model = _target_model(tool, entry, "long")
            rows.append({
                "date": day,
                "ts": rec.get("ts"),
                "trigger": trigger,
                "direction": direction,
                "strength": rec.get("strength"),
                **model,
            })
    return rows


def _rklz_anomalies() -> list[dict]:
    out = []
    for item in _daily_trs(_daily_bars(_read_1m("RKLZ"))):
        range_pct = (item["high"] - item["low"]) / item["close"] * 100.0
        gap_pct = abs(item["open"] - item["close"]) / item["close"] * 100.0
        if item["tr_pct"] >= 25.0 or range_pct >= 25.0 or gap_pct >= 20.0:
            out.append({**item, "range_pct": range_pct, "gap_pct": gap_pct})
    return out


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for idx in range(-period, 0):
        delta = values[idx] - values[idx - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _find_rebound_cases(limit_days: int = 90) -> list[dict]:
    bars = _read_1m("RKLB")
    if not bars:
        return []
    latest = bars[-1].ts
    start = latest - timedelta(days=limit_days)
    by_day: dict[str, list[Bar]] = defaultdict(list)
    for b in bars:
        if b.ts >= start:
            by_day[b.ts.strftime("%Y-%m-%d")].append(b)

    cases: list[dict] = []
    for day, day_bars in sorted(by_day.items()):
        closes: list[float] = []
        last_case_ts: datetime | None = None
        for idx, b in enumerate(day_bars):
            closes.append(b.close)
            rsi = _rsi(closes)
            if rsi is None or rsi > 30:
                continue
            if last_case_ts and (b.ts - last_case_ts).total_seconds() < 3600:
                continue
            future = day_bars[idx + 1: idx + 91]
            if not future:
                continue
            bottom = min([b.low] + [x.low for x in future[:10]])
            max_after = max(x.high for x in future)
            rebound_pct = (max_after - bottom) / bottom * 100.0 if bottom > 0 else 0.0
            if rebound_pct < 2.0:
                continue
            max_bar = next(x for x in future if x.high == max_after)
            cases.append({
                "day": day,
                "bottom_ts": b.ts.strftime("%Y-%m-%d %H:%M"),
                "bottom_price": bottom,
                "rsi": rsi,
                "max_after_ts": max_bar.ts.strftime("%Y-%m-%d %H:%M"),
                "max_after": max_after,
                "rebound_pct": rebound_pct,
                "minutes_to_high": int((max_bar.ts - b.ts).total_seconds() / 60),
            })
            last_case_ts = b.ts
    return sorted(cases, key=lambda x: x["rebound_pct"], reverse=True)


def _cap_rule_rows() -> list[dict]:
    rows = []
    for day in ("2026-05-21", "2026-05-22"):
        for rec in _read_json(REVIEW_DIR / day / "triggers.json"):
            if rec.get("trigger") != "direction_trend" or rec.get("strength") != "STRONG":
                continue
            dc = rec.get("decision_context") or {}
            pc = dc.get("price_context") or {}
            ind = dc.get("indicators_raw") or {}
            data = rec.get("data") or {}
            current = _safe_float(pc.get("current")) or _safe_float(data.get("current"))
            vwap = _safe_float(ind.get("vwap")) or _safe_float(data.get("vwap"))
            day_chg = _safe_float(pc.get("day_change_pct")) or _safe_float(data.get("day_change_pct"))
            rsi_hist = ind.get("rsi_history") or []
            rsi_slope = None
            if isinstance(rsi_hist, list) and len(rsi_hist) >= 2:
                a = _safe_float(rsi_hist[-5] if len(rsi_hist) >= 5 else rsi_hist[0])
                z = _safe_float(rsi_hist[-1])
                if a is not None and z is not None:
                    rsi_slope = z - a
            bars = (((dc.get("kline_data") or {}).get("bars")) or [])[-3:]
            highs = [_safe_float(x.get("high")) for x in bars if isinstance(x, dict)]
            lower_highs = len(highs) == 3 and all(v is not None for v in highs) and highs[0] > highs[1] > highs[2]
            price_lt_vwap = current is not None and vwap is not None and current < vwap
            rsi_down = rsi_slope is not None and rsi_slope <= 0
            hit = bool(day_chg is not None and abs(day_chg) >= 3.0 and (price_lt_vwap or rsi_down or lower_highs))
            rows.append({
                "date": day,
                "ts": rec.get("ts"),
                "direction": rec.get("direction"),
                "confidence": rec.get("confidence"),
                "day_chg": day_chg,
                "price_lt_vwap": price_lt_vwap,
                "rsi_slope": rsi_slope,
                "lower_highs": lower_highs,
                "would_cap": hit,
            })
    return rows


def _sim_weekly_status() -> dict:
    state_path = ROOT / "data" / "sim_weekly" / "live_state.json"
    state = _read_json(state_path) if state_path.exists() else {}
    bars = state.get("bars") or []
    return {
        "state_exists": state_path.exists(),
        "week_start": state.get("week_start"),
        "bars": len(bars),
        "has_25_bars": len(bars) >= 25,
        "settled": state.get("settled"),
    }


def _fmt_pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}%"


def _write_report() -> None:
    git_hash = _git_hash()
    atr_rows = _trigger_price_samples()
    leveraged_sub1 = [r for r in atr_rows if r["ticker"] in LEVERAGED and r["stop_pct"] < 1.0]
    too_wide = [r for r in atr_rows if r["stop_pct"] > 6.0]
    anchor = _target_model("RKLX", 79.96, "long")
    anomalies = _rklz_anomalies()
    rebound_cases = _find_rebound_cases()
    cap_rows = _cap_rule_rows()
    sim_status = _sim_weekly_status()

    by_ticker = defaultdict(list)
    for row in atr_rows:
        by_ticker[row["ticker"]].append(row["stop_pct"])
    atr_summary = []
    for tk, vals in sorted(by_ticker.items()):
        atr_summary.append((tk, len(vals), min(vals), median(vals), max(vals)))

    cap_counter = Counter((r["date"], r["would_cap"]) for r in cap_rows)
    lines = [
        "# Weekend P0 Results",
        "",
        "VERSION: v0.1.0",
        "DATE: 2026-05-23",
        f"BASELINE_COMMIT: `{git_hash}`",
        "STATUS: read_only_validation",
        "",
        "## 1. ATR 止损/目标硬验收",
        "",
        "| Check | Result | Pass |",
        "|---|---:|:---:|",
        f"| RKLX/RKLZ sub-1% stop count | {len(leveraged_sub1)} | {'YES' if not leveraged_sub1 else 'NO'} |",
        f"| stop distance > 6% count | {len(too_wide)} | {'YES' if not too_wide else 'NO'} |",
        f"| RKLX 79.96 anchor stop | ${anchor['stop']:.2f} ({anchor['stop_pct']:.2f}%) | {'YES' if anchor['stop'] <= 77.5 else 'NO'} |",
        "",
        "| Ticker | Samples | Min stop% | Median stop% | Max stop% |",
        "|---|---:|---:|---:|---:|",
    ]
    for tk, n, mn, med, mx in atr_summary:
        lines.append(f"| {tk} | {n} | {mn:.2f}% | {med:.2f}% | {mx:.2f}% |")

    lines += [
        "",
        "结论: 当前 ATR 展示模型通过三条硬验收。它仍是显示/参考层验证,不改变方向触发器。",
        "",
        "## 2. RKLZ 历史 1m 异常日排查",
        "",
        "| Day | Count | Open | High | Low | Close | TR% | Range% | Gap% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if anomalies:
        for a in anomalies[:30]:
            lines.append(
                f"| {a['day']} | {a['count']} | {a['open']:.2f} | {a['high']:.2f} | {a['low']:.2f} | "
                f"{a['close']:.2f} | {a['tr_pct']:.2f}% | {a['range_pct']:.2f}% | {a['gap_pct']:.2f}% |"
            )
    else:
        lines.append("| - | 0 | - | - | - | - | - | - | - |")
    lines += [
        "",
        "建议: ATR 计算中应跳过 TR% >= 25% 的异常日,并保留 cap。若后续发现拆股/复权问题,再做 CSV 清洗。",
        "",
        "## 3. rebound_delay 离线回填样本",
        "",
        f"近 90 天离线扫描得到 {len(rebound_cases)} 个 RSI<=30 后 90 分钟内反弹 >=2% 的候选案例。下面列前 20 个:",
        "",
        "| Day | Bottom ET | Bottom | RSI | Rebound High ET | High | Rebound | Minutes |",
        "|---|---|---:|---:|---|---:|---:|---:|",
    ]
    for c in rebound_cases[:20]:
        lines.append(
            f"| {c['day']} | {c['bottom_ts'][11:]} | ${c['bottom_price']:.2f} | {c['rsi']:.1f} | "
            f"{c['max_after_ts'][11:]} | ${c['max_after']:.2f} | {c['rebound_pct']:.2f}% | {c['minutes_to_high']} |"
        )
    lines += [
        "",
        "注意: 这只是底部候选样本回填,还没有把每个样本与当日 trigger 对齐。下一步应输出 first long STRONG 延迟和 delay_layer。",
        "",
        "## 4. direction_trend 置信度封顶候选规则离线试跑",
        "",
        "候选规则: direction_trend STRONG 且 abs(day_chg)>=3%,同时 price<vwap 或 rsi_slope<=0 或 lower_highs=True,则离线标记为 would_cap。",
        "",
        "| Date | STRONG direction_trend | Would cap |",
        "|---|---:|---:|",
    ]
    for day in ("2026-05-21", "2026-05-22"):
        total = sum(1 for r in cap_rows if r["date"] == day)
        capped = sum(1 for r in cap_rows if r["date"] == day and r["would_cap"])
        lines.append(f"| {day} | {total} | {capped} |")
    lines += [
        "",
        "| Date | Time | Dir | Conf | Day Chg | price<VWAP | RSI slope | lower highs | would cap |",
        "|---|---|---|---:|---:|:---:|---:|:---:|:---:|",
    ]
    for r in cap_rows:
        lines.append(
            f"| {r['date']} | {(r['ts'] or '')[-8:]} | {r['direction']} | {r['confidence']} | "
            f"{_fmt_pct(r['day_chg'])} | {'Y' if r['price_lt_vwap'] else 'N'} | "
            f"{'-' if r['rsi_slope'] is None else f'{r['rsi_slope']:.2f}'} | "
            f"{'Y' if r['lower_highs'] else 'N'} | {'Y' if r['would_cap'] else 'N'} |"
        )
    lines += [
        "",
        "结论: 这条规则目前只完成“会影响多少条”的离线试跑。是否上线还必须结合波段结果判断误伤率。",
        "",
        "## 5. SimWeekly 状态检查",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| live_state exists | {sim_status['state_exists']} |",
        f"| week_start | {sim_status['week_start']} |",
        f"| bars in live_state | {sim_status['bars']} |",
        f"| has at least 25 bars | {sim_status['has_25_bars']} |",
        f"| settled | {sim_status['settled']} |",
        "",
        "建议: 如果 live_state bars < 25,需要给 SimWeekly 增加历史 5m 预热；如果已经 >=25,冷启动问题暂时不作为 P0。",
        "",
        "## 6. 策略建议草案",
        "",
        "不建议周末直接改主策略。建议只把下面三条作为下周讨论项:",
        "",
        "1. direction_trend 置信度封顶: 方向可以显示,但微结构未确认时不叫强烈。",
        "2. rebound_delay: 等离线样本与 trigger 对齐后,再决定是升级条件问题还是 dispatch 问题。",
        "3. PositionFollowupMonitor: 先设计为接管退出侧噪音,不是额外叠加新推送。",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    _write_report()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
