"""
MagicQuant — 开盘简报历史回测
用 RKLB 365天历史数据验证每日偏向判断的准确率

逻辑:
  对每个交易日，用"该日之前"的数据计算偏向判断
  看"该日"实际涨跌是否和判断一致
  统计整体准确率 / 按评分分段的准确率

用法:
    cd C:\\MagicQuant
    python backtest_briefing.py

输出:
    data/backtest/briefing_backtest.md
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
HIST_DIR = BASE_DIR / "data" / "historical"
BT_DIR   = BASE_DIR / "data" / "backtest"
BT_DIR.mkdir(parents=True, exist_ok=True)


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
#  指标计算（日线级别）
# ══════════════════════════════════════════════════════════════════
def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[-i] - closes[-i-1]
        if d > 0: gains  += d
        else:     losses -= d
    if losses == 0: return 100.0
    rs = (gains / period) / (losses / period)
    return round(100 - 100 / (1 + rs), 1)


def calc_bias_score(closes, highs, lows, volumes):
    """
    和 daily_briefing.py 完全相同的评分逻辑
    输入: 截止昨日的历史数据列表
    输出: score(0-12), bias, label
    """
    if len(closes) < 20:
        return None

    score   = 0
    details = []

    ma5  = sum(closes[-5:])  / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    rsi  = calc_rsi(closes)

    vol_3  = sum(volumes[-3:])  / 3
    vol_10 = sum(volumes[-10:]) / 10
    vol_ratio = round(vol_3 / vol_10, 2) if vol_10 > 0 else 1.0

    close     = closes[-1]
    prev_high = highs[-1]
    prev_low  = lows[-1]
    mom_3d    = (closes[-1] - closes[-4]) / closes[-4] * 100 if len(closes) >= 4 else 0

    # 维度 1: 均线趋势
    if ma5 > ma20 * 1.005:   score += 2
    elif ma5 > ma20:          score += 1

    # 维度 2: 收盘 vs MA10
    if close > ma10 * 1.01:  score += 2
    elif close > ma10:        score += 1

    # 维度 3: RSI
    if 50 <= rsi <= 65:       score += 2
    elif 65 < rsi <= 75:      score += 1
    elif rsi > 75:            score -= 1

    # 维度 4: 量能
    if vol_ratio >= 1.3:      score += 2
    elif vol_ratio >= 1.0:    score += 1

    # 维度 5: 3日动量
    if mom_3d >= 3.0:         score += 2
    elif mom_3d >= 0:         score += 1

    # 维度 6: 收盘位置
    rng = prev_high - prev_low
    if rng > 0:
        pos = (close - prev_low) / rng
        if pos >= 0.7:        score += 2
        elif pos >= 0.4:      score += 1

    score = max(0, min(12, score))

    # v2 优化逻辑（基于回测数据分析）:
    # - 强烈看多: score≥8 且 RSI≤72（过滤超买反转，从53%→59%）
    # - 偏多: 仅 score=7（score 6 准确率仅38.9%，改中性）
    # - 强烈看空: score≤2 且 RSI≥35（过滤超卖反弹，从50%→64%）
    # - 其余全部中性: score 3-6 / RSI超买的高分 / RSI超卖的低分
    if score >= 8 and rsi <= 72:
        bias, label = "bullish_strong", "强烈看多"
    elif score == 7:
        bias, label = "bullish_weak",   "偏多"
    elif score <= 2 and rsi >= 35:
        bias, label = "bearish_strong",  "强烈看空"
    else:
        bias, label = "neutral",        "中性"

    return {"score": score, "bias": bias, "label": label, "rsi": round(rsi, 1)}


# ══════════════════════════════════════════════════════════════════
#  主回测逻辑
# ══════════════════════════════════════════════════════════════════
def run_backtest():
    csv_path = HIST_DIR / "RKLB_1m.csv"
    if not csv_path.exists():
        print(f"❌ 找不到 {csv_path}")
        print("   请先运行 fetch_and_backtest.py 拉取历史数据")
        return

    print("  加载 RKLB 历史数据...")
    df = pd.read_csv(csv_path)
    df["time_key"] = pd.to_datetime(df["time_key"])
    df["close"]    = df["close"].astype(float)
    df["high"]     = df["high"].astype(float)
    df["low"]      = df["low"].astype(float)
    df["volume"]   = df["volume"].astype(float)
    df["date"]     = df["time_key"].dt.date

    # 聚合成日线
    daily = df.groupby("date").agg(
        open=("close",  "first"),
        high=("high",   "max"),
        low=("low",     "min"),
        close=("close", "last"),
        volume=("volume","sum"),
    ).reset_index()
    daily = daily.sort_values("date").reset_index(drop=True)

    print(f"  共 {len(daily)} 个交易日")
    print(f"  时间范围: {daily['date'].iloc[0]} ~ {daily['date'].iloc[-1]}")

    # 需要至少 21 天历史才能计算指标
    START_IDX = 21
    results   = []

    for i in range(START_IDX, len(daily)):
        # 用"昨日及之前"的数据做判断（不能看当天）
        hist    = daily.iloc[:i]
        today   = daily.iloc[i]

        closes  = list(hist["close"].values)
        highs   = list(hist["high"].values)
        lows    = list(hist["low"].values)
        volumes = list(hist["volume"].values)

        bias = calc_bias_score(closes, highs, lows, volumes)
        if bias is None:
            continue

        # 当天实际涨跌
        today_chg = (today["close"] - today["open"]) / today["open"] * 100
        today_dir = "up" if today_chg > 0 else "down"

        # 判断是否正确
        if bias["bias"] in ("bullish_strong", "bullish_weak"):
            predicted_dir = "up"
        elif bias["bias"] in ("bearish_strong", "bearish_weak"):
            predicted_dir = "down"
        else:
            predicted_dir = "neutral"  # 中性不计入方向准确率

        correct = (predicted_dir == today_dir) if predicted_dir != "neutral" else None

        results.append({
            "date":          str(today["date"]),
            "score":         bias["score"],
            "bias":          bias["bias"],
            "label":         bias["label"],
            "predicted_dir": predicted_dir,
            "actual_chg":    round(today_chg, 2),
            "actual_dir":    today_dir,
            "correct":       correct,
            "today_open":    today["open"],
            "today_close":   today["close"],
        })

    df_results = pd.DataFrame(results)

    # ── 统计分析 ─────────────────────────────────────────────
    # 剔除中性判断（不统计准确率）
    directional = df_results[df_results["predicted_dir"] != "neutral"].copy()
    neutral_cnt = len(df_results) - len(directional)

    total       = len(directional)
    correct_cnt = directional["correct"].sum()
    win_rate    = round(correct_cnt / total * 100, 1) if total > 0 else 0

    # 按评分段统计
    def score_group(s):
        if s >= 8:  return "8-12 强烈看多"
        if s >= 6:  return "6-7  偏多"
        if s == 5:  return "5    中性"
        if s >= 3:  return "3-4  偏空"
        return              "0-2  强烈看空"

    df_results["score_group"] = df_results["score"].apply(score_group)
    by_score = (
        directional.groupby(directional["score"].apply(score_group))
        .agg(count=("correct","count"),
             win=("correct","sum"),
             avg_chg=("actual_chg","mean"))
        .reset_index()
        .rename(columns={"score": "score_group"})
    )
    by_score["win_rate"] = (by_score["win"] / by_score["count"] * 100).round(1)
    by_score = by_score.sort_values("score_group")

    # 按标签统计
    by_label = (
        directional.groupby("label")
        .agg(count=("correct","count"),
             win=("correct","sum"),
             avg_chg=("actual_chg","mean"))
        .reset_index()
    )
    by_label["win_rate"] = (by_label["win"] / by_label["count"] * 100).round(1)

    # 看多 vs 看空
    bullish = directional[directional["predicted_dir"]=="up"]
    bearish = directional[directional["predicted_dir"]=="down"]
    bull_wr = round(bullish["correct"].mean()*100, 1) if len(bullish)>0 else 0
    bear_wr = round(bearish["correct"].mean()*100, 1) if len(bearish)>0 else 0

    # ── 生成 HTML 报告 ─────────────────────────────────────────
    def _wr_cls(wr):
        return "ok" if wr >= 60 else ("warn" if wr >= 50 else "fail")

    def _label_cls(lbl):
        return "bull-bg" if "看多" in lbl else ("bear-bg" if "看空" in lbl else "neut-bg")

    rows_score = ""
    for _, row in by_score.iterrows():
        rows_score += (
            f"<tr><td>{row['score_group']}</td>"
            f"<td class='num'>{row['count']}</td>"
            f"<td class='num {_wr_cls(row['win_rate'])}'>{row['win_rate']}%</td>"
            f"<td class='num'>{row['avg_chg']:+.2f}%</td></tr>"
        )

    rows_label = ""
    for _, row in by_label.iterrows():
        rows_label += (
            f"<tr><td><span class='tag {_label_cls(row['label'])}'>{row['label']}</span></td>"
            f"<td class='num'>{row['count']}</td>"
            f"<td class='num {_wr_cls(row['win_rate'])}'>{row['win_rate']}%</td>"
            f"<td class='num'>{row['avg_chg']:+.2f}%</td></tr>"
        )

    rows_detail = ""
    for _, row in df_results.tail(20).iterrows():
        if row["correct"] == True:
            ok_html = "<span class='ok'>✅</span>"
        elif row["correct"] == False:
            ok_html = "<span class='fail'>❌</span>"
        else:
            ok_html = "<span class='neut'>➡️ 中性</span>"
        chg_cls = "bull" if row["actual_chg"] > 0 else "bear"
        rows_detail += (
            f"<tr><td>{row['date']}</td>"
            f"<td><span class='tag {_label_cls(row['label'])}'>{row['label']}</span></td>"
            f"<td class='ctr'>{row['score']}</td>"
            f"<td class='num {chg_cls}'>{row['actual_chg']:+.2f}%</td>"
            f"<td class='ctr'>{ok_html}</td></tr>"
        )

    if win_rate >= 60:
        conc_cls, conc_icon = "ok", "✅"
        conc_txt = f"总体准确率 {win_rate}% — 开盘简报具有实际参考价值"
    elif win_rate >= 55:
        conc_cls, conc_icon = "warn", "⚠️"
        conc_txt = f"总体准确率 {win_rate}% — 略优于随机，有一定参考价值"
    else:
        conc_cls, conc_icon = "fail", "❌"
        conc_txt = f"总体准确率 {win_rate}% — 接近随机，建议优化评分逻辑"

    extra_conc = ""
    if not by_score.empty:
        best_seg = by_score.loc[by_score["win_rate"].idxmax()]
        if best_seg["win_rate"] >= 60:
            extra_conc += (
                f"<p>📌 最准确判断段: <strong>{best_seg['score_group']}</strong>"
                f" (准确率 {best_seg['win_rate']}%，样本 {int(best_seg['count'])} 天)</p>"
            )
        worst_seg = by_score.loc[by_score["win_rate"].idxmin()]
        if worst_seg["win_rate"] < 50:
            extra_conc += (
                f"<p class='warn'>⚠️ 最不可靠: <strong>{worst_seg['score_group']}</strong>"
                f" (准确率 {worst_seg['win_rate']}%，建议此段改为中性观望)</p>"
            )

    wr_cls = _wr_cls(win_rate)
    body = (
        f"<h1>RKLB 开盘简报 历史回测报告</h1>"
        f"<div class='meta'>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f" &nbsp;·&nbsp; 数据范围: {df_results['date'].iloc[0]} ~ {df_results['date'].iloc[-1]}"
        f" &nbsp;·&nbsp; 样本天数: {len(df_results)} 天（排除中性 {neutral_cnt} 天）</div>"

        f"<div class='card'><h2>总体准确率</h2><table>"
        f"<tr><th>指标</th><th class='num'>数值</th></tr>"
        f"<tr><td>有效判断天数</td><td class='num'>{total} 天</td></tr>"
        f"<tr><td>方向正确</td><td class='num'>{correct_cnt} 天</td></tr>"
        f"<tr><td><strong>总体准确率</strong></td>"
        f"<td class='num {wr_cls}'><strong>{win_rate}%</strong></td></tr>"
        f"<tr><td>看多判断准确率</td>"
        f"<td class='num {_wr_cls(bull_wr)}'>{bull_wr}% ({len(bullish)} 次)</td></tr>"
        f"<tr><td>看空判断准确率</td>"
        f"<td class='num {_wr_cls(bear_wr)}'>{bear_wr}% ({len(bearish)} 次)</td></tr>"
        f"<tr><td>中性观望（不参与统计）</td><td class='num'>{neutral_cnt} 天</td></tr>"
        f"</table></div>"

        f"<div class='card'><h2>按评分段准确率</h2><table>"
        f"<tr><th>评分</th><th class='num'>天数</th>"
        f"<th class='num'>准确率</th><th class='num'>平均实际涨跌</th></tr>"
        f"{rows_score}</table></div>"

        f"<div class='card'><h2>按判断标签准确率</h2><table>"
        f"<tr><th>标签</th><th class='num'>天数</th>"
        f"<th class='num'>准确率</th><th class='num'>平均实际涨跌</th></tr>"
        f"{rows_label}</table></div>"

        f"<div class='card'><h2>结论</h2>"
        f"<p class='{conc_cls}'>{conc_icon} {conc_txt}</p>"
        f"{extra_conc}</div>"

        f"<div class='card'><h2>最近 20 天明细</h2><table>"
        f"<tr><th>日期</th><th>判断</th><th class='ctr'>评分</th>"
        f"<th class='num'>实际涨跌</th><th class='ctr'>是否正确</th></tr>"
        f"{rows_detail}</table></div>"
    )
    report = _html_page("RKLB 开盘简报历史回测报告", body)

    # 保存
    out_path = BT_DIR / "briefing_backtest.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    # 保存明细 CSV
    csv_out = BT_DIR / "briefing_backtest_detail.csv"
    df_results.to_csv(csv_out, index=False)

    return report, win_rate, df_results


# ══════════════════════════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════════════════════════
def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 60)
    print("  MagicQuant 开盘简报历史回测")
    print("=" * 60)

    result = run_backtest()
    if result is None:
        return

    report, win_rate, df = result

    out_path = BT_DIR / "briefing_backtest.html"
    print(f"\n  ✅ 回测完成  总体准确率: {win_rate}%")
    print(f"  报告已保存: {out_path}")
    print(f"  用浏览器打开查看详细结果！")


if __name__ == "__main__":
    main()
