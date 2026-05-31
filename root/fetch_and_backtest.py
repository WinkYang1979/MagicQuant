"""
MagicQuant — 历史数据拉取 + 回测
Polygon.io 免费 API，拉取 RKLB/RKLX/RKLZ 过去 365 天 1 分钟 K 线
然后用 swing_detector v0.5.5 逻辑回测，评估信号质量

用法:
    cd C:\MagicQuant
    python fetch_and_backtest.py

输出:
    data/historical/RKLB_1m.csv       ← 历史 K 线
    data/historical/RKLX_1m.csv
    data/historical/RKLZ_1m.csv
    data/backtest/backtest_report.md  ← 回测报告
    data/backtest/signals_detail.csv  ← 信号明细
"""

import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

# ══════════════════════════════════════════════════════════════════
#  配置
# ══════════════════════════════════════════════════════════════════
API_KEY   = "ipIkF6FsAk9JFNFA27BgpeWa3hpDTzD4"
TICKERS   = ["RKLB", "RKLX", "RKLZ"]
DAYS_BACK = 365

BASE_DIR  = Path(__file__).parent
HIST_DIR  = BASE_DIR / "data" / "historical"
BT_DIR    = BASE_DIR / "data" / "backtest"
HIST_DIR.mkdir(parents=True, exist_ok=True)
BT_DIR.mkdir(parents=True, exist_ok=True)

# 回测参数 (swing_detector v0.5.5)
RAPID_MOVE_PCT    = 0.8
RAPID_MOVE_WINDOW = 2      # 根 1m K 线 ≈ 2 分钟
TREND_CHG_PCT     = 0.8
TREND_CHG_STRONG  = 2.0
EVAL_30           = 30     # 分钟
EVAL_60           = 60     # 分钟
GLOBAL_MUTEX_MIN  = 1      # 全局互斥 1 根 K 线


# ══════════════════════════════════════════════════════════════════
#  Step 1: 拉取历史数据（支持分页）
# ══════════════════════════════════════════════════════════════════
def fetch_polygon_1m(ticker: str, days: int = 365) -> pd.DataFrame:
    """
    拉取 Polygon 1 分钟 K 线，支持自动分页。
    Polygon 免费版每次最多 50,000 条，1年数据约 160,000 条，需要分 4 次拉。
    """
    end_date   = datetime.now()
    start_date = end_date - timedelta(days=days)

    all_results = []
    # 按月分段拉取，避免单次超限
    current = start_date
    segment_days = 60   # 每段 60 天，约 37,800 条，安全

    print(f"\n  [{ticker}] 拉取 {days} 天历史数据（分段）...")

    while current < end_date:
        seg_end = min(current + timedelta(days=segment_days), end_date)
        from_str = current.strftime("%Y-%m-%d")
        to_str   = seg_end.strftime("%Y-%m-%d")

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/minute"
            f"/{from_str}/{to_str}"
            f"?adjusted=true&sort=asc&limit=50000&apiKey={API_KEY}"
        )

        try:
            r = requests.get(url, timeout=30)
            data = r.json()
        except Exception as e:
            print(f"    ❌ {from_str}~{to_str} 请求失败: {e}")
            current = seg_end
            time.sleep(13)
            continue

        if data.get("status") == "ERROR":
            print(f"    ❌ API 错误: {data.get('error', data)}")
            break

        results = data.get("results", [])
        count = len(results)
        all_results.extend(results)
        print(f"    {from_str} ~ {to_str}: {count} 条", end="")

        # 如果返回满 50,000 条，可能还有更多（分页）
        next_url = data.get("next_url")
        page = 0
        while next_url and page < 10:
            next_url_full = f"{next_url}&apiKey={API_KEY}"
            time.sleep(13)  # 限速
            try:
                r2 = requests.get(next_url_full, timeout=30)
                d2 = r2.json()
                extra = d2.get("results", [])
                all_results.extend(extra)
                count += len(extra)
                print(f" +{len(extra)}", end="")
                next_url = d2.get("next_url")
                page += 1
            except Exception as e:
                print(f" [分页错误: {e}]", end="")
                break

        print(f" → 累计 {count} 条")
        current = seg_end
        time.sleep(13)  # Polygon 免费版 5次/分钟

    if not all_results:
        print(f"  ⚠️ [{ticker}] 无数据")
        return pd.DataFrame()

    df = pd.DataFrame(all_results)
    df["time_key"] = (
        pd.to_datetime(df["t"], unit="ms", utc=True)
        .dt.tz_convert("US/Eastern")
        .dt.strftime("%Y-%m-%d %H:%M:%S")
    )
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df = df[["time_key", "open", "high", "low", "close", "volume"]].copy()
    df = df.drop_duplicates("time_key").sort_values("time_key").reset_index(drop=True)

    print(f"  ✅ [{ticker}] 共 {len(df)} 条  ({df['time_key'].iloc[0]} ~ {df['time_key'].iloc[-1]})")
    return df


def fetch_all() -> dict:
    print("\n" + "="*60)
    print("  Step 1: 拉取历史数据")
    print("="*60)

    dfs = {}
    for ticker in TICKERS:
        cache_path = HIST_DIR / f"{ticker}_1m.csv"

        # 缓存判断：今天已拉过就跳过
        if cache_path.exists():
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            age_hours = (datetime.now() - mtime).total_seconds() / 3600
            if age_hours < 6:
                print(f"\n  [{ticker}] 读缓存 (更新于 {mtime.strftime('%H:%M')})")
                df = pd.read_csv(cache_path)
                print(f"    共 {len(df)} 条")
                dfs[ticker] = df
                continue

        df = fetch_polygon_1m(ticker, DAYS_BACK)
        if not df.empty:
            df.to_csv(cache_path, index=False)
            print(f"  💾 已保存: {cache_path}")
            dfs[ticker] = df

    return dfs


# ══════════════════════════════════════════════════════════════════
#  Step 2: 指标计算
# ══════════════════════════════════════════════════════════════════
def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).round(1)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["close"]  = df["close"].astype(float)
    df["high"]   = df["high"].astype(float)
    df["low"]    = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df["time_key"] = pd.to_datetime(df["time_key"])

    df["rsi"] = calc_rsi(df["close"], 14)

    # 日内变动：每天开盘第一根 close 作为 day_open
    df["date"]     = df["time_key"].dt.date
    df["day_open"] = df.groupby("date")["close"].transform("first")
    df["day_chg"]  = (df["close"] - df["day_open"]) / df["day_open"] * 100

    # 2 分钟快速变动
    df["chg_2m"] = (df["close"] - df["close"].shift(RAPID_MOVE_WINDOW)) \
                   / df["close"].shift(RAPID_MOVE_WINDOW) * 100

    # 震荡检测：最近 10 根的高低差 / 总涨跌
    df["roll_high"] = df["close"].rolling(10).max()
    df["roll_low"]  = df["close"].rolling(10).min()
    df["roll_move"] = (df["close"] - df["close"].shift(10)).abs()
    df["chop_ratio"] = (df["roll_high"] - df["roll_low"]) / df["roll_move"].replace(0, float("nan"))

    return df


# ══════════════════════════════════════════════════════════════════
#  Step 3: 模拟信号触发
# ══════════════════════════════════════════════════════════════════
def simulate_signals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 30:
        return pd.DataFrame()

    signals = []
    last_signal_idx = {"trend_long": -9999, "trend_short": -9999,
                       "rapid_up": -9999, "rapid_down": -9999}
    TREND_COOLDOWN = 20   # 分钟 ≈ 20 根 K 线
    RAPID_COOLDOWN = 20   # 分钟

    for i in range(30, len(df)):
        row = df.iloc[i]

        day_chg  = row["day_chg"]
        rsi      = row["rsi"]
        chg_2m   = row["chg_2m"]
        price    = row["close"]
        ts       = row["time_key"]
        choppy   = (row["chop_ratio"] > 3.0) if not pd.isna(row["chop_ratio"]) else False

        if pd.isna(day_chg) or pd.isna(rsi):
            continue

        # ── direction_trend ──────────────────────────────────
        if abs(day_chg) >= TREND_CHG_PCT and not choppy:
            direction = "long" if day_chg > 0 else "short"
            cool_key  = f"trend_{direction}"

            # RSI 确认
            rsi_ok = True
            if direction == "long"  and rsi < 52: rsi_ok = False
            if direction == "short" and rsi > 48: rsi_ok = False

            if rsi_ok and (i - last_signal_idx[cool_key]) >= TREND_COOLDOWN:
                strength = "STRONG" if abs(day_chg) >= TREND_CHG_STRONG else "WEAK"
                signals.append({
                    "idx": i, "time": ts,
                    "trigger": "direction_trend",
                    "direction": direction, "strength": strength,
                    "price": price, "rsi": round(rsi, 1),
                    "day_chg": round(day_chg, 2), "chg_2m": None,
                })
                last_signal_idx[cool_key] = i
                continue

        # ── rapid_move ───────────────────────────────────────
        if not pd.isna(chg_2m) and abs(chg_2m) >= RAPID_MOVE_PCT and not choppy:
            direction = "long" if chg_2m > 0 else "short"
            cool_key  = "rapid_up" if direction == "long" else "rapid_down"

            if (i - last_signal_idx[cool_key]) >= RAPID_COOLDOWN:
                signals.append({
                    "idx": i, "time": ts,
                    "trigger": "rapid_move",
                    "direction": direction, "strength": "WEAK",
                    "price": price, "rsi": round(rsi, 1),
                    "day_chg": round(day_chg, 2), "chg_2m": round(chg_2m, 2),
                })
                last_signal_idx[cool_key] = i

    return pd.DataFrame(signals)


# ══════════════════════════════════════════════════════════════════
#  Step 4: 评估信号有效性
# ══════════════════════════════════════════════════════════════════
def evaluate_signals(signals_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    if signals_df.empty:
        return signals_df

    prices = price_df["close"].astype(float).values
    results = []

    for _, sig in signals_df.iterrows():
        idx       = int(sig["idx"])
        direction = sig["direction"]
        entry     = float(sig["price"])

        # 30 分钟后价格
        idx_30   = min(idx + EVAL_30, len(prices) - 1)
        price_30 = float(prices[idx_30])
        chg_30   = (price_30 - entry) / entry * 100

        # 60 分钟后价格
        idx_60   = min(idx + EVAL_60, len(prices) - 1)
        price_60 = float(prices[idx_60])
        chg_60   = (price_60 - entry) / entry * 100

        valid_30 = (chg_30 > 0) if direction == "long" else (chg_30 < 0)
        valid_60 = (chg_60 > 0) if direction == "long" else (chg_60 < 0)

        r = sig.to_dict()
        r.update({
            "price_30m": round(price_30, 4),
            "chg_30m":   round(chg_30, 2),
            "valid_30m": valid_30,
            "price_60m": round(price_60, 4),
            "chg_60m":   round(chg_60, 2),
            "valid_60m": valid_60,
        })
        results.append(r)

    return pd.DataFrame(results)


# ══════════════════════════════════════════════════════════════════
#  Step 5: 生成报告
# ══════════════════════════════════════════════════════════════════
def generate_report(ev: pd.DataFrame, ticker: str = "RKLB") -> str:
    if ev.empty:
        return f"# {ticker} 回测报告\n\n无信号数据\n"

    total    = len(ev)
    win_30   = round(ev["valid_30m"].sum() / total * 100, 1)
    win_60   = round(ev["valid_60m"].sum() / total * 100, 1)

    def tbl(grouped):
        rows = []
        for _, r in grouped.iterrows():
            rows.append(
                f"| {r.iloc[0]} | {r['count']} | {r['win_30m']}% | {r['win_60m']}% |"
            )
        return rows

    by_trig = ev.groupby("trigger").agg(
        count=("valid_30m","count"),
        win_30m=("valid_30m", lambda x: round(x.mean()*100,1)),
        win_60m=("valid_60m", lambda x: round(x.mean()*100,1)),
    ).reset_index()

    by_dir = ev.groupby("direction").agg(
        count=("valid_30m","count"),
        win_30m=("valid_30m", lambda x: round(x.mean()*100,1)),
        win_60m=("valid_60m", lambda x: round(x.mean()*100,1)),
    ).reset_index()

    by_str = ev.groupby("strength").agg(
        count=("valid_30m","count"),
        win_30m=("valid_30m", lambda x: round(x.mean()*100,1)),
        win_60m=("valid_60m", lambda x: round(x.mean()*100,1)),
    ).reset_index()

    lines = [
        f"# {ticker} 回测报告",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 策略: swing_detector v0.5.5  |  数据: 最近 {DAYS_BACK} 天",
        f"",
        f"## 总体胜率",
        f"| 总信号数 | 30分钟胜率 | 60分钟胜率 |",
        f"|---|---|---|",
        f"| {total} 条 | **{win_30}%** | **{win_60}%** |",
        f"",
        f"## 按触发器",
        f"| 触发器 | 次数 | 30m胜率 | 60m胜率 |",
        f"|---|---|---|---|",
    ] + tbl(by_trig) + [
        f"",
        f"## 按方向",
        f"| 方向 | 次数 | 30m胜率 | 60m胜率 |",
        f"|---|---|---|---|",
    ] + tbl(by_dir) + [
        f"",
        f"## 按强度",
        f"| 强度 | 次数 | 30m胜率 | 60m胜率 |",
        f"|---|---|---|---|",
    ] + tbl(by_str) + ["", "## 结论"]

    if win_30 >= 60:
        lines.append(f"✅ 30分钟胜率 {win_30}% — **策略有效**")
    elif win_30 >= 50:
        lines.append(f"⚠️ 30分钟胜率 {win_30}% — **略优于随机**,需观察")
    else:
        lines.append(f"❌ 30分钟胜率 {win_30}% — **策略不佳**,建议调整")

    if not by_trig.empty:
        best  = by_trig.loc[by_trig["win_30m"].idxmax()]
        worst = by_trig.loc[by_trig["win_30m"].idxmin()]
        lines.append(f"📌 最优触发器: **{best['trigger']}** ({best['win_30m']}%)")
        if worst["win_30m"] < 50:
            lines.append(f"⚠️ 最差触发器: **{worst['trigger']}** ({worst['win_30m']}%) — 建议调整")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  MagicQuant 历史回测  (365天, swing_detector v0.5.5)")
    print("=" * 60)
    print(f"  预计耗时: 10-15 分钟 (Polygon 限速)")

    # Step 1: 拉数据
    dfs = fetch_all()

    if "RKLB" not in dfs or dfs["RKLB"].empty:
        print("\n❌ 无法获取 RKLB 数据，退出")
        sys.exit(1)

    # Step 2: 加指标
    print("\n" + "="*60)
    print("  Step 2: 计算技术指标")
    print("="*60)
    df_rklb = add_indicators(dfs["RKLB"])
    print(f"  RKLB: {len(df_rklb)} 条，指标计算完成")

    # Step 3: 模拟信号
    print("\n" + "="*60)
    print("  Step 3: 模拟信号触发")
    print("="*60)
    signals = simulate_signals(df_rklb)
    print(f"  共触发信号: {len(signals)} 条")
    if not signals.empty:
        for k, v in Counter(signals["trigger"]).items():
            print(f"    {k}: {v}")
        dir_cnt = Counter(signals["direction"])
        str_cnt = Counter(signals["strength"])
        print(f"  方向: 看多={dir_cnt.get('long',0)}, 看空={dir_cnt.get('short',0)}")
        print(f"  强度: STRONG={str_cnt.get('STRONG',0)}, WEAK={str_cnt.get('WEAK',0)}")

    # Step 4: 评估
    print("\n" + "="*60)
    print("  Step 4: 评估信号有效性")
    print("="*60)
    evaluated = evaluate_signals(signals, df_rklb)
    if not evaluated.empty:
        w30 = round(evaluated["valid_30m"].mean()*100, 1)
        w60 = round(evaluated["valid_60m"].mean()*100, 1)
        print(f"  30分钟胜率: {w30}%")
        print(f"  60分钟胜率: {w60}%")
        detail_path = BT_DIR / "signals_detail.csv"
        evaluated.to_csv(detail_path, index=False)
        print(f"  明细已保存: {detail_path}")

    # Step 5: 报告
    print("\n" + "="*60)
    print("  Step 5: 生成报告")
    print("="*60)
    report = generate_report(evaluated, "RKLB")
    report_path = BT_DIR / "backtest_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {report_path}")

    print("\n" + "="*60)
    print(report)
    print("="*60)
    print("\n✅ 完成！把上面的报告发给我分析。")


if __name__ == "__main__":
    main()
