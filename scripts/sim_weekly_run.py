"""SimWeekly 实时 runner —— 独立进程,纯纸面。读 focus 共享快照,自管周度组合。

周期: 周一 RTH 开盘 reset $10k → 周中可隔夜 → 周五 16:00 ET 收盘结算出记分卡。
只在 RTH(09:30-16:00 ET, 周一~周五)交易; 盘外只待命。
不改 bot_controller / 不下真单 / 不碰主策略 / 不建 Futu 连接(只读 snapshot JSON)。
启动:  python scripts/sim_weekly_run.py [--agent] [--poll 30]
"""
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.sim_weekly import strategy as strat
from core.sim_weekly.portfolio import SimPortfolio
from core.sim_weekly.deciders import RuleDecider, AgentCommitteeDecider
from core.sim_weekly.engine import (ENTRY_CONV, MAX_LOSS_PER_TRADE, RTH_START, RTH_END,
                                     _target_fraction, _held_direction)

SNAPSHOT = os.path.join("data", "shared", "market_snapshot.json")
STATE = os.path.join("data", "sim_weekly", "live_state.json")
TICKERS = ["RKLB", "RKLX", "RKLZ"]
CAPITAL = 10000.0


def _et_now():
    return datetime.now(ET) if ET else datetime.now()


def _is_rth(et):
    return et.weekday() < 5 and RTH_START <= (et.hour, et.minute) < RTH_END


def _monday_str(et):
    return (et - timedelta(days=et.weekday())).strftime("%Y-%m-%d")


def _read_snapshot():
    try:
        s = json.load(open(SNAPSHOT, encoding="utf-8"))
        quotes = s.get("quotes", {}) or {}
        prices = {}
        for tk in TICKERS:
            q = quotes.get(tk) or quotes.get("US." + tk) or {}
            p = q.get("price") or q.get("last")
            if p:
                prices[tk] = float(p)
        return prices
    except Exception:
        return {}


def _load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)


def _new_week_state(week_start, open_px):
    return {"week_start": week_start, "settled": False, "bars": [], "cur5": None,
            "week_open_rklb": open_px,
            "portfolio": {"cash": CAPITAL, "positions": {}, "trades": [], "total_fees": 0.0}}


def _pf_from(st):
    pf = SimPortfolio(initial_capital=CAPITAL)
    p = st["portfolio"]
    pf.cash, pf.positions, pf.trades = p["cash"], p["positions"], p["trades"]
    pf.total_fees = p.get("total_fees", 0.0)
    return pf


def _settle(st, prices):
    pf = _pf_from(st)
    pf.flatten(prices, _et_now().strftime("%Y-%m-%d %H:%M:%S"), reason="friday close settle")
    eq = pf.equity(prices)
    sells = [t for t in pf.trades if t["side"] == "sell"]
    wins = [t for t in sells if t.get("pnl", 0) > 0]
    bh = None
    if st.get("week_open_rklb") and prices.get("RKLB"):
        bh = round((prices["RKLB"] - st["week_open_rklb"]) / st["week_open_rklb"] * 100, 2)
    sc = {"week_start": st["week_start"], "final_equity": eq,
          "return_pct": round((eq - CAPITAL) / CAPITAL * 100, 2),
          "n_trades": len([t for t in pf.trades if t["side"] == "buy"]),
          "win_rate_pct": round(len(wins) / len(sells) * 100, 1) if sells else None,
          "total_fees": round(pf.total_fees, 2), "realized_pnl": pf.realized_pnl(),
          "benchmark_buyhold_RKLB_pct": bh, "trades": pf.trades}
    os.makedirs("data/sim_weekly", exist_ok=True)
    json.dump(sc, open(f"data/sim_weekly/week_{st['week_start']}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    print(f"  [sim_run] 📒 周结算 {st['week_start']}: 周收益 {sc['return_pct']:+.2f}% "
          f"(躺平RKLB {bh}%)  权益 ${eq:.2f}  交易 {sc['n_trades']} 笔")
    st["portfolio"] = {"cash": pf.cash, "positions": pf.positions, "trades": pf.trades,
                       "total_fees": pf.total_fees}


def step(decider):
    et = _et_now()
    prices = _read_snapshot()
    st = _load_state()
    wk = _monday_str(et)

    # 新的一周 -> 归档/重置
    if st.get("week_start") != wk:
        if st.get("week_start") and not st.get("settled") and prices:
            _settle(st, prices); _save_state(st)
        st = _new_week_state(wk, prices.get("RKLB"))
        print(f"  [sim_run] 🔄 新周重置 {wk}  纸面 ${CAPITAL:.0f}")
        _save_state(st)

    if not _is_rth(et):
        # 周五收盘后结算一次
        if et.weekday() == 4 and (et.hour, et.minute) >= RTH_END and not st.get("settled") and prices:
            _settle(st, prices); st["settled"] = True; _save_state(st)
        return

    if not prices.get("RKLB"):
        return
    if st.get("week_open_rklb") is None:
        st["week_open_rklb"] = prices["RKLB"]

    pf = _pf_from(st)
    ts = et.strftime("%Y-%m-%d %H:%M:%S")

    # 跟踪止损
    for tk in list(pf.positions.keys()):
        pos, px = pf.positions[tk], prices.get(tk)
        if not px:
            continue
        pos["peak"] = max(pos.get("peak", pos["cost_price"]), px)
        trail = round(pos["peak"] * (1 - pos.get("stop_pct", strat.STOP_PCT.get(tk, 0.04))), 4)
        pos["stop"] = trail if pos.get("stop") is None else max(pos["stop"], trail)
        if px <= pos["stop"]:
            pf.sell(tk, pos["qty"], pos["stop"], ts, reason="trail/stop hit")

    # 5m bar 聚合 + 收线决策
    bucket = et.replace(minute=(et.minute // 5) * 5, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    cur5, p = st.get("cur5"), prices["RKLB"]
    if not cur5 or cur5["time"] != bucket:
        if cur5:
            st["bars"].append(cur5); st["bars"] = st["bars"][-200:]
            today = [b for b in st["bars"] if b["time"][:10] == bucket[:10]]
            _apply_target(pf, decider.decide({"rklb_bars": st["bars"], "rklb_today_bars": today}), prices, ts)
        cur5 = {"time": bucket, "open": p, "high": p, "low": p, "close": p, "volume": 0}
    else:
        cur5["high"], cur5["low"], cur5["close"] = max(cur5["high"], p), min(cur5["low"], p), p
    st["cur5"] = cur5

    st["portfolio"] = {"cash": pf.cash, "positions": pf.positions, "trades": pf.trades,
                       "total_fees": pf.total_fees, "equity": pf.equity(prices)}
    _save_state(st)
    print(f"  [sim_run] {ts} ET eq=${pf.equity(prices):.2f} pos={list(pf.positions)}")


def _apply_target(pf, target, prices, ts):
    tdir = target.get("direction", "flat")
    held = _held_direction(pf)
    equity = pf.equity(prices)
    if held and tdir != "flat" and tdir != held:
        tk = next(iter(pf.positions))
        pf.sell(tk, pf.positions[tk]["qty"], prices.get(tk) or pf.positions[tk]["cost_price"], ts, "flip exit")
        held = None
    if held is None and tdir in ("long", "short") and target["conviction"] >= ENTRY_CONV:
        inst = target["instrument"]
        if inst and prices.get(inst):
            entry, stop_pct = prices[inst], target["stop_pct"] or 0.04
            frac = _target_fraction(target["conviction"])
            if frac > 0:
                qty = min(int(equity * frac / entry), int(equity * MAX_LOSS_PER_TRADE / (entry * stop_pct)))
                if qty > 0:
                    pf.buy(inst, qty, entry, ts, f"conv{target['conviction']} {target['reason']}",
                           stop=round(entry * (1 - stop_pct), 4))
                    if inst in pf.positions:
                        pf.positions[inst]["stop_pct"] = stop_pct


def main():
    use_agent = "--agent" in sys.argv
    poll = int(sys.argv[sys.argv.index("--poll") + 1]) if "--poll" in sys.argv else 30
    decider = AgentCommitteeDecider() if use_agent else RuleDecider()
    print(f"SimWeekly live runner 启动 · decider={decider.name} · poll={poll}s · 纯纸面 · 只读 snapshot")
    while True:
        try:
            step(decider)
        except Exception as e:
            print(f"  [sim_run] step error(已隔离,不影响主系统): {e}")
        time.sleep(poll)


if __name__ == "__main__":
    main()
