"""
MagicQuant — 手动召集 AI 智囊团 (v0.3.6 patch)

与 focus_manager._call_ai_advisor_async 等价,
但不依赖"触发器命中",用户可通过 /ai_test 指令主动调用.

用途:
  1. 验证 4 家 AI 连通性(非 token 消耗的 test_ai_providers,而是真实场景测试)
  2. 盘中想随时问 Leader "现在怎么看"
  3. 盘后/盘前无触发时,主动获取 AI 视角

复用 ai_advisor.consult_advisors,所以:
  - 输出格式与触发推送完全一致(3 顾问 + Opus Leader)
  - 历史记录落盘到同一个 ai_advisor_history.json
  - 今日成本累加到 ai_advisor_cost.json
"""

from datetime import datetime
from typing import Optional, Callable

try:
    from .ai_advisor import consult_advisors
    HAS_ADVISOR = True
except ImportError as e:
    HAS_ADVISOR = False
    _import_err = str(e)


def manual_consult(
    session,
    indicators_cache: dict,
    reason: str = "手动召集",
    send_tg_fn: Optional[Callable] = None,
) -> dict:
    """
    手动召集 AI 智囊团,不依赖触发器.
    
    参数:
        session:          当前 FocusSession (从 focus_manager 取)
        indicators_cache: 指标缓存 (从 focus_manager 取)
        reason:           召集原因(会显示在推送头部)
        send_tg_fn:       TG 推送函数(可选,不传则只返回结果)
    
    返回:
        consult_advisors 的完整结果 dict
        - summary_text: TG 推送文本
        - advisors:     3 位顾问结果
        - leader:       Leader 最终决策
        - total_cost_usd
        - error (若失败)
    """
    if not HAS_ADVISOR:
        err = f"❌ AI 智囊团模块未加载: {_import_err}"
        if send_tg_fn:
            send_tg_fn(err)
        return {"error": err, "summary_text": err}
    
    if session is None or not getattr(session, "active", False):
        err = (
            "⚠️ 当前没有运行中的 Focus 盯盘\n"
            "请先用 /focus 启动盯盘,再用 /ai_test 召集智囊团."
        )
        if send_tg_fn:
            send_tg_fn(err)
        return {"error": err, "summary_text": err}
    
    # ── 构建伪 trigger(标记为手动调用)──
    trigger = {
        "type":     "manual_consult",
        "reason":   reason,
        "severity": "manual",
        "ticker":   session.master.replace("US.", ""),
    }
    
    # ── 构建 market_ctx(v0.4.1 修复: session 里没有 last_quotes,
    #    应该用 get_last_price + session_high + session_low)──
    prices = {}
    try:
        for tk_full in [session.master] + list(session.followers):
            tk = tk_full.replace("US.", "")
            cur = session.get_last_price(tk_full)
            if cur is not None:
                prices[tk] = {
                    "price": round(cur, 4),
                    "low":   round(session.session_low.get(tk_full, cur), 4),
                    "high":  round(session.session_high.get(tk_full, cur), 4),
                }
    except Exception as e:
        print(f"  [manual_consult] 读取价格失败: {e}")
    
    market_ctx = {
        "prices":     prices,
        "indicators": indicators_cache or {},
        "time":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    # ── 构建 portfolio_ctx ──
    positions_out = {}
    try:
        positions_snap = session.positions_snapshot or {}
        for tk_full, pos in positions_snap.items():
            if not isinstance(pos, dict):
                continue
            tk = tk_full.replace("US.", "")
            qty = pos.get("qty", 0) or pos.get("qty_held", 0)
            if qty <= 0:
                continue
            cur_price = prices.get(tk, {}).get("price") or pos.get("current_price", 0)
            positions_out[tk] = {
                "qty":           qty,
                "cost_basis":    pos.get("cost_price", pos.get("cost_basis", 0)),
                "current_price": cur_price,
            }
    except Exception as e:
        print(f"  [manual_consult] 读取持仓失败: {e}")
    
    cash = 20000.0
    try:
        if hasattr(session, "cash") and session.cash is not None:
            cash = session.cash
        elif hasattr(session, "account_info") and session.account_info:
            cash = session.account_info.get("cash", cash)
    except:
        pass
    
    portfolio_ctx = {
        "cash":      cash,
        "positions": positions_out,
    }
    
    # ── 调用智囊团 ──
    print(f"  [manual_consult] 召集智囊团 · 原因: {reason}")
    result = consult_advisors(trigger, market_ctx, portfolio_ctx)
    
    # ── 给 summary_text 加个手动标识 ──
    if result and result.get("summary_text"):
        # 在头部插入一行,说明是手动召集
        original = result["summary_text"]
        manual_header = (
            f"🔧 手动召集智囊团 · {reason}\n"
            f"(非触发推送,用户主动请求)\n"
            f"─────────────\n"
        )
        result["summary_text"] = manual_header + original
        
        if send_tg_fn:
            send_tg_fn(result["summary_text"])
            print(f"  [manual_consult] ✅ 推送成功, 花费 ${result.get('total_cost_usd', 0):.4f}")
    
    return result
