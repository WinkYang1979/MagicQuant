"""
MagicQuant 慧投 - Signal Engine v0.1.0
Dare to dream. Data to win.

Run: python core\signal_engine.py --once
"""

import argparse, json, os, sys, time
from datetime import datetime
import pandas as pd
import numpy as np

# ── Config ────────────────────────────────────────────────────────
HOST         = "127.0.0.1"
PORT         = 11111
ACCOUNT_SIZE = 20000
KL_NUM       = 90
SIGNALS_FILE = r"C:\MagicQuant\data\signals_latest.json"
WATCHLIST    = r"C:\MagicQuant\config\watchlist.json"

TICKER_CONFIG = {
    "US.TSLA": {"name": "Tesla",         "style": "swing"},
    "US.SOXL": {"name": "SOXL 3x Semi",  "style": "daytrader"},
    "US.RKLB": {"name": "Rocket Lab",     "style": "daytrader"},
    "US.RKLX": {"name": "RocketLab CFD",  "style": "daytrader"},
}

try:
    from moomoo import (OpenQuoteContext, OpenSecTradeContext, SubType,
                        KLType, RET_OK, AuType, TrdMarket, TrdEnv, SecurityFirm)
except ImportError:
    from futu import (OpenQuoteContext, OpenSecTradeContext, SubType,
                      KLType, RET_OK, AuType, TrdMarket, TrdEnv, SecurityFirm)


def get_tickers(positions=None):
    """
    获取要分析的股票列表 = watchlist ∪ 持仓(v0.2.2)
    positions: dict ticker -> pos_info (from get_positions)
               为 None 时只用 watchlist
    """
    tickers = []
    if os.path.exists(WATCHLIST):
        try:
            wl = json.load(open(WATCHLIST, encoding="utf-8"))
            tickers = list(dict.fromkeys(wl.get("auto", []) + wl.get("manual", [])))
        except:
            pass
    if not tickers:
        tickers = list(TICKER_CONFIG.keys())

    # v0.2.2: 持仓里的票即使不在 watchlist 也要分析
    if positions:
        for pos_tk in positions.keys():
            if pos_tk not in tickers:
                tickers.append(pos_tk)
                print(f"  [auto-add] 持仓票 {pos_tk} 未在 watchlist,自动加入分析")
    return tickers


# ── Indicators ────────────────────────────────────────────────────

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return round(float((100 - 100/(1+rs)).iloc[-1]), 2)


def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig  = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return round(float(macd.iloc[-1]),4), round(float(sig.iloc[-1]),4), round(float(hist.iloc[-1]),4)


def calc_bollinger(close, period=20, std_dev=2):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    lc, lu, lm, ll = close.iloc[-1], upper.iloc[-1], mid.iloc[-1], lower.iloc[-1]
    pct_b = (lc - ll) / (lu - ll) if (lu - ll) != 0 else 0.5
    return round(float(lu),4), round(float(lm),4), round(float(ll),4), round(float(pct_b),4)


def calc_mas(close):
    return {f"ma{p}": round(float(close.rolling(p).mean().iloc[-1]),4)
            for p in [5, 10, 20, 60] if len(close) >= p}


def calc_atr(high, low, close, period=14):
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])


def calc_volume_ratio(volume, period=20):
    avg = volume.iloc[:-1].tail(period).mean()
    return round(float(volume.iloc[-1] / avg), 2) if avg > 0 else 1.0


def detect_candlestick(open_, high, low, close):
    patterns = []
    if len(close) < 2: return patterns
    o, h, l, c = float(open_.iloc[-1]), float(high.iloc[-1]), float(low.iloc[-1]), float(close.iloc[-1])
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    total = h - l
    if total == 0: return patterns
    if lower_wick > body*2 and upper_wick < body*0.5 and c > o:
        patterns.append(("锤子线", "bullish", "底部反转信号"))
    if upper_wick > body*2 and lower_wick < body*0.5 and c < o:
        patterns.append(("流星线", "bearish", "顶部反转信号"))
    if body < total*0.1:
        patterns.append(("十字星", "neutral", "方向犹豫，等待确认"))
    po, pc = float(open_.iloc[-2]), float(close.iloc[-2])
    if pc < po and c > o and c > po and o < pc:
        patterns.append(("看涨吞没", "bullish", "强力反转信号"))
    if pc > po and c < o and c < po and o > pc:
        patterns.append(("看跌吞没", "bearish", "强力下跌信号"))
    return patterns


def calc_stop_targets(price, signal, atr, style):
    sl_m = 1.0 if style == "daytrader" else 1.5
    t1_m = 1.5 if style == "daytrader" else 2.0
    t2_m = 2.5 if style == "daytrader" else 3.5
    if signal == "BUY":
        sl = round(price - atr*sl_m, 2); t1 = round(price + atr*t1_m, 2); t2 = round(price + atr*t2_m, 2)
    elif signal == "SELL":
        sl = round(price + atr*sl_m, 2); t1 = round(price - atr*t1_m, 2); t2 = round(price - atr*t2_m, 2)
    else:
        sl = round(price - atr*sl_m, 2); t1 = round(price + atr*t1_m, 2); t2 = round(price + atr*t2_m, 2)
    return {"stop_loss": sl, "target1": t1, "target2": t2, "risk_per_share": round(abs(price-sl), 2)}


def calc_position_size(price, stop_loss):
    rps = abs(price - stop_loss)
    if rps == 0: return 0
    shares = int(ACCOUNT_SIZE * 0.05 / rps)
    return max(0, min(shares, int(ACCOUNT_SIZE * 0.3 / price)))


def generate_signal(rsi, macd_hist, pct_b, vol_ratio, mas, patterns):
    score = 0; reasons = []
    if rsi < 35:   score += 2; reasons.append(f"RSI {rsi} 超卖，反弹机会")
    elif rsi < 50: score += 1; reasons.append(f"RSI {rsi} 偏弱")
    elif rsi > 70: score -= 2; reasons.append(f"RSI {rsi} 超买 ⚠️")
    elif rsi > 55: score += 1; reasons.append(f"RSI {rsi} 偏强，动能向上")

    if macd_hist > 0: score += 2; reasons.append("MACD 柱正值，多头动能")
    else:             score -= 2; reasons.append("MACD 柱负值，空头动能")

    if pct_b < 0.2:         score += 2; reasons.append(f"布林下轨支撑（%B={pct_b:.2f}）")
    elif pct_b > 0.8:       score -= 1; reasons.append(f"布林上轨压力（%B={pct_b:.2f}）")
    elif 0.4 < pct_b < 0.6: score += 1

    if "ma5" in mas and "ma20" in mas:
        if mas["ma5"] > mas["ma20"]: score += 1; reasons.append(f"MA5 > MA20，短线多头排列")
        else:                         score -= 1; reasons.append(f"MA5 < MA20，短线空头排列")
    if "ma20" in mas and "ma60" in mas:
        if mas["ma20"] > mas["ma60"]: score += 1; reasons.append("MA20 > MA60，中线趋势向上")
        else:                          score -= 1; reasons.append("MA20 < MA60，中线趋势向下")

    if vol_ratio > 1.5:   score += 1; reasons.append(f"放量 {vol_ratio}x")
    elif vol_ratio < 0.7: score -= 1; reasons.append(f"缩量 {vol_ratio}x，信号较弱")

    for name, sentiment, desc in patterns:
        if sentiment == "bullish":   score += 1; reasons.append(f"K线形态：{name} — {desc}")
        elif sentiment == "bearish": score -= 1; reasons.append(f"K线形态：{name} — {desc}")
        else:                                     reasons.append(f"K线形态：{name} — {desc}")

    signal = "BUY" if score >= 4 else "SELL" if score <= -3 else "HOLD"
    confidence = min(95, max(40, 50 + score * 7))
    urgency = 1
    if rsi > 72 or rsi < 28: urgency += 1
    if pct_b > 0.9 or pct_b < 0.1: urgency += 1
    if vol_ratio > 2.0: urgency += 1
    if signal in ("BUY","SELL"): urgency += 1
    return signal, confidence, reasons, min(5, urgency)


def get_positions():
    positions = {}
    account_info = {}
    try:
        trd_ctx = OpenSecTradeContext(
            host=HOST, port=PORT,
            filter_trdmarket=TrdMarket.US,
            security_firm=SecurityFirm.FUTUAU
        )
        ret, data = trd_ctx.position_list_query(trd_env=TrdEnv.REAL)
        if ret == RET_OK and len(data) > 0:
            for _, row in data.iterrows():
                code = row.get("code","")
                qty  = float(row.get("qty", 0))
                cost = float(row.get("cost_price", 0))
                pl   = float(row.get("pl_val", 0))
                positions[code] = {
                    "qty": qty,
                    "cost_price": round(cost, 2),
                    "pl_val": round(pl, 2),
                    "pl_pct": round(pl/(cost*qty)*100, 2) if cost*qty > 0 else 0
                }
        ret2, acc = trd_ctx.accinfo_query(trd_env=TrdEnv.REAL)
        if ret2 == RET_OK and len(acc) > 0:
            row = acc.iloc[0]
            account_info = {
                "cash": round(float(row.get("cash", 0)), 2),
                "total_assets": round(float(row.get("total_assets", 0)), 2),
                "market_val": round(float(row.get("market_val", 0)), 2),
            }
            print(f"  账户: 现金=${account_info['cash']:,.2f} 总资产=${account_info['total_assets']:,.2f}")
        trd_ctx.close()
    except Exception as e:
        print(f"  持仓查询: {e}")
    return positions, account_info


def fetch_and_analyze(quote_ctx, ticker, positions):
    result = {"ticker": ticker}
    cfg = TICKER_CONFIG.get(ticker, {"name": ticker, "style": "swing"})
    result["name"] = cfg["name"]
    result["style"] = cfg["style"]

    ret, snap = quote_ctx.get_market_snapshot([ticker])
    if ret != RET_OK:
        result["error"] = "Snapshot failed"; return result

    row = snap.iloc[0]
    price = float(row["last_price"])
    prev  = float(row["prev_close_price"])
    result.update({
        "price": price, "prev_close": prev,
        "change": round(price-prev, 4),
        "change_pct": round((price-prev)/prev*100, 2) if prev else 0,
        "volume": int(row["volume"]),
        "update_time": str(row["update_time"]),
    })

    quote_ctx.subscribe([ticker], [SubType.K_DAY], subscribe_push=False)
    ret_kl, kl = quote_ctx.get_cur_kline(ticker, KL_NUM, KLType.K_DAY, AuType.QFQ)
    if ret_kl != RET_OK or len(kl) < 30:
        result["error"] = "K-line data insufficient"; return result

    close  = kl["close"].astype(float)
    open_  = kl["open"].astype(float)
    high   = kl["high"].astype(float)
    low    = kl["low"].astype(float)
    volume = kl["volume"].astype(float)

    rsi = calc_rsi(close)
    macd, macd_sig, macd_hist = calc_macd(close)
    bb_upper, bb_mid, bb_lower, pct_b = calc_bollinger(close)
    mas = calc_mas(close)
    vol_ratio = calc_volume_ratio(volume)
    atr = calc_atr(high, low, close)
    patterns = detect_candlestick(open_, high, low, close)

    signal, confidence, reasons, urgency = generate_signal(
        rsi, macd_hist, pct_b, vol_ratio, mas, patterns)

    risk = calc_stop_targets(price, signal, atr, cfg["style"])
    suggested_shares = calc_position_size(price, risk["stop_loss"])
    position = positions.get(ticker)
    # 无持仓时填空结构，保证 JSON 里始终有 position 字段
    if position is None:
        position = {
            "qty":        0,
            "cost_price": 0.0,
            "pl_val":     0.0,
            "pl_pct":     0.0,
            "held":       False,   # 标记无持仓
        }
    else:
        position["held"] = True
        if abs(position.get("pl_pct", 0)) > 5:
            urgency = min(5, urgency + 1)

    result.update({
        "indicators": {
            "rsi": rsi, "macd": macd, "macd_sig": macd_sig, "macd_hist": macd_hist,
            "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
            "pct_b": pct_b, "vol_ratio": vol_ratio, "atr": round(atr,4), **mas,
        },
        "signal": signal, "confidence": confidence,
        "urgency": urgency, "reasons": reasons,
        "candlestick_patterns": [{"name":p[0],"type":p[1],"desc":p[2]} for p in patterns],
        "risk": risk, "suggested_shares": suggested_shares,
        "position": position,
        "price_history": close.tail(7).round(4).tolist(),
    })
    return result


def print_report(results):
    SIG = {"BUY":"🟢 买入","SELL":"🔴 观望/做空","HOLD":"🟡 持有"}
    print(f"\n{'='*65}")
    print(f"  MagicQuant 慧投 v0.1.0  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*65}")
    for r in results:
        t = r["ticker"].replace("US.","")
        if "error" in r:
            print(f"\n  {t}: ❌ {r['error']}"); continue
        ind = r["indicators"]
        risk = r.get("risk",{})
        pos = r.get("position")
        lvl = r.get("urgency",1)
        sign = "+" if r["change"] >= 0 else ""
        print(f"\n  ── {t} ({r['name']}) {'★'*lvl} 级别{lvl} ──")
        print(f"     价格: ${r['price']:.2f}  {sign}{r['change']:.2f} ({sign}{r['change_pct']:.2f}%)")
        print(f"     信号: {SIG.get(r['signal'],r['signal'])}  信心: {r['confidence']}%")
        print(f"     RSI:{ind['rsi']}  MACD:{ind['macd_hist']:+.4f}  量比:{ind['vol_ratio']}x  ATR:{ind['atr']}")
        ma_str = "  ".join([f"MA{k[2:]}:{v}" for k,v in ind.items() if k.startswith("ma")])
        if ma_str: print(f"     {ma_str}")
        print(f"     止损:${risk.get('stop_loss','?')}  目标1:${risk.get('target1','?')}  目标2:${risk.get('target2','?')}")
        print(f"     建议:{r.get('suggested_shares',0)}股  风险/股:${risk.get('risk_per_share','?')}")
        if pos:
            s = "+" if pos["pl_val"]>=0 else ""
            print(f"     持仓:{pos['qty']}股 成本:${pos['cost_price']} 盈亏:{s}${pos['pl_val']}({s}{pos['pl_pct']}%)")
        for reason in r["reasons"][:4]:
            print(f"       · {reason}")
    print(f"\n{'='*65}\n")


def save_json(results, account_info=None):
    os.makedirs(os.path.dirname(SIGNALS_FILE), exist_ok=True)
    out = {
        "generated_at": datetime.now().isoformat(),
        "signals": results,
        "account": account_info or {}
    }
    with open(SIGNALS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  → Saved to {SIGNALS_FILE}")


def main(run_once=False, interval=300):
    print(f"\n  Connecting FutuOpenD ({HOST}:{PORT})...")
    quote_ctx = OpenQuoteContext(host=HOST, port=PORT)
    positions, account_info = get_positions()
    if positions:
        print(f"  Positions: {list(positions.keys())}")
    try:
        while True:
            # v0.2.2: 每轮先刷新持仓,再决定要分析哪些票
            positions, account_info = get_positions()
            tickers = get_tickers(positions)   # ← 传入 positions 自动合并
            results = [fetch_and_analyze(quote_ctx, t, positions) for t in tickers]
            print_report(results)
            save_json(results, account_info)
            if run_once: break
            print(f"  Next update in {interval}s")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        quote_ctx.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    main(run_once=args.once, interval=args.interval)
