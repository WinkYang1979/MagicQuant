"""
═══════════════════════════════════════════════════════════════════
  MagicQuant — verify_signals.py
  VERSION : v0.1.0
  DATE    : 2026-05-12

  精准复盘工具:读取 data/review/YYYY-MM-DD/triggers.json 的
  decision_context,逐条验证三类问题:

    1) 数据问题  — 用 decision_context.kline_data 重算 RSI,
                  对比 indicators_raw.rsi_14;差异 > 1.0 即标记
    2) 逻辑问题  — 指标算对了但方向判断有矛盾,如:
                  · long 信号 + RSI > 75 (超买追多)
                  · short 信号 + day_chg > 5% (强趋势中看空)
                  · RTH 信号 + is_today=False (盘前数据触发 RTH 信号)
    3) 时机问题  — 方向对但路径先大幅回撤,如:推送 long 信号后
                  30 分钟内先回撤 >1% 才反弹到目标

  输出:
    data/review/YYYY-MM-DD/verify_report.html  — 时间轴 + 详情
    data/review/YYYY-MM-DD/verify_summary.json — 分类统计
    控制台打印摘要

  用法:
    python verify_signals.py               # 复盘今天
    python verify_signals.py 2026-05-12    # 复盘指定日期
═══════════════════════════════════════════════════════════════════
"""
import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent
REVIEW_ROOT = BASE_DIR / "data" / "review"


# ─────────────────────────────────────────────────────────────────
#  数据加载
# ─────────────────────────────────────────────────────────────────
def load_triggers(date_str: str) -> list:
    path = REVIEW_ROOT / date_str / "triggers.json"
    if not path.exists():
        print(f"⚠️ {path} 不存在")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f) or []


def load_kline(date_str: str, ticker: str, period: str = "1m") -> Optional[list]:
    """加载归档的 K 线 (1m or 5m)"""
    short = ticker.replace("US.", "")
    path = REVIEW_ROOT / date_str / f"kline_{period}_{short}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
#  1) 数据问题:重算 RSI 验证一致性
# ─────────────────────────────────────────────────────────────────
def verify_rsi_consistency(record: dict) -> Optional[dict]:
    """
    用 decision_context.kline_data.bars 重新计算 RSI(14),
    对比 indicators_raw.rsi_14。差异 > 1.0 视为数据问题。
    """
    ctx = record.get("decision_context") or {}
    kl_data = ctx.get("kline_data") or {}
    ind = ctx.get("indicators_raw") or {}

    bars = kl_data.get("bars") or []
    stored_rsi = ind.get("rsi_14")
    if not bars or stored_rsi is None:
        return None
    if len(bars) < 15:
        return None  # 不够算 RSI(14)

    try:
        import pandas as pd
        from core.focus.micro_indicators import calc_rsi_fast
        closes = pd.Series([float(b["close"]) for b in bars])
        recalc = calc_rsi_fast(closes, 14)
        diff = abs(recalc - float(stored_rsi))
        if diff > 1.0:
            return {
                "type":      "data_issue",
                "subtype":   "rsi_mismatch",
                "stored":    stored_rsi,
                "recalc":    recalc,
                "diff":      round(diff, 2),
                "summary":   f"RSI 存储 {stored_rsi} vs 重算 {recalc} (差 {diff:.1f})",
            }
    except Exception as e:
        return {
            "type":     "data_issue",
            "subtype":  "rsi_recalc_failed",
            "summary":  f"RSI 重算失败: {e}",
        }
    return None


# ─────────────────────────────────────────────────────────────────
#  2) 逻辑问题:方向 vs 指标矛盾
# ─────────────────────────────────────────────────────────────────
def verify_direction_logic(record: dict) -> Optional[dict]:
    """检查方向判断与当时指标是否矛盾"""
    trigger = record.get("trigger", "")
    direction = record.get("direction", "")
    ctx = record.get("decision_context") or {}
    ind = ctx.get("indicators_raw") or {}
    price = ctx.get("price_context") or {}

    rsi = ind.get("rsi_14")
    is_today = ind.get("is_today", True)
    day_chg = price.get("day_change_pct")

    issues = []

    # 盘前 K 线触发 RTH 依赖信号
    rth_triggers = {"swing_top", "swing_bottom", "overbought_surge",
                    "near_resistance", "near_support"}
    if trigger in rth_triggers and is_today is False:
        issues.append(f"RTH 信号但 is_today=False (盘前 fallback 数据)")

    # long 信号 + RSI 超买
    if direction == "long" and rsi is not None and rsi > 75:
        issues.append(f"long 方向但 RSI={rsi} (超买区追多)")
    # short 信号 + RSI 超卖
    if direction == "short" and rsi is not None and rsi < 35:
        issues.append(f"short 方向但 RSI={rsi} (超卖区追空)")

    # short 信号 + 日内强势上涨
    if direction == "short" and day_chg is not None and day_chg >= 5.0:
        issues.append(f"short 方向但日内 +{day_chg:.1f}% (强趋势看空)")
    # long 信号 + 日内强势下跌
    if direction == "long" and day_chg is not None and day_chg <= -5.0:
        issues.append(f"long 方向但日内 {day_chg:.1f}% (强趋势看多)")

    # swing_bottom + 日内涨幅 > 5%
    if trigger == "swing_bottom" and day_chg is not None and day_chg > 5.0:
        issues.append(f"swing_bottom 但日内 +{day_chg:.1f}% (已大涨不存在底)")

    if issues:
        return {
            "type":    "logic_issue",
            "subtype": "direction_indicator_conflict",
            "details": issues,
            "summary": " / ".join(issues),
        }
    return None


# ─────────────────────────────────────────────────────────────────
#  3) 时机问题:推送后 30 分钟的价格走势
# ─────────────────────────────────────────────────────────────────
def verify_timing(record: dict, kline_1m: list) -> Optional[dict]:
    """
    用 1m K 线找推送后 30 分钟价格走势,判断:
      · 方向是否被验证 (long → 涨 / short → 跌)
      · 是否有显著反向回撤 (>1%) 才到达目标
    """
    if not kline_1m:
        return None

    direction = record.get("direction", "")
    if direction not in ("long", "short"):
        return None  # neutral/止盈类信号不验证方向

    ts_str = record.get("ts", "")
    ctx = record.get("decision_context") or {}
    price_ctx = ctx.get("price_context") or {}
    entry_px = price_ctx.get("current")
    if not entry_px or not ts_str:
        return None

    # 找推送 ts 对应的 1m bar 索引
    try:
        target_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

    # bar time_key 格式 "2026-05-12 10:31:00"
    start_idx = None
    for i, bar in enumerate(kline_1m):
        tk = bar.get("time_key", "")
        try:
            bar_dt = datetime.strptime(tk[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if bar_dt >= target_dt:
            start_idx = i
            break
    if start_idx is None:
        return None  # 推送时间在 K 线之后,无后续数据

    # 取后续 30 根 1m K 线
    window = kline_1m[start_idx:start_idx + 30]
    if len(window) < 5:
        return None  # 数据不足

    highs = [float(b["high"]) for b in window]
    lows  = [float(b["low"])  for b in window]
    max_px = max(highs)
    min_px = min(lows)
    last_px = float(window[-1]["close"])

    move_up_pct   = (max_px - entry_px) / entry_px * 100
    move_down_pct = (min_px - entry_px) / entry_px * 100

    # 方向验证
    if direction == "long":
        # 期望涨 → 看 max_px 比 entry 涨多少
        target_move = move_up_pct
        adverse_move = move_down_pct  # 负数,越小越坏
        verified = target_move >= 0.5
    else:  # short
        target_move = move_down_pct  # 负数,越小越好
        adverse_move = move_up_pct
        verified = target_move <= -0.5

    # 时机问题:方向对但路径上有显著反向回撤
    timing_issue = False
    timing_note = ""
    if verified and abs(adverse_move) >= 1.0:
        timing_issue = True
        timing_note = f"方向对但路径先反向 {adverse_move:+.2f}%"

    return {
        "type":            "timing_check",
        "direction":       direction,
        "entry_px":        entry_px,
        "max_after":       round(max_px, 4),
        "min_after":       round(min_px, 4),
        "last_after":      round(last_px, 4),
        "move_up_pct":     round(move_up_pct, 2),
        "move_down_pct":   round(move_down_pct, 2),
        "verified":        verified,
        "timing_issue":    timing_issue,
        "timing_note":     timing_note,
        "summary":         (
            f"方向{'✅对' if verified else '❌错'} · "
            f"30min 内 ↑{move_up_pct:+.2f}% / ↓{move_down_pct:+.2f}%"
            + (f" · {timing_note}" if timing_issue else "")
        ),
    }


# ─────────────────────────────────────────────────────────────────
#  主分析流程
# ─────────────────────────────────────────────────────────────────
def analyze(date_str: str) -> dict:
    triggers = load_triggers(date_str)
    if not triggers:
        return {"date": date_str, "count": 0, "records": [], "summary": {}}

    # 预加载所有 ticker 的 1m K 线
    tickers = list({t.get("ticker", "") for t in triggers if t.get("ticker")})
    kline_1m_map = {tk: load_kline(date_str, tk, "1m") for tk in tickers}

    analyzed = []
    summary = {
        "total":         len(triggers),
        "data_issues":   0,
        "logic_issues":  0,
        "timing_issues": 0,
        "verified_correct": 0,
        "wrong_direction":  0,
        "no_followup":   0,
    }

    for rec in triggers:
        result = {
            "record":     rec,
            "data_check":   verify_rsi_consistency(rec),
            "logic_check":  verify_direction_logic(rec),
            "timing_check": verify_timing(rec, kline_1m_map.get(rec.get("ticker"))),
        }
        if result["data_check"]:
            summary["data_issues"] += 1
        if result["logic_check"]:
            summary["logic_issues"] += 1
        tc = result["timing_check"]
        if tc:
            if tc.get("verified"):
                summary["verified_correct"] += 1
                if tc.get("timing_issue"):
                    summary["timing_issues"] += 1
            else:
                summary["wrong_direction"] += 1
        else:
            summary["no_followup"] += 1
        analyzed.append(result)

    return {"date": date_str, "count": len(triggers),
            "records": analyzed, "summary": summary}


# ─────────────────────────────────────────────────────────────────
#  HTML 报告生成
# ─────────────────────────────────────────────────────────────────
def render_html(analysis: dict) -> str:
    date_str = analysis["date"]
    s = analysis["summary"]
    rows = []
    for item in analysis["records"]:
        rec = item["record"]
        dc = item["data_check"]
        lc = item["logic_check"]
        tc = item["timing_check"]

        ts = rec.get("ts", "")
        trigger = rec.get("trigger", "")
        ticker = (rec.get("ticker") or "").replace("US.", "")
        direction = rec.get("direction", "")
        strength = rec.get("strength", "")
        ctx = rec.get("decision_context") or {}
        ind = ctx.get("indicators_raw") or {}
        price = ctx.get("price_context") or {}

        # 状态徽章
        badges = []
        if dc: badges.append('<span class="badge bad">数据</span>')
        if lc: badges.append('<span class="badge bad">逻辑</span>')
        if tc:
            if tc.get("verified"):
                if tc.get("timing_issue"):
                    badges.append('<span class="badge warn">时机</span>')
                else:
                    badges.append('<span class="badge good">方向对</span>')
            else:
                badges.append('<span class="badge bad">方向错</span>')
        else:
            badges.append('<span class="badge muted">无后续</span>')

        # 详情段
        problems = []
        if dc:
            problems.append(f"<li>📊 <b>数据问题</b>: {dc.get('summary')}</li>")
        if lc:
            problems.append(f"<li>🧠 <b>逻辑问题</b>: {lc.get('summary')}</li>")
        if tc and tc.get("timing_issue"):
            problems.append(f"<li>⏰ <b>时机问题</b>: {tc.get('timing_note')}</li>")
        if tc and not tc.get("verified"):
            problems.append(f"<li>🎯 <b>方向错误</b>: {tc.get('summary')}</li>")

        kl_bars = (ctx.get("kline_data") or {}).get("bars") or []
        last3 = kl_bars[-3:] if kl_bars else []
        kline_summary = " · ".join(
            f"{b.get('time','')[-8:-3]} C{b.get('close')}" for b in last3
        )

        timing_html = ""
        if tc:
            timing_html = (
                f"<div class='timing'>"
                f"入场 ${tc['entry_px']:.2f} → 30min ↑{tc['move_up_pct']:+.2f}% "
                f"/ ↓{tc['move_down_pct']:+.2f}% · 末价 ${tc['last_after']:.2f}"
                f"</div>"
            )

        rows.append(f"""
        <div class="card">
          <div class="row">
            <span class="ts">{ts}</span>
            <span class="ticker">{ticker}</span>
            <span class="trigger">{trigger}</span>
            <span class="dir {direction}">{direction or '—'}</span>
            <span class="strength">{strength}</span>
            {' '.join(badges)}
          </div>
          <div class="row meta">
            现价 ${price.get('current','—')} ·
            日内 {price.get('day_change_pct','—')}% ·
            RSI {ind.get('rsi_14','—')} ·
            vol_ratio {ind.get('vol_ratio','—')} ·
            is_today={ind.get('is_today')}
          </div>
          <div class="row kline">最近 5m K 线: {kline_summary}</div>
          {timing_html}
          {('<ul class="problems">' + ''.join(problems) + '</ul>') if problems else ''}
        </div>
        """)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>MagicQuant 复盘报告 {date_str}</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
          background: #0f1419; color: #c8d3e0; margin: 0; padding: 24px; }}
  h1 {{ color: #f0f3f6; }}
  .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
  .stat {{ background: #1a2230; padding: 12px 18px; border-radius: 8px; min-width: 120px; }}
  .stat .num {{ font-size: 28px; font-weight: 700; color: #ffd66e; }}
  .stat .lbl {{ font-size: 12px; color: #8b9bae; }}
  .card {{ background: #1a2230; padding: 14px; border-radius: 10px;
           margin-bottom: 12px; border-left: 4px solid #2a3445; }}
  .card .row {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
                margin-bottom: 6px; }}
  .ts {{ color: #6c7a8a; font-family: monospace; }}
  .ticker {{ color: #ffd66e; font-weight: 700; }}
  .trigger {{ color: #8ed1ff; font-family: monospace; font-size: 13px; }}
  .dir {{ padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
  .dir.long {{ background: #1e3a2e; color: #5eff9d; }}
  .dir.short {{ background: #3a1e1e; color: #ff7878; }}
  .dir.neutral {{ background: #2a3445; color: #c8d3e0; }}
  .strength {{ font-size: 11px; color: #8b9bae; }}
  .badge {{ padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; }}
  .badge.good {{ background: #1e3a2e; color: #5eff9d; }}
  .badge.bad  {{ background: #3a1e1e; color: #ff7878; }}
  .badge.warn {{ background: #3a2e1e; color: #ffb86b; }}
  .badge.muted{{ background: #2a3445; color: #6c7a8a; }}
  .meta {{ font-size: 12px; color: #8b9bae; font-family: monospace; }}
  .kline {{ font-size: 11px; color: #6c7a8a; font-family: monospace; }}
  .timing {{ font-size: 12px; color: #8ed1ff; margin: 6px 0; }}
  .problems {{ background: #221823; padding: 8px 14px; border-radius: 6px;
               margin: 8px 0 0 0; font-size: 13px; }}
  .problems li {{ margin: 4px 0; }}
</style>
</head>
<body>
<h1>🔍 MagicQuant 信号复盘 · {date_str}</h1>
<div class="summary">
  <div class="stat"><div class="num">{s['total']}</div><div class="lbl">总推送</div></div>
  <div class="stat"><div class="num">{s['data_issues']}</div><div class="lbl">数据问题</div></div>
  <div class="stat"><div class="num">{s['logic_issues']}</div><div class="lbl">逻辑问题</div></div>
  <div class="stat"><div class="num">{s['timing_issues']}</div><div class="lbl">时机问题</div></div>
  <div class="stat"><div class="num">{s['verified_correct']}</div><div class="lbl">方向已验证</div></div>
  <div class="stat"><div class="num">{s['wrong_direction']}</div><div class="lbl">方向错误</div></div>
  <div class="stat"><div class="num">{s['no_followup']}</div><div class="lbl">无后续数据</div></div>
</div>
<h2>时间轴</h2>
{''.join(rows) if rows else '<p>无触发记录</p>'}
</body>
</html>
"""
    return html


# ─────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MagicQuant 信号精准复盘")
    parser.add_argument("date", nargs="?", default=None,
                        help="复盘日期 YYYY-MM-DD (默认今天)")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")

    print(f"\n🔍 复盘 {date_str}")
    print(f"   读取 {REVIEW_ROOT / date_str / 'triggers.json'}")

    analysis = analyze(date_str)
    s = analysis["summary"]

    if analysis["count"] == 0:
        print("⚠️ 当日无触发记录")
        return

    print(f"\n📊 摘要")
    print(f"   总推送:     {s['total']}")
    print(f"   数据问题:   {s['data_issues']}")
    print(f"   逻辑问题:   {s['logic_issues']}")
    print(f"   时机问题:   {s['timing_issues']}")
    print(f"   方向已验证: {s['verified_correct']}")
    print(f"   方向错误:   {s['wrong_direction']}")
    print(f"   无后续数据: {s['no_followup']}")

    # 写 JSON summary + HTML
    out_dir = REVIEW_ROOT / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    # summary (去掉 record 完整内容以保持精简)
    summary_path = out_dir / "verify_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "date":    date_str,
            "summary": s,
            "issues":  [
                {
                    "ts":       r["record"].get("ts"),
                    "trigger":  r["record"].get("trigger"),
                    "ticker":   r["record"].get("ticker"),
                    "direction": r["record"].get("direction"),
                    "data_issue":   r["data_check"]["summary"]   if r["data_check"]   else None,
                    "logic_issue":  r["logic_check"]["summary"]  if r["logic_check"]  else None,
                    "timing":       r["timing_check"]["summary"] if r["timing_check"] else None,
                }
                for r in analysis["records"]
                if r["data_check"] or r["logic_check"]
                   or (r["timing_check"] and (not r["timing_check"].get("verified")
                                              or r["timing_check"].get("timing_issue")))
            ],
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 摘要写入: {summary_path}")

    # HTML 报告
    html_path = out_dir / "verify_report.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(analysis))
    print(f"📄 HTML 报告: {html_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
