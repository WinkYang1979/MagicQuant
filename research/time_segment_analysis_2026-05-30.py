# -*- coding: utf-8 -*-
"""
RKLB 时段规律分析(只读, 不碰策略代码)
─────────────────────────────────────
用户方向: 按特殊时段切开找规律 + 近期加权。
分析维度:
  1. 按 ET 小时: 波动率(|1m收益|)、成交量 → 找密集/低迷时段
  2. RTH(9:30-16:00) vs 盘前(4:00-9:30) vs 隔夜(其余)
  3. 开盘首 30min vs 盘中 vs 尾盘 30min
  4. 周一开盘 vs 周五收盘 vs 普通日
  5. 近期加权: 近2周/近4周 vs 全样本 的同时段对比(看规律是否漂移)

时段→墨尔本: US开盘 9:30 ET = 墨尔本 23:30(May AEST); 盘前 4:00 ET = 墨尔本 18:00。
纯统计, 不下交易结论; 给策略设计提供"何时有波动可做/何时该避"的事实基础。
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_OUT = []
def emit(s=""):
    _OUT.append(str(s))

df = pd.read_csv(ROOT / "data" / "historical" / "RKLB_1m.csv")
df["dt"] = pd.to_datetime(df["time_key"])
df = df.sort_values("dt").reset_index(drop=True)
df["ret"] = df["close"].pct_change() * 100
df["absret"] = df["ret"].abs()
df["hh"] = df["dt"].dt.hour
df["mm"] = df["dt"].dt.minute
df["dow"] = df["dt"].dt.dayofweek   # 0=Mon
df["date"] = df["dt"].dt.date
df["minutes"] = df["hh"] * 60 + df["mm"]

RTH_S, RTH_E = 9*60+30, 16*60   # 9:30-16:00 ET


def seg(m):
    if RTH_S <= m < RTH_E:
        return "RTH"
    if 4*60 <= m < RTH_S:
        return "盘前"
    return "隔夜/盘后"


df["seg"] = df["minutes"].apply(seg)
last_date = df["dt"].max()
df["days_ago"] = (last_date - df["dt"]).dt.days


def block(title):
    emit("\n" + "="*60 + f"\n  {title}\n" + "="*60)


block("1. 按 ET 小时: 波动率 & 成交量(密集 vs 低迷)")
g = df.groupby("hh").agg(n=("absret","size"), 波动=("absret","mean"),
                         量=("volume","mean")).reset_index()
emit(f"{'ET时':>5}{'样本':>8}{'平均|1m收益|%':>14}{'平均成交量':>12}  分布")
mx = g["波动"].max()
for _, r in g.iterrows():
    bar = "#"*int(r["波动"]/mx*30)
    mel = (int(r["hh"])+14) % 24   # ET→墨尔本(+14h, May)
    emit(f"{int(r['hh']):>3}时{'':1}{int(r['n']):>8}{r['波动']:>14.3f}{r['量']:>12.0f}  {bar} (墨{mel:02d}时)")


block("2. RTH vs 盘前 vs 隔夜/盘后")
g2 = df.groupby("seg").agg(n=("absret","size"), 波动=("absret","mean"),
                           量=("volume","mean"), 均收益=("ret","mean")).reset_index()
emit(f"{'时段':>10}{'样本':>9}{'波动%':>9}{'成交量':>10}{'1m均收益%':>11}")
for _, r in g2.iterrows():
    emit(f"{r['seg']:>10}{int(r['n']):>9}{r['波动']:>9.3f}{r['量']:>10.0f}{r['均收益']:>11.4f}")


block("3. RTH 内: 开盘首30min / 盘中 / 尾盘30min")
rth = df[df["seg"]=="RTH"].copy()
def rthpart(m):
    if m < RTH_S+30: return "开盘30min"
    if m >= RTH_E-30: return "尾盘30min"
    return "盘中"
rth["part"] = rth["minutes"].apply(rthpart)
g3 = rth.groupby("part").agg(n=("absret","size"), 波动=("absret","mean"),
                             量=("volume","mean")).reset_index()
order={"开盘30min":0,"盘中":1,"尾盘30min":2}
g3=g3.sort_values("part",key=lambda s:s.map(order))
emit(f"{'区段':>12}{'样本':>9}{'波动%':>9}{'成交量':>10}")
for _,r in g3.iterrows():
    emit(f"{r['part']:>12}{int(r['n']):>9}{r['波动']:>9.3f}{r['量']:>10.0f}")


block("4. 周几 × RTH 波动(周一开盘 / 周五收盘)")
dow_cn=["周一","周二","周三","周四","周五","周六","周日"]
g4=rth.groupby("dow").agg(波动=("absret","mean"),量=("volume","mean"),均收益=("ret","mean")).reset_index()
emit(f"{'':>6}{'波动%':>9}{'成交量':>10}{'1m均收益%':>11}")
for _,r in g4.iterrows():
    emit(f"{dow_cn[int(r['dow'])]:>6}{r['波动']:>9.3f}{r['量']:>10.0f}{r['均收益']:>11.4f}")
# 周五尾盘 vs 周一开盘
fri_close=rth[(rth["dow"]==4)&(rth["minutes"]>=RTH_E-30)]
mon_open=rth[(rth["dow"]==0)&(rth["minutes"]<RTH_S+30)]
emit(f"\n  周五尾盘30min: 波动 {fri_close['absret'].mean():.3f}% 均收益 {fri_close['ret'].mean():+.4f}%")
emit(f"  周一开盘30min: 波动 {mon_open['absret'].mean():.3f}% 均收益 {mon_open['ret'].mean():+.4f}%")


block("5. 近期加权: 全样本 vs 近4周 vs 近2周(规律是否漂移)")
for label, days in [("全样本", 99999), ("近4周", 28), ("近2周", 14)]:
    sub = df[df["days_ago"] <= days]
    r = sub[sub["seg"]=="RTH"]
    op = r[r["minutes"]<RTH_S+30]
    emit(f"  {label:>6}(交易日~{sub['date'].nunique()}天): "
          f"RTH波动 {r['absret'].mean():.3f}% | 开盘30min波动 {op['absret'].mean():.3f}% | "
          f"RTH日均收益 {r.groupby('date')['ret'].sum().mean():+.2f}%")

emit("\n注: 数据 2025-05-19~2026-05-18; 波动=平均|1分钟收益|%; 墨尔本时间=ET+14h(5月AEST)。")
emit("用途: 给策略提供时段事实(何时有波动/何时低迷), 不直接当交易规则。")

from pathlib import Path as _P
_P(ROOT / "research" / "_timeseg_result.txt").write_text("\n".join(_OUT), encoding="utf-8")
print("\n".join(_OUT))
