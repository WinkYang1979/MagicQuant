"""
MagicQuant — 策略寻优系统 v1.0
自动遍历参数空间，找到胜率 > 65% 且每天 3-5 条信号的最优策略

三个策略并行测试:
  V1: 优化现有 direction_trend + rapid_move 参数
  V2: 突破策略 (价格突破今日高低点)
  V3: 量价策略 (量比 > 阈值 + 价格变动)

Walk-Forward 验证防止过拟合:
  前 270 天 → 训练集 (寻优)
  后  95 天 → 验证集 (测试真实水平)

用法:
    cd C:\MagicQuant
    python strategy_optimizer.py

输出:
    data/backtest/optimizer_report.md   ← 寻优报告
    data/backtest/best_params.json      ← 最优参数(可直接用于 swing_detector)
"""

import json
import itertools
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
HIST_DIR = BASE_DIR / "data" / "historical"
BT_DIR   = BASE_DIR / "data" / "backtest"
BT_DIR.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════
#  目标
# ══════════════════════════════════════════════════════════════════
TARGET_WIN_RATE   = 0.65   # 胜率门槛
TARGET_MIN_SIG    = 3      # 每天最少信号数
TARGET_MAX_SIG    = 5      # 每天最多信号数
TRAIN_DAYS        = 270    # 训练集天数
EVAL_WINDOW       = 30     # 信号评估窗口(分钟)

# ══════════════════════════════════════════════════════════════════
#  指标计算
# ══════════════════════════════════════════════════════════════════
def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).round(1)


def prepare_data(csv_path: Path) -> pd.DataFrame:
    """加载并预计算所有需要的指标"""
    df = pd.read_csv(csv_path)
    df["time_key"] = pd.to_datetime(df["time_key"])
    df["close"]    = df["close"].astype(float)
    df["high"]     = df["high"].astype(float)
    df["low"]      = df["low"].astype(float)
    df["volume"]   = df["volume"].astype(float)

    # RSI
    df["rsi"] = calc_rsi(df["close"], 14)

    # 日内变动
    df["date"]     = df["time_key"].dt.date
    df["day_open"] = df.groupby("date")["close"].transform("first")
    df["day_high"] = df.groupby("date")["high"].transform("max")
    df["day_low"]  = df.groupby("date")["low"].transform("min")
    # 用 expanding max/min 得到"截止当前"的日内高低
    df["intraday_high"] = df.groupby("date")["high"].transform(lambda x: x.expanding().max())
    df["intraday_low"]  = df.groupby("date")["low"].transform(lambda x: x.expanding().min())
    df["day_chg"]  = (df["close"] - df["day_open"]) / df["day_open"] * 100

    # 快速变动(2分钟)
    df["chg_2m"]  = (df["close"] - df["close"].shift(2)) / df["close"].shift(2) * 100

    # 量比(最近3根 vs 前10根)
    df["vol_ma10"] = df["volume"].rolling(10).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma10"].replace(0, float("nan"))

    # 震荡检测
    df["roll_high"]  = df["close"].rolling(10).max()
    df["roll_low"]   = df["close"].rolling(10).min()
    df["roll_move"]  = (df["close"] - df["close"].shift(10)).abs()
    df["chop_ratio"] = (df["roll_high"] - df["roll_low"]) / df["roll_move"].replace(0, float("nan"))

    return df.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════
#  三个策略的信号生成器
# ══════════════════════════════════════════════════════════════════
def strategy_v1(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    V1: 优化版 direction_trend + rapid_move
    参数:
        trend_chg:      日内涨跌触发阈值 (%)
        trend_strong:   STRONG 门槛 (%)
        rapid_pct:      2分钟快速变动阈值 (%)
        cooldown:       冷却时间 (根K线数)
        rsi_filter:     是否启用 RSI 过滤
        choppy_filter:  震荡过滤阈值 (0=不过滤)
    """
    trend_chg     = params["trend_chg"]
    trend_strong  = params["trend_strong"]
    rapid_pct     = params["rapid_pct"]
    cooldown      = params["cooldown"]
    rsi_filter    = params["rsi_filter"]
    choppy_filter = params["choppy_filter"]

    signals = []
    last = {"trend_long": -9999, "trend_short": -9999,
            "rapid_up":   -9999, "rapid_down":  -9999}

    for i in range(30, len(df)):
        row     = df.iloc[i]
        day_chg = row["day_chg"]
        rsi     = row["rsi"]
        chg_2m  = row["chg_2m"]
        price   = row["close"]
        ts      = row["time_key"]
        choppy  = (row["chop_ratio"] > choppy_filter) if choppy_filter > 0 and not pd.isna(row["chop_ratio"]) else False

        if pd.isna(day_chg) or pd.isna(rsi):
            continue

        # direction_trend
        if abs(day_chg) >= trend_chg and not choppy:
            direction = "long" if day_chg > 0 else "short"
            key = f"trend_{direction}"
            rsi_ok = True
            if rsi_filter:
                if direction == "long"  and rsi < 52: rsi_ok = False
                if direction == "short" and rsi > 48: rsi_ok = False
            if rsi_ok and (i - last[key]) >= cooldown:
                strength = "STRONG" if abs(day_chg) >= trend_strong else "WEAK"
                signals.append({"idx": i, "time": ts, "strategy": "V1",
                                 "trigger": "direction_trend", "direction": direction,
                                 "strength": strength, "price": price, "rsi": rsi})
                last[key] = i
                continue

        # rapid_move
        if not pd.isna(chg_2m) and abs(chg_2m) >= rapid_pct and not choppy:
            direction = "long" if chg_2m > 0 else "short"
            key = "rapid_up" if direction == "long" else "rapid_down"
            if (i - last[key]) >= cooldown:
                signals.append({"idx": i, "time": ts, "strategy": "V1",
                                 "trigger": "rapid_move", "direction": direction,
                                 "strength": "WEAK", "price": price, "rsi": rsi})
                last[key] = i

    return pd.DataFrame(signals)


def strategy_v2(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    V2: 突破策略
    当价格突破今日截止当前的高点或低点时触发
    参数:
        breakout_pct:  突破幅度阈值 (超过高点/低点多少% 才算突破)
        vol_confirm:   是否需要量比确认
        vol_threshold: 量比门槛
        cooldown:      冷却时间
    """
    breakout_pct  = params["breakout_pct"]
    vol_confirm   = params["vol_confirm"]
    vol_threshold = params["vol_threshold"]
    cooldown      = params["cooldown"]

    signals = []
    last = {"break_up": -9999, "break_down": -9999}

    for i in range(30, len(df)):
        row       = df.iloc[i]
        price     = row["close"]
        prev_high = df.iloc[i-1]["intraday_high"]  # 前一根的日内高
        prev_low  = df.iloc[i-1]["intraday_low"]   # 前一根的日内低
        vol_ratio = row["vol_ratio"]
        ts        = row["time_key"]

        if pd.isna(prev_high) or pd.isna(prev_low):
            continue

        vol_ok = True
        if vol_confirm and not pd.isna(vol_ratio):
            vol_ok = vol_ratio >= vol_threshold

        # 向上突破
        if price > prev_high * (1 + breakout_pct / 100) and vol_ok:
            if (i - last["break_up"]) >= cooldown:
                signals.append({"idx": i, "time": ts, "strategy": "V2",
                                 "trigger": "breakout_up", "direction": "long",
                                 "strength": "STRONG", "price": price,
                                 "rsi": row["rsi"], "vol_ratio": vol_ratio})
                last["break_up"] = i

        # 向下突破
        elif price < prev_low * (1 - breakout_pct / 100) and vol_ok:
            if (i - last["break_down"]) >= cooldown:
                signals.append({"idx": i, "time": ts, "strategy": "V2",
                                 "trigger": "breakout_down", "direction": "short",
                                 "strength": "STRONG", "price": price,
                                 "rsi": row["rsi"], "vol_ratio": vol_ratio})
                last["break_down"] = i

    return pd.DataFrame(signals)


def strategy_v3(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    V3: 量价策略
    量比异常放大 + 价格同向变动
    参数:
        vol_threshold: 量比触发门槛
        price_chg:     同时需要价格变动 (%)
        cooldown:      冷却时间
        rsi_extreme:   是否只在 RSI 极值区触发
    """
    vol_threshold = params["vol_threshold"]
    price_chg     = params["price_chg"]
    cooldown      = params["cooldown"]
    rsi_extreme   = params["rsi_extreme"]

    signals = []
    last = {"vol_up": -9999, "vol_down": -9999}

    for i in range(30, len(df)):
        row       = df.iloc[i]
        vol_ratio = row["vol_ratio"]
        chg_2m    = row["chg_2m"]
        rsi       = row["rsi"]
        price     = row["close"]
        ts        = row["time_key"]

        if pd.isna(vol_ratio) or pd.isna(chg_2m) or pd.isna(rsi):
            continue

        # 量比达标
        if vol_ratio < vol_threshold:
            continue

        # 价格变动达标
        if abs(chg_2m) < price_chg:
            continue

        # RSI 极值过滤
        if rsi_extreme:
            if chg_2m > 0 and rsi > 70:  continue   # 超买不追多
            if chg_2m < 0 and rsi < 30:  continue   # 超卖不追空

        direction = "long" if chg_2m > 0 else "short"
        key = "vol_up" if direction == "long" else "vol_down"

        if (i - last[key]) >= cooldown:
            signals.append({"idx": i, "time": ts, "strategy": "V3",
                             "trigger": "vol_price", "direction": direction,
                             "strength": "STRONG" if vol_ratio >= vol_threshold * 1.5 else "WEAK",
                             "price": price, "rsi": rsi, "vol_ratio": vol_ratio})
            last[key] = i

    return pd.DataFrame(signals)


# ══════════════════════════════════════════════════════════════════
#  信号评估
# ══════════════════════════════════════════════════════════════════
def evaluate(signals_df: pd.DataFrame, prices: np.ndarray,
             window: int = EVAL_WINDOW) -> dict:
    """评估信号质量，返回统计指标"""
    if signals_df is None or len(signals_df) == 0:
        return {"total": 0, "win_rate": 0, "signals_per_day": 0,
                "max_loss_streak": 0, "avg_win": 0, "avg_loss": 0}

    results = []
    for _, sig in signals_df.iterrows():
        idx   = int(sig["idx"])
        entry = float(sig["price"])
        dir_  = sig["direction"]

        idx_e = min(idx + window, len(prices) - 1)
        exit_p = float(prices[idx_e])
        chg    = (exit_p - entry) / entry * 100
        win    = (chg > 0) if dir_ == "long" else (chg < 0)
        pnl    = abs(chg) if win else -abs(chg)
        results.append({"win": win, "pnl": pnl, "chg": chg})

    if not results:
        return {"total": 0, "win_rate": 0, "signals_per_day": 0,
                "max_loss_streak": 0, "avg_win": 0, "avg_loss": 0}

    rdf  = pd.DataFrame(results)
    total = len(rdf)
    wins  = rdf["win"].sum()
    win_rate = wins / total

    # 每天信号数
    days = signals_df["time"].dt.date.nunique() if hasattr(signals_df["time"].iloc[0], 'date') else 1
    spd  = round(total / max(days, 1), 1)

    # 最大连败
    streak = max_streak = 0
    for w in rdf["win"]:
        if not w:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    avg_win  = rdf[rdf["win"]]["chg"].mean() if wins > 0 else 0
    avg_loss = rdf[~rdf["win"]]["chg"].mean() if (total - wins) > 0 else 0

    return {
        "total":           total,
        "win_rate":        round(win_rate, 4),
        "signals_per_day": spd,
        "max_loss_streak": max_streak,
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss, 2),
    }


def passes_filter(stats: dict) -> bool:
    """是否满足上线条件"""
    return (
        stats["win_rate"]        >= TARGET_WIN_RATE and
        stats["signals_per_day"] >= TARGET_MIN_SIG  and
        stats["signals_per_day"] <= TARGET_MAX_SIG  and
        stats["total"]           >= 50              and   # 至少50条信号才可信
        stats["max_loss_streak"] <= 8               # 连败不超过8次
    )


# ══════════════════════════════════════════════════════════════════
#  参数空间
# ══════════════════════════════════════════════════════════════════
V1_PARAMS = {
    "trend_chg":     [1.0, 1.5, 2.0, 2.5, 3.0],
    "trend_strong":  [2.0, 2.5, 3.0],
    "rapid_pct":     [0.8, 1.0, 1.5, 2.0],
    "cooldown":      [20, 40, 60],
    "rsi_filter":    [True, False],
    "choppy_filter": [2.0, 3.0, 0],   # 0=不过滤
}

V2_PARAMS = {
    "breakout_pct":  [0.3, 0.5, 0.8, 1.0, 1.5],
    "vol_confirm":   [True, False],
    "vol_threshold": [1.5, 2.0, 2.5],
    "cooldown":      [20, 40, 60],
}

V3_PARAMS = {
    "vol_threshold": [1.5, 2.0, 2.5, 3.0],
    "price_chg":     [0.3, 0.5, 0.8, 1.0],
    "cooldown":      [20, 40, 60],
    "rsi_extreme":   [True, False],
}


def param_combinations(param_dict: dict) -> list:
    keys   = list(param_dict.keys())
    values = list(param_dict.values())
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


# ══════════════════════════════════════════════════════════════════
#  主寻优引擎
# ══════════════════════════════════════════════════════════════════
def optimize(df: pd.DataFrame, strategy_fn, param_space: dict,
             strategy_name: str) -> list:
    """
    在训练集上遍历所有参数组合，返回通过过滤条件的 Top 结果
    """
    # 训练/验证分割
    dates      = sorted(df["date"].unique())
    train_dates = dates[:TRAIN_DAYS]
    val_dates   = dates[TRAIN_DAYS:]

    df_train = df[df["date"].isin(train_dates)].copy()
    df_val   = df[df["date"].isin(val_dates)].copy()

    prices_train = df_train["close"].values
    prices_val   = df_val["close"].values

    combos = param_combinations(param_space)
    total  = len(combos)
    print(f"\n  [{strategy_name}] 遍历 {total} 种参数组合...")

    results = []
    passed  = 0

    for i, params in enumerate(combos):
        if (i + 1) % 100 == 0:
            print(f"    进度 {i+1}/{total}  通过 {passed} 个", end="\r")

        # 训练集信号
        sigs_train = strategy_fn(df_train, params)
        stats_train = evaluate(sigs_train, prices_train)

        if not passes_filter(stats_train):
            continue
        passed += 1

        # 验证集信号
        sigs_val = strategy_fn(df_val, params)
        stats_val = evaluate(sigs_val, prices_val)

        results.append({
            "params":      params,
            "train":       stats_train,
            "val":         stats_val,
            "val_win":     stats_val["win_rate"],
            "train_win":   stats_train["win_rate"],
            "both_pass":   passes_filter(stats_val),
        })

    print(f"\n    训练集通过: {passed} 个 / {total}")
    both = sum(1 for r in results if r["both_pass"])
    print(f"    训练+验证都通过: {both} 个")

    # 按验证集胜率排序
    results.sort(key=lambda x: x["val_win"], reverse=True)
    return results[:10]   # 返回 Top 10


# ══════════════════════════════════════════════════════════════════
#  报告生成
# ══════════════════════════════════════════════════════════════════
def format_result(r: dict, rank: int) -> list:
    p  = r["params"]
    tr = r["train"]
    vl = r["val"]
    ok = "✅" if r["both_pass"] else "⚠️ 训练好但验证差(过拟合)"

    lines = [
        f"### #{rank}  验证集胜率 {vl['win_rate']*100:.1f}%  {ok}",
        f"",
        f"| 参数 | 值 |",
        f"|---|---|",
    ]
    for k, v in p.items():
        lines.append(f"| {k} | {v} |")

    lines += [
        f"",
        f"| 指标 | 训练集({TRAIN_DAYS}天) | 验证集({365-TRAIN_DAYS}天) |",
        f"|---|---|---|",
        f"| 胜率 | {tr['win_rate']*100:.1f}% | **{vl['win_rate']*100:.1f}%** |",
        f"| 信号数/天 | {tr['signals_per_day']} | {vl['signals_per_day']} |",
        f"| 总信号数 | {tr['total']} | {vl['total']} |",
        f"| 最大连败 | {tr['max_loss_streak']} | {vl['max_loss_streak']} |",
        f"| 平均盈利 | +{tr['avg_win']}% | +{vl['avg_win']}% |",
        f"| 平均亏损 | {tr['avg_loss']}% | {vl['avg_loss']}% |",
        f"",
    ]
    return lines


def generate_report(v1_results, v2_results, v3_results) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# MagicQuant 策略寻优报告",
        f"> 生成时间: {now}",
        f"> 目标: 胜率 > {TARGET_WIN_RATE*100:.0f}%，每天 {TARGET_MIN_SIG}-{TARGET_MAX_SIG} 条信号",
        f"> 方法: Walk-Forward 验证 (训练{TRAIN_DAYS}天 / 验证{365-TRAIN_DAYS}天)",
        f"",
        f"---",
        f"",
        f"## 策略 V1: 优化版 direction_trend + rapid_move",
    ]

    if v1_results:
        best = v1_results[0]
        lines.append(f"> 最优验证集胜率: **{best['val_win']*100:.1f}%**")
        lines.append(f"")
        for i, r in enumerate(v1_results[:3], 1):
            lines += format_result(r, i)
    else:
        lines += [f"", f"❌ 无参数组合同时通过训练集和验证集", f""]

    lines += [
        f"---",
        f"",
        f"## 策略 V2: 突破策略",
    ]

    if v2_results:
        best = v2_results[0]
        lines.append(f"> 最优验证集胜率: **{best['val_win']*100:.1f}%**")
        lines.append(f"")
        for i, r in enumerate(v2_results[:3], 1):
            lines += format_result(r, i)
    else:
        lines += [f"", f"❌ 无参数组合同时通过训练集和验证集", f""]

    lines += [
        f"---",
        f"",
        f"## 策略 V3: 量价策略",
    ]

    if v3_results:
        best = v3_results[0]
        lines.append(f"> 最优验证集胜率: **{best['val_win']*100:.1f}%**")
        lines.append(f"")
        for i, r in enumerate(v3_results[:3], 1):
            lines += format_result(r, i)
    else:
        lines += [f"", f"❌ 无参数组合同时通过训练集和验证集", f""]

    # 总结
    lines += [f"---", f"", f"## 总结与建议", f""]

    all_results = [
        ("V1 优化版", v1_results),
        ("V2 突破",   v2_results),
        ("V3 量价",   v3_results),
    ]

    # 找全局最优
    global_best = None
    global_best_name = ""
    for name, results in all_results:
        if results and results[0]["both_pass"]:
            if global_best is None or results[0]["val_win"] > global_best["val_win"]:
                global_best = results[0]
                global_best_name = name

    if global_best:
        lines += [
            f"### ✅ 推荐上线策略: {global_best_name}",
            f"",
            f"验证集胜率: **{global_best['val_win']*100:.1f}%**",
            f"每天信号数: {global_best['val']['signals_per_day']} 条",
            f"",
            f"**参数配置:**",
            f"```json",
            json.dumps(global_best["params"], indent=2, ensure_ascii=False),
            f"```",
            f"",
            f"将以上参数更新到 `core/focus/swing_detector.py` 的 `DEFAULT_PARAMS` 即可上线。",
        ]
    else:
        lines += [
            f"### ⚠️ 当前数据范围内没有策略同时满足所有条件",
            f"",
            f"**可能原因:**",
            f"- RKLB 历史走势随机性较强，65% 胜率门槛偏高",
            f"- 建议将目标胜率降至 60% 重新寻优",
            f"- 或等待更多历史数据积累后再寻优",
        ]

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  MagicQuant 策略寻优系统 v1.0")
    print(f"  目标: 胜率>{TARGET_WIN_RATE*100:.0f}%  信号{TARGET_MIN_SIG}-{TARGET_MAX_SIG}条/天")
    print("=" * 60)

    # 加载数据
    rklb_path = HIST_DIR / "RKLB_1m.csv"
    if not rklb_path.exists():
        print(f"❌ 找不到 {rklb_path}")
        print("   请先运行 fetch_and_backtest.py 拉取历史数据")
        return

    print("\n  加载 RKLB 历史数据...")
    df = prepare_data(rklb_path)
    print(f"  共 {len(df)} 条  ({df['time_key'].iloc[0]} ~ {df['time_key'].iloc[-1]})")

    dates = sorted(df["date"].unique())
    print(f"  共 {len(dates)} 个交易日")
    print(f"  训练集: 前 {TRAIN_DAYS} 天  验证集: 后 {len(dates)-TRAIN_DAYS} 天")

    # V1 寻优
    print("\n" + "="*60)
    print("  [V1] 优化 direction_trend + rapid_move 参数")
    v1_combos = param_combinations(V1_PARAMS)
    print(f"  参数组合数: {len(v1_combos)}")
    v1_results = optimize(df, strategy_v1, V1_PARAMS, "V1")

    # V2 寻优
    print("\n" + "="*60)
    print("  [V2] 突破策略寻优")
    v2_combos = param_combinations(V2_PARAMS)
    print(f"  参数组合数: {len(v2_combos)}")
    v2_results = optimize(df, strategy_v2, V2_PARAMS, "V2")

    # V3 寻优
    print("\n" + "="*60)
    print("  [V3] 量价策略寻优")
    v3_combos = param_combinations(V3_PARAMS)
    print(f"  参数组合数: {len(v3_combos)}")
    v3_results = optimize(df, strategy_v3, V3_PARAMS, "V3")

    # 生成报告
    print("\n" + "="*60)
    print("  生成报告...")
    report = generate_report(v1_results, v2_results, v3_results)

    report_path = BT_DIR / "optimizer_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {report_path}")

    # 保存最优参数
    all_best = []
    for name, results in [("V1", v1_results), ("V2", v2_results), ("V3", v3_results)]:
        if results:
            all_best.append({
                "strategy": name,
                "val_win_rate": results[0]["val_win"],
                "params": results[0]["params"],
                "train_stats": results[0]["train"],
                "val_stats": results[0]["val"],
            })

    if all_best:
        all_best.sort(key=lambda x: x["val_win_rate"], reverse=True)
        params_path = BT_DIR / "best_params.json"
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(all_best[0], f, indent=2, ensure_ascii=False)
        print(f"  最优参数已保存: {params_path}")

    print("\n" + "="*60)
    print(report)
    print("="*60)
    print("\n✅ 寻优完成！把报告发给我分析。")


if __name__ == "__main__":
    main()
