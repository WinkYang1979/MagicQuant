"""
MagicQuant — AI 虚拟操盘大赛主引擎

机制:
  1. 后台循环,每 N 秒一次
  2. 拉取 RKLB/RKLX/RKLZ 实时价格
  3. 并行调用所有启用的 AI(每 AI 看相同数据)
  4. 解析 AI 决策
  5. 在各自虚拟账户里执行
  6. 持久化记录
  7. 每轮结束推一条 TG 快讯(可选)
"""

import os
import time
import json
import threading
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable, List

from core.realtime_quote import get_client as get_quote_client

from .portfolio import VirtualPortfolio
from .providers import build_all_providers
from .prompt import SYSTEM_PROMPT, build_user_prompt, parse_decision


# ── 从 config.settings 同步 API Keys 到环境变量 ────────
# 原因:用户的 .env 用 CLAUDE_API_KEY 变量名,config.settings 已加载,
#      但 providers.py 只看环境变量,所以在这里把它们写回 os.environ
def _sync_api_keys_to_env():
    """从 config.settings 读 API keys 并写入 os.environ"""
    try:
        from config import settings as _s
        if getattr(_s, "CLAUDE_API_KEY", None) and not os.getenv("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = _s.CLAUDE_API_KEY
        if getattr(_s, "OPENAI_API_KEY", None) and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = _s.OPENAI_API_KEY
        # DeepSeek / Moonshot 如果 settings 里有就同步
        for attr_key in ["DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY"]:
            val = getattr(_s, attr_key, None)
            if val and not os.getenv(attr_key):
                os.environ[attr_key] = val
    except Exception as e:
        print(f"  [race] _sync_api_keys_to_env failed: {e}")

_sync_api_keys_to_env()


try:
    from moomoo import KLType, AuType
except ImportError:
    from futu import KLType, AuType


# ── 参数 ──────────────────────────────────────────────
DECISION_INTERVAL_SEC    = 180     # 每 3 分钟决策一次(稳健模式)
KLINE_FETCH_INTERVAL_SEC = 60      # K 线 60 秒拉一次
MAX_QTY_PER_TRADE        = 300     # 限制 AI 单笔最大股数
TRADING_TICKERS = ["US.RKLB", "US.RKLX", "US.RKLZ"]


# ── 全局状态 ──────────────────────────────────────────
_race_thread:    Optional[threading.Thread] = None
_stop_event = threading.Event()
_portfolios:     dict = {}   # {ai_name: VirtualPortfolio}
_providers:      dict = {}   # {ai_name: Provider}
_race_active    = False
_started_at     = None
_round_count    = 0

_race_lock = threading.Lock()


def is_race_active() -> bool:
    return _race_active


def get_portfolios() -> dict:
    """只读访问"""
    return dict(_portfolios)


def get_providers() -> dict:
    return dict(_providers)


def start_race(send_tg_fn: Optional[Callable] = None,
               ai_names: Optional[List[str]] = None,
               interval: int = DECISION_INTERVAL_SEC) -> str:
    """
    启动 AI 虚拟操盘大赛.
    
    ai_names: 要启用的 AI 名称列表,None=全部启用
    """
    global _race_thread, _stop_event, _portfolios, _providers
    global _race_active, _started_at, _round_count
    
    with _race_lock:
        if _race_active:
            return "⚠️ 大赛已在进行中,请先 /race_stop"
        
        # 构建所有可用 providers
        all_providers = build_all_providers()
        if not all_providers:
            return "❌ 没有可用的 AI Provider,请检查 .env 里的 API Key"
        
        # 过滤
        if ai_names:
            _providers = {k: v for k, v in all_providers.items() if k in ai_names}
        else:
            _providers = all_providers
        
        if not _providers:
            return f"❌ 指定的 AI 名称都不可用: {ai_names}"
        
        # 每个 AI 一个账户(尝试从文件恢复,否则新建)
        _portfolios = {}
        from config.settings import BASE_DIR
        for name, provider in _providers.items():
            path = os.path.join(BASE_DIR, "data", f"portfolio_{name}.json")
            _portfolios[name] = VirtualPortfolio.load(path, name)
        
        _stop_event = threading.Event()
        _race_active = True
        _started_at = datetime.now()
        _round_count = 0
        
        # 启动后台线程
        _race_thread = threading.Thread(
            target=_race_loop,
            args=(send_tg_fn, interval),
            daemon=True,
            name="AIRaceLoop",
        )
        _race_thread.start()
    
    names_display = ", ".join(p.display_name for p in _providers.values())
    return (
        f"🏁 AI 虚拟操盘大赛已启动\n"
        f"\n"
        f"参赛 AI: {names_display}\n"
        f"决策间隔: {interval} 秒\n"
        f"起始资金: $20,000 / AI\n"
        f"\n"
        f"可交易: RKLB / RKLX / RKLZ\n"
        f"费率: 买 $1.29 固定 / 卖 $1.31~$1.60 (Moomoo AU 真实)\n"
        f"\n"
        f"/race_stats 查看排行\n"
        f"/race_stop 停止大赛"
    )


def stop_race(send_tg_fn: Optional[Callable] = None) -> str:
    """停止大赛"""
    global _race_active, _race_thread
    
    with _race_lock:
        if not _race_active:
            return "⚠️ 没有运行中的大赛"
        
        _stop_event.set()
        _race_active = False
    
    # 等待线程结束
    if _race_thread:
        _race_thread.join(timeout=5)
    
    # 保存最终状态
    _save_all_portfolios()
    
    # 汇总报告
    summary = get_race_summary()
    return summary


def get_race_summary() -> str:
    """获取当前/最终排行"""
    if not _portfolios:
        return "📊 尚未开始大赛"
    
    # 用最新价(如果能拿到)
    current_prices = _fetch_prices_safe()
    
    summaries = []
    for name, p in _portfolios.items():
        summaries.append(p.summary(current_prices))
    
    # 按 total_pnl 排序
    summaries.sort(key=lambda s: s["total_pnl"], reverse=True)
    
    now = datetime.now().strftime("%H:%M:%S")
    elapsed_min = int((datetime.now() - _started_at).total_seconds() / 60) if _started_at else 0
    
    lines = [
        f"🏆 AI 操盘大赛排行 · {now}",
        f"运行: {elapsed_min} 分钟 · 第 {_round_count} 轮",
        f"",
    ]
    
    medals = ["🥇", "🥈", "🥉", "🏅", "🎖️"]
    for idx, s in enumerate(summaries):
        medal = medals[idx] if idx < len(medals) else "  "
        display_name = _providers[s["ai_name"]].display_name if s["ai_name"] in _providers else s["ai_name"]
        sign = "+" if s["total_pnl"] >= 0 else ""
        lines.append(
            f"{medal} {display_name}\n"
            f"    权益: ${s['equity']:,.2f}  "
            f"盈亏: {sign}${s['total_pnl']:,.2f} ({sign}{s['total_pnl_pct']:.2f}%)\n"
            f"    交易: {s['total_trades']}  "
            f"AI花费: ${s['ai_cost_usd']:.4f}  "
            f"佣金: ${s['total_commission']:.2f}"
        )
    
    # 总算力成本
    total_ai_cost = sum(s["ai_cost_usd"] for s in summaries)
    total_tokens = sum(s["ai_tokens"] for s in summaries)
    total_calls = sum(s.get("ai_calls", 0) for s in summaries)
    
    lines += [
        "",
        f"═════════════════════",
        f"💰 累计 AI 算力成本: ${total_ai_cost:.4f}",
        f"🔢 Tokens 使用: {total_tokens:,}",
        f"📞 调用次数: {total_calls}",
    ]
    
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  主循环
# ══════════════════════════════════════════════════════════════════

def _race_loop(send_tg_fn: Optional[Callable], interval: int):
    global _round_count
    
    print(f"  [race] started, {len(_providers)} AI(s)")
    if send_tg_fn:
        try:
            names = ", ".join(p.display_name for p in _providers.values())
            send_tg_fn(f"🏁 虚拟操盘开始: {names}")
        except:
            pass
    
    last_kline_fetch = 0
    indicators_cache = {}
    
    while not _stop_event.is_set():
        t_start = time.time()
        _round_count += 1
        
        try:
            # 1) 拉实时价
            market_prices = _fetch_prices_safe()
            if not market_prices:
                print(f"  [race] no prices, skip round")
                if _stop_event.wait(timeout=interval):
                    break
                continue
            
            # 2) 拉 K 线指标(每 60 秒一次,只算 RKLB)
            now = time.time()
            if now - last_kline_fetch >= KLINE_FETCH_INTERVAL_SEC:
                indicators_cache = _fetch_indicators_safe(market_prices.get("RKLB", {}).get("price", 0))
                last_kline_fetch = now
            
            # 3) 构建 market_data
            market_data = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "prices": market_prices,
                "indicators": indicators_cache,
            }
            
            # 4) 并行调用所有 AI
            _run_round(market_data, send_tg_fn)
            
            # 5) 保存
            _save_all_portfolios()
            
        except Exception as e:
            print(f"  [race] loop error: {e}")
            traceback.print_exc()
        
        # 自适应休眠
        elapsed = time.time() - t_start
        sleep_for = max(5, interval - elapsed)
        if _stop_event.wait(timeout=sleep_for):
            break
    
    print(f"  [race] stopped after {_round_count} rounds")
    if send_tg_fn:
        try:
            send_tg_fn(f"🏁 虚拟操盘结束 · 共 {_round_count} 轮")
        except:
            pass


def _run_round(market_data: dict, send_tg_fn: Optional[Callable]):
    """一轮:并行让所有 AI 决策 + 执行"""
    
    current_prices = {
        tk: info["price"] for tk, info in market_data["prices"].items()
    }
    # 也加上 US. 前缀版本(portfolio 用 RKLB,get_client 用 US.RKLB)
    full_prices = {}
    for tk, p in current_prices.items():
        full_prices[tk] = p
        full_prices[f"US.{tk}"] = p
    
    # 并行调用
    tasks = {}
    with ThreadPoolExecutor(max_workers=len(_providers)) as pool:
        for name, provider in _providers.items():
            portfolio = _portfolios[name]
            portfolio_summary = portfolio.summary(full_prices)
            user_prompt = build_user_prompt(market_data, portfolio_summary)
            
            tasks[pool.submit(provider.call, SYSTEM_PROMPT, user_prompt, 400, 25)] = name
        
        results = {}
        for future in as_completed(tasks):
            name = tasks[future]
            try:
                results[name] = future.result()
            except Exception as e:
                print(f"  [race] {name} call failed: {e}")
                results[name] = {"text": "", "error": str(e)[:100],
                                 "input_tokens": 0, "output_tokens": 0,
                                 "cost_usd": 0, "duration_ms": 0}
    
    # 解析 + 执行
    round_summary_lines = []
    for name, result in results.items():
        provider = _providers[name]
        portfolio = _portfolios[name]
        
        if result.get("error"):
            round_summary_lines.append(f"  ❌ {provider.display_name}: {result['error'][:50]}")
            # 仍然记录决策(空)
            portfolio.record_decision(
                current_prices, 
                {"action": "HOLD", "ticker": None, "qty": 0,
                 "reason": f"调用失败: {result['error'][:50]}", "confidence": 0,
                 "parse_ok": False},
                0, 0, f"[ERROR] {result['error']}"
            )
            continue
        
        decision = parse_decision(result["text"])
        
        # 记录决策
        portfolio.record_decision(
            current_prices, decision,
            result.get("input_tokens", 0) + result.get("output_tokens", 0),
            result.get("cost_usd", 0),
            result.get("text", "")
        )
        
        # 执行交易
        action_display = decision["action"]
        if decision["action"] == "BUY" and decision["ticker"]:
            ticker_full = decision["ticker"]
            price = current_prices.get(ticker_full, 0)
            qty = min(decision["qty"], MAX_QTY_PER_TRADE)
            if price > 0 and qty > 0:
                r = portfolio.buy(ticker_full, qty, price, decision["reason"])
                if r["ok"]:
                    action_display = f"BUY {qty} {ticker_full} @${price:.2f}"
                else:
                    action_display = f"BUY FAIL ({r['error']})"
        elif decision["action"] == "SELL" and decision["ticker"]:
            ticker_full = decision["ticker"]
            price = current_prices.get(ticker_full, 0)
            qty = min(decision["qty"], MAX_QTY_PER_TRADE)
            if price > 0 and qty > 0:
                r = portfolio.sell(ticker_full, qty, price, decision["reason"])
                if r["ok"]:
                    action_display = f"SELL {qty} {ticker_full} @${price:.2f}"
                else:
                    action_display = f"SELL FAIL ({r['error']})"
        
        conf = decision.get("confidence", 0)
        round_summary_lines.append(
            f"  {_get_emoji_for_action(decision['action'])} {provider.display_name}: "
            f"{action_display} · 信心{conf}% · ${result.get('cost_usd', 0):.4f}"
        )
    
    # 每 N 轮推送一次摘要(不刷屏)
    # 有交易的轮次必推;纯 HOLD 的轮次每 10 轮推一次摘要
    has_trade = any(
        d.get("action") in ("BUY", "SELL") 
        for name in results 
        for d in [parse_decision(results[name].get("text", ""))]
        if d.get("parse_ok")
    )
    if has_trade or _round_count % 10 == 0:
        if send_tg_fn:
            try:
                time_str = datetime.now().strftime("%H:%M:%S")
                msg = (
                    f"🏁 第 {_round_count} 轮 · {time_str}\n"
                    f"RKLB ${current_prices.get('RKLB', 0):.2f} · "
                    f"RKLX ${current_prices.get('RKLX', 0):.2f} · "
                    f"RKLZ ${current_prices.get('RKLZ', 0):.2f}\n"
                    + "\n".join(round_summary_lines)
                )
                send_tg_fn(msg)
            except Exception as e:
                print(f"  [race] tg push failed: {e}")


def _get_emoji_for_action(action: str) -> str:
    return {"BUY": "🛒", "SELL": "💰", "HOLD": "⏸️"}.get(action, "❓")


def _fetch_prices_safe() -> dict:
    """拉实时价,返回 {ticker_short: {price, low, high}}"""
    try:
        client = get_quote_client()
        quotes = client.fetch_many(TRADING_TICKERS)
        result = {}
        for tk, q in quotes.items():
            if q:
                short = tk.replace("US.", "")
                result[short] = {
                    "price": q["price"],
                    "low":   q.get("low_price", q["price"]),
                    "high":  q.get("high_price", q["price"]),
                }
        return result
    except Exception as e:
        print(f"  [race] fetch_prices error: {e}")
        return {}


def _fetch_indicators_safe(current_price: float) -> dict:
    """拉 RKLB 5M K 线 + 算指标"""
    if current_price <= 0:
        return {}
    try:
        from core.focus.micro_indicators import calc_all_micro
        client = get_quote_client()
        if not client._ensure_quote():
            return {}
        with client._quote_lock:
            ret, kl = client._quote_ctx.get_cur_kline(
                "US.RKLB", 30, KLType.K_5M, AuType.QFQ
            )
        if ret != 0 or kl is None or len(kl) == 0:
            return {}
        return calc_all_micro(kl, current_price)
    except Exception as e:
        print(f"  [race] fetch_indicators error: {e}")
        return {}


def _save_all_portfolios():
    from config.settings import BASE_DIR
    for name, p in _portfolios.items():
        path = os.path.join(BASE_DIR, "data", f"portfolio_{name}.json")
        try:
            p.save(path)
        except Exception as e:
            print(f"  [race] save {name} error: {e}")


def reset_all_portfolios() -> str:
    """重置所有账户"""
    global _portfolios
    if _race_active:
        return "⚠️ 大赛进行中,请先 /race_stop"
    
    from config.settings import BASE_DIR
    count = 0
    for fname in os.listdir(os.path.join(BASE_DIR, "data")):
        if fname.startswith("portfolio_") and fname.endswith(".json"):
            try:
                os.remove(os.path.join(BASE_DIR, "data", fname))
                count += 1
            except:
                pass
    _portfolios = {}
    return f"✅ 已重置 {count} 个 AI 账户"
