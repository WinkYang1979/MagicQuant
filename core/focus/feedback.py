"""
MagicQuant Focus — 用户反馈验证
Dare to dream. Data to win.

职责:
  1. 推送触发时,快照当前持仓
  2. 用户点 [✅已下单] → 查最新持仓对比
  3. 持仓变化 → 确认成交 + 推送盈亏数字
  4. 未变化 → 30 秒后重试一次(可能还在挂单)
  5. 用户点 [❌已忽略] → 标记"已消费",不重复触发
"""

import time
import threading
from datetime import datetime
from typing import Optional, Callable

from core.realtime_quote import get_client as get_quote_client


# ── 待验证的订单 ───────────────────────────────────────────
# key: trigger_id(唯一)  value: 快照 + 推送信息
_pending_verifications = {}
_verify_lock = threading.Lock()


class TriggerSnapshot:
    """一次触发时记录的持仓快照 + 推送元数据"""

    def __init__(self, trigger_id: str, ticker: str,
                 trigger_name: str, positions_before: dict,
                 suggested_action: str, suggested_qty: int = 0,
                 suggested_price: float = 0):
        self.trigger_id       = trigger_id
        self.ticker           = ticker
        self.trigger_name     = trigger_name
        self.positions_before = positions_before.copy() if positions_before else {}
        self.created_at       = datetime.now()
        self.suggested_action = suggested_action   # "SELL_HALF" / "SELL_ALL" / "BUY" etc.
        self.suggested_qty    = suggested_qty
        self.suggested_price  = suggested_price
        self.status           = "pending"          # pending / confirmed / ignored / timeout
        self.retry_count      = 0


def register_trigger(ticker: str, trigger_name: str,
                     positions_snapshot: dict,
                     suggested_action: str = "",
                     suggested_qty: int = 0,
                     suggested_price: float = 0) -> str:
    """
    推送时调用:记录这次触发的上下文
    返回 trigger_id,用于按钮 callback_data
    """
    trigger_id = f"{ticker}_{int(time.time())}"
    snap = TriggerSnapshot(
        trigger_id, ticker, trigger_name,
        positions_snapshot, suggested_action,
        suggested_qty, suggested_price
    )
    with _verify_lock:
        _pending_verifications[trigger_id] = snap
        # 清理 30 分钟前的旧记录
        now = time.time()
        stale = [
            tid for tid, s in _pending_verifications.items()
            if (datetime.now() - s.created_at).total_seconds() > 1800
        ]
        for tid in stale:
            del _pending_verifications[tid]
    return trigger_id


def get_trigger(trigger_id: str) -> Optional[TriggerSnapshot]:
    with _verify_lock:
        return _pending_verifications.get(trigger_id)


def _compare_positions(before: dict, after: dict, ticker: str) -> dict:
    """
    比较前后持仓,返回差异.
    返回:
      {"changed": True/False, "qty_delta": -100, "before_qty": 200,
       "after_qty": 100, "before_cost": 11.25, "current_price": 12.08,
       "realized_pl_estimate": 83.0}
    """
    pos_before = before.get(ticker, {}) if before else {}
    pos_after  = after.get(ticker, {})  if after  else {}

    qty_before = float(pos_before.get("qty", 0))
    qty_after  = float(pos_after.get("qty", 0))
    qty_delta  = qty_after - qty_before

    cost_before = float(pos_before.get("cost_price", 0))
    cur_price   = float(pos_after.get("current_price", 0)) or \
                  float(pos_before.get("current_price", 0))

    # 估算已实现盈亏(假设按当前价成交)
    realized_est = 0.0
    if qty_delta < 0 and cost_before > 0:
        # 卖出了 abs(qty_delta) 股
        realized_est = abs(qty_delta) * (cur_price - cost_before)

    return {
        "changed":        abs(qty_delta) > 0.01,
        "qty_delta":      qty_delta,
        "before_qty":     qty_before,
        "after_qty":      qty_after,
        "before_cost":    cost_before,
        "current_price":  cur_price,
        "realized_pl_estimate": round(realized_est, 2),
        "direction":      "SELL" if qty_delta < 0 else ("BUY" if qty_delta > 0 else "NONE"),
    }


def verify_trigger(trigger_id: str, send_tg_fn: Callable,
                   auto_retry_sec: int = 30) -> str:
    """
    用户点 [✅已下单] 调用.
    立刻查最新持仓,对比快照.
    变化 → 确认消息
    没变化 → 安排 30 秒后重试
    """
    snap = get_trigger(trigger_id)
    if snap is None:
        return "⚠️ 此触发已过期(30 分钟前),无法验证\n请直接查看 /positions"

    if snap.status != "pending":
        return f"ℹ️ 此触发已标记为 {snap.status},不再重复验证"

    # 立刻查当前持仓
    client = get_quote_client()
    current_positions = client.fetch_positions()

    if current_positions is None:
        # Futu 挂了
        return (
            "⚠️ Futu 连接暂时不可用,无法验证持仓\n"
            "请稍后发 /positions 手动查看"
        )

    diff = _compare_positions(snap.positions_before, current_positions, snap.ticker)

    if diff["changed"]:
        # 🎉 变化了,确认成交
        snap.status = "confirmed"
        ticker_short = snap.ticker.replace("US.", "")
        direction_emoji = "💰" if diff["direction"] == "SELL" else "🛒"
        direction_cn = "卖出" if diff["direction"] == "SELL" else "买入"

        msg_lines = [
            f"✅ <b>确认操作</b> · {ticker_short}",
            f"",
            f"{direction_emoji} {direction_cn} {abs(diff['qty_delta']):.0f} 股",
            f"持仓: {diff['before_qty']:.0f} → {diff['after_qty']:.0f} 股",
        ]

        if diff["direction"] == "SELL" and diff["realized_pl_estimate"] != 0:
            pl = diff["realized_pl_estimate"]
            sign = "+" if pl >= 0 else ""
            msg_lines.append(f"估算落袋: {sign}${pl:.2f}")

        # 剩余持仓
        if diff["after_qty"] > 0:
            remaining_pos = current_positions.get(snap.ticker, {})
            rem_pl = remaining_pos.get("pl_val", 0)
            rem_pct = remaining_pos.get("pl_pct", 0)
            sign = "+" if rem_pl >= 0 else ""
            msg_lines += [
                f"",
                f"📡 继续盯盘剩余 {diff['after_qty']:.0f} 股",
                f"浮盈 {sign}${rem_pl:.2f} ({sign}{rem_pct:.2f}%)",
            ]
        else:
            msg_lines += [
                f"",
                f"📡 已清仓,继续盯 {snap.ticker.replace('US.','')} 等下一个波段",
            ]

        # 替换成纯文本(send_tg 会过滤 HTML)
        msg = "\n".join(msg_lines).replace("<b>", "").replace("</b>", "")
        return msg

    # 没变化,安排 30 秒后重试
    snap.retry_count += 1
    if snap.retry_count == 1:
        # 启动重试线程
        threading.Thread(
            target=_delayed_retry,
            args=(trigger_id, send_tg_fn, auto_retry_sec),
            daemon=True,
            name=f"Retry-{trigger_id}"
        ).start()
        return (
            f"⏳ 未检测到持仓变化\n"
            f"可能原因:\n"
            f"1. 限价单还在挂单队列\n"
            f"2. 刚下单 Futu 还没同步\n\n"
            f"⏱️ {auto_retry_sec} 秒后自动重试验证...\n"
            f"或按 [❌已忽略] 放弃"
        )
    else:
        return f"ℹ️ 已在重试中,请稍候(第 {snap.retry_count} 次)"


def _delayed_retry(trigger_id: str, send_tg_fn: Callable, delay_sec: int):
    """延迟重试"""
    time.sleep(delay_sec)

    snap = get_trigger(trigger_id)
    if snap is None or snap.status != "pending":
        return

    client = get_quote_client()
    current_positions = client.fetch_positions()
    if current_positions is None:
        try:
            send_tg_fn(f"⚠️ 重试验证失败(Futu 暂时不可用),请手动查 /positions")
        except:
            pass
        return

    diff = _compare_positions(snap.positions_before, current_positions, snap.ticker)
    ticker_short = snap.ticker.replace("US.", "")

    if diff["changed"]:
        snap.status = "confirmed"
        direction_emoji = "💰" if diff["direction"] == "SELL" else "🛒"
        direction_cn = "卖出" if diff["direction"] == "SELL" else "买入"

        msg_lines = [
            f"✅ 重试成功 · {ticker_short} · 确认成交",
            f"",
            f"{direction_emoji} {direction_cn} {abs(diff['qty_delta']):.0f} 股",
            f"持仓: {diff['before_qty']:.0f} → {diff['after_qty']:.0f} 股",
        ]
        if diff["direction"] == "SELL" and diff["realized_pl_estimate"] != 0:
            pl = diff["realized_pl_estimate"]
            sign = "+" if pl >= 0 else ""
            msg_lines.append(f"估算落袋: {sign}${pl:.2f}")

        try:
            send_tg_fn("\n".join(msg_lines))
        except:
            pass
    else:
        # 重试仍未变化
        msg = (
            f"❌ {ticker_short} 持仓仍未变化\n"
            f"\n"
            f"可能:\n"
            f"• 订单还在挂单中(限价未达到)\n"
            f"• 订单被撤/拒绝\n"
            f"• 实际未下单\n"
            f"\n"
            f"建议:\n"
            f"1. 去 Moomoo 检查订单状态\n"
            f"2. 或发 /positions 手动核对"
        )
        try:
            send_tg_fn(msg)
        except:
            pass
        snap.status = "timeout"


def mark_ignored(trigger_id: str) -> str:
    """用户点 [❌已忽略]"""
    snap = get_trigger(trigger_id)
    if snap is None:
        return "⚠️ 此触发已过期"
    if snap.status != "pending":
        return f"ℹ️ 此触发已标记为 {snap.status}"
    snap.status = "ignored"
    ticker_short = snap.ticker.replace("US.", "")
    return f"❌ 已忽略 {ticker_short} 的 {snap.trigger_name} 信号\n继续盯盘中..."


def recompute_price(trigger_id: str) -> str:
    """用户点 [🔄改挂单价]"""
    snap = get_trigger(trigger_id)
    if snap is None:
        return "⚠️ 此触发已过期"

    client = get_quote_client()
    quote = client.fetch_one(snap.ticker)
    if quote is None:
        return "⚠️ 实时价获取失败"

    cur_price = quote["price"]
    ticker_short = snap.ticker.replace("US.", "")

    # 根据原建议动作重算挂单价
    if "SELL" in snap.suggested_action.upper():
        new_price_aggressive = round(cur_price * 0.998, 2)   # 略低于市价,易成交
        new_price_patient    = round(cur_price * 1.003, 2)   # 略高,赌回弹
        return (
            f"🔄 {ticker_short} 重新挂单价\n"
            f"\n"
            f"现价: ${cur_price:.2f}\n"
            f"\n"
            f"快速成交: ${new_price_aggressive:.2f}(-0.2%)\n"
            f"略微等待: ${new_price_patient:.2f}(+0.3%)\n"
            f"\n"
            f"持仓 {snap.suggested_qty} 股"
        )
    else:
        new_price_aggressive = round(cur_price * 1.002, 2)
        new_price_patient    = round(cur_price * 0.998, 2)
        return (
            f"🔄 {ticker_short} 重新挂单价\n"
            f"\n"
            f"现价: ${cur_price:.2f}\n"
            f"\n"
            f"快速成交: ${new_price_aggressive:.2f}(+0.2%)\n"
            f"略微等待: ${new_price_patient:.2f}(-0.2%)\n"
            f"\n"
            f"建议买 {snap.suggested_qty} 股"
        )


def get_pending_count() -> int:
    """待验证的触发数量"""
    with _verify_lock:
        return sum(1 for s in _pending_verifications.values() if s.status == "pending")
