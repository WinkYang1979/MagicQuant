"""
MagicQuant — 策略寻优系统 v2.0
新增业界验证策略:
  V4: 开盘区间突破 ORB (来源: Zarattini et al. 2024, QuantConnect)
  V5: VWAP + 量比组合 (来源: LuxAlgo / ForexTester VWAP Guide 2026)
  V6: VWAP均值回归 (来源: ChartSwatcher VWAP Strategy Guide 2025)

原有策略保留:
  V1: 优化版 direction_trend + rapid_move (MagicQuant 自研)
  V2: 突破策略 (MagicQuant 自研)
  V3: 量价策略 (MagicQuant 自研)

Walk-Forward 验证 + 3折交叉验证防止过拟合

用法:
    cd C:\\MagicQuant
    python strategy_optimizer_v2.py

输出:
    data/backtest/optimizer_v2_report.md
    data/backtest/best_params_v2.json
"""

import json, itertools, pandas as pd, numpy as np
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
HIST_DIR = BASE_DIR / "data" / "historical"
BT_DIR   = BASE_DIR / "data" / "backtest"
BT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_WIN_RATE = 0.65
TARGET_MIN_SIG  = 3
TARGET_MAX_SIG  = 5
EVAL_WINDOW     = 30   # 分钟

# ══════════════════════════════════════════════════════════════════
#  指标计算
# ══════════════════════════════════════════════════════════════════
def calc_rsi(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).round(1)

def calc_vwap_intraday(df):
    """每天重置的 VWAP"""
    df = df.copy()
    df["typical"] = (df["high"] + df["low"] + df["close"]) / 3
    df["pv"]      = df["typical"] * df["volume"]
    df["cum_pv"]  = df.groupby("date")["pv"].cumsum()
    df["cum_vol"] = df.groupby("date")["volume"].cumsum()
    df["vwap"]    = df["cum_pv"] / df["cum_vol"].replace(0, float("nan"))
    return df["vwap"]

def prepare_data(csv_path):
    df = pd.read_csv(csv_path)
    df["time_key"] = pd.to_datetime(df["time_key"])
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)

    df["rsi"]      = calc_rsi(df["close"], 14)
    df["date"]     = df["time_key"].dt.date
    df["hour_et"]  = df["time_key"].dt.hour
    df["minute_et"]= df["time_key"].dt.minute

    # 日内开盘价 & 日内高低
    df["day_open"]      = df.groupby("date")["open"].transform("first")
    df["intra_high"]    = df.groupby("date")["high"].transform(lambda x: x.expanding().max())
    df["intra_low"]     = df.groupby("date")["low"].transform(lambda x: x.expanding().min())
    df["day_chg"]       = (df["close"] - df["day_open"]) / df["day_open"] * 100
    df["chg_2m"]        = (df["close"] - df["close"].shift(2)) / df["close"].shift(2) * 100

    # 量比
    df["vol_ma10"]  = df["volume"].rolling(10).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma10"].replace(0, float("nan"))

    # 震荡检测
    df["roll_hi"]   = df["close"].rolling(10).max()
    df["roll_lo"]   = df["close"].rolling(10).min()
    df["roll_move"] = (df["close"] - df["close"].shift(10)).abs()
    df["chop"]      = (df["roll_hi"] - df["roll_lo"]) / df["roll_move"].replace(0, float("nan"))

    # VWAP
    df["vwap"]      = calc_vwap_intraday(df)

    # 开盘区间高低（前N分钟）- 用于 ORB
    # 标记每根K线是第几分钟（相对当天开盘）
    df["day_minute"] = df.groupby("date").cumcount()

    return df.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════
#  策略 V1: 优化版 direction_trend + rapid_move
#  来源: MagicQuant 自研 swing_detector v0.5.5
# ══════════════════════════════════════════════════════════════════
def strategy_v1(df, params):
    """
    来源: MagicQuant swing_detector v0.5.5 (自研)
    参数:
        trend_chg:      日内涨跌触发阈值(%)
        trend_strong:   STRONG门槛(%)
        rapid_pct:      2分钟变动阈值(%)
        cooldown:       冷却(根K线数)
        rsi_filter:     是否RSI过滤
        choppy_filter:  震荡过滤阈值
    """
    tc=params["trend_chg"]; ts=params["trend_strong"]
    rp=params["rapid_pct"]; cd=params["cooldown"]
    rf=params["rsi_filter"]; cf=params["choppy_filter"]

    signals=[]
    last={"tl":-9999,"ts":-9999,"ru":-9999,"rd":-9999}

    for i in range(30, len(df)):
        r=df.iloc[i]
        dc=r["day_chg"]; rs=r["rsi"]; c2=r["chg_2m"]
        p=r["close"]; t=r["time_key"]
        choppy=(r["chop"]>cf) if cf>0 and not pd.isna(r["chop"]) else False
        if pd.isna(dc) or pd.isna(rs): continue

        if abs(dc)>=tc and not choppy:
            d="long" if dc>0 else "short"
            k="tl" if d=="long" else "ts"
            ok=True
            if rf:
                if d=="long" and rs<52: ok=False
                if d=="short" and rs>48: ok=False
            if ok and (i-last[k])>=cd:
                signals.append({"idx":i,"time":t,"strategy":"V1_MagicQuant自研",
                    "trigger":"direction_trend","direction":d,
                    "strength":"STRONG" if abs(dc)>=ts else "WEAK",
                    "price":p,"rsi":rs})
                last[k]=i; continue

        if not pd.isna(c2) and abs(c2)>=rp and not choppy:
            d="long" if c2>0 else "short"
            k="ru" if d=="long" else "rd"
            if (i-last[k])>=cd:
                signals.append({"idx":i,"time":t,"strategy":"V1_MagicQuant自研",
                    "trigger":"rapid_move","direction":d,
                    "strength":"WEAK","price":p,"rsi":rs})
                last[k]=i

    return pd.DataFrame(signals)


# ══════════════════════════════════════════════════════════════════
#  策略 V2: 日内高低突破
#  来源: MagicQuant 自研
# ══════════════════════════════════════════════════════════════════
def strategy_v2(df, params):
    """
    来源: MagicQuant 自研
    参数:
        breakout_pct:   突破幅度(%)
        vol_confirm:    量比确认
        vol_threshold:  量比门槛
        cooldown:       冷却
    """
    bp=params["breakout_pct"]; vc=params["vol_confirm"]
    vt=params["vol_threshold"]; cd=params["cooldown"]

    signals=[]
    last={"bu":-9999,"bd":-9999}

    for i in range(30, len(df)):
        r=df.iloc[i]; p=r["close"]; t=r["time_key"]
        ph=df.iloc[i-1]["intra_high"]; pl=df.iloc[i-1]["intra_low"]
        vr=r["vol_ratio"]
        if pd.isna(ph) or pd.isna(pl): continue
        vol_ok=True
        if vc and not pd.isna(vr): vol_ok=(vr>=vt)

        if p>ph*(1+bp/100) and vol_ok and (i-last["bu"])>=cd:
            signals.append({"idx":i,"time":t,"strategy":"V2_MagicQuant自研",
                "trigger":"breakout_up","direction":"long",
                "strength":"STRONG","price":p,"rsi":r["rsi"]})
            last["bu"]=i
        elif p<pl*(1-bp/100) and vol_ok and (i-last["bd"])>=cd:
            signals.append({"idx":i,"time":t,"strategy":"V2_MagicQuant自研",
                "trigger":"breakout_down","direction":"short",
                "strength":"STRONG","price":p,"rsi":r["rsi"]})
            last["bd"]=i

    return pd.DataFrame(signals)


# ══════════════════════════════════════════════════════════════════
#  策略 V3: 量价组合
#  来源: MagicQuant 自研
# ══════════════════════════════════════════════════════════════════
def strategy_v3(df, params):
    """
    来源: MagicQuant 自研
    """
    vt=params["vol_threshold"]; pc=params["price_chg"]
    cd=params["cooldown"]; re=params["rsi_extreme"]

    signals=[]
    last={"vu":-9999,"vd":-9999}

    for i in range(30, len(df)):
        r=df.iloc[i]
        vr=r["vol_ratio"]; c2=r["chg_2m"]; rs=r["rsi"]
        p=r["close"]; t=r["time_key"]
        if pd.isna(vr) or pd.isna(c2) or pd.isna(rs): continue
        if vr<vt or abs(c2)<pc: continue
        if re:
            if c2>0 and rs>70: continue
            if c2<0 and rs<30: continue

        d="long" if c2>0 else "short"
        k="vu" if d=="long" else "vd"
        if (i-last[k])>=cd:
            signals.append({"idx":i,"time":t,"strategy":"V3_MagicQuant自研",
                "trigger":"vol_price","direction":d,
                "strength":"STRONG" if vr>=vt*1.5 else "WEAK",
                "price":p,"rsi":rs})
            last[k]=i

    return pd.DataFrame(signals)


# ══════════════════════════════════════════════════════════════════
#  策略 V4: 开盘区间突破 ORB
#  来源: Zarattini, Barbon & Aziz (2024) via QuantConnect
#         ORBSetups.com 回测数据库
#         TradeThātSwing ORB Strategy Guide
# ══════════════════════════════════════════════════════════════════
def strategy_v4(df, params):
    """
    来源:
      - Zarattini, Barbon & Aziz (2024) "Opening Range Breakout for Stocks in Play"
        QuantConnect: quantconnect.com/research/18444
        结论: 加量比过滤后 Sharpe ratio 2.4，接近beta=0
      - ORBSetups.com: 150,000+ 历史回测数据集
        结论: 10:00-12:00 ET 信号最强，1PM后效果明显下降
      - TradeThātSwing: 15分钟开盘区间 + 5分钟收盘突破确认

    参数:
        orb_minutes:    开盘区间时长(分钟): 5/15/30
        vol_confirm:    是否需要量比确认
        vol_threshold:  量比门槛
        rsi_filter:     是否RSI过滤
        time_cutoff_h:  最晚入场时间(ET小时,13=1PM)
        cooldown:       冷却
    """
    om=params["orb_minutes"]; vc=params["vol_confirm"]
    vt=params["vol_threshold"]; rf=params["rsi_filter"]
    tc_h=params["time_cutoff_h"]; cd=params["cooldown"]

    # 先计算每天的开盘区间
    orb_cache = {}   # date -> (orb_high, orb_low)
    for date, grp in df.groupby("date"):
        orb_bars = grp[grp["day_minute"] < om]
        if len(orb_bars) == 0: continue
        orb_cache[date] = (orb_bars["high"].max(), orb_bars["low"].min())

    signals=[]
    last={"orb_u":-9999,"orb_d":-9999}

    for i in range(om+5, len(df)):
        r=df.iloc[i]; p=r["close"]; t=r["time_key"]
        date=r["date"]; rs=r["rsi"]; vr=r["vol_ratio"]

        if date not in orb_cache: continue
        orb_hi, orb_lo = orb_cache[date]

        # 时间过滤: 只在 09:30-time_cutoff ET 交易
        h=r["hour_et"]; m=r["minute_et"]
        if h < 9 or (h==9 and m<30): continue
        if h >= tc_h: continue

        # 只在开盘区间结束后才能触发
        if r["day_minute"] <= om: continue

        vol_ok = True
        if vc and not pd.isna(vr): vol_ok = (vr >= vt)

        # 向上突破
        if p > orb_hi and vol_ok:
            rsi_ok = True
            if rf and not pd.isna(rs): rsi_ok = (rs > 50) and (rs < 75)
            if rsi_ok and (i-last["orb_u"])>=cd:
                signals.append({"idx":i,"time":t,
                    "strategy":"V4_ORB_Zarattini2024",
                    "trigger":"orb_breakout_up","direction":"long",
                    "strength":"STRONG","price":p,"rsi":rs,
                    "orb_hi":orb_hi,"orb_lo":orb_lo})
                last["orb_u"]=i

        # 向下突破
        elif p < orb_lo and vol_ok:
            rsi_ok = True
            if rf and not pd.isna(rs): rsi_ok = (rs < 50) and (rs > 25)
            if rsi_ok and (i-last["orb_d"])>=cd:
                signals.append({"idx":i,"time":t,
                    "strategy":"V4_ORB_Zarattini2024",
                    "trigger":"orb_breakout_down","direction":"short",
                    "strength":"STRONG","price":p,"rsi":rs,
                    "orb_hi":orb_hi,"orb_lo":orb_lo})
                last["orb_d"]=i

    return pd.DataFrame(signals)


# ══════════════════════════════════════════════════════════════════
#  策略 V5: VWAP + 量比做多做空
#  来源: LuxAlgo VWAP Entry Strategies (Feb 2025)
#         ForexTester VWAP Trading Guide (Jan 2026)
# ══════════════════════════════════════════════════════════════════
def strategy_v5(df, params):
    """
    来源:
      - LuxAlgo "VWAP Entry Strategies for Day Traders" (2025)
        luxalgo.com: 价格在VWAP上方+RSI>50 做多
      - ForexTester "6 Powerful VWAP Trading Strategies" (Jan 2026)
        核心: 价格突破VWAP + 成交量确认 = 买入信号
      - ChartSwatcher VWAP Guide: 大盘股偏离VWAP 2%回归

    参数:
        vwap_cross_confirm: 需要收盘穿越VWAP(不只是触碰)
        vol_threshold:      量比门槛
        rsi_min_long:       做多最低RSI
        rsi_max_long:       做多最高RSI(不追超买)
        rsi_max_short:      做空最高RSI
        rsi_min_short:      做空最低RSI
        cooldown:           冷却
    """
    vcc=params["vwap_cross_confirm"]; vt=params["vol_threshold"]
    rl=params["rsi_min_long"]; rml=params["rsi_max_long"]
    rms=params["rsi_max_short"]; rns=params["rsi_min_short"]
    cd=params["cooldown"]

    signals=[]
    last={"vl":-9999,"vs":-9999}

    for i in range(30, len(df)):
        r=df.iloc[i]; p=r["close"]; t=r["time_key"]
        vwap=r["vwap"]; rs=r["rsi"]; vr=r["vol_ratio"]
        if pd.isna(vwap) or pd.isna(rs) or pd.isna(vr): continue

        # 量比确认
        if vr < vt: continue

        prev_close = df.iloc[i-1]["close"]
        prev_vwap  = df.iloc[i-1]["vwap"] if not pd.isna(df.iloc[i-1]["vwap"]) else vwap

        # 做多: 价格从下方穿越 VWAP + RSI 在合理区间
        if p > vwap:
            crossed = (prev_close <= prev_vwap) if vcc else True
            rsi_ok  = rl <= rs <= rml
            if crossed and rsi_ok and (i-last["vl"])>=cd:
                signals.append({"idx":i,"time":t,
                    "strategy":"V5_VWAP_LuxAlgo2025",
                    "trigger":"vwap_cross_up","direction":"long",
                    "strength":"STRONG" if vr>=vt*1.5 else "WEAK",
                    "price":p,"rsi":rs,"vwap":vwap})
                last["vl"]=i

        # 做空: 价格从上方跌破 VWAP
        elif p < vwap:
            crossed = (prev_close >= prev_vwap) if vcc else True
            rsi_ok  = rns <= rs <= rms
            if crossed and rsi_ok and (i-last["vs"])>=cd:
                signals.append({"idx":i,"time":t,
                    "strategy":"V5_VWAP_LuxAlgo2025",
                    "trigger":"vwap_cross_down","direction":"short",
                    "strength":"STRONG" if vr>=vt*1.5 else "WEAK",
                    "price":p,"rsi":rs,"vwap":vwap})
                last["vs"]=i

    return pd.DataFrame(signals)


# ══════════════════════════════════════════════════════════════════
#  策略 V6: VWAP 均值回归
#  来源: ChartSwatcher "A Practical Guide to VWAP Strategy" (Sep 2025)
#         QuantifiedStrategies RSI Mean Reversion
# ══════════════════════════════════════════════════════════════════
def strategy_v6(df, params):
    """
    来源:
      - ChartSwatcher "A Practical Guide to VWAP Strategy Trading" (Sep 2025)
        chartswatcher.com: 价格偏离VWAP后回归有统计优势
        "Backtests on SPY using mean reversion logic showed a positive edge"
      - QuantifiedStrategies RSI Strategy: RSI均值回归在股票上效果最好
        quantifiedstrategies.com: RSI<30买入，RSI>70卖出

    参数:
        vwap_dev_pct:   偏离VWAP百分比触发(%)
        rsi_oversold:   超卖RSI门槛(做多)
        rsi_overbought: 超买RSI门槛(做空)
        cooldown:       冷却
        choppy_filter:  震荡过滤
    """
    vd=params["vwap_dev_pct"]; ro=params["rsi_oversold"]
    rob=params["rsi_overbought"]; cd=params["cooldown"]
    cf=params["choppy_filter"]

    signals=[]
    last={"mr_l":-9999,"mr_s":-9999}

    for i in range(30, len(df)):
        r=df.iloc[i]; p=r["close"]; t=r["time_key"]
        vwap=r["vwap"]; rs=r["rsi"]
        choppy=(r["chop"]>cf) if cf>0 and not pd.isna(r["chop"]) else False
        if pd.isna(vwap) or pd.isna(rs) or vwap<=0: continue
        if choppy: continue   # 震荡市才做回归，但极度震荡除外

        dev_pct = (p - vwap) / vwap * 100

        # 价格大幅低于VWAP + RSI超卖 → 预期回归，做多
        if dev_pct <= -vd and rs <= ro:
            if (i-last["mr_l"])>=cd:
                signals.append({"idx":i,"time":t,
                    "strategy":"V6_VWAP均值回归_ChartSwatcher2025",
                    "trigger":"mean_revert_long","direction":"long",
                    "strength":"STRONG" if rs<=25 else "WEAK",
                    "price":p,"rsi":rs,"vwap":vwap,"dev_pct":dev_pct})
                last["mr_l"]=i

        # 价格大幅高于VWAP + RSI超买 → 预期回归，做空
        elif dev_pct >= vd and rs >= rob:
            if (i-last["mr_s"])>=cd:
                signals.append({"idx":i,"time":t,
                    "strategy":"V6_VWAP均值回归_ChartSwatcher2025",
                    "trigger":"mean_revert_short","direction":"short",
                    "strength":"STRONG" if rs>=75 else "WEAK",
                    "price":p,"rsi":rs,"vwap":vwap,"dev_pct":dev_pct})
                last["mr_s"]=i

    return pd.DataFrame(signals)


# ══════════════════════════════════════════════════════════════════
#  评估 + 过滤
# ══════════════════════════════════════════════════════════════════
def evaluate(signals_df, prices, window=EVAL_WINDOW):
    if signals_df is None or len(signals_df)==0:
        return {"total":0,"win_rate":0,"signals_per_day":0,
                "max_loss_streak":0,"avg_win":0,"avg_loss":0}

    results=[]
    for _, sig in signals_df.iterrows():
        idx=int(sig["idx"]); entry=float(sig["price"]); d=sig["direction"]
        ie=min(idx+window, len(prices)-1)
        ex=float(prices[ie]); chg=(ex-entry)/entry*100
        win=(chg>0) if d=="long" else (chg<0)
        results.append({"win":win,"pnl":abs(chg) if win else -abs(chg),"chg":chg})

    rdf=pd.DataFrame(results)
    total=len(rdf); wins=rdf["win"].sum()
    days=signals_df["time"].dt.date.nunique() if hasattr(signals_df["time"].iloc[0],"date") else 1
    spd=round(total/max(days,1),1)

    streak=mx=0
    for w in rdf["win"]:
        if not w: streak+=1; mx=max(mx,streak)
        else: streak=0

    return {
        "total":total, "win_rate":round(wins/total,4),
        "signals_per_day":spd, "max_loss_streak":mx,
        "avg_win":round(rdf[rdf["win"]]["chg"].mean(),2) if wins>0 else 0,
        "avg_loss":round(rdf[~rdf["win"]]["chg"].mean(),2) if (total-wins)>0 else 0,
    }

def passes_filter(s):
    return (s["win_rate"]>=TARGET_WIN_RATE and
            s["signals_per_day"]>=TARGET_MIN_SIG and
            s["signals_per_day"]<=TARGET_MAX_SIG and
            s["total"]>=50 and s["max_loss_streak"]<=8)


# ══════════════════════════════════════════════════════════════════
#  参数空间
# ══════════════════════════════════════════════════════════════════
V1_SPACE={
    "trend_chg":[1.0,1.5,2.0,2.5,3.0],"trend_strong":[2.0,2.5,3.0],
    "rapid_pct":[0.8,1.0,1.5,2.0],"cooldown":[20,40,60],
    "rsi_filter":[True,False],"choppy_filter":[2.0,3.0,0],
}
V2_SPACE={
    "breakout_pct":[0.3,0.5,0.8,1.0,1.5],"vol_confirm":[True,False],
    "vol_threshold":[1.5,2.0,2.5],"cooldown":[20,40,60],
}
V3_SPACE={
    "vol_threshold":[1.5,2.0,2.5,3.0],"price_chg":[0.3,0.5,0.8,1.0],
    "cooldown":[20,40,60],"rsi_extreme":[True,False],
}
V4_SPACE={
    "orb_minutes":[5,15,30],
    "vol_confirm":[True,False],
    "vol_threshold":[1.5,2.0,2.5],
    "rsi_filter":[True,False],
    "time_cutoff_h":[12,13,14],   # 12=noon, 13=1PM, 14=2PM ET
    "cooldown":[20,40,60],
}
V5_SPACE={
    "vwap_cross_confirm":[True,False],
    "vol_threshold":[1.2,1.5,2.0],
    "rsi_min_long":[45,50,55],
    "rsi_max_long":[65,70,75],
    "rsi_max_short":[55,50,45],
    "rsi_min_short":[25,30,35],
    "cooldown":[20,40,60],
}
V6_SPACE={
    "vwap_dev_pct":[1.0,1.5,2.0,2.5],
    "rsi_oversold":[30,35,40],
    "rsi_overbought":[60,65,70],
    "cooldown":[20,40,60],
    "choppy_filter":[2.0,3.0,0],
}

def param_combos(space):
    keys=list(space.keys()); vals=list(space.values())
    return [dict(zip(keys,c)) for c in itertools.product(*vals)]


# ══════════════════════════════════════════════════════════════════
#  3折 Walk-Forward 寻优
# ══════════════════════════════════════════════════════════════════
FOLDS = [
    (0.60, 0.40),  # 折1: 前60%训练, 后40%验证
    (0.70, 0.30),  # 折2: 前70%训练, 后30%验证
    (0.80, 0.20),  # 折3: 前80%训练, 后20%验证
]

def optimize_3fold(df, strategy_fn, space, name):
    combos=param_combos(space)
    dates=sorted(df["date"].unique()); n=len(dates)
    print(f"\n  [{name}] {len(combos)} 种参数组合 × {len(FOLDS)} 折...")

    results=[]; passed=0
    for ci, params in enumerate(combos):
        if (ci+1)%200==0:
            print(f"    进度 {ci+1}/{len(combos)}  通过 {passed}", end="\r")

        fold_stats=[]
        for train_r, val_r in FOLDS:
            t_end=int(n*train_r)
            train_dates=dates[:t_end]; val_dates=dates[t_end:]
            df_tr=df[df["date"].isin(train_dates)]
            df_vl=df[df["date"].isin(val_dates)]

            s_tr=strategy_fn(df_tr, params)
            st_tr=evaluate(s_tr, df_tr["close"].values)
            if not passes_filter(st_tr):
                fold_stats=None; break

            s_vl=strategy_fn(df_vl, params)
            st_vl=evaluate(s_vl, df_vl["close"].values)
            fold_stats.append({"train":st_tr,"val":st_vl})

        if fold_stats is None: continue
        passed+=1

        # 3折平均验证胜率
        avg_val_wr=sum(f["val"]["win_rate"] for f in fold_stats)/len(fold_stats)
        min_val_wr=min(f["val"]["win_rate"] for f in fold_stats)
        all_pass=all(passes_filter(f["val"]) for f in fold_stats)

        results.append({
            "params":params, "folds":fold_stats,
            "avg_val_wr":avg_val_wr, "min_val_wr":min_val_wr,
            "all_folds_pass":all_pass,
        })

    print(f"\n    训练集通过: {passed}  全折验证通过: {sum(1 for r in results if r['all_folds_pass'])}")
    results.sort(key=lambda x: (x["all_folds_pass"], x["avg_val_wr"]), reverse=True)
    return results[:10]


# ══════════════════════════════════════════════════════════════════
#  HTML 模板
# ══════════════════════════════════════════════════════════════════
_HTML_CSS = (
    ":root{--g:#16a34a;--r:#dc2626;--gr:#6b7280;--bd:#e5e7eb;--bg:#f9fafb;--cd:#fff;--tx:#111827;--hd:#374151}"
    "*{box-sizing:border-box;margin:0;padding:0}"
    "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
    "background:var(--bg);color:var(--tx);padding:16px;line-height:1.6;font-size:15px}"
    ".wrap{max-width:820px;margin:0 auto}"
    "h1{font-size:1.35em;margin-bottom:4px}"
    "h2{font-size:1.05em;font-weight:700;color:var(--hd);margin:0 0 10px}"
    ".meta{color:var(--gr);font-size:.85em;margin-bottom:16px}"
    ".card{background:var(--cd);border:1px solid var(--bd);border-radius:8px;padding:14px 16px;margin-bottom:12px}"
    ".tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:.8em;font-weight:600}"
    ".bull{color:var(--g)}.bear{color:var(--r)}.neut{color:var(--gr)}"
    ".bull-bg{background:#dcfce7;color:var(--g)}.bear-bg{background:#fee2e2;color:var(--r)}"
    ".neut-bg{background:#f3f4f6;color:var(--gr)}"
    "table{width:100%;border-collapse:collapse;font-size:.9em;margin:8px 0}"
    "th{background:#f3f4f6;padding:7px 10px;border:1px solid var(--bd);color:var(--hd);font-weight:600;text-align:left}"
    "td{padding:6px 10px;border:1px solid var(--bd);vertical-align:top}"
    "tr:nth-child(even) td{background:#fafafa}"
    ".num{text-align:right}.ctr{text-align:center}"
    ".ok{color:var(--g);font-weight:600}.fail{color:var(--r);font-weight:600}.warn{color:#d97706}"
    "hr{border:none;border-top:1px solid var(--bd);margin:10px 0}"
    "pre{background:#f3f4f6;padding:10px;border-radius:4px;font-size:.85em;overflow-x:auto;white-space:pre-wrap}"
    "@media(max-width:500px){body{padding:10px;font-size:14px}th,td{padding:5px 7px}"
    ".card{padding:10px 12px}}"
)


def _html_page(title: str, body: str) -> str:
    return (
        f'<!DOCTYPE html><html lang="zh"><head>'
        f'<meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}</title>'
        f'<style>{_HTML_CSS}</style>'
        f'</head><body><div class="wrap">{body}</div></body></html>'
    )


# ══════════════════════════════════════════════════════════════════
#  报告生成
# ══════════════════════════════════════════════════════════════════
def fmt_result(r, rank):
    p = r["params"]; af = r["all_folds_pass"]
    tag_cls = "bull-bg" if af else "warn"
    tag_txt = "全折通过" if af else "部分折通过"
    avg_cls = "ok" if r["avg_val_wr"] >= 0.65 else ("warn" if r["avg_val_wr"] >= 0.55 else "fail")

    param_rows = "".join(
        f"<tr><td>{k}</td><td class='num'>{v}</td></tr>"
        for k, v in p.items()
    )
    fold_rows = ""
    for fi, (train_r, _) in enumerate(FOLDS):
        if fi >= len(r["folds"]): break
        fd = r["folds"][fi]; tr = fd["train"]; vl = fd["val"]
        vl_cls = "ok" if vl["win_rate"] >= 0.65 else ("warn" if vl["win_rate"] >= 0.55 else "fail")
        fold_rows += (
            f"<tr><td>折{fi+1}（训练{int(train_r*100)}%）</td>"
            f"<td class='num'>{tr['win_rate']*100:.1f}%</td>"
            f"<td class='num {vl_cls}'>{vl['win_rate']*100:.1f}%</td>"
            f"<td class='num'>{vl['signals_per_day']}</td>"
            f"<td class='num'>{vl['max_loss_streak']}</td></tr>"
        )

    return (
        f"<div class='card' style='margin-bottom:8px'>"
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px'>"
        f"<strong>#{rank}</strong>"
        f" <span>平均验证胜率 <span class='{avg_cls}'>{r['avg_val_wr']*100:.1f}%</span></span>"
        f" <span>最低折 {r['min_val_wr']*100:.1f}%</span>"
        f" <span class='tag {tag_cls}'>{tag_txt}</span></div>"
        f"<table><tr><th>参数</th><th class='num'>值</th></tr>{param_rows}</table>"
        f"<table style='margin-top:8px'>"
        f"<tr><th>折次</th><th class='num'>训练胜率</th><th class='num'>验证胜率</th>"
        f"<th class='num'>信号/天</th><th class='num'>最大连败</th></tr>"
        f"{fold_rows}</table></div>"
    )


def generate_report(all_results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    strategy_labels = {
        "V1": "V1: direction_trend+rapid_move (MagicQuant自研)",
        "V2": "V2: 日内高低突破 (MagicQuant自研)",
        "V3": "V3: 量价组合 (MagicQuant自研)",
        "V4": "V4: 开盘区间突破ORB (Zarattini et al.2024)",
        "V5": "V5: VWAP穿越+量比 (LuxAlgo 2025)",
        "V6": "V6: VWAP均值回归 (ChartSwatcher 2025)",
    }

    sections = ""
    global_best = None; global_best_name = ""
    for key, (name, results) in zip(
        ["V1","V2","V3","V4","V5","V6"],
        [(n, r) for n, r in all_results.items()]
    ):
        label = strategy_labels.get(key, name)
        if results:
            best = results[0]
            best_cls = "ok" if best["avg_val_wr"] >= 0.65 else ("warn" if best["avg_val_wr"] >= 0.55 else "fail")
            top_html = "".join(fmt_result(r, i) for i, r in enumerate(results[:3], 1))
            sections += (
                f"<div class='card'><h2>{label}</h2>"
                f"<p>最优平均验证胜率: <span class='{best_cls}'>"
                f"<strong>{best['avg_val_wr']*100:.1f}%</strong></span>"
                f"  最低折: {best['min_val_wr']*100:.1f}%</p><hr>{top_html}</div>"
            )
            if best["all_folds_pass"] and (global_best is None or best["avg_val_wr"] > global_best["avg_val_wr"]):
                global_best = best; global_best_name = label
        else:
            sections += (
                f"<div class='card'><h2>{label}</h2>"
                f"<p class='fail'>❌ 无参数组合通过训练集+验证集过滤</p></div>"
            )

    if global_best:
        best_params = json.dumps(global_best["params"], indent=2, ensure_ascii=False)
        summary = (
            f"<div class='card'><h2>总结</h2>"
            f"<p class='ok'><strong>✅ 推荐上线策略: {global_best_name}</strong></p>"
            f"<p>平均验证集胜率: <strong class='ok'>{global_best['avg_val_wr']*100:.1f}%</strong>"
            f"  最低折胜率: <strong>{global_best['min_val_wr']*100:.1f}%</strong></p>"
            f"<p style='margin-top:8px'><strong>最优参数:</strong></p>"
            f"<pre>{best_params}</pre></div>"
        )
    else:
        summary = (
            "<div class='card'><h2>总结</h2>"
            "<p class='warn'>⚠️ 当前没有策略同时满足所有条件</p>"
            "<p>建议: 将目标胜率从65%降至60%重新寻优</p></div>"
        )

    body = (
        f"<h1>MagicQuant 策略寻优报告 v2.0</h1>"
        f"<div class='meta'>生成时间: {now}"
        f" &nbsp;·&nbsp; 目标: 胜率>{TARGET_WIN_RATE*100:.0f}%"
        f" 信号{TARGET_MIN_SIG}-{TARGET_MAX_SIG}条/天"
        f" &nbsp;·&nbsp; 方法: 3折Walk-Forward验证</div>"
        f"{summary}{sections}"
    )
    return _html_page("MagicQuant 策略寻优报告 v2.0", body)


# ══════════════════════════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════════════════════════
def main():
    print("="*60)
    print("  MagicQuant 策略寻优 v2.0")
    print(f"  目标: 胜率>{TARGET_WIN_RATE*100:.0f}%  信号{TARGET_MIN_SIG}-{TARGET_MAX_SIG}条/天")
    print("  策略: V1自研 V2自研 V3自研 V4_ORB V5_VWAP穿越 V6_VWAP回归")
    print("  验证: 3折Walk-Forward")
    print("="*60)

    path=HIST_DIR/"RKLB_1m.csv"
    if not path.exists():
        print(f"❌ 找不到 {path}，请先运行 fetch_and_backtest.py")
        return

    print("\n  加载数据...")
    df=prepare_data(path)
    dates=sorted(df["date"].unique())
    print(f"  {len(df)} 条  {len(dates)} 个交易日")

    combos_count={
        "V1":len(param_combos(V1_SPACE)),
        "V2":len(param_combos(V2_SPACE)),
        "V3":len(param_combos(V3_SPACE)),
        "V4":len(param_combos(V4_SPACE)),
        "V5":len(param_combos(V5_SPACE)),
        "V6":len(param_combos(V6_SPACE)),
    }
    total_combos=sum(combos_count.values())
    print(f"\n  参数组合总数: {total_combos}")
    for k,v in combos_count.items(): print(f"    {k}: {v}")
    print(f"  预计时间: {total_combos//60+5}-{total_combos//40+10} 分钟")

    all_results={}
    strategies={
        "V1":(strategy_v1, V1_SPACE),
        "V2":(strategy_v2, V2_SPACE),
        "V3":(strategy_v3, V3_SPACE),
        "V4":(strategy_v4, V4_SPACE),
        "V5":(strategy_v5, V5_SPACE),
        "V6":(strategy_v6, V6_SPACE),
    }

    for key,(fn,space) in strategies.items():
        print(f"\n{'='*60}")
        all_results[key]=optimize_3fold(df, fn, space, key)

    print(f"\n{'='*60}")
    print("  生成报告...")
    report=generate_report(all_results)

    rp=BT_DIR/"optimizer_report.html"
    with open(rp,"w",encoding="utf-8") as f: f.write(report)
    print(f"  报告: {rp}")

    # 保存最优
    best_list=[]
    for k,results in all_results.items():
        if results:
            best_list.append({
                "strategy":k,
                "avg_val_wr":results[0]["avg_val_wr"],
                "all_folds_pass":results[0]["all_folds_pass"],
                "params":results[0]["params"],
            })
    best_list.sort(key=lambda x:(x["all_folds_pass"],x["avg_val_wr"]),reverse=True)
    if best_list:
        bp=BT_DIR/"best_params_v2.json"
        with open(bp,"w",encoding="utf-8") as f:
            json.dump(best_list[0],f,indent=2,ensure_ascii=False)
        print(f"  最优参数: {bp}")

    print("\n✅ 完成！用浏览器打开报告查看详细结果。")

if __name__=="__main__":
    main()
