"""VERSION: v0.1.0
DEPENDS: config/settings.py

Telegram formatting for SimWeekly duel paper notifications.
SimWeekly 纸面 PK Telegram 私聊格式统一模块。
"""
from __future__ import annotations

import html
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Iterable


ACTOR = {
    "claude_rule": "🤖 Claude",
    "openai_v1": "🧠 OpenAI",
    "sim_weekly": "📊 SimWeekly",
    "buyhold_RKLB": "📈 BuyHold-RKLB",
    "buyhold_RKLX": "📈 BuyHold-RKLX",
}

PAPER_SUFFIX = "(纸面模拟)"

# 标的 → 对 RKLB 的方向白话(RKLX=2x做多, RKLZ=2x做空/反向)
_BIAS = {"RKLX": "看多RKLB", "RKLB": "看多RKLB", "RKLZ": "看空RKLB"}

# 策略理由速记 → 大白话(多词短语优先)
_REASON_PHRASES = [
    ("5m up", "5分钟上行"),
    ("5m down", "5分钟下行"),
    ("trend long", "顺势做多"),
    ("guard short", "防守转空"),
    ("e9>e21", "均线多头(EMA9>EMA21)"),
    ("e9<e21", "均线空头(EMA9<EMA21)"),
    ("px>vwap", "价在VWAP上方"),
    ("px<vwap", "跌破VWAP"),
    ("STRONG", "强趋势"),
    ("indicators-na", "指标数据不足"),
]


def _bias_label(ticker) -> str | None:
    return _BIAS.get(str(ticker or "").replace("US.", "").upper())


def humanize_reason(reason: str) -> str:
    """把策略理由速记译成大白话。/ Translate compact strategy shorthand to plain Chinese.
    例: 'conv79 5m down e9<e21 px<vwap rsi33 gapATR0.5'
      → '信心79 · 5分钟下行 · 均线空头(EMA9<EMA21) · 跌破VWAP · RSI33 · 均线间距0.5ATR'
    内部记录的 reason 串保持不变, 仅推送显示时翻译。"""
    if not reason or reason == "-":
        return reason
    s = reason
    for token, cn in _REASON_PHRASES:
        s = s.replace(token, cn)
    s = re.sub(r"\bconv(\d+)", lambda m: f"信心{m.group(1)}", s)
    s = re.sub(r"\brsi(\d+)", lambda m: f"RSI{m.group(1)}", s, flags=re.IGNORECASE)
    s = re.sub(r"\bgapATR([\d.]+)", lambda m: f"均线间距{m.group(1)}ATR", s)
    s = re.sub(r"\bweek([+-]?[\d.]+)%", lambda m: f"周变动{m.group(1)}%", s)
    # 剩余以空格分隔的 token 用 · 连接, 更易读
    return " · ".join(p for p in s.split() if p)


def actor_label(actor: str) -> str:
    return ACTOR.get(actor, actor)


def fmt_header(kind: str) -> str:
    return f"📊 <b>{html.escape(kind)}</b>"


def _money(value) -> str:
    try:
        amount = float(value)
        return f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}"
    except Exception:
        return "$-"


def _price(value) -> str:
    try:
        return f"${float(value):.2f}"
    except Exception:
        return "$-"


def _time_hhmm(ts: str) -> str:
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
    except Exception:
        return str(ts)[11:16] if len(str(ts)) >= 16 else "-"


def _hold_minutes(entry_ts: str, exit_ts: str) -> int | None:
    try:
        start = datetime.strptime(str(entry_ts)[:19], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(str(exit_ts)[:19], "%Y-%m-%d %H:%M:%S")
        return int((end - start).total_seconds() / 60)
    except Exception:
        return None


def pair_trades(trades: list[dict]) -> list[dict]:
    """Pair buy/sell rows FIFO. / 按 FIFO 配对买卖流水。"""
    open_lots: dict[str, list[dict]] = {}
    rounds: list[dict] = []
    for trade in trades:
        side = trade.get("side")
        ticker = trade.get("ticker")
        if side == "buy":
            open_lots.setdefault(ticker, []).append(trade)
        elif side == "sell":
            lots = open_lots.get(ticker) or []
            entry = lots.pop(0) if lots else {}
            rounds.append({
                "ticker": ticker,
                "entry_ts": entry.get("ts", "?"),
                "entry_px": entry.get("price"),
                "exit_ts": trade.get("ts", "?"),
                "exit_px": trade.get("price"),
                "qty": trade.get("qty"),
                "pnl": trade.get("pnl"),
                "hold_min": _hold_minutes(entry.get("ts", ""), trade.get("ts", "")) if entry else None,
                "entry_reason": entry.get("reason", ""),
                "exit_reason": trade.get("reason", ""),
            })
    return rounds


def fmt_trade(actor: str, trade: dict, entry_trade: dict | None = None) -> str:
    """Format one live paper trade. / 格式化实时纸面成交。"""
    side = trade.get("side")
    action = "买入" if side == "buy" else "卖出" if side == "sell" else str(side or "成交")
    line = (
        f"{actor_label(actor)} · {action}  {html.escape(str(trade.get('ticker') or '-'))}  "
        f"{trade.get('qty', '-')} 股 @ {_price(trade.get('price'))}"
    )
    if side == "sell" and trade.get("pnl") is not None:
        line += f"  盈亏 {_money(trade.get('pnl'))}"
    reason_label = "理由" if side == "buy" else "原因"
    reason_text = humanize_reason(str(trade.get("reason") or "-"))
    if side == "buy":
        bias = _bias_label(trade.get("ticker"))
        if bias:
            reason_text = f"{bias}｜{reason_text}"
    reason = html.escape(reason_text)
    details = f"{reason_label}: {reason}  ·  {_time_hhmm(str(trade.get('ts') or ''))} ET"
    if side == "sell" and entry_trade:
        hold = _hold_minutes(str(entry_trade.get("ts") or ""), str(trade.get("ts") or ""))
        if hold is not None:
            details += f"  ·  持仓 {hold} 分"
    return f"{line}\n{details}  ·  {PAPER_SUFFIX}"


def fmt_trade_summary(actor: str, trades: Iterable[dict]) -> str:
    rows = list(trades)
    lines = [f"{actor_label(actor)} · {len(rows)} 笔纸面成交摘要"]
    for trade in rows:
        side = "买" if trade.get("side") == "buy" else "卖"
        pnl = f" {_money(trade.get('pnl'))}" if trade.get("pnl") is not None else ""
        lines.append(
            f"· {side} {trade.get('ticker','-')} x{trade.get('qty','-')} @ {_price(trade.get('price'))}{pnl} "
            f"{_time_hhmm(str(trade.get('ts') or ''))} ET"
        )
    lines.append(PAPER_SUFFIX)
    return "\n".join(lines)


class TradeAlertThrottle:
    """Merge alerts when one actor trades too often. / 同一选手短时过多成交时合并。"""

    def __init__(self, window_sec: int = 300, threshold: int = 3):
        self.window_sec = window_sec
        self.threshold = threshold
        self._events: dict[str, list[tuple[float, dict]]] = {}

    def record(self, actor: str, trade: dict, now: float | None = None) -> tuple[str, list[dict]]:
        now = time.time() if now is None else float(now)
        events = [(ts, tr) for ts, tr in self._events.get(actor, []) if now - ts <= self.window_sec]
        events.append((now, trade))
        self._events[actor] = events
        if len(events) >= self.threshold:
            trades = [tr for _, tr in events]
            self._events[actor] = []
            return "summary", trades
        return "single", [trade]


def _risk_adjusted(score: dict) -> float:
    dd = abs(float(score.get("max_drawdown_pct") or 0.0)) or 0.01
    return float(score.get("return_pct") or 0.0) / dd


def fmt_daily(date_label: str, scores: dict) -> str:
    """Format daily duel report. / 格式化日度 PK 汇总。"""
    lines = [fmt_header(f"双方 PK 日报 · {date_label}"), "当日表现展示，不作比赛裁定。", ""]
    ranked = sorted(scores, key=lambda name: _risk_adjusted(scores[name]), reverse=True)
    for rank, name in enumerate(ranked, 1):
        score = scores[name]
        rounds = pair_trades(score.get("trades", []))
        lines.append(
            f"<b>#{rank} {actor_label(name)}</b>  "
            f"{float(score.get('return_pct') or 0.0):+.2f}%  "
            f"回撤{score.get('max_drawdown_pct', '-')}%  "
            f"风调{_risk_adjusted(score):+.2f}  往返{len(rounds)}笔"
        )
        for row in rounds[:12]:
            pnl = _money(row.get("pnl")) if row.get("pnl") is not None else "$-"
            lines.append(
                f"  · {row['ticker']} 买{_time_hhmm(row['entry_ts'])}@{row['entry_px']} "
                f"→ 卖{_time_hhmm(row['exit_ts'])}@{row['exit_px']} ({pnl})"
            )
        if len(rounds) > 12:
            lines.append(f"  …另 {len(rounds)-12} 笔见完整报表")
        lines.append("")
    benchmark = scores.get("buyhold_RKLB", {}).get("return_pct")
    if benchmark is None:
        for score in scores.values():
            benchmark = score.get("benchmark_buyhold_RKLB_pct")
            if benchmark is not None:
                break
    lines.append("对照 买入持有 RKLB: " + (f"{benchmark}%" if benchmark is not None else "?"))
    lines.append(PAPER_SUFFIX)
    return "\n".join(lines)


def fmt_weekly(week_label: str, scores: dict) -> str:
    """Format weekend duel summary. / 格式化周末 PK 总结。"""
    lines = [fmt_header(f"双方 PK 周末总报告 · {week_label}"), "本周表现展示，不作比赛裁定。", ""]
    ranked = sorted(scores, key=lambda name: _risk_adjusted(scores[name]), reverse=True)
    for rank, name in enumerate(ranked, 1):
        score = scores[name]
        rounds = pair_trades(score.get("trades", []))
        lines.append(
            f"<b>#{rank} {actor_label(name)}</b>: "
            f"收益 {float(score.get('return_pct') or 0.0):+.2f}% · "
            f"回撤 {score.get('max_drawdown_pct', '-')}% · "
            f"风调 {_risk_adjusted(score):+.2f} · "
            f"往返 {len(rounds)} 笔 · 费用 {_money(score.get('total_fees'))}"
        )
        if rounds:
            best = max(rounds, key=lambda row: float(row.get("pnl") or 0.0))
            worst = min(rounds, key=lambda row: float(row.get("pnl") or 0.0))
            lines.append(
                f"  最好: {best['ticker']} {_money(best.get('pnl'))}; "
                f"最差: {worst['ticker']} {_money(worst.get('pnl'))}"
            )
        else:
            lines.append("  本周无成交")
    lines += [
        "",
        "结论: 本报告用于周末复盘；正式裁定只看用户指定测试集的冻结口径记分板。下周周一资金重置为 $10,000 后重新开赛。",
        PAPER_SUFFIX,
    ]
    return "\n".join(lines)


def send_private(text: str) -> bool:
    """Best-effort private Telegram send. / 私聊发送，缺凭证或失败不影响主流程。"""
    try:
        from config.settings import TG_BOT_TOKEN, TG_CHAT_ID
    except Exception:
        return False
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return False
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", data=data, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False
