"""
MagicQuant Focus — 主循环管理器
Dare to dream. Data to win.

职责:
  1. 启动/停止盯盘 session
  2. 主循环:定时拉价格 + K 线 + 持仓
  3. 跑触发器,命中就推送
  4. 线程安全,可从 bot_controller 调用

用法:
    from core.focus import start_focus, stop_focus, get_focus_status

    start_focus(master="US.RKLB", send_tg_fn=send_tg)
    # ... 触发器命中时会自动调 send_tg_fn 推送
    stop_focus()
"""

import time
import threading
import traceback
from datetime import datetime
from typing import Callable, Optional

try:
    from moomoo import KLType, AuType
except ImportError:
    from futu import KLType, AuType

from core.realtime_quote import get_client as get_quote_client

from .context import FocusSession
from .micro_indicators import calc_all_micro
from .swing_detector import run_all_triggers
from .pusher import format_trigger_message

# AI 智囊团 (v0.3.5)
try:
    from .ai_advisor import consult_advisors
    HAS_AI_ADVISOR = True
except ImportError as e:
    HAS_AI_ADVISOR = False
    print(f"  [focus] ai_advisor not available: {e}")


# ── 全局单例 ─────────────────────────────────────────────
_current_session: Optional[FocusSession] = None
_manager_thread:  Optional[threading.Thread] = None
_stop_event = threading.Event()
_session_lock = threading.Lock()

# AI 咨询开关(可以在运行时通过 /ai_advise_on/off 切换)
_ai_advise_enabled = True


def set_ai_advise(enabled: bool):
    """开关 AI 智囊团"""
    global _ai_advise_enabled
    _ai_advise_enabled = enabled


def is_ai_advise_enabled() -> bool:
    return _ai_advise_enabled and HAS_AI_ADVISOR


# ── 参数(v0.3.1 基于 2026-04-21 压测数据调优)────────
# 压测结果:1秒频率 20/20 成功,avg 209ms p95 211ms
# 压测结果:4 只并发 216ms,无限流
# 压测结果:K 线 65ms,超快
POLL_INTERVAL_MARKET      = 1    # 盘中 1 秒 / 次(激进,已验证稳定)
POLL_INTERVAL_OFFHOURS    = 5    # 盘外 5 秒 / 次
KLINE_FETCH_INTERVAL      = 30   # K 线 30 秒拉一次(5分钟 K 不用太频繁)
POSITION_FETCH_INTERVAL   = 30   # 持仓 30 秒刷一次(从 60 改为 30)


def is_us_market_open() -> bool:
    """
    粗略判断美股是否在交易时间.
    24h 交易环境下保守返回 True, 让盯盘保持活跃.
    TODO: 之后接入真正的交易日历
    """
    return True


def start_focus(master: str = "US.RKLB",
                followers: list = None,
                send_tg_fn: Callable = None,
                auto_attach_positions: bool = True) -> str:
    """
    启动焦点盯盘
    
    v0.3.3: 改用 pairs.py 的正确多空配对
    """
    global _current_session, _manager_thread, _stop_event

    with _session_lock:
        if _current_session is not None and _current_session.active:
            return f"⚠️ 已有盯盘运行中({_current_session.master}),请先 /unfocus"

        # 自动识别跟随标的
        if followers is None:
            followers = []

        # v0.3.3: 根据 pairs.py 的配对规则,自动添加所有配对票
        from .pairs import get_all_followers, get_pair_config
        pair_cfg = get_pair_config(master)
        candidate_followers = get_all_followers(master)

        if auto_attach_positions:
            try:
                positions = get_quote_client().fetch_positions() or {}
                # 1) 持仓里的配对票自动加入
                for candidate in candidate_followers:
                    if candidate in positions and candidate not in followers:
                        followers.append(candidate)
                # 2) 即使不持仓,做多+做空工具也都加进来(盯盘需要)
                for candidate in candidate_followers:
                    if candidate not in followers:
                        followers.append(candidate)
            except Exception as e:
                print(f"  [focus] auto-attach failed: {e}")
                # 失败也要把配对票加上(无持仓数据的情况)
                followers = [tk for tk in candidate_followers if tk not in followers] + followers

        # 创建 session
        _current_session = FocusSession(master, followers)
        _stop_event = threading.Event()

        # 启动后台线程
        _manager_thread = threading.Thread(
            target=_focus_loop,
            args=(_current_session, send_tg_fn, _stop_event),
            daemon=True,
            name="FocusLoop"
        )
        _manager_thread.start()

    # 展示配对信息
    long_tools = [tk.replace("US.", "") for tk in pair_cfg.get("long", [])]
    short_tools = [tk.replace("US.", "") for tk in pair_cfg.get("short", [])]
    master_name = pair_cfg.get("name", master)

    return (
        f"🎯 已进入盯盘模式\n"
        f"\n"
        f"主标的: {master.replace('US.', '')}  {master_name}\n"
        f"做多工具: {', '.join(long_tools) if long_tools else '(无)'}\n"
        f"做空工具: {', '.join(short_tools) if short_tools else '(无)'}\n"
        f"频率:   {POLL_INTERVAL_MARKET}秒 / 次(盘中)\n"
        f"\n"
        f"波段信号命中时会主动推送.\n"
        f"/status 查看状态  /unfocus 退出"
    )


def stop_focus() -> str:
    """停止盯盘"""
    global _current_session, _manager_thread, _stop_event

    with _session_lock:
        if _current_session is None or not _current_session.active:
            return "当前没有运行中的盯盘"

        _stop_event.set()
        _current_session.active = False
        summary = _current_session.summary()

    # 等线程退出(最多 5 秒)
    if _manager_thread:
        _manager_thread.join(timeout=5)

    return f"✅ 盯盘已停止\n\n{summary}"


def get_focus_status() -> str:
    """获取当前盯盘状态"""
    global _current_session
    if _current_session is None or not _current_session.active:
        return "当前没有运行中的盯盘\n\n💡 /focus 启动 RKLB 波段做 T 模式"
    return _current_session.summary()


def is_focused() -> bool:
    return _current_session is not None and _current_session.active


# ══════════════════════════════════════════════════════════════════
#  导出实时状态给 Dashboard(v0.3.2 新增)
# ══════════════════════════════════════════════════════════════════

import json
import os
_indicators_cache_global = {}   # 把指标缓存也暴露给 dashboard


def get_live_state() -> dict:
    """
    返回 Dashboard 用的完整实时状态 JSON.
    格式固定,不含 Python 对象,可直接 json.dumps
    """
    if _current_session is None or not _current_session.active:
        return {
            "active": False,
            "message": "当前没有运行中的盯盘",
            "updated_at": datetime.now().strftime("%H:%M:%S"),
        }

    sess = _current_session
    master = sess.master
    master_price = sess.get_last_price(master)
    master_high = sess.session_high.get(master)
    master_low = sess.session_low.get(master)

    # 主标的数据
    master_data = {
        "ticker":  master.replace("US.", ""),
        "full":    master,
        "price":   master_price,
        "high":    master_high,
        "low":     master_low,
        "peak":    sess.peak_price.get(master),
        "trough":  sess.trough_price.get(master),
    }

    # 加入指标数据
    ind = _indicators_cache_global or {}
    if ind.get("data_ok"):
        master_data.update({
            "rsi_5m":     ind.get("rsi_5m"),
            "vwap":       ind.get("vwap"),
            "vol_ratio":  ind.get("vol_ratio"),
            "dist_high":  ind.get("dist_high"),
            "dist_low":   ind.get("dist_low"),
            "candle":     ind.get("candle"),
        })

    # 计算涨跌
    if master_price and master_low:
        # 这里用 session 低开算,粗略估算日内变化
        # TODO: 需要接入昨收数据
        change_pct = None
    else:
        change_pct = None

    # 跟随标的 / 持仓
    followers_data = []
    for tk in sess.followers:
        pos = sess.get_position(tk) or {}
        cur_price = sess.get_last_price(tk) or pos.get("current_price", 0)
        qty = pos.get("qty", 0)
        cost = pos.get("cost_price", 0)
        pl_val = pos.get("pl_val", 0)
        pl_pct = pos.get("pl_pct", 0)
        followers_data.append({
            "ticker":   tk.replace("US.", ""),
            "full":     tk,
            "price":    cur_price,
            "qty":      qty,
            "cost":     cost,
            "pl_val":   pl_val,
            "pl_pct":   pl_pct,
            "market_val": round(qty * cur_price, 2) if qty and cur_price else 0,
            "has_position": qty != 0,
        })

    # 价格历史(最近 30 分钟,用于画迷你图)
    price_history = {}
    for tk in [master] + sess.followers:
        hist = sess.prices.get(tk, [])
        # 每 15 秒取一个点,不要返回全部(太多)
        if len(hist) > 0:
            # 简化:最多返回 60 个点
            step = max(1, len(hist) // 60)
            sampled = [(ts, p) for i, (ts, p) in enumerate(hist) if i % step == 0]
            price_history[tk.replace("US.", "")] = [
                {"t": datetime.fromtimestamp(ts).strftime("%H:%M:%S"), "p": p}
                for ts, p in sampled
            ]

    # 最近 10 条触发历史(从 feedback 拿)
    from .feedback import _pending_verifications, _verify_lock
    with _verify_lock:
        triggers = [
            {
                "id":         snap.trigger_id,
                "ticker":     snap.ticker.replace("US.", ""),
                "name":       snap.trigger_name,
                "time":       snap.created_at.strftime("%H:%M:%S"),
                "status":     snap.status,
                "action":     snap.suggested_action,
                "qty":        snap.suggested_qty,
                "price":      snap.suggested_price,
            }
            for snap in sorted(
                _pending_verifications.values(),
                key=lambda s: s.created_at,
                reverse=True,
            )[:10]
        ]

    return {
        "active":       True,
        "started_at":   sess.started_at.strftime("%H:%M:%S"),
        "duration_min": int((datetime.now() - sess.started_at).total_seconds() / 60),
        "master":       master_data,
        "followers":    followers_data,
        "price_history": price_history,
        "triggers":     triggers,
        "stats": {
            "loops":    sess.loop_count,
            "triggers": sess.trigger_count,
            "pushes":   sess.push_count,
            "errors":   sess.error_count,
        },
        "poll_interval": POLL_INTERVAL_MARKET,
        "updated_at":    datetime.now().strftime("%H:%M:%S"),
    }


def write_state_to_file(state_path: str = None):
    """把当前状态写入 JSON 文件(给 dashboard 读)"""
    from config.settings import BASE_DIR
    if state_path is None:
        state_path = os.path.join(BASE_DIR, "data", "focus_state.json")
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(get_live_state(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [focus] write state error: {e}")


# ══════════════════════════════════════════════════════════════════
#  主循环
# ══════════════════════════════════════════════════════════════════

def _focus_loop(session: FocusSession, send_tg_fn: Callable, stop_event: threading.Event):
    """盯盘主循环(后台线程)"""
    print(f"  [focus] loop started for {session.master}")
    try:
        send_tg_fn(f"🎯 盯盘循环已启动 · {session.master.replace('US.','')}")
    except:
        pass

    client = get_quote_client()

    # 时间戳
    last_kline_fetch    = 0
    last_position_fetch = 0
    kline_cache         = None   # 只缓存主标的 5 分钟 K 线
    indicators_cache    = {}

    while not stop_event.is_set():
        t_loop_start = time.time()
        session.loop_count += 1

        try:
            # ── 拉实时价(主标 + 跟随)─────────────────
            all_tickers = [session.master] + session.followers
            quotes = client.fetch_many(all_tickers)

            for tk, q in quotes.items():
                if q:
                    session.update_price(tk, q["price"])

            # ── K 线 & 指标(仅主标)────────────────
            now = time.time()
            if now - last_kline_fetch >= KLINE_FETCH_INTERVAL:
                kline_cache = _fetch_5m_kline(client, session.master)
                last_kline_fetch = now

            current_master_price = session.get_last_price(session.master)
            if kline_cache is not None and current_master_price:
                indicators_cache = calc_all_micro(kline_cache, current_master_price)
                # v0.3.2: 全局暴露,供 Dashboard 读取
                global _indicators_cache_global
                _indicators_cache_global = indicators_cache

            # ── 持仓刷新 ───────────────────────────────
            if now - last_position_fetch >= POSITION_FETCH_INTERVAL:
                positions = client.fetch_positions()
                if positions is not None:
                    session.update_positions(positions)
                last_position_fetch = now

            # ── 跑触发器 ───────────────────────────────
            if indicators_cache and indicators_cache.get("data_ok"):
                hits = run_all_triggers(
                    session,
                    session.master,
                    session.followers,
                    indicators_cache,
                )

                for hit in hits:
                    try:
                        session.mark_triggered(f"{hit['trigger']}_{hit['ticker']}")

                        # 注册 trigger,拿到 trigger_id
                        from .feedback import register_trigger
                        d = hit.get("data", {})
                        trigger_id = register_trigger(
                            ticker=hit["ticker"],
                            trigger_name=hit["trigger"],
                            positions_snapshot=session.positions_snapshot,
                            suggested_action=d.get("suggested_action", "SELL" if "target" in hit["trigger"] or "drawdown" in hit["trigger"] or "top" in hit["trigger"] else "BUY"),
                            suggested_qty=d.get("sell_half_qty", d.get("qty", 0)),
                            suggested_price=d.get("sell_price_half", d.get("current", 0)),
                        )

                        msg = format_trigger_message(hit, session, trigger_id=trigger_id)
                        if send_tg_fn:
                            send_tg_fn(msg["text"], buttons=msg.get("buttons"))
                            session.push_count += 1

                        # ── AI 智囊团咨询 (v0.3.5) ────────────────
                        if is_ai_advise_enabled() and send_tg_fn:
                            try:
                                # 在独立线程异步调用,不阻塞主循环
                                threading.Thread(
                                    target=_call_ai_advisor_async,
                                    args=(hit, session, indicators_cache, send_tg_fn),
                                    daemon=True,
                                    name=f"AIAdvisor-{hit['trigger']}",
                                ).start()
                            except Exception as e:
                                print(f"  [focus] ai advisor dispatch error: {e}")
                    except Exception as e:
                        print(f"  [focus] push error: {e}")
                        traceback.print_exc()
                        session.error_count += 1

        except Exception as e:
            session.error_count += 1
            print(f"  [focus] loop error: {e}")
            traceback.print_exc()
            # 连续出错暂停 5 秒
            if session.error_count % 5 == 0:
                time.sleep(5)

        # ── 自适应休眠 ───────────────────────────────
        elapsed = time.time() - t_loop_start
        interval = POLL_INTERVAL_MARKET if is_us_market_open() else POLL_INTERVAL_OFFHOURS
        sleep_for = max(0.5, interval - elapsed)

        # v0.3.2: 每次循环结束写状态文件(给 dashboard)
        # 每 2 个循环写一次,避免磁盘 I/O 太频繁
        if session.loop_count % 2 == 0:
            try:
                write_state_to_file()
            except:
                pass

        if stop_event.wait(timeout=sleep_for):
            break

    # 停止时写一次最终状态
    try:
        write_state_to_file()
    except:
        pass

    print(f"  [focus] loop stopped")
    try:
        send_tg_fn(f"✅ 盯盘循环已停止 · 共运行 {session.loop_count} 轮")
    except:
        pass


def _fetch_5m_kline(client, ticker: str, num: int = 30):
    """拉最近 30 根 5 分钟 K 线"""
    try:
        if not client._ensure_quote():
            return None
        with client._quote_lock:
            ret, kl = client._quote_ctx.get_cur_kline(
                ticker, num, KLType.K_5M, AuType.QFQ
            )
        if ret == 0 and kl is not None and len(kl) > 0:
            return kl
        return None
    except Exception as e:
        print(f"  [focus] kline fetch error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
#  AI 智囊团异步调用 (v0.3.5)
# ══════════════════════════════════════════════════════════════════

def _call_ai_advisor_async(
    hit: dict,
    session: FocusSession,
    indicators_cache: dict,
    send_tg_fn: Callable,
):
    """
    后台线程调用 AI 智囊团,完成后推送给 TG.
    不阻塞主 Focus 循环.
    """
    try:
        # ── 构建 trigger 字典 ──
        trigger = {
            "type":     hit.get("trigger", "unknown"),
            "reason":   hit.get("reason") or (hit.get("data") or {}).get("msg", ""),
            "severity": hit.get("severity", "normal"),
            "ticker":   hit.get("ticker"),
        }
        
        # ── 构建市场数据 ──
        prices = {}
        # Focus 触发的 ticker 的最新价
        hit_data = hit.get("data", {})
        if hit.get("ticker") and "current" in hit_data:
            tk = hit["ticker"].replace("US.", "")
            prices[tk] = {
                "price": hit_data["current"],
                "low":   hit_data.get("low", hit_data["current"]),
                "high":  hit_data.get("high", hit_data["current"]),
            }
        
        # 尝试从 session 里拿其他 ticker 的最新价
        try:
            for tk_full in [session.master] + list(session.followers):
                tk = tk_full.replace("US.", "")
                if tk in prices:
                    continue
                # session 里保存的实时价
                last_quote = session.last_quotes.get(tk_full) if hasattr(session, "last_quotes") else None
                if last_quote:
                    prices[tk] = {
                        "price": last_quote.get("price", 0),
                        "low":   last_quote.get("low_price", 0),
                        "high":  last_quote.get("high_price", 0),
                    }
        except Exception as e:
            print(f"  [ai_advisor] 读取价格失败: {e}")
        
        market_ctx = {
            "prices":     prices,
            "indicators": indicators_cache or {},
            "time":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # ── 构建持仓数据 ──
        positions_out = {}
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
        
        # 现金:如果 session 有记录就用,否则假设
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
        
        # ── 调用 AI 智囊团 ──
        result = consult_advisors(trigger, market_ctx, portfolio_ctx)
        
        # ── 推送到 TG ──
        if result and result.get("summary_text"):
            send_tg_fn(result["summary_text"])
            print(f"  [ai_advisor] ✅ 推送成功, 花费 ${result.get('total_cost_usd', 0):.4f}")
        else:
            print(f"  [ai_advisor] 未产生推送")
            
    except Exception as e:
        print(f"  [ai_advisor] 异常: {e}")
        traceback.print_exc()
        try:
            send_tg_fn(f"⚠️ AI 智囊团调用失败: {str(e)[:100]}")
        except:
            pass
