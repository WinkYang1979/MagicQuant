"""
MagicQuant SimWeekly duel live runner.
VERSION: v0.2.0
DEPENDS: data/shared/market_snapshot.json, core/sim_weekly/duel.py,
         core/sim_weekly/contestants.py, core/sim_weekly/openai_contestant.py

Run ClaudeRuleContestant and OpenAIContestant through the same Contestant
interface used by the offline duel harness.
用离线公平擂台相同的 Contestant 接口跑实时纸面 PK，消除 decider/engine 漂移。
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "shared" / "market_snapshot.json"
SIM_DIR = ROOT / "data" / "sim_weekly"
TICKERS = ("RKLB", "RKLX", "RKLZ")
CAPITAL = 10000.0
RTH_START = (9, 30)
RTH_END = (16, 0)
ALL_HOURS_WEEKDAY_END = (20, 0)
ENTRY_CUTOFF = (15, 30)
ET = ZoneInfo("America/New_York")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from core.sim_weekly.contestants import ClaudeRuleContestant
import core.sim_weekly.contestants as contestants_mod
from core.sim_weekly.duel import BarContext, Contestant, _max_drawdown
from core.sim_weekly.openai_contestant import OpenAIContestant
import core.sim_weekly.openai_contestant as openai_contestant_mod
from core.sim_weekly.portfolio import SimPortfolio
from core.sim_weekly.tg_format import (
    TradeAlertThrottle,
    fmt_daily,
    fmt_trade,
    fmt_trade_summary,
    send_private,
)


CONTESTANTS: dict[str, Callable[[], Contestant]] = {
    "claude_rule": lambda: ClaudeRuleContestant(SIM_DIR / "claude_adaptive_config.json"),
    "openai_v1": lambda: OpenAIContestant(SIM_DIR / "openai_adaptive_config.json"),
}


def _et_now() -> datetime:
    return datetime.now(ET)


def _is_rth(et: datetime) -> bool:
    return et.weekday() < 5 and RTH_START <= (et.hour, et.minute) < RTH_END


def _is_trade_window(et: datetime, trade_hours: str) -> bool:
    if trade_hours == "all":
        return et.weekday() < 5
    return _is_rth(et)


def _is_settle_time(et: datetime, trade_hours: str) -> bool:
    if et.weekday() > 4:
        return True
    if et.weekday() != 4:
        return False
    cutoff = ALL_HOURS_WEEKDAY_END if trade_hours == "all" else RTH_END
    return (et.hour, et.minute) >= cutoff


def _apply_trade_hours(trade_hours: str) -> None:
    if trade_hours != "all":
        return
    # Paper duel only: allow both contestants to open new positions outside RTH.
    # 仅纸面 PK: 放开双方选手 RTH 后的新开仓限制，不影响 core/focus 实盘策略。
    contestants_mod.ENTRY_CUTOFF = dt_time(23, 59)
    openai_contestant_mod.ENTRY_CUTOFF = dt_time(23, 59)


def _trade_session(ts: str) -> str:
    try:
        et = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return "unknown"
    return "rth" if _is_rth(et) else "non_rth"


def _empty_session_stats() -> dict:
    return {
        "entries": 0,
        "exits": 0,
        "wins": 0,
        "losses": 0,
        "realized_pnl": 0.0,
        "win_rate_pct": None,
    }


def _session_stats(trades: list[dict]) -> dict:
    # Split paper duel builds by RTH/non-RTH; historical trades are inferred by ts.
    # 将纸面 PK 建仓按 RTH/非 RTH 拆开统计；旧成交没有 session 时按时间反推。
    stats = {name: _empty_session_stats() for name in ("rth", "non_rth", "unknown")}
    for trade in trades:
        side = trade.get("side")
        if side not in ("buy", "sell"):
            continue
        session = trade.get("session") or _trade_session(str(trade.get("ts") or ""))
        if session not in stats:
            session = "unknown"
        if side == "buy":
            stats[session]["entries"] += 1
            continue
        pnl = float(trade.get("pnl") or 0.0)
        stats[session]["exits"] += 1
        stats[session]["realized_pnl"] += pnl
        if pnl > 0:
            stats[session]["wins"] += 1
        else:
            stats[session]["losses"] += 1
    for item in stats.values():
        item["realized_pnl"] = round(item["realized_pnl"], 2)
        exits = item["exits"]
        if exits:
            item["win_rate_pct"] = round(item["wins"] / exits * 100, 1)
    return stats


def _monday_str(et: datetime) -> str:
    return (et - timedelta(days=et.weekday())).strftime("%Y-%m-%d")


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _state_path(name: str) -> Path:
    return SIM_DIR / f"live_duel_{name}.json"


def _ledger_path(day: str) -> Path:
    return SIM_DIR / f"duel_ledger_{day}.json"


def _read_snapshot() -> tuple[dict[str, float], dict[str, float]]:
    payload = _read_json(SNAPSHOT, {})
    quotes = payload.get("quotes") if isinstance(payload, dict) else {}
    prices: dict[str, float] = {}
    volumes: dict[str, float] = {}
    for ticker in TICKERS:
        item = (quotes or {}).get(ticker) or (quotes or {}).get(f"US.{ticker}") or {}
        price = item.get("price") or item.get("last")
        volume = item.get("volume")
        try:
            if price:
                prices[ticker] = float(price)
        except Exception:
            pass
        try:
            if volume is not None:
                volumes[ticker] = float(volume)
        except Exception:
            pass
    return prices, volumes


def _new_bar(ts: str, price: float, volume: float = 0.0) -> dict:
    return {"time": ts, "open": price, "high": price, "low": price, "close": price, "volume": volume}


def _update_bar(bar: dict, price: float, volume_delta: float) -> None:
    bar["high"] = max(float(bar["high"]), price)
    bar["low"] = min(float(bar["low"]), price)
    bar["close"] = price
    bar["volume"] = float(bar.get("volume", 0.0) or 0.0) + max(0.0, volume_delta)


def _portfolio_to_dict(pf: SimPortfolio, prices: dict[str, float]) -> dict:
    return {
        "cash": pf.cash,
        "positions": pf.positions,
        "trades": pf.trades,
        "total_fees": pf.total_fees,
        "equity": pf.equity(prices),
        "equity_curve": pf.equity_curve,
    }


def _portfolio_from_dict(payload: dict) -> SimPortfolio:
    pf = SimPortfolio(initial_capital=CAPITAL)
    pf.cash = float(payload.get("cash") or CAPITAL)
    pf.positions = payload.get("positions") or {}
    pf.trades = payload.get("trades") or []
    pf.total_fees = float(payload.get("total_fees") or 0.0)
    pf.equity_curve = [tuple(row) for row in (payload.get("equity_curve") or [])]
    return pf


def _score_live(name: str, state: dict, pf: SimPortfolio, prices: dict[str, float]) -> dict:
    sells = [t for t in pf.trades if t.get("side") == "sell"]
    wins = [t for t in sells if float(t.get("pnl") or 0.0) > 0]
    final_equity = pf.equity(prices)
    gross_win = sum(float(t.get("pnl") or 0.0) for t in wins)
    gross_loss = sum(float(t.get("pnl") or 0.0) for t in sells if float(t.get("pnl") or 0.0) <= 0)
    benchmark = None
    week_open = state.get("week_open_rklb")
    if week_open and prices.get("RKLB"):
        benchmark = round((prices["RKLB"] - float(week_open)) / float(week_open) * 100, 2)
    return {
        "contestant": name,
        "week_start": state.get("week_start"),
        "final_equity": final_equity,
        "return_pct": round((final_equity - CAPITAL) / CAPITAL * 100, 2),
        "n_trades": len([t for t in pf.trades if t.get("side") == "buy"]),
        "n_round_trips": len(sells),
        "win_rate_pct": round(len(wins) / len(sells) * 100, 1) if sells else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(gross_loss / max(1, len(sells) - len(wins)), 2),
        "profit_factor": round(gross_win / abs(gross_loss), 3) if gross_loss < 0 else None,
        "max_drawdown_pct": _max_drawdown(pf.equity_curve),
        "total_fees": round(pf.total_fees, 2),
        "benchmark_buyhold_RKLB_pct": benchmark,
        "session_stats": _session_stats(pf.trades),
        "errors": len([t for t in pf.trades if t.get("side") == "error"]),
        "trades": pf.trades,
    }


class LiveAccount:
    def __init__(self, name: str, contestant: Contestant, trade_alerts: bool = True):
        self.name = name
        self.contestant = contestant
        self.state: dict = {}
        self.portfolio = SimPortfolio(initial_capital=CAPITAL)
        self.loaded_week: str | None = None
        self.trade_alerts = trade_alerts
        self.alert_throttle = TradeAlertThrottle()

    def load_or_reset(self, week: str, prices: dict[str, float]) -> None:
        if self.loaded_week == week:
            return
        state = _read_json(_state_path(self.name), {})
        stale_schema = "history" not in state or not isinstance(state.get("cur5"), dict)
        if state.get("week_start") != week or stale_schema:
            state = {
                "name": self.name,
                "week_start": week,
                "settled": False,
                "history": {tk: [] for tk in TICKERS},
                "cur5": {},
                "last_volume": {},
                "week_open_rklb": prices.get("RKLB"),
                "last_closed_ts": None,
                "portfolio": {},
            }
            self.portfolio = SimPortfolio(initial_capital=CAPITAL)
            self.contestant.reset(CAPITAL)
            print(f"[duel:{self.name}] new week {week}")
        else:
            self.portfolio = _portfolio_from_dict(state.get("portfolio") or {})
            self.contestant.reset(CAPITAL)
        self.state = state
        self.loaded_week = week

    def save(self, prices: dict[str, float]) -> None:
        self.state["portfolio"] = _portfolio_to_dict(self.portfolio, prices)
        _write_json(_state_path(self.name), self.state)

    def settle(self, prices: dict[str, float], ts: str, reason: str) -> None:
        if self.state.get("settled"):
            return
        before = len(self.portfolio.trades)
        self.portfolio.flatten(prices, ts, reason=reason)
        for trade in self.portfolio.trades[before:]:
            trade.setdefault("session", _trade_session(str(trade.get("ts") or ts)))
        if len(self.portfolio.trades) > before:
            print(f"[duel:{self.name}] flattened {len(self.portfolio.trades) - before} trade(s)")
        self.portfolio.mark(ts, prices)
        self.state["settled"] = True
        self.save(prices)

    def close_bar(self, bars_now: dict[str, dict], ts: str, prices: dict[str, float]) -> None:
        if "RKLB" not in bars_now:
            return
        history = self.state.setdefault("history", {tk: [] for tk in TICKERS})
        ctx = BarContext(
            datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"),
            ts,
            bars_now,
            history,
            self.portfolio,
            is_last_bar=False,
        )
        before = len(self.portfolio.trades)
        old_trades = list(self.portfolio.trades)
        try:
            self.contestant.on_bar(ctx)
        except Exception as exc:
            self.portfolio.trades.append({
                "ts": ts,
                "side": "error",
                "ticker": "",
                "qty": 0,
                "price": 0,
                "fee": 0,
                "session": _trade_session(ts),
                "reason": f"contestant error: {exc}",
            })
        for ticker, bar in bars_now.items():
            history.setdefault(ticker, []).append(bar)
            history[ticker] = history[ticker][-500:]
        self.portfolio.mark(ts, prices)
        self.state["last_closed_ts"] = ts
        if len(self.portfolio.trades) > before:
            for trade in self.portfolio.trades[before:]:
                trade.setdefault("session", _trade_session(str(trade.get("ts") or ts)))
                print(f"[duel:{self.name}] {trade.get('side','?').upper()} {trade.get('ticker','')} "
                      f"x{trade.get('qty')} @ {trade.get('price')} {trade.get('reason','')}")
                if self.trade_alerts and trade.get("side") in ("buy", "sell"):
                    self._send_trade_alert(trade, old_trades)

    def _send_trade_alert(self, trade: dict, old_trades: list[dict]) -> None:
        mode, trades = self.alert_throttle.record(self.name, trade)
        if mode == "summary":
            send_private(fmt_trade_summary(self.name, trades))
            return
        entry = _find_entry_for_sell(old_trades, trade) if trade.get("side") == "sell" else None
        send_private(fmt_trade(self.name, trade, entry_trade=entry))


def _find_entry_for_sell(old_trades: list[dict], sell_trade: dict) -> dict | None:
    ticker = sell_trade.get("ticker")
    open_lots: list[dict] = []
    for trade in old_trades:
        if trade.get("ticker") != ticker:
            continue
        if trade.get("side") == "buy":
            open_lots.append(trade)
        elif trade.get("side") == "sell" and open_lots:
            open_lots.pop(0)
    return open_lots[0] if open_lots else None


def _bucket_start(et: datetime) -> str:
    return et.replace(minute=(et.minute // 5) * 5, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _step_account(account: LiveAccount, now: datetime, prices: dict[str, float], volumes: dict[str, float],
                  trade_hours: str = "rth") -> None:
    week = _monday_str(now)
    account.load_or_reset(week, prices)
    state = account.state
    if not state.get("week_open_rklb") and prices.get("RKLB"):
        state["week_open_rklb"] = prices["RKLB"]

    if _is_settle_time(now, trade_hours) and prices:
        settle_reason = f"friday {trade_hours} settle" if now.weekday() == 4 else f"weekend {trade_hours} settle"
        account.settle(prices, now.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
                       reason=settle_reason)
        account.save(prices)
        return

    if not _is_trade_window(now, trade_hours):
        account.save(prices)
        return

    if not prices.get("RKLB"):
        account.save(prices)
        return

    bucket = _bucket_start(now)
    cur5 = state.setdefault("cur5", {})
    last_volume = state.setdefault("last_volume", {})

    closed_bars = {}
    for ticker in TICKERS:
        price = prices.get(ticker)
        if not price:
            continue
        volume = float(volumes.get(ticker, 0.0) or 0.0)
        prev_volume = float(last_volume.get(ticker, volume) or 0.0)
        volume_delta = max(0.0, volume - prev_volume)
        last_volume[ticker] = volume
        bar = cur5.get(ticker)
        if bar and bar.get("time") != bucket:
            closed_bars[ticker] = bar
            cur5[ticker] = _new_bar(bucket, price, volume_delta)
        elif not bar:
            cur5[ticker] = _new_bar(bucket, price, volume_delta)
        else:
            _update_bar(bar, price, volume_delta)

    if closed_bars:
        closed_ts = next(iter(closed_bars.values()))["time"]
        # Contestants follow the charter cutoff; runner also avoids late new bars.
        # 选手遵守章程截止时间；runner 仍允许它们管理已有仓位。
        if datetime.strptime(closed_ts, "%Y-%m-%d %H:%M:%S").time() <= datetime.strptime("15:55", "%H:%M").time():
            account.close_bar(closed_bars, closed_ts, prices)
    account.save(prices)


def _write_ledger(accounts: list[LiveAccount], prices: dict[str, float], day: str) -> Path:
    payload = {
        "schema_version": "duel-ledger-v1",
        "date": day,
        "updated_at": _et_now().strftime("%Y-%m-%d %H:%M:%S"),
        "contestants": {
            account.name: _score_live(account.name, account.state, account.portfolio, prices)
            for account in accounts
        },
    }
    path = _ledger_path(day)
    _write_json(path, payload)
    return path


def _maybe_send_daily_report(now: datetime, ledger_path: Path, enabled: bool) -> None:
    if not enabled or now.weekday() >= 5 or (now.hour, now.minute) < (16, 10):
        return
    marker_path = SIM_DIR / "duel_daily_report_sent.json"
    marker = _read_json(marker_path, {})
    day = ledger_path.stem.replace("duel_ledger_", "")
    if marker.get("last_sent_date") == day:
        return
    ledger = _read_json(ledger_path, {})
    scores = ledger.get("contestants") or {}
    if not scores:
        return
    text = fmt_daily(day, scores)
    if send_private(text):
        _write_json(marker_path, {"last_sent_date": day, "sent_at": now.strftime("%Y-%m-%d %H:%M:%S")})


def _maybe_run_openai_nightly(now: datetime, ledger_path: Path) -> None:
    if now.weekday() >= 5 or (now.hour, now.minute) < (16, 15):
        return
    marker_path = SIM_DIR / "openai_nightly_review_sent.json"
    marker = _read_json(marker_path, {})
    day = ledger_path.stem.replace("duel_ledger_", "")
    if marker.get("last_review_date") == day:
        return
    try:
        from scripts.sim_weekly_openai_nightly_review import run_review, _telegram_text

        result = run_review(day, apply=True)
        if result.get("ok"):
            send_private(_telegram_text(result))
            _write_json(marker_path, {"last_review_date": day, "reviewed_at": now.strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as exc:
        print(f"[duel] openai nightly review skipped: {exc}")


def _maybe_run_claude_nightly(now: datetime, ledger_path: Path) -> None:
    if now.weekday() >= 5 or (now.hour, now.minute) < (16, 15):
        return
    marker_path = SIM_DIR / "claude_nightly_review_sent.json"
    marker = _read_json(marker_path, {})
    day = ledger_path.stem.replace("duel_ledger_", "")
    if marker.get("last_review_date") == day:
        return
    try:
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "sim_weekly_claude_nightly_review.py"),
            "--date",
            day,
            "--telegram",
        ]
        completed = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=120)
        if completed.returncode == 0:
            _write_json(marker_path, {"last_review_date": day, "reviewed_at": now.strftime("%Y-%m-%d %H:%M:%S")})
        else:
            print(f"[duel] claude nightly review failed: {completed.stderr[-500:] or completed.stdout[-500:]}")
    except Exception as exc:
        print(f"[duel] claude nightly review skipped: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SimWeekly fair duel live paper accounts.")
    parser.add_argument("--poll", type=int, default=30, help="Poll interval seconds.")
    parser.add_argument("--trade-hours", choices=("rth", "all"), default="rth",
                        help="Paper duel trading window: rth or all weekday hours.")
    parser.add_argument("--once", action="store_true", help="Run one step and exit.")
    parser.add_argument("--no-daily-report", action="store_true", help="Disable post-close Telegram daily report.")
    parser.add_argument("--no-trade-alert", action="store_true", help="Disable live paper trade Telegram alerts.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _apply_trade_hours(args.trade_hours)
    accounts = [LiveAccount(name, factory(), trade_alerts=not args.no_trade_alert) for name, factory in CONTESTANTS.items()]
    print(f"SimWeekly fair duel runner started poll={args.poll}s trade_hours={args.trade_hours} contestants={','.join(CONTESTANTS)}")
    if args.trade_hours == "all":
        print("Waiting for focus market_snapshot.json; paper duel trades on fresh weekday 5m bars, including pre/post/overnight.")
    else:
        print("Waiting for focus market_snapshot.json; no live paper trades occur until fresh RTH 5m bars close.")
    print("Trade alert throttle is in-memory; restarting this runner clears the 5-minute merge window.")
    while True:
        try:
            now = _et_now()
            prices, volumes = _read_snapshot()
            for account in accounts:
                _step_account(account, now, prices, volumes, trade_hours=args.trade_hours)
            ledger = _write_ledger(accounts, prices, now.strftime("%Y-%m-%d"))
            _maybe_send_daily_report(now, ledger, enabled=not args.no_daily_report)
            _maybe_run_claude_nightly(now, ledger)
            _maybe_run_openai_nightly(now, ledger)
        except Exception as exc:
            print(f"[duel] step error: {exc}")
        if args.once:
            return 0
        time.sleep(max(5, args.poll))


if __name__ == "__main__":
    raise SystemExit(main())
