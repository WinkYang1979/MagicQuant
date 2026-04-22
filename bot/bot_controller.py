"""
MagicQuant 慧投 — Telegram Bot Controller v0.3.0
Dare to dream. Data to win.

变更 v0.5.11(2026-04-22):
  - 🆕 /profile 指令:查看当前机会密度画像 + 未来 12 小时时间线
  - 🆕 /status 升级:显示 profile / event / 今日提醒计划
  - 依赖 activity_profile v0.1.0 / event_calendar v0.1.0 /
        proactive_reminder v0.1.0 / focus_manager v0.5.8 / pusher v0.5.11

变更 v0.5.10(2026-04-22):
  - 🆕 夜盘 (overnight) 时段自动启动 Focus,实现 24h 盯盘闭环
  - 启动逻辑中 overnight 与 pre/post 合并到低频(10秒)分支
  - 夜盘启动提示附加"流动性差注意假信号"

变更 v0.3.0(2026-04-21):
  - 🆕 Focus 焦点盯盘模式:RKLB 波段做 T 信号系统
  - 新指令:/focus /unfocus /status
  - 主从盯盘(RKLB 信号源 → RKLZ/RKLX 交易)
  - 7 大触发器:波段顶/底/回撤/浮盈/异动等
  - 智能 A/B/C 推送样式
  - 盘中 2秒/次,盘外 10秒/次

变更 v0.2.3(2026-04-21):
  - 账户资金 HKD 聚合 bug 修复,多币种正确显示

变更 v0.2.2:
  - 新增 core/realtime_quote 持仓/账户实时查询能力
  - /signal 查询前同时刷新持仓(方案 2),watchlist 外持仓也显示
  - 新持仓自动加入 watchlist(方案 3,持久化到 watchlist.json)
  - signal_engine 每轮自动合并 watchlist ∪ 持仓,确保全量分析
  - fmt_signal 兼容"仅持仓"票(无指标时显示简版)

变更 v0.2.1:
  - 新增 core/realtime_quote 模块，/signal /detail 查询前刷新实时价
  - fmt_signal 改为样式 2：价格行 + 指标行 双时间戳
  - Futu QuoteContext 常驻连接，毫秒级响应

Owner: Zhen Yang
"""

import json, os, sys, time, subprocess, threading, re
sys.path.insert(0, r"C:\MagicQuant")

from config.settings import (
    TG_BOT_TOKEN as BOT_TOKEN, TG_CHAT_ID as CHAT_ID,
    SIGNALS_FILE, ACCOUNT_FILE, WATCHLIST_FILE, PUSH_TIMES,
    DEFAULT_WATCHLIST, BASE_DIR, LANGUAGE,
    CLAUDE_API_KEY, CLAUDE_MODEL, CLAUDE_PRICE_IN, CLAUDE_PRICE_OUT,
    OPENAI_API_KEY, OPENAI_MODEL, OPENAI_PRICE_IN, OPENAI_PRICE_OUT,
    STATEMENTS_DIR,
)
from version import get_logo, get_changelog_text, get_version_string, APP_NAME_CN, APP_NAME_EN, VERSION
from i18n import t, set_lang
set_lang(LANGUAGE)

BOT_CONTROLLER_VERSION = "v0.5.11"
BOT_CONTROLLER_DATE    = "2026-04-22"

# 对账单解析模块 / Statement parser module
try:
    from statement_parser import (
        parse_pdf, save_statement, load_statement,
        get_missing_dates, get_existing_dates, calc_pnl_from_statements,
        statement_path,
    )
    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False

# AI 操盘模块 / AI virtual trading module
try:
    from ai_trader import (
        run_once as ai_run_once,
        get_summary as ai_get_summary,
        get_positions_detail as ai_get_positions,
        load_trades as ai_load_trades,
        count_pdt as ai_count_pdt,
        load_portfolio,
    )
    HAS_AI_TRADER = True
except ImportError:
    HAS_AI_TRADER = False

# 实时报价模块 / Realtime quote (v0.2.1)
try:
    from core.realtime_quote import (
        get_client as get_quote_client,
        close_client as close_quote_client,
        merge_realtime_into_signal,
        merge_positions_into_signals,
    )
    HAS_REALTIME = True
except ImportError:
    HAS_REALTIME = False
    print("  [warn] core.realtime_quote not available, prices will be snapshot only")

# 焦点盯盘模块 / Focus mode (v0.3.0)
try:
    from core.focus import (
        start_focus as focus_start,
        stop_focus  as focus_stop,
        get_focus_status,
        is_focused,
        set_ai_advise,
        is_ai_advise_enabled,
        HAS_AI_ADVISOR,
    )
    HAS_FOCUS = True
    # v0.3.6: 手动召集智囊团
    try:
        from core.focus import manual_consult, HAS_MANUAL_CONSULT
    except ImportError:
        HAS_MANUAL_CONSULT = False
    # v0.3.6: 心跳监控
    try:
        from core.focus import (
            get_heartbeat_text,
            start_heartbeat_loop,
            stop_heartbeat_loop,
            is_heartbeat_enabled,
            get_heartbeat_interval,
            HAS_HEARTBEAT,
        )
    except ImportError:
        HAS_HEARTBEAT = False
except ImportError as e:
    HAS_FOCUS = False
    HAS_AI_ADVISOR = False
    HAS_MANUAL_CONSULT = False
    HAS_HEARTBEAT = False
    print(f"  [warn] core.focus not available: {e}")

# v0.4: Risk Engine + Override Log
try:
    from core.risk_engine import (
        can_trade,
        format_result_for_tg,
        run_all_fixtures,
        format_test_result_for_tg,
        compute_stats as risk_compute_stats,
        format_stats_for_tg as risk_format_stats,
        read_recent_logs as risk_read_recent,
        log_risk_check,
        get_risk_config,
    )
    HAS_RISK_ENGINE = True
except ImportError as e:
    HAS_RISK_ENGINE = False
    print(f"  [warn] core.risk_engine not available: {e}")

try:
    from core.override_logger import (
        log_override,
        read_recent_overrides,
        compute_override_stats,
        format_override_stats_for_tg,
    )
    HAS_OVERRIDE_LOG = True
except ImportError:
    HAS_OVERRIDE_LOG = False

try:
    from core.agents import (
        start_race as race_start,
        stop_race  as race_stop,
        is_race_active,
        get_race_summary,
        get_portfolios as race_portfolios,
        get_providers  as race_providers,
        reset_all_portfolios as race_reset,
        build_all_providers,
    )
    HAS_RACE = True
except ImportError as e:
    HAS_RACE = False
    print(f"  [warn] core.agents not available: {e}")

import urllib.request, urllib.parse, urllib.error
from datetime import datetime

# ── 路径 ──────────────────────────────────────────────────────────
FETCHER      = os.path.join(BASE_DIR, "core", "signal_engine.py")
USAGE_FILE   = os.path.join(BASE_DIR, "data", "usage.json")   # 费用统计文件

# ── 全局状态 ──────────────────────────────────────────────────────
pushed_times   = set()
sent_alerts    = set()
last_update_id = 0
detail_cooldown = {}   # ticker -> 上次触发时间戳，防重复点击


# ══════════════════════════════════════════════════════════════════
#  费用统计 / Usage Tracking
# ══════════════════════════════════════════════════════════════════

# Claude Sonnet 4 定价（每百万 token）
# Input: $3.00 / Output: $15.00  (截至 2026-04)
CLAUDE_PRICE_IN  = 3.00 / 1_000_000   # per token
CLAUDE_PRICE_OUT = 15.00 / 1_000_000  # per token

def load_usage():
    """加载费用统计 / Load usage stats"""
    try:
        if os.path.exists(USAGE_FILE):
            return json.load(open(USAGE_FILE, encoding="utf-8"))
    except:
        pass
    return {"month": "", "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "history": []}


def save_usage(usage):
    """保存费用统计 / Save usage stats"""
    try:
        os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
        json.dump(usage, open(USAGE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  Usage save error: {e}")


def record_usage(ticker, tokens_in, tokens_out, cost_usd):
    """记录一次 API 调用 / Record one API call"""
    usage = load_usage()
    month = datetime.now().strftime("%Y-%m")
    # 新月份重置 / Reset on new month
    if usage.get("month") != month:
        usage = {"month": month, "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "history": []}
    usage["month"] = month
    usage["calls"]      += 1
    usage["tokens_in"]  += tokens_in
    usage["tokens_out"] += tokens_out
    usage["cost_usd"]   += cost_usd
    usage["history"].append({
        "time":       datetime.now().strftime("%m-%d %H:%M"),
        "ticker":     ticker,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "cost_usd":   round(cost_usd, 6),
    })
    # 只保留最近 50 条 / Keep last 50 records
    usage["history"] = usage["history"][-50:]
    save_usage(usage)


def estimate_cost(prompt: str) -> tuple[int, float]:
    """
    粗估 token 数和费用（调用前显示）
    Rough estimate: 1 token ≈ 3 chars (mixed Chinese/English)
    Returns: (estimated_total_tokens, estimated_cost_usd)
    """
    est_in  = len(prompt) // 3 + 150   # +150 system prompt overhead
    est_out = 350                        # 200-300字 ≈ 350 tokens
    cost    = est_in * CLAUDE_PRICE_IN + est_out * CLAUDE_PRICE_OUT
    return est_in + est_out, cost


# ══════════════════════════════════════════════════════════════════
#  Claude API 调用
# ══════════════════════════════════════════════════════════════════

def build_analysis_prompt(ticker: str, signal_data: dict) -> tuple[str, str]:
    """
    构建 AI 分析 prompt（Claude 和 OpenAI 共用）
    新格式：综合判断 → 关键价位 → 风险提示 → 操作建议（含手数+金额）
    Returns: (system_prompt, user_prompt)
    """
    ind      = signal_data.get("indicators", {})
    risk     = signal_data.get("risk", {})
    sig      = signal_data.get("signal", "?")
    price    = signal_data.get("price", 0)
    name     = signal_data.get("name", ticker)
    style    = signal_data.get("style", "swing")
    pos      = signal_data.get("position", {})
    patterns = ", ".join(p["name"] for p in signal_data.get("candlestick_patterns", [])) or "无"
    reasons  = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(signal_data.get("reasons", [])[:5]))
    ph       = signal_data.get("price_history", [])

    # 账户和持仓信息
    account_size   = signal_data.get("_account_size", 20000)
    available_cash = signal_data.get("_available_cash", account_size)
    suggested_qty  = signal_data.get("suggested_shares", 0)
    sl             = risk.get("stop_loss", "?")
    t1             = risk.get("target1", "?")
    t2             = risk.get("target2", "?")

    # 当前持仓描述
    if pos and pos.get("qty", 0) > 0:
        qty        = pos["qty"]
        cost       = pos["cost_price"]
        pl_val     = pos.get("pl_val", 0)
        pl_pct     = pos.get("pl_pct", 0)
        mkt_val    = round(qty * price, 2)
        pos_desc   = (
            f"当前持仓: {qty} 股  成本: ${cost}  "
            f"现价市值: ${mkt_val:,.2f}  "
            f"浮盈亏: {'+'if pl_val>=0 else ''}{pl_val:.2f} ({pl_pct:+.1f}%)"
        )
        action_hint = f"持仓者可选择：继续持有 / 部分止盈（建议卖出股数）/ 全部卖出"
    else:
        pos_desc    = "当前无持仓"
        action_hint = f"可用资金: ${available_cash:,.2f}，系统建议买入 {suggested_qty} 股"

    system = (
        "你是一位有10年经验的美股量化交易员，擅长技术分析和日内/波段交易。"
        "分析时直接、简洁、有逻辑，不废话，不加免责声明。"
        "操作建议必须给出明确的股数和总金额，不能只说价格范围。"
        "用中文回答，严格按用户要求的格式输出。"
    )

    user = (
        f"请分析 {ticker}（{name}，{style}风格），当前数据如下：\n\n"
        f"═══ 市场数据 ═══\n"
        f"现价: ${price:.2f}  系统信号: {sig}  信心: {signal_data.get('confidence', 0)}%\n"
        f"RSI(相对强弱): {ind.get('rsi','?')}  "
        f"MACD柱(动量): {ind.get('macd_hist',0):+.4f}  "
        f"量比: {ind.get('vol_ratio',0)}x\n"
        f"布林%B: {ind.get('pct_b',0):.3f}  ATR(波幅): {ind.get('atr','?')}\n"
        f"MA5/20/60: {ind.get('ma5','?')} / {ind.get('ma20','?')} / {ind.get('ma60','?')}\n"
        f"布林上/下轨: ${ind.get('bb_upper','?')} / ${ind.get('bb_lower','?')}\n"
        f"系统止损: ${sl}  目标1: ${t1}  目标2: ${t2}\n"
        f"K线形态: {patterns}\n"
        f"近7日收盘: {ph}\n\n"
        f"═══ 账户状态 ═══\n"
        f"账户规模: ${account_size:,.2f}  {pos_desc}\n"
        f"{action_hint}\n\n"
        f"信号依据:\n{reasons}\n\n"
        f"═══ 输出格式（每段2-4句，总计250-350字）═══\n"
        f"【综合判断】当前行情特征，结合技术面给出持有/入场/离场的核心结论\n"
        f"【关键价位】列出最重要支撑位和压力位（给具体价格数字）\n"
        f"【风险提示】当前最需要警惕的1-2个风险点\n"
        f"【操作建议】给出明确建议：\n"
        f"  - 若建议买入：买入XX股，入场价$XX-$XX，总额约$XX，止损$XX，目标$XX\n"
        f"  - 若建议持有：继续持有XX股 或 减仓至XX股，止损严守$XX\n"
        f"  - 若建议卖出：卖出XX股（全部/部分），预计回收$XX\n"
    )

    return system, user


def call_claude(ticker: str, signal_data: dict) -> str:
    """
    调用 Claude API + web_search 工具做深度分析
    包含：技术面 + 账户仓位 + 联网搜索新闻/大单/期货
    """
    if not CLAUDE_API_KEY:
        return t("claude_no_key")

    system, user = build_analysis_prompt(ticker, signal_data)

    # 预估费用
    est_tokens, est_cost = estimate_cost(user)

    # 加入联网搜索的扩展 prompt
    ticker_short = ticker.replace("US.", "")
    name         = signal_data.get("name", ticker_short)
    search_instruction = (
        "\n\n═══ 联网搜索任务 ═══\n"
        f"请用 web_search 搜索 {ticker_short} 最新消息（近7天），"
        f"重点找：重大新闻、期权异动、分析师评级变化、相关行业动态。\n"
        "搜索结果请精简摘要，控制在200字以内。\n"
        "在【综合判断】前增加：\n"
        "【市场消息】列出2-3条最重要的消息（无则写：暂无重大消息）\n"
        "注意：必须完整输出所有板块，包括【操作建议】，不可截断。\n"
    )
    user_with_search = user + search_instruction

    # 构建 API 请求（加 web_search 工具）
    payload = json.dumps({
        "model":      CLAUDE_MODEL,
        "max_tokens": 1500,
        "system":     system,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages":   [{"role": "user", "content": user_with_search}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return t("claude_api_error", code=e.code, msg=body[:200])
    except Exception as e:
        return t("claude_timeout", err=str(e))

    # 解析响应（可能含多个 content block）
    ai_text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            ai_text += block["text"]

    usage_info = result.get("usage", {})
    tokens_in  = usage_info.get("input_tokens", est_tokens)
    tokens_out = usage_info.get("output_tokens", 400)
    cost_usd   = tokens_in * CLAUDE_PRICE_IN + tokens_out * CLAUDE_PRICE_OUT
    record_usage(ticker, tokens_in, tokens_out, cost_usd)

    cost_note = t("claude_cost_note", tin=tokens_in, tout=tokens_out, cost=cost_usd * 100)
    return ai_text.strip() + "\n\n" + cost_note


def call_openai(ticker: str, signal_data: dict) -> str:
    """
    调用 OpenAI API 做深度分析
    使用相同 prompt 格式，OpenAI 原生支持联网（需开启 browsing）
    """
    if not OPENAI_API_KEY:
        return "⚠️ 未配置 OPENAI_API_KEY，请在 config/settings.py 中填入。"

    system, user = build_analysis_prompt(ticker, signal_data)
    ticker_short = ticker.replace("US.", "")
    name = signal_data.get("name", ticker_short)

    # OpenAI 联网提示（通过 prompt 引导）
    search_instruction = (
        "\n\n═══ 市场消息分析 ═══\n"
        f"请基于你的知识，结合 {ticker_short}（{name}）近期可能的重大消息分析：\n"
        "1. 近期是否有重大新闻、财报、分析师评级变化\n"
        "2. 相关行业动态和宏观因素\n"
        "3. 期权/期货市场异动信号\n"
        "在【综合判断】前增加：\n"
        "【市场消息】列出2-3条影响该股的重要消息（无则写：暂无重大消息）\n"
    )
    user_final = user + search_instruction

    payload = json.dumps({
        "model":   OPENAI_MODEL,
        "tools":   [{"type": "web_search_preview"}],
        "input":   f"{system}\n\n{user_final}",
        "max_output_tokens": 1000,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return f"❌ OpenAI API 错误 {e.code}: {body[:200]}"
    except Exception as e:
        return f"❌ OpenAI 超时或网络错误: {e}"

    # 解析 responses API 格式
    ai_text = ""
    for item in result.get("output", []):
        if item.get("type") == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    ai_text += block.get("text", "")

    if not ai_text:
        return "❌ OpenAI 返回内容为空"

    usage_info = result.get("usage", {})
    tokens_in  = usage_info.get("input_tokens", 0)
    tokens_out = usage_info.get("output_tokens", 0)
    cost_usd   = tokens_in * OPENAI_PRICE_IN + tokens_out * OPENAI_PRICE_OUT
    record_usage(f"{ticker}_openai", tokens_in, tokens_out, cost_usd)

    cost_note = f"\nAI算力成本: 输入{tokens_in}tok + 输出{tokens_out}tok = {cost_usd*100:.3f}¢"
    return ai_text.strip() + "\n\n" + cost_note

def send_tg(text, buttons=None):
    text = re.sub(r"<[^>]+>", "", str(text))
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    chunks = [text[i:i+3500] for i in range(0, len(text), 3500)]
    for i, chunk in enumerate(chunks):
        try:
            url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": chunk}
            if buttons and i == len(chunks) - 1:
                payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})
            data = urllib.parse.urlencode(payload).encode()
            urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
        except Exception as e:
            print(f"  TG error: {e}")


def handle_callback(callback_query, wl):
    """处理 inline 按钮点击 / Handle inline button clicks"""
    data = callback_query.get("data", "")

    # 先应答消除 loading 圈，show_alert=true 弹出需要点击关闭的提示框
    try:
        url   = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
        cdata = urllib.parse.urlencode({
            "callback_query_id": callback_query["id"],
            "text":       "✅ 已收到，正在分析，请稍候...",
            "show_alert": "true",   # 弹出对话框，需手动关闭
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=cdata), timeout=5)
    except:
        pass

    print(f"  CALLBACK: {data}")

    if data.startswith("detail_"):
        ticker_cb = data.replace("detail_", "")

        # ── 防重复点击：60秒冷却 ──────────────────────────────────
        now_ts = time.time()
        last_ts = detail_cooldown.get(ticker_cb, 0)
        if now_ts - last_ts < 60:
            remaining = int(60 - (now_ts - last_ts))
            send_tg(f"⏳ {ticker_cb} 分析正在进行中，{remaining}秒后可再次触发。")
            return None
        detail_cooldown[ticker_cb] = now_ts

        # ── 立即发一条确认消息，让用户知道已收到 ─────────────────
        send_tg(f"⏳ 正在分析 {ticker_cb}，请稍候...")

        try:
            result = cmd_detail(ticker_cb)
            return result
        except Exception as e:
            import traceback
            err_msg = f"❌ 按钮出错 [{ticker_cb}]\n{traceback.format_exc()[-400:]}"
            print(err_msg)
            send_tg(err_msg)
            return None

    if data.startswith("agent_"):
        ticker_cb = data.replace("agent_", "")
        send_tg(
            f"🔬 {ticker_cb} Agent 深度分析\n"
            ""
            f"Agent 框架开发中,即将上线.\n"
            f"将支持:Graham价值分析 / Cathie Wood成长分析\n"
            f"/ 多空力量对比 / 新闻情绪综合评估"
        )
        return None

    # ── Focus 反馈按钮(v0.3.0)─────────────────────────
    # fb_done_XXX  用户已下单,需验证
    # fb_skip_XXX  用户忽略
    # fb_repx_XXX  重算挂单价
    # fb_ai_XXX    问 AI
    if data.startswith("fb_"):
        if not HAS_FOCUS:
            send_tg("❌ Focus 模块未加载")
            return None

        from core.focus import verify_trigger, mark_ignored, recompute_price

        parts = data.split("_", 2)
        if len(parts) < 3:
            send_tg("⚠️ 按钮数据格式错误")
            return None

        action = parts[1]          # done / skip / repx / ai
        trigger_id = parts[2]

        try:
            if action == "done":
                send_tg("⏳ 正在验证持仓变化...")
                result = verify_trigger(trigger_id, send_tg_fn=send_tg, auto_retry_sec=30)
                send_tg(result)
            elif action == "skip":
                send_tg(mark_ignored(trigger_id))
            elif action == "repx":
                send_tg(recompute_price(trigger_id))
            elif action == "ai":
                # 简版:触发对当前主票的 /detail
                ticker_short = trigger_id.split("_")[0].replace("US.", "")
                send_tg(f"🧠 正在 AI 深度分析 {ticker_short}...")
                try:
                    result = cmd_detail(ticker_short)
                    if result:
                        send_tg(result)
                except Exception as e:
                    send_tg(f"❌ AI 分析失败: {e}")
            else:
                send_tg(f"⚠️ 未知反馈动作: {action}")
        except Exception as e:
            import traceback
            print(f"  [fb] error: {traceback.format_exc()}")
            send_tg(f"❌ 反馈处理失败: {e}")
        return None

    # ── Focus v0.5.9 按钮回调 ──────────────────────────────
    if data.startswith("focus_"):
        try:
            if data.startswith("focus_order_"):
                etf = data.replace("focus_order_", "")
                try:
                    from core.focus.pusher import format_order_text
                    order_text = format_order_text(etf)
                    if order_text:
                        send_tg(order_text)
                    else:
                        send_tg(f"⚠️ {etf} 交易计划已过期,等下一个信号")
                except ImportError:
                    send_tg("❌ pusher 模块未加载")
                return None

            if data.startswith("focus_ai_"):
                ticker_cb = data.replace("focus_ai_", "")
                now_ts = time.time()
                last_ts = detail_cooldown.get(ticker_cb, 0)
                if now_ts - last_ts < 60:
                    send_tg(f"⏳ {ticker_cb} 分析中,{int(60-(now_ts-last_ts))}秒后再试")
                    return None
                detail_cooldown[ticker_cb] = now_ts
                send_tg(f"🧠 正在用 AI 分析 {ticker_cb},请稍候...")
                try:
                    return cmd_detail(ticker_cb)
                except Exception as e:
                    import traceback
                    send_tg(f"❌ AI 分析失败: {traceback.format_exc()[-300:]}")
                    return None

            if data == "focus_ignore":
                send_tg("👌 已忽略,继续盯盘")
                return None

            if data.startswith("focus_detail_"):
                ticker_cb = data.replace("focus_detail_", "")
                try:
                    wl_local = load_watchlist()
                    return cmd_signal([ticker_cb], wl_local)
                except Exception as e:
                    send_tg(f"获取详情失败: {e}")
                    return None

            send_tg(f"⚠️ 暂未实现: {data}")
        except Exception as e:
            import traceback
            print(f"  [focus_cb] error: {traceback.format_exc()}")
            send_tg(f"❌ Focus 按钮处理失败: {e}")
        return None

    return None


def get_updates(offset=0):
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
        resp = urllib.request.urlopen(url, timeout=35)
        return json.loads(resp.read()).get("result", [])
    except:
        return []


# ══════════════════════════════════════════════════════════════════
#  数据加载
# ══════════════════════════════════════════════════════════════════

AI_ANALYSIS_FILE = os.path.join(BASE_DIR, "data", "ai_analysis.json")


def save_ai_analysis(ticker: str, source: str, text: str, signal_data: dict):
    """
    保存 AI 分析结果到 ai_analysis.json，供 Dashboard 读取
    source: 'claude' 或 'openai'
    """
    try:
        data = {}
        if os.path.exists(AI_ANALYSIS_FILE):
            data = json.load(open(AI_ANALYSIS_FILE, encoding="utf-8"))
        if ticker not in data:
            data[ticker] = {}
        data[ticker][source] = {
            "text":       text,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "cached_ts":  time.time(),   # 用于缓存过期判断
            "price":      signal_data.get("price", 0),
            "signal":     signal_data.get("signal", "?"),
        }
        os.makedirs(os.path.dirname(AI_ANALYSIS_FILE), exist_ok=True)
        json.dump(data, open(AI_ANALYSIS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  save_ai_analysis error: {e}")


def load_signals():
    try:
        data = json.load(open(SIGNALS_FILE, encoding="utf-8"))
        # 注入指标生成时间，便于 fmt_signal 显示双时间戳
        generated_at = data.get("generated_at", "")
        for s in data.get("signals", []):
            s["indicator_at"] = generated_at
        return data
    except:
        return None


# ══════════════════════════════════════════════════════════════════
#  实时价刷新辅助 / Realtime Quote Refresh Helpers (v0.2.1)
# ══════════════════════════════════════════════════════════════════

def refresh_quote_into_signal(s: dict) -> dict:
    """
    查询前刷新：用 Futu 实时 quote 覆盖 signal 中的价格字段。
    失败自动降级为 JSON 原值（price_is_live=False）。
    """
    if not HAS_REALTIME or not s:
        if s is not None:
            s["price_is_live"] = False
        return s
    try:
        quote = get_quote_client().fetch_one(s.get("ticker", ""))
        return merge_realtime_into_signal(s, quote)
    except Exception as e:
        print(f"  [realtime] refresh failed: {e}")
        s["price_is_live"] = False
        return s


def refresh_quotes_batch(signals: list) -> list:
    """批量刷新实时价（用于 /signal 列表，4 只票约 0.3~0.5 秒）。"""
    if not HAS_REALTIME or not signals:
        for s in signals or []:
            s["price_is_live"] = False
        return signals
    try:
        tickers = [s.get("ticker", "") for s in signals if s.get("ticker")]
        quotes  = get_quote_client().fetch_many(tickers)
        for s in signals:
            q = quotes.get(s.get("ticker"))
            merge_realtime_into_signal(s, q)
        return signals
    except Exception as e:
        print(f"  [realtime] batch refresh failed: {e}")
        for s in signals:
            s["price_is_live"] = False
        return signals


def refresh_positions_into_signals(signals: list) -> list:
    """
    实时刷新持仓(v0.2.2)
    - 把当前所有 watchlist 里的票的持仓更新为最新
    - 如果账户里有 watchlist 外的票(如刚买的 RKLZ),在 signals 末尾追加"仅持仓"记录
    - 同时把新票自动加入 watchlist(持久化)
    """
    if not HAS_REALTIME:
        return signals
    try:
        positions = get_quote_client().fetch_positions()
        if positions is None:
            print("  [realtime] positions fetch failed, keep JSON data")
            return signals

        # 先合并持仓到 signals
        signals = merge_positions_into_signals(signals, positions)

        # 自动把新持仓票加入 watchlist(方案 3)
        try:
            wl = load_watchlist()
            existing = set(wl.get("auto", []) + wl.get("manual", []))
            new_tickers = [tk for tk in positions.keys() if tk not in existing]
            if new_tickers:
                wl.setdefault("auto", [])
                for tk in new_tickers:
                    if tk not in wl["auto"]:
                        wl["auto"].append(tk)
                save_watchlist(wl)
                print(f"  [auto-watchlist] 新持仓自动加入 watchlist: {new_tickers}")
        except Exception as e:
            print(f"  [auto-watchlist] 自动加入失败: {e}")

        return signals
    except Exception as e:
        print(f"  [realtime] positions refresh error: {e}")
        return signals


def refresh_account_live() -> dict | None:
    """实时拉账户资金(v0.2.2),失败返回 None,调用方自行用 JSON fallback"""
    if not HAS_REALTIME:
        return None
    try:
        return get_quote_client().fetch_account()
    except Exception as e:
        print(f"  [realtime] account fetch error: {e}")
        return None


def load_watchlist():
    try:
        if os.path.exists(WATCHLIST_FILE):
            return json.load(open(WATCHLIST_FILE, encoding="utf-8"))
    except:
        pass
    default = {"auto": [], "manual": ["US.RKLB", "US.RKLX", "US.TSLA", "US.SOXL"]}
    save_watchlist(default)
    return default


def save_watchlist(wl):
    wl["updated_at"] = datetime.now().isoformat()
    json.dump(wl, open(WATCHLIST_FILE, "w", encoding="utf-8"), indent=2)


def load_account_data():
    try:
        return json.load(open(ACCOUNT_FILE, encoding="utf-8"))
    except:
        return None


def all_tickers(wl):
    return list(dict.fromkeys(wl.get("auto", []) + wl.get("manual", [])))


def norm(raw):
    raw = raw.strip().upper()
    return raw if raw.startswith("US.") else "US." + raw


def safe_float(val, default=0):
    try:
        v = float(val)
        return v if v == v else default  # NaN check
    except:
        return default


def refresh():
    try:
        subprocess.run([sys.executable, FETCHER, "--once"], timeout=90, cwd=BASE_DIR)
    except Exception as e:
        print(f"  Refresh error: {e}")


# ══════════════════════════════════════════════════════════════════
#  格式化输出
# ══════════════════════════════════════════════════════════════════

def stars(n):
    return "★" * min(5, n) + " " + t("list_urgency", lvl=n)


def pct_from_price(price: float, target: float) -> str:
    """计算目标价相对当前价的涨跌幅 / Calc % change from current price to target"""
    if price <= 0:
        return ""
    pct = (target - price) / price * 100
    return f"{'+' if pct >= 0 else ''}{pct:.1f}%"


def _fmt_position_only(s: dict, idx=None) -> str:
    """
    格式化"仅持仓"票(v0.2.2)
    场景: 用户刚买入但还没进 watchlist,signal_engine 也还没分析
    只显示基本持仓信息 + 提示加入 watchlist
    """
    ticker_short = s["ticker"].replace("US.", "")
    pos = s.get("position", {})
    price = s.get("price", pos.get("current_price", 0) or pos.get("cost_price", 0))
    qty   = pos.get("qty", 0)
    cost  = pos.get("cost_price", 0)
    pl    = pos.get("pl_val", 0)
    plp   = pos.get("pl_pct", 0)
    sign  = "+" if pl >= 0 else ""

    prefix = f"【{idx}】" if idx is not None else ""

    lines = [
        f"{prefix}{ticker_short}  🆕 新持仓(无技术指标)",
        "",
        f"💼 持仓 {qty:.0f} 股 @ ${cost:.2f}",
        f"💵 现价 ${price:.2f}",
        f"📊 盈亏 {sign}${pl:.2f} ({sign}{plp:.2f}%)",
        "",
        f"⏳ 技术指标将在下次 signal_engine 刷新时可用",
        f"💡 /detail {ticker_short} 手动触发分析",
    ]
    return "\n".join(lines)


def calc_fees(shares: int, price: float, side: str) -> dict:
    """
    富途澳洲（Moomoo AU）美股实际费率，基于账户对账单验证（2026-04）
    每笔订单固定收费，与股数无关：
      - Platform Fee:   $0.99  买+卖
      - Settlement Fee: $0.30  买+卖
      - TAF:            $0.02  仅卖出（FINRA，固定）
      - 无佣金(Commission)
    Returns: dict with fee breakdown and total
    """
    platform   = 0.99
    settlement = 0.30
    taf        = 0.02 if side == "SELL" else 0.00
    total      = round(platform + settlement + taf, 2)
    return {
        "platform":   platform,
        "settlement": settlement,
        "taf":        taf,
        "total":      total,
        "side":       side,
    }


def fmt_signal(s, idx=None):
    """
    格式化单只股票信号摘要
    - HOLD：不显示操作建议块
    - BUY/SELL：显示手数、金额、富途手续费明细
    - 仅持仓(v0.2.2): 新买入但还没进 watchlist 的票,只显示持仓信息
    idx: 序号（int），None 时不显示序号
    注意：不能用 t 作变量名（会覆盖 i18n 的 t 函数），统一用 ticker_short
    """
    # v0.2.2: 处理"仅持仓"票(刚买入,还没分析指标)
    if s.get("_position_only"):
        return _fmt_position_only(s, idx)

    ticker_short = s["ticker"].replace("US.", "")
    sig          = s["signal"]
    ind          = s["indicators"]
    risk         = s.get("risk", {})
    pos          = s.get("position")
    lvl          = s.get("urgency", 1)
    cs           = "+" if s["change"] >= 0 else ""
    price        = s["price"]
    shares       = s.get("suggested_shares", 0)

    sig_label    = {"BUY": t("sig_buy"), "SELL": t("sig_sell"), "HOLD": t("sig_hold")}.get(sig, t("sig_unknown"))
    action_label = {"BUY": t("action_buy"), "SELL": t("action_sell"), "HOLD": t("action_hold")}.get(sig, t("action_unknown"))

    # 标题行
    prefix = t("stock_idx", n=idx) if idx is not None else t("stock_no_idx")
    title  = t("signal_header",
               prefix=prefix, ticker=ticker_short, name=s["name"],
               sig=sig_label, lvl=lvl, conf=s.get("confidence", 0))

    sl  = risk.get("stop_loss")
    t1  = risk.get("target1")
    t2  = risk.get("target2")
    rps = risk.get("risk_per_share", "?")

    # ── 实时价 & 指标时间显示(样式 2,v0.2.1)───────────────
    is_live       = s.get("price_is_live", False)
    price_at      = s.get("price_at", "") or s.get("update_time", "")
    indicator_at  = s.get("indicator_at", "")
    quote_age_sec = s.get("quote_age_sec", -1)

    def _short_time(ts):
        """只取 HH:MM:SS 部分"""
        try:
            if not ts:
                return "?"
            if "T" in ts:
                return ts.split("T")[-1][:8]
            if " " in ts:
                return ts.split(" ")[-1][:8]
            return ts[-8:]
        except:
            return "?"

    price_time_short = _short_time(price_at)
    indi_time_short  = _short_time(indicator_at)

    # 时效标签
    if is_live:
        if 0 <= quote_age_sec < 60:
            live_tag = "🟢 实时"
        elif quote_age_sec < 300:
            live_tag = f"🟡 {quote_age_sec}s前"
        elif quote_age_sec < 3600:
            live_tag = f"🟠 {quote_age_sec//60}m前"
        else:
            live_tag = "⚫ 盘外"
    else:
        live_tag = "⚪ 快照"

    lines = [
        title,
        "",
        f"💵 价格 ${price:.2f} ({cs}{s['change']:.2f} {cs}{s['change_pct']:.2f}%)  🕐 {price_time_short} {live_tag}",
        f"📊 指标 RSI/MACD/BB 等              🕐 {indi_time_short}",
        f"止损价:  ${sl}  ({pct_from_price(price, sl) if sl else '?'})",
        f"目标价1: ${t1}  ({pct_from_price(price, t1) if t1 else '?'})",
        f"目标价2: ${t2}  ({pct_from_price(price, t2) if t2 else '?'})",
        f"风险/股: ${rps}  (每股最大亏损)",
    ]

    # ── 操作建议块：HOLD 不显示，BUY/SELL 显示手数+费用 ──────────
    if sig in ("BUY", "SELL") and shares > 0:
        total_cost = round(price * shares, 2)
        fees       = calc_fees(shares, price, sig)
        # 买入：只算买入手续费；卖出：算卖出手续费
        # 完整往返（买+卖）参考费用也一并展示
        roundtrip  = round(
            calc_fees(shares, price, "BUY")["total"] +
            calc_fees(shares, price, "SELL")["total"], 4)

        lines += [
            "",
            f"— {action_label} —",
            t("suggest_shares", n=shares),
            t("unit_price",     price=price),
            t("total_cost",     total=total_cost),
            "",
            t("section_fees"),
            t("fee_platform",   val=fees["platform"]),
            t("fee_settlement", val=fees["settlement"]),
        ]
        if fees["taf"] > 0:
            lines.append(t("fee_taf", val=fees["taf"]))
        lines += [
            t("fee_this_trade", val=fees["total"]),
            t("fee_roundtrip",  val=roundtrip),
        ]

    lines += [
        "",
        t("section_tech"),
        f"RSI 相对强弱: {ind['rsi']}  "
        f"{'⚠️超买' if ind['rsi']>70 else '💡超卖' if ind['rsi']<35 else '正常'}",
        f"MACD 柱状: {ind['macd_hist']:+.3f}  "
        f"{'多头↑' if ind['macd_hist']>0 else '空头↓'}",
        f"量比: {ind['vol_ratio']}x  "
        f"{'放量' if ind['vol_ratio']>1.3 else '缩量' if ind['vol_ratio']<0.7 else '均量'}",
    ]
    if "ma5" in ind and "ma20" in ind:
        ma_trend = "多头排列↑" if ind["ma5"] > ind["ma20"] else "空头排列↓"
        lines += [
            f"MA5  (5日均线):  {ind['ma5']}",
            f"MA20 (20日均线): {ind['ma20']}",
            f"MA60 (60日均线): {ind.get('ma60', '?')}  {ma_trend}",
        ]

    for p in s.get("candlestick_patterns", []):
        lines.append(t("candlestick", name=p["name"], desc=p["desc"]))

    # 仓位块：始终显示，无持仓显示 0
    held = pos and pos.get("held", pos.get("qty", 0) > 0)
    lines.append("")
    lines.append(t("section_position"))
    if held and pos.get("qty", 0) > 0:
        ps      = "+" if pos["pl_val"] >= 0 else ""
        cur_val = round(pos["qty"] * price, 2)
        lines += [
            f"  持仓: {pos['qty']} 股  成本: ${pos['cost_price']}  现价: ${price:.2f}",
            f"  持仓市值: ${cur_val:,.2f}",
            t("pos_pl", sign=ps, pl=pos["pl_val"], pct=pos["pl_pct"]),
        ]
    else:
        lines.append("  当前无持仓  (0 股  $0.00)")

    if s.get("reasons"):
        lines.append("")
        lines.append(t("signal_reason", reason=s["reasons"][0]))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  指令处理
# ══════════════════════════════════════════════════════════════════

def cmd_detail(ticker_raw, force_refresh=False):
    """
    推送单只股票详细分析 + Claude AI 深度分析
    force_refresh=True 时忽略缓存强制重新联网
    v0.2.1: 查询前刷新实时价
    v0.2.2: 同时刷新持仓,兼容 watchlist 外的新持仓票
    """
    data = load_signals()
    if not data:
        return t("no_data_futu")          # 直接 return，callback 能发
    ticker = norm(ticker_raw)

    # 🆕 v0.2.2: 先刷一下持仓,把新持仓票并进来
    signals = refresh_positions_into_signals(data.get("signals", []))
    data["signals"] = signals

    sig_map = {s["ticker"]: s for s in data.get("signals", [])}
    s = sig_map.get(ticker)
    if not s:
        return t("no_data_ticker", ticker=ticker_raw)
    if "error" in s:
        return t("data_error", ticker=ticker_raw, err=s["error"])

    # 🆕 刷新实时价(v0.2.1)
    s = refresh_quote_into_signal(s)

    # 🆕 v0.2.2: 如果是"仅持仓"票(没有技术指标),提示用户并返回简版
    if s.get("_position_only") or not s.get("indicators"):
        ticker_short = s["ticker"].replace("US.", "")
        pos = s.get("position", {})
        qty = pos.get("qty", 0)
        cost = pos.get("cost_price", 0)
        pl = pos.get("pl_val", 0)
        plp = pos.get("pl_pct", 0)
        price = s.get("price", 0)
        sign = "+" if pl >= 0 else ""
        return (
            f"⚠️ {ticker_short} 技术指标尚未生成\n"
            f"━━━━━━━━━━━━━━\n"
            f"💼 持仓 {qty:.0f} 股 @ ${cost:.2f}\n"
            f"💵 现价 ${price:.2f}\n"
            f"📊 盈亏 {sign}${pl:.2f} ({sign}{plp:.2f}%)\n\n"
            f"💡 下次 signal_engine 运行(约几分钟内)将自动分析\n"
            f"💡 {ticker_short} 已自动加入 watchlist\n"
            f"💡 立即触发: 运行 python core\\signal_engine.py --once"
        )

    ticker_short = s["ticker"].replace("US.", "")
    ind   = s["indicators"]
    risk  = s.get("risk", {})
    sig   = s["signal"]
    price = s["price"]                    # ← 修复 NameError
    pos   = s.get("position")
    sig_label = {"BUY": t("sig_buy"), "SELL": t("sig_sell"), "HOLD": t("sig_hold")}.get(sig, t("sig_unknown"))

    lines = [
        t("detail_title", sig=sig_label.strip("[]【】"), ticker=ticker_short),
        "",
        t("section_reasons"),
    ]
    for i, reason in enumerate(s.get("reasons", []), 1):
        lines.append(f"{i}. {reason}")

    atr  = ind.get("atr", 0)
    sl   = risk.get("stop_loss")
    t1   = risk.get("target1")
    t2   = risk.get("target2")
    rps  = risk.get("risk_per_share", "?")
    style = s.get("style", "swing")
    sl_mult = "1.0×ATR" if style == "daytrader" else "1.5×ATR"
    t1_mult = "1.5×ATR" if style == "daytrader" else "2.0×ATR"
    t2_mult = "2.5×ATR" if style == "daytrader" else "3.5×ATR"

    lines += [
        "",
        t("section_full_tech"),
        f"RSI 相对强弱指数:  {ind['rsi']}  "
        f"{t('rsi_overbought') if ind['rsi']>70 else t('rsi_oversold') if ind['rsi']<30 else t('rsi_normal')}",
        f"MACD 柱状值:      {ind['macd_hist']:+.4f}  "
        f"{t('macd_bull') if ind['macd_hist']>0 else t('macd_bear')}",
        f"布林%B 位置:       {ind['pct_b']:.3f}  "
        f"{t('bb_upper') if ind['pct_b']>0.8 else t('bb_lower') if ind['pct_b']<0.2 else t('bb_mid')}",
        f"量比（相对均量）:  {ind['vol_ratio']}x  "
        f"{t('vol_high') if ind['vol_ratio']>1.3 else t('vol_low') if ind['vol_ratio']<0.7 else t('vol_normal')}",
        f"ATR 平均真实波幅:  {atr}",
        f"MA5  (5日均线):    {ind.get('ma5', '?')}",
        f"MA10 (10日均线):   {ind.get('ma10', '?')}",
        f"MA20 (20日均线):   {ind.get('ma20', '?')}",
        f"MA60 (60日均线):   {ind.get('ma60', '?')}",
        f"布林上轨:          ${ind.get('bb_upper', '?')}",
        f"布林下轨:          ${ind.get('bb_lower', '?')}",
        "",
        t("section_risk"),
        f"止损价:  ${sl}  ({pct_from_price(price, sl) if sl else '?'})  依据: {sl_mult}",
        f"目标1:   ${t1}  ({pct_from_price(price, t1) if t1 else '?'})  依据: {t1_mult}",
        f"目标2:   ${t2}  ({pct_from_price(price, t2) if t2 else '?'})  依据: {t2_mult}",
        f"风险/股: ${rps}  (当前价到止损的距离，即每股最大亏损)",
        t("suggest_shares", n=s.get("suggested_shares", 0)),
        f"  → 账户 5% 风险仓位: ${round(s.get('suggested_shares',0) * float(rps if rps != '?' else 0), 2):,.2f}",
        "",
    ]

    for p in s.get("candlestick_patterns", []):
        lines.append(t("candlestick", name=p["name"], desc=p["desc"]))

    held = pos and pos.get("held", pos.get("qty", 0) > 0)
    lines.append("")
    lines.append(t("section_position"))
    if held and pos.get("qty", 0) > 0:
        ps      = "+" if pos["pl_val"] >= 0 else ""
        cur_val = round(pos["qty"] * price, 2)
        lines += [
            f"  持仓: {pos['qty']} 股  成本: ${pos['cost_price']}  现价: ${price:.2f}",
            f"  持仓市值: ${cur_val:,.2f}",
            t("pos_pl_short", sign=ps, pl=pos["pl_val"], pct=pos["pl_pct"]),
        ]
    else:
        lines.append("  当前无持仓  (0 股  $0.00)")

    lines.append("")
    lines.append(t("updated_at", t=s.get("update_time", "?")))

    # ── Claude AI 分析 ────────────────────────────────────────────
    # 先发送基础技术面（不等 AI）/ Send technical data first, AI async
    if CLAUDE_API_KEY:
        lines.append("")
        lines.append(t("claude_analyzing", ticker=ticker_short))
    else:
        lines.append("")
        lines.append(t("claude_no_key_hint"))   # 提示配置 Key，不报错

    base_text = "\n".join(lines)
    send_tg(base_text)

    if not CLAUDE_API_KEY and not OPENAI_API_KEY:
        return None

    # 异步调用两个 AI，并行执行 / Async parallel AI calls
    def ai_push():
        # ── 缓存检查：1小时内同一股票不重复联网调用 ──────────────
        cache_ttl    = 3600  # 秒，1小时
        use_cache    = not force_refresh
        cached_claude = None
        cached_openai = None

        if use_cache and os.path.exists(AI_ANALYSIS_FILE):
            try:
                cached = json.load(open(AI_ANALYSIS_FILE, encoding="utf-8"))
                ticker_data = cached.get(ticker_short, {})
                now_ts = time.time()

                for src, key in [("claude", "claude"), ("openai", "openai")]:
                    entry = ticker_data.get(src)
                    if entry and entry.get("cached_ts", 0) + cache_ttl > now_ts:
                        if src == "claude":
                            cached_claude = entry.get("text")
                        else:
                            cached_openai = entry.get("text")
            except:
                pass

        # 有缓存：直接推送，告知用户
        if cached_claude or cached_openai:
            age_min = int((time.time() - (
                json.load(open(AI_ANALYSIS_FILE, encoding="utf-8"))
                .get(ticker_short, {})
                .get("claude" if cached_claude else "openai", {})
                .get("cached_ts", time.time())
            )) / 60) if os.path.exists(AI_ANALYSIS_FILE) else 0

            send_tg(
                f"📋 {ticker_short} AI 分析（{age_min}分钟前缓存）\n"
                f"发送 /detail {ticker_short} fresh 可强制刷新"
            )
            if cached_claude:
                buttons = [[{"text": f"🔬 {ticker_short} Agent 深度分析",
                             "callback_data": f"agent_{ticker_short}"}]]
                send_tg(t("claude_result_header", ticker=ticker_short) + "\n\n" + cached_claude,
                        buttons=buttons)
            if cached_openai:
                send_tg(f"🟢 OpenAI 分析 | {ticker_short}\n\n" + cached_openai)
            return

        # 无缓存或强制刷新：调用 API
        from config.settings import ACCOUNT_SIZE
        s_with_account = dict(s)
        s_with_account["_account_size"]   = ACCOUNT_SIZE
        s_with_account["_available_cash"] = ACCOUNT_SIZE

        # 尝试读取真实可用现金
        try:
            acc_data = load_account_data()
            if acc_data and acc_data.get("account"):
                cash = safe_float(acc_data["account"].get("cash", ACCOUNT_SIZE))
                if cash > 0:
                    s_with_account["_available_cash"] = cash
        except:
            pass

        _, est_cost = estimate_cost(
            f"{ticker_short} {sig} RSI={ind.get('rsi')} MACD={ind.get('macd_hist')}")

        claude_result = [None]
        openai_result = [None]

        def _call_claude():
            if CLAUDE_API_KEY:
                send_tg(t("claude_estimating_search", ticker=ticker_short, cost=est_cost * 100))
                claude_result[0] = call_claude(ticker_short, s_with_account)

        def _call_openai():
            if OPENAI_API_KEY:
                openai_result[0] = call_openai(ticker_short, s_with_account)

        threads = []
        if CLAUDE_API_KEY:
            th = threading.Thread(target=_call_claude, daemon=True)
            th.start()
            threads.append(th)
        if OPENAI_API_KEY:
            th = threading.Thread(target=_call_openai, daemon=True)
            th.start()
            threads.append(th)

        for th in threads:
            th.join(timeout=90)

        # 推送 Claude 结果，并写入文件
        if claude_result[0]:
            buttons = [[{"text": f"🔬 {ticker_short} Agent 深度分析",
                         "callback_data": f"agent_{ticker_short}"}]]
            send_tg(
                t("claude_result_header", ticker=ticker_short) + "\n\n" + claude_result[0],
                buttons=buttons,
            )
            save_ai_analysis(ticker_short, "claude", claude_result[0], s)

        # 推送 OpenAI 结果，并写入文件
        if openai_result[0]:
            send_tg(f"🟢 OpenAI 分析 | {ticker_short}\n\n" + openai_result[0])
            save_ai_analysis(ticker_short, "openai", openai_result[0], s)

    threading.Thread(target=ai_push, daemon=True).start()
    return None  # 已手动 send_tg，不返回文本


def cmd_signal(args, wl):
    data = load_signals()
    if not data:
        return t("no_signal_data")

    # 🆕 批量刷新实时价(v0.2.1,4 只票约 0.3~0.5 秒)
    refresh_quotes_batch(data.get("signals", []))

    # 🆕 刷新实时持仓(v0.2.2),并把新持仓票追加到 signals
    signals_with_positions = refresh_positions_into_signals(data.get("signals", []))
    data["signals"] = signals_with_positions

    sig_map = {s["ticker"]: s for s in data.get("signals", [])}

    # 单只股票：直接返回文本（不加按钮，保持原有行为）
    if args:
        ticker_norm = norm(args[0])
        s = sig_map.get(ticker_norm)
        if not s:
            return f"No data for {ticker_norm}. Use /add {args[0]} first."
        if "error" in s:
            return f"Error for {ticker_norm}: {s['error']}"
        ticker_short = ticker_norm.replace("US.", "")
        buttons = [[{"text": t("btn_detail", ticker=ticker_short),
                     "callback_data": f"detail_{ticker_short}"}]]
        send_tg(fmt_signal(s), buttons=buttons)
        return None

    # 全部股票：开头一行说明，每只单独推送 + 按钮
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    send_tg(t("signal_title", now=now) + "\n" + t("urgency_explain"))

    # v0.2.2: watchlist + 持仓追加的"仅持仓"票 都显示
    tickers_list = list(all_tickers(wl))
    # 追加 refresh_positions 挂上来但不在 watchlist 的票
    for s in data["signals"]:
        tk = s.get("ticker")
        if tk and tk not in tickers_list:
            tickers_list.append(tk)

    for idx, tk in enumerate(tickers_list, 1):
        s = sig_map.get(tk)
        if s and "error" not in s:
            ticker_short = tk.replace("US.", "")
            buttons = [[{"text": t("btn_detail", ticker=ticker_short),
                         "callback_data": f"detail_{ticker_short}"}]]
            msg = fmt_signal(s, idx=idx)
            msg += f"\n💡 深度分析：/detail {ticker_short}  随时咨询：/ask {ticker_short} 你的问题"
            send_tg(msg, buttons=buttons)

    # 汇总提示行(兼容 indicators 为空的"仅持仓"票)
    footer = []
    ob  = [s["ticker"].replace("US.", "") for s in data["signals"]
           if "error" not in s and s.get("indicators", {}).get("rsi", 0) > 70]
    os_ = [s["ticker"].replace("US.", "") for s in data["signals"]
           if "error" not in s and 0 < s.get("indicators", {}).get("rsi", 0) < 30]
    if ob:  footer.append(t("warn_overbought", tickers=", ".join(ob)))
    if os_: footer.append(t("hint_oversold",   tickers=", ".join(os_)))
    footer.append(t("pdt_reminder"))
    send_tg("\n".join(footer))
    return None


def cmd_add(args, wl):
    if not args:
        return t("add_usage")
    added, already = [], []
    for raw in args:
        ticker_norm = norm(raw)
        if ticker_norm in all_tickers(wl):
            already.append(ticker_norm.replace("US.", ""))
        else:
            wl["manual"].append(ticker_norm)
            added.append(ticker_norm.replace("US.", ""))
    save_watchlist(wl)
    lines = []
    if added:
        lines.append(t("added", tickers=", ".join(added)))
        def _refresh_and_push():
            refresh()
            result = cmd_signal([], wl)
            if result:
                send_tg(result)
        threading.Thread(target=_refresh_and_push, daemon=True).start()
    if already:
        lines.append(t("already_in_list", tickers=", ".join(already)))
    return "\n".join(lines)


def cmd_remove(args, wl):
    if not args:
        return t("remove_usage")
    removed, protected, notfound = [], [], []
    for raw in args:
        ticker_norm = norm(raw)
        if ticker_norm in wl.get("auto", []):
            protected.append(ticker_norm.replace("US.", ""))
        elif ticker_norm in wl.get("manual", []):
            wl["manual"].remove(ticker_norm)
            removed.append(ticker_norm.replace("US.", ""))
        else:
            notfound.append(ticker_norm.replace("US.", ""))
    save_watchlist(wl)
    lines = []
    if removed:   lines.append(t("removed",   tickers=", ".join(removed)))
    if protected: lines.append(t("protected", tickers=", ".join(protected)))
    if notfound:  lines.append(t("not_found", tickers=", ".join(notfound)))
    return "\n".join(lines)


def cmd_list(wl):
    data    = load_signals()
    sig_map = {s["ticker"]: s for s in data.get("signals", [])} if data else {}
    lines   = [t("list_title") + "\n"]
    for tk in all_tickers(wl):
        lock = "[P]" if tk in wl.get("auto", []) else "   "
        s = sig_map.get(tk)
        if s and "error" not in s:
            sig_label = {"BUY": t("list_sig_buy"), "SELL": t("list_sig_sell"), "HOLD": t("list_sig_hold")}.get(s["signal"], "?")
            lines.append(f"{lock} {tk.replace('US.', '')} - ${s['price']:.2f} [{sig_label}] " + t("list_urgency", lvl=s.get("urgency", 1)))
        else:
            lines.append(f"{lock} {tk.replace('US.', '')} - " + t("list_no_data"))
    lines.append("\n" + t("list_footer_pos"))
    lines.append(t("list_total", n=len(all_tickers(wl))))
    return "\n".join(lines)


def _build_risk_status_text() -> str:
    """构建 /risk 指令输出: 账户级风控状态"""
    lines = [
        "🛡️ Risk Engine 状态",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    try:
        cfg = get_risk_config()
        lines.append("📋 当前风控阈值:")
        lines.append(f"  PDT 限制:      {cfg.get('pdt_limit', 3)} 次/5日")
        lines.append(f"  日亏熔断:      ${cfg.get('daily_loss_limit_usd', -400)}")
        lines.append(f"  回撤熔断:      {cfg.get('max_drawdown_pct', -8)}%")
        lines.append(f"  最低 RR 比:    {cfg.get('min_rr_ratio', 1.5)}")
        lines.append(f"  最低净利:      ${cfg.get('min_net_profit_usd', 5)}")
        lines.append(f"  最低信心:      {cfg.get('min_confidence', 0.6)*100:.0f}%")
        lines.append(f"  最大杠杆:      {cfg.get('max_effective_leverage', 1.8)}")
        lines.append(f"  集中度上限:    {cfg.get('max_concentration_pct', 60)}%")
    except Exception as e:
        lines.append(f"⚠️ 无法读取配置: {e}")

    # 最近 5 条 risk_log
    if HAS_RISK_ENGINE:
        try:
            recent = risk_read_recent(5)
            if recent:
                lines.append("")
                lines.append("📜 最近 5 次检查:")
                for r in recent:
                    tk = (r.get("ticker") or "?").replace("US.", "")
                    sev = r.get("severity", "?")
                    code = r.get("primary_reason_code", "?")
                    emoji = {"pass":"✅","advisory":"💡","warn":"⚠️","block":"❌"}.get(sev, "?")
                    lines.append(f"  {emoji} {tk} · {code}")
        except:
            pass

    lines.append("")
    lines.append("💡 /risk_test 跑回归测试")
    lines.append("💡 /risk_stats [天数] 统计报告")
    lines.append("💡 /risk_check TICKER QTY ENTRY STOP TARGET 手动测试")

    return "\n".join(lines)


def cmd_help(args=None):
    """
    主 help:分组展示所有指令 + 一句话说明
    /help XXX:显示 XXX 指令的详细介绍
    """
    # 如果带参数,显示指令详细介绍
    if args and len(args) > 0:
        return cmd_help_detail(args[0].lower())

    return (
        "📖 MagicQuant 指令手册\n\n"

        "🎯 盯盘模式(核心)\n"
        "/focus [ticker]    启动波段盯盘,默认 RKLB\n"
        "/unfocus           停止盯盘\n"
        "/status            查看盯盘状态\n"
        "/profile [hours]   查看机会密度画像(默认 12h)\n\n"

        "📊 行情信号\n"
        "/signal [ticker]   查看所有/指定股票信号\n"
        "/detail ticker     某只股票深度分析(含AI)\n"
        "/ask ticker 问题    自定义问 AI 关于某只股票\n\n"

        "👀 股票管理\n"
        "/list              查看跟踪列表\n"
        "/add ticker        添加跟踪\n"
        "/remove ticker     移除跟踪\n\n"

        "💼 账户持仓\n"
        "/account           查看账户资金\n"
        "/positions         查看所有持仓\n"
        "/history [天数]    查看交易历史\n"
        "/pnl               查看总盈亏\n"
        "/pdt               PDT规则状态\n\n"

        "🤖 AI 虚拟操盘\n"
        "/ai_positions      虚拟组合持仓\n"
        "/ai_trades         虚拟操盘历史\n"
        "/ai_report         虚拟操盘报告\n"
        "/summary           日度总结\n\n"

        "🏁 AI 大赛(多 AI 赛马)\n"
        "/race [interval]   启动大赛(默认 60 秒)\n"
        "/race_stop         停止大赛\n"
        "/race_stats        当前排行\n"
        "/race_cost         AI 算力成本\n"
        "/race_reset        重置所有账户\n"
        "/race_providers    查看可用 AI\n\n"

        "🤖 AI 智囊团(Focus 触发时咨询)\n"
        "/ai_advise_on      开启智囊团(默认开)\n"
        "/ai_advise_off     关闭智囊团\n"
        "/ai_advise_status  查看状态\n"
        "/ai_test [原因]    🆕 主动召集(不等触发)\n\n"

        "💓 心跳监控(v0.3.6)\n"
        "/heartbeat         立即看系统在干什么\n"
        "/heartbeat_on [N]  每 N 分钟自动推送\n"
        "/heartbeat_off     关闭定时心跳\n"
        "/heartbeat_status  查心跳状态\n\n"

        "🛡️ Risk Engine (v0.4)\n"
        "/risk              🆕 风控状态 + 阈值\n"
        "/risk_test         🆕 跑 28 场景回归\n"
        "/risk_stats [天]    🆕 风控统计\n"
        "/risk_check ...    🆕 手动测一个交易\n\n"

        "⚙️ 系统\n"
        "/push_on           开启定时推送\n"
        "/push_off          关闭定时推送(默认)\n"
        "/refresh           手动刷新信号\n"
        "/refresh_account   手动刷新账户\n"
        "/usage             本月 AI 费用\n"
        "/version           版本信息\n"
        "/about             关于 MagicQuant\n\n"

        "💡 获取详情\n"
        "/help 指令名  例如: /help focus"
    )


def cmd_help_detail(cmd_name: str) -> str:
    """单个指令的详细帮助"""

    DETAILS = {
        # ── 盯盘类 ────────────────────────────────
        "focus": (
            "🎯 /focus — 焦点波段盯盘\n\n"
            "启动实时盯盘,RKLB 作为信号源,\n"
            "自动关联你持有的 RKLZ/RKLX.\n\n"
            "【用法】\n"
            "• /focus              盯 RKLB(默认)\n"
            "• /focus TSLA         盯 TSLA\n\n"
            "【7 大触发器】\n"
            "1. 浮盈达标 (5% 或 $50)\n"
            "2. 高位回撤 (从峰值 -1.2%)\n"
            "3. 波段顶 (RSI>70 + 反转K线)\n"
            "4. 波段底 (RSI<35 + 锤子线)\n"
            "5. 快速异动 (2分钟>1%)\n"
            "6. 突破 (进行中)\n"
            "7. 接近止损 (进行中)\n\n"
            "【频率】盘中 2 秒/次\n"
            "【成本】完全免费,不用 AI\n\n"
            "💡 命中触发才推送,不刷屏"
        ),
        "unfocus": (
            "🛑 /unfocus — 停止盯盘\n\n"
            "立刻关闭 Focus 循环,并显示本次盯盘的统计:\n"
            "• 运行时长\n"
            "• 循环次数\n"
            "• 触发次数\n"
            "• 推送次数"
        ),
        "status": (
            "📡 /status — 查看盯盘状态\n\n"
            "随时查看当前盯盘是否运行、\n"
            "主标的、跟随标的、持仓盈亏、已触发次数等."
        ),

        # ── 信号类 ────────────────────────────────
        "signal": (
            "📊 /signal — 行情信号\n\n"
            "【用法】\n"
            "• /signal             所有跟踪股票\n"
            "• /signal RKLB        指定股票\n\n"
            "【显示内容】\n"
            "• 实时价(🟢/🟡/⚪ 标识时效)\n"
            "• 指标(RSI/MACD/布林/量比)\n"
            "• 止损/目标价\n"
            "• 持仓盈亏\n"
            "• BUY/SELL/HOLD 建议\n\n"
            "💡 默认不推送,主动问才有"
        ),
        "detail": (
            "🔍 /detail — 深度分析\n\n"
            "【用法】\n"
            "• /detail RKLB        完整技术分析\n"
            "• /detail RKLB fresh  强制刷新缓存\n\n"
            "包含:\n"
            "• 所有技术指标详解\n"
            "• K线形态识别\n"
            "• Claude AI 深度判断(约 0.2¢)\n"
            "• 操作建议\n\n"
            "💡 1 小时缓存,避免重复收费\n"
            "💡 60 秒内同票不重复触发"
        ),
        "ask": (
            "💬 /ask — 自定义问 AI\n\n"
            "【用法】\n"
            "• /ask RKLB 现在能加仓吗\n"
            "• /ask TSLA 财报前风险大吗\n\n"
            "用 AI 回答任何关于某只股票的问题,\n"
            "AI 会结合实时行情+技术指标+持仓回答.\n\n"
            "【成本】约 0.3~0.5¢ / 次"
        ),

        # ── 股票管理 ──────────────────────────────
        "list": "📋 /list — 查看当前跟踪的所有股票(auto + manual)",
        "add": (
            "➕ /add — 添加跟踪股票\n\n"
            "【用法】\n"
            "• /add TSLA\n"
            "• /add TSLA NVDA AAPL  (批量)\n\n"
            "💡 买入的新股票会自动加入,不用手动 /add"
        ),
        "remove": (
            "➖ /remove — 移除跟踪\n\n"
            "• /remove TSLA"
        ),

        # ── 账户类 ────────────────────────────────
        "account": (
            "💰 /account — 账户资金\n\n"
            "实时显示:\n"
            "• 总资产 (USD)\n"
            "• 持仓市值\n"
            "• 可用现金\n"
            "• 其他币种余额(AUD/HKD 等)\n\n"
            "💡 走实时 Futu API,比 Moomoo App 还新"
        ),
        "positions": (
            "💼 /positions — 所有持仓\n\n"
            "显示每只持仓票:\n"
            "• 数量、成本、现价、市值\n"
            "• 实时盈亏\n"
            "• 总盈亏汇总"
        ),
        "history": (
            "📜 /history — 交易历史\n\n"
            "• /history        最近 30 天\n"
            "• /history 7      最近 7 天"
        ),
        "pnl": "📈 /pnl — 基于对账单计算的精确总盈亏(含费用)",
        "pdt": (
            "⚠️ /pdt — PDT 规则状态\n\n"
            "澳洲 Moomoo 账户 <$25k 限制:\n"
            "• 5 个交易日内最多 3 次日内交易\n"
            "• 超过会被限制 90 天\n\n"
            "系统会追踪你的日内交易次数并提醒"
        ),

        # ── AI 虚拟操盘 ───────────────────────────
        "ai_positions": "🤖 /ai_positions — AI 虚拟组合当前持仓",
        "ai_trades":    "🤖 /ai_trades — AI 虚拟操盘全部历史",
        "ai_report":    "🤖 /ai_report — AI 虚拟操盘业绩报告",
        "summary":      "📊 /summary — 今日账户+持仓+信号摘要",

        # ── 系统 ──────────────────────────────────
        "push_on": (
            "🔔 /push_on — 开启定时推送\n\n"
            "在 PUSH_TIMES(如 09:00 / 21:30)\n"
            "自动推送所有股票信号.\n\n"
            "💡 v0.3.0 后默认关闭,需要手动开"
        ),
        "push_off": (
            "🔕 /push_off — 关闭定时推送(默认)\n\n"
            "只响应主动指令,不自动推送"
        ),
        "refresh":         "🔄 /refresh — 手动重新拉取信号(约 30 秒)",
        "refresh_account": "🔄 /refresh_account — 手动刷新账户/持仓数据",
        "usage": (
            "💰 /usage — 本月 AI 费用\n\n"
            "显示:\n"
            "• Claude API 消耗\n"
            "• OpenAI API 消耗\n"
            "• 月度累计费用"
        ),
        "version": "📦 /version — 版本号 + 最新变更",
        "about":   "ℹ️ /about — MagicQuant logo 和介绍",
    }

    if cmd_name in DETAILS:
        return DETAILS[cmd_name]

    return (
        f"❓ 未知指令: /{cmd_name}\n\n"
        f"发送 /help 查看所有可用指令"
    )


# ── 账户数据指令 ───────────────────────────────────────────────────

def cmd_account():
    # v0.2.2: 优先走实时接口
    # v0.2.3: 多币种正确展示(富途澳洲账户的 HKD 聚合坑)
    live_acc = refresh_account_live()

    if live_acc is not None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cash         = live_acc.get("cash", 0)
        total_assets = live_acc.get("total_assets", 0)
        market_val   = live_acc.get("market_val", 0)
        multi        = live_acc.get("multi_currency", {})

        lines = [
            f"💰 账户资金 · 🟢 实时",
            f"🕐 {now}",
            "",
            f"━━━ 美股账户(USD)━━━",
            f"总资产:   ${total_assets:,.2f}",
            f"持仓市值: ${market_val:,.2f}",
            f"可用现金: ${cash:,.2f}",
        ]

        # 如果有其他币种现金,一并显示
        other_currencies = [(k, v) for k, v in multi.items() if k != "USD"]
        if other_currencies:
            lines.append("")
            lines.append(f"━━━ 其他币种 ━━━")
            for cur, v in other_currencies:
                if v["cash"] > 0 or v["assets"] > 0:
                    lines.append(f"{cur}: 现金 {v['cash']:,.2f}  资产 {v['assets']:,.2f}")

        return "\n".join(lines)

    # 降级:Futu 连不上,读 JSON
    data = load_account_data()
    if not data:
        return t("no_account_data")
    acc = data.get("account", {})
    if not acc:
        return t("account_empty")

    cash         = safe_float(acc.get("cash", 0))
    total_assets = safe_float(acc.get("total_assets", 0))
    market_val   = safe_float(acc.get("market_val", 0))
    power        = (safe_float(acc.get("power", 0))
                    or safe_float(acc.get("buy_power", 0))
                    or safe_float(acc.get("max_power_short", 0)))
    frozen       = safe_float(acc.get("frozen_cash", 0))
    pl_val       = safe_float(acc.get("unrealized_pl", 0)) or safe_float(acc.get("pl_val", 0))
    collected_at = data.get("collected_at", "")[:16].replace("T", " ")

    lines = [
        t("account_title", t=collected_at), "",
        t("total_assets", val=total_assets),
        t("cash", val=cash),
        t("market_val", val=market_val),
        t("frozen", val=frozen),
    ]
    if power > 0:
        lines.append(t("buy_power", val=power))
    if pl_val != 0:
        ps = "+" if pl_val >= 0 else ""
        lines.append(t("unrealized_pl", sign=ps, val=abs(pl_val)))
    lines += ["", f"⚪ 快照数据 ({collected_at}),Futu 连接暂不可用", t("account_refresh")]
    return "\n".join(lines)


def cmd_positions():
    # v0.2.2: 优先走实时接口
    if HAS_REALTIME:
        try:
            live_positions = get_quote_client().fetch_positions()
            if live_positions is not None:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if not live_positions:
                    return f"💼 持仓 · 🟢 实时\n🕐 {now}\n\n当前空仓"

                lines = [f"💼 持仓 · 🟢 实时", f"🕐 {now}", ""]
                total_pl = 0.0
                for code, pos in live_positions.items():
                    short_code = code.replace("US.", "")
                    qty       = pos.get("qty", 0)
                    cost      = pos.get("cost_price", 0)
                    cur_price = pos.get("current_price", 0)
                    pl_val    = pos.get("pl_val", 0)
                    pl_pct    = pos.get("pl_pct", 0)
                    mkt_val   = round(qty * cur_price, 2) if cur_price else round(qty * cost, 2)
                    total_pl += pl_val
                    pl_sign = "+" if pl_val >= 0 else ""
                    emoji   = "📈" if pl_val >= 0 else "📉"
                    lines += [
                        f"{emoji} {short_code}",
                        f"  数量: {qty:.0f} 股  成本: ${cost:.2f}  现价: ${cur_price:.2f}",
                        f"  市值: ${mkt_val:,.2f}",
                        f"  盈亏: {pl_sign}${pl_val:.2f} ({pl_sign}{pl_pct:.2f}%)",
                        "",
                    ]
                total_sign = "+" if total_pl >= 0 else ""
                lines.append(f"━━━━━━━━━━━━")
                lines.append(f"总盈亏: {total_sign}${abs(total_pl):,.2f}")
                return "\n".join(lines)
        except Exception as e:
            print(f"  [realtime] cmd_positions failed: {e}")
            # 继续下面的 JSON 降级

    # 降级:读 JSON
    data = load_account_data()
    if not data:
        return t("no_account_data")
    positions = data.get("positions", [])
    if not positions:
        return t("no_positions")

    collected_at = data.get("collected_at", "")[:16].replace("T", " ")
    lines = [t("positions_title", t=collected_at), ""]
    total_pl = 0
    for pos in positions:
        code      = str(pos.get("code", "")).replace("US.", "")
        qty       = safe_float(pos.get("qty", 0))
        cost      = safe_float(pos.get("cost_price", 0))
        mkt_val   = safe_float(pos.get("market_val", pos.get("market_value", 0)))
        pl_val    = safe_float(pos.get("pl_val", pos.get("pl", 0)))
        pl_ratio  = safe_float(pos.get("pl_ratio", 0))
        pl_pct    = pl_ratio * 100 if abs(pl_ratio) < 10 else safe_float(pos.get("pl_pct", 0))
        cur_price = safe_float(pos.get("current_price", pos.get("price", cost)))
        total_pl += pl_val
        pl_sign   = "+" if pl_val >= 0 else ""
        emoji     = "📈" if pl_val >= 0 else "📉"
        lines += [
            f"{emoji} {code}",
            t("pos_row1", qty=qty, cost=cost, price=cur_price),
            t("pos_row2", mkt=mkt_val),
            t("pos_row3", sign=pl_sign, pl=pl_val, pct=pl_pct),
            "",
        ]
    total_sign = "+" if total_pl >= 0 else ""
    lines.append(t("pos_total_pl", sign=total_sign, pl=abs(total_pl)))
    lines.append(f"\n⚪ 快照数据,Futu 连接暂不可用")
    return "\n".join(lines)


def cmd_history(days=30):
    data = load_account_data()
    if not data:
        return t("no_account_data2")
    deals = data.get("history_deals", [])
    if not deals:
        return t("no_history", days=days)

    pnl        = data.get("pnl_summary", {})
    by_ticker  = pnl.get("by_ticker", {})
    lines = [t("history_title", days=days), ""]
    lines.append(t("history_total", n=len(deals)))
    lines.append(t("history_fee", fee=float(pnl.get("total_fee", 0))))
    lines += ["", t("section_by_ticker")]

    for code, stats in by_ticker.items():
        ticker_short = code.replace("US.", "")
        buy   = safe_float(stats.get("buy_val", 0))
        sell  = safe_float(stats.get("sell_val", 0))
        count = int(safe_float(stats.get("count", 0)))
        fee   = safe_float(stats.get("fee", 0))
        lines.append(t("history_row", ticker=ticker_short, n=count, buy=buy, sell=sell, fee=fee))

    lines += ["", t("section_recent")]
    recent = sorted(deals, key=lambda x: str(x.get("create_time", x.get("deal_time", ""))), reverse=True)[:10]
    for d in recent:
        code       = str(d.get("code", "")).replace("US.", "")
        side       = str(d.get("trd_side", "")).upper()
        qty        = float(d.get("qty", d.get("deal_qty", 0)))
        deal_price = float(d.get("price", d.get("deal_price", 0)))
        ts         = str(d.get("create_time", d.get("deal_time", "")))[:16]
        side_label = t("deal_buy") if "BUY" in side or "LONG" in side else t("deal_sell")
        lines.append(t("deal_row", t=ts, ticker=code, qty=qty, price=deal_price, side=side_label))

    return "\n".join(lines)


def cmd_pdt():
    data = load_account_data()
    if not data:
        return t("no_account_data2")
    deals = data.get("history_deals", [])
    if not deals:
        return t("pdt_no_deals")

    from datetime import timedelta
    now           = datetime.now()
    five_days_ago = now - timedelta(days=7)

    day_trades = {}
    for d in deals:
        ts = str(d.get("create_time", d.get("deal_time", "")))
        if not ts or ts < str(five_days_ago)[:10]:
            continue
        date = ts[:10]
        code = str(d.get("code", "")).replace("US.", "")
        side = str(d.get("trd_side", "")).upper()
        if date not in day_trades:
            day_trades[date] = {}
        if code not in day_trades[date]:
            day_trades[date][code] = set()
        day_trades[date][code].add("BUY" if "BUY" in side or "LONG" in side else "SELL")

    pdt_count   = 0
    pdt_details = []
    for date, tickers_day in sorted(day_trades.items()):
        for code, sides in tickers_day.items():
            if "BUY" in sides and "SELL" in sides:
                pdt_count += 1
                pdt_details.append(f"  {date}: {code}")

    remaining = max(0, 3 - pdt_count)
    lines = [
        t("pdt_title"), "",
        t("pdt_account_size"),
        t("pdt_window"),
        t("pdt_used", n=pdt_count),
        t("pdt_remaining", n=remaining),
        "",
    ]
    if pdt_details:
        lines.append(t("pdt_records"))
        lines.extend(pdt_details)
        lines.append("")
    if remaining == 0:
        lines += [t("pdt_warn_zero"), t("pdt_warn_freeze")]
    elif remaining == 1:
        lines.append(t("pdt_warn_one"))
    else:
        lines.append(t("pdt_ok"))
    return "\n".join(lines)


def cmd_refresh_account():
    """重新采集账户数据 / Refresh account data"""
    collector = os.path.join(BASE_DIR, "core", "data_collector.py")
    try:
        result = subprocess.run(
            [sys.executable, collector],
            timeout=120, cwd=BASE_DIR,
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return t("refresh_ok")
        else:
            return t("refresh_fail", err=result.stderr[-200:])
    except Exception as e:
        return t("refresh_error", err=e)


def cmd_usage():
    """查看本月 Claude API 累计费用 / View monthly Claude API usage"""
    usage = load_usage()
    month    = usage.get("month", "—")
    calls    = usage.get("calls", 0)
    tok_in   = usage.get("tokens_in", 0)
    tok_out  = usage.get("tokens_out", 0)
    cost     = usage.get("cost_usd", 0.0)
    history  = usage.get("history", [])

    lines = [
        t("usage_title", month=month), "",
        t("usage_calls", n=calls),
        t("usage_tokens", tin=tok_in, tout=tok_out),
        t("usage_cost", cost=cost, cost_cny=cost * 7.2),  # 粗估人民币
        "",
    ]
    if history:
        lines.append(t("usage_recent"))
        for rec in history[-5:][::-1]:  # 最近5条，倒序
            lines.append(
                f"  {rec['time']} {rec['ticker']:6s} "
                f"in:{rec['tokens_in']:4d} out:{rec['tokens_out']:4d} "
                f"${rec['cost_usd']*100:.3f}¢"
            )
    lines += ["", t("usage_note")]
    return "\n".join(lines)


def cmd_ask(args):
    """
    /ask TSLL 现在能加仓吗
    随时向 Claude AI 提问，联网回答，150字以内
    """
    if not args or len(args) < 2:
        return "用法：/ask 股票代码 你的问题\n例如：/ask TSLL 现在能加仓吗\n     /ask RKLX 今天有什么大消息"

    ticker_raw   = args[0]
    question     = " ".join(args[1:])
    ticker_short = ticker_raw.upper()
    ticker_full  = norm(ticker_raw)

    if not CLAUDE_API_KEY:
        return t("claude_no_key")

    # 获取最新信号数据作为背景
    data    = load_signals()
    sig_map = {s["ticker"]: s for s in data.get("signals", [])} if data else {}
    s       = sig_map.get(ticker_full, {})
    price   = s.get("price", "?")
    sig     = s.get("signal", "?")
    ind     = s.get("indicators", {})
    pos     = s.get("position", {})

    context = ""
    if s:
        context = (
            f"当前市场数据（{ticker_short}）：\n"
            f"现价: ${price}  信号: {sig}\n"
            f"RSI: {ind.get('rsi','?')}  MACD柱: {ind.get('macd_hist',0):+.4f}  "
            f"量比: {ind.get('vol_ratio','?')}x\n"
        )
        if pos and pos.get("qty", 0) > 0:
            context += (
                f"持仓: {pos['qty']}股  成本: ${pos['cost_price']}  "
                f"浮盈亏: {pos.get('pl_pct',0):+.1f}%\n"
            )

    send_tg(f"🔍 正在查询：{ticker_short} — {question}\n预计 15-30 秒...")

    def _ask():
        prompt = (
            f"{context}\n"
            f"用户问题：{question}\n\n"
            f"请联网搜索最新信息后，用中文简洁回答（150字以内），"
            f"给出明确的操作建议或结论，不废话。"
        )
        payload = json.dumps({
            "model":      CLAUDE_MODEL,
            "max_tokens": 400,
            "system":     "你是专业美股交易员助理，直接回答问题，给出明确结论，不废话。",
            "tools":      [{"type": "web_search_20250305", "name": "web_search"}],
            "messages":   [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
            ai_text = "".join(
                b["text"] for b in result.get("content", [])
                if b.get("type") == "text"
            ).strip()
            usage    = result.get("usage", {})
            tin      = usage.get("input_tokens", 0)
            tout     = usage.get("output_tokens", 0)
            cost_usd = tin * CLAUDE_PRICE_IN + tout * CLAUDE_PRICE_OUT
            record_usage(ticker_short, tin, tout, cost_usd)

            # 写入 ask_results.json 供网页读取
            ask_file = os.path.join(BASE_DIR, "data", "ask_results.json")
            try:
                results = {}
                if os.path.exists(ask_file):
                    results = json.load(open(ask_file, encoding="utf-8"))
                if ticker_short not in results:
                    results[ticker_short] = []
                results[ticker_short].insert(0, {
                    "question":  question,
                    "answer":    ai_text,
                    "time":      datetime.now().strftime("%H:%M"),
                    "cost":      round(cost_usd * 100, 3),
                })
                results[ticker_short] = results[ticker_short][:10]  # 最多保留10条
                json.dump(results, open(ask_file, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
            except Exception as we:
                print(f"  ask_results save error: {we}")

            send_tg(
                f"💬 {ticker_short} | {question}\n"
                ""
                f"{ai_text}\n"
                f"\nAI算力成本: {tout}tok / {cost_usd*100:.3f}¢"
            )
        except Exception as e:
            send_tg(f"❌ 查询失败: {e}")

    threading.Thread(target=_ask, daemon=True).start()
    return None


def cmd_summary():
    """/summary — 推送开发进度和待办事项"""
    notes_file = os.path.join(BASE_DIR, "data", "dev_notes.json")
    try:
        notes = json.load(open(notes_file, encoding="utf-8"))
    except:
        return "暂无开发笔记，请确认 data/dev_notes.json 存在。"

    lines = [
        f"=== MagicQuant 开发进度 ===",
        f"版本: v{notes.get('current_version')}  "
        f"更新: {notes.get('last_updated')}",
        "",
        f"✅ 今日完成 ({len(notes.get('today_done', []))} 项):",
    ]
    for item in notes.get("today_done", []):
        lines.append(f"  · {item}")

    lines += ["", "⚠️ 遗留问题:"]
    for item in notes.get("pending_issues", []):
        lines.append(f"  · {item}")

    lines += ["", "📋 下次继续:"]
    for item in notes.get("next_session", []):
        lines.append(f"  {item}")

    lines += [
        "",
        f"下一版本目标: v{notes.get('next_version')}",
    ]
    return "\n".join(lines)
    """/ai_positions — AI 当前虚拟持仓"""
    if not HAS_AI_TRADER:
        return "⚠️ ai_trader 模块未找到，请确认 core/ai_trader.py 已部署。"

    data    = load_signals()
    prices  = {}
    if data:
        prices = {s["ticker"]: s["price"]
                  for s in data.get("signals", []) if "error" not in s}

    positions = ai_get_positions(prices)
    summary   = ai_get_summary(prices)

    sign = "+" if summary["pnl"] >= 0 else ""
    lines = [
        f"=== AI 虚拟持仓 ===",
        f"总资产: ${summary['total_assets']:,.2f}  "
        f"现金: ${summary['cash']:,.2f}",
        f"累计盈亏: {sign}${summary['pnl']:,.2f} ({sign}{summary['pnl_pct']:.1f}%)",
        f"运行: {summary['days_running']} 天  "
        f"PDT: {summary['pdt_used']}/3",
        "",
    ]

    if not positions:
        lines.append("当前无持仓")
    else:
        for pos in positions:
            ticker_short = pos["ticker"].replace("US.", "")
            ps = "+" if pos["pl_val"] >= 0 else ""
            lines += [
                f"{'📈' if pos['pl_val']>=0 else '📉'} {ticker_short}",
                f"  持仓: {pos['qty']} 股  成本: ${pos['cost_price']}",
                f"  现价: ${pos['price']:.2f}  市值: ${pos['mkt_val']:,.2f}",
                f"  盈亏: {ps}${pos['pl_val']:,.2f} ({ps}{pos['pl_pct']:.1f}%)",
                f"  买入时间: {pos['buy_time']}",
                "",
            ]
    return "\n".join(lines)


def cmd_ai_trades():
    """/ai_trades — AI 最近交易记录"""
    if not HAS_AI_TRADER:
        return "⚠️ ai_trader 模块未找到。"

    trades = ai_load_trades()
    if not trades:
        return "AI 暂无交易记录。"

    recent = trades[-10:][::-1]  # 最近10笔，倒序
    lines  = [f"=== AI 交易记录（最近{len(recent)}笔）===", ""]

    for tr in recent:
        ticker_short = tr["ticker"].replace("US.", "")
        action_label = "买入" if tr["action"] == "BUY" else "卖出"
        line = (f"{tr['time'][:16]}  {action_label} {ticker_short} "
                f"{tr['qty']}股 @${tr['price']:.2f}")
        if "pnl" in tr:
            ps = "+" if tr["pnl"] >= 0 else ""
            line += f"  盈亏: {ps}${tr['pnl']:.2f}"
        lines.append(line)
        lines.append(f"  依据: {tr.get('reason','')}")
        lines.append("")

    return "\n".join(lines)


def cmd_ai_report():
    """/ai_report — AI 阶段性盈亏报告"""
    if not HAS_AI_TRADER:
        return "⚠️ ai_trader 模块未找到。"

    data   = load_signals()
    prices = {}
    if data:
        prices = {s["ticker"]: s["price"]
                  for s in data.get("signals", []) if "error" not in s}

    summary = ai_get_summary(prices)
    trades  = ai_load_trades()

    sign = "+" if summary["pnl"] >= 0 else ""
    lines = [
        f"=== AI 虚拟操盘报告 ===",
        f"运行周期: {summary['days_running']} 天",
        "",
        f"起始资金: ${summary['initial_cash']:,.2f}",
        f"当前总资产: ${summary['total_assets']:,.2f}",
        f"累计盈亏: {sign}${summary['pnl']:,.2f} ({sign}{summary['pnl_pct']:.1f}%)",
        "",
        f"交易统计:",
        f"  总交易笔数: {summary['total_trades']} 笔",
        f"  盈利笔数:   {summary['win_trades']} 笔",
        f"  胜率:       {summary['win_rate']}%",
        f"  PDT已用:    {summary['pdt_used']}/3",
        "",
    ]

    # 按股票统计盈亏
    by_ticker = {}
    for tr in trades:
        tk = tr["ticker"].replace("US.", "")
        if tk not in by_ticker:
            by_ticker[tk] = {"buy": 0, "sell": 0, "pnl": 0.0, "count": 0}
        by_ticker[tk]["count"] += 1
        if tr["action"] == "BUY":
            by_ticker[tk]["buy"] += tr["qty"] * tr["price"]
        elif tr["action"] == "SELL":
            by_ticker[tk]["sell"] += tr["qty"] * tr["price"]
            by_ticker[tk]["pnl"]  += tr.get("pnl", 0)

    if by_ticker:
        lines.append("按股票统计:")
        for tk, stats in by_ticker.items():
            ps = "+" if stats["pnl"] >= 0 else ""
            lines.append(
                f"  {tk}: {stats['count']}笔  "
                f"盈亏 {ps}${stats['pnl']:.2f}"
            )

    return "\n".join(lines)
    """/pnl — 从已入库对账单计算盈亏汇总"""
    if not HAS_PARSER:
        return t("pnl_no_parser")
    existing = get_existing_dates()
    if not existing:
        return t("pnl_no_data")

    pnl       = calc_pnl_from_statements()
    by_ticker = pnl.get("by_ticker", {})
    missing   = pnl.get("missing_dates", [])
    sign      = "+" if pnl["total_pnl"] >= 0 else ""

    lines = [
        t("pnl_title", date_range=pnl["date_range"]), "",
        t("pnl_trade_days",   n=pnl["trade_days"]),
        t("pnl_total_trades", n=pnl["total_trades"]),
        t("pnl_total_fees",   fee=pnl["total_fees"]),
        t("pnl_total",        sign=sign, pnl=abs(pnl["total_pnl"])),
        "", t("pnl_by_ticker"),
    ]
    for tk, stats in by_ticker.items():
        ps = "+" if stats["net_pnl"] >= 0 else ""
        lines.append(t("pnl_row",
            ticker=tk,
            buy=stats["total_buy"], sell=stats["total_sell"],
            fee=stats["fees_est"],
            sign=ps, pnl=abs(stats["net_pnl"])))

    if missing:
        lines += ["", t("pnl_missing_hint", n=len(missing))]
        for ds in missing[:5]:
            lines.append(f"  {ds}")
        if len(missing) > 5:
            lines.append(f"  ... 共 {len(missing)} 天")
        lines.append(t("pnl_upload_hint"))
    return "\n".join(lines)


def handle_document(msg: dict):
    """
    处理用户发来的 PDF 文件（富途对账单）
    Handle incoming PDF document (Moomoo AU statement)
    """
    if not HAS_PARSER:
        return t("pnl_no_parser")

    doc      = msg.get("document", {})
    filename = doc.get("file_name", "")
    file_id  = doc.get("file_id", "")

    if not filename.lower().endswith(".pdf"):
        return None

    # 判断是否是对账单
    is_stmt = (
        "statement" in filename.lower() or
        bool(re.search(r"\d{16}", filename)) or
        filename.startswith("1009271")
    )
    if not is_stmt:
        return None

    send_tg(t("stmt_parsing", filename=filename))

    # 下载文件
    try:
        url       = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        resp      = urllib.request.urlopen(url, timeout=10)
        file_path = json.loads(resp.read())["result"]["file_path"]
        dl_url    = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        tmp_path  = os.path.join(BASE_DIR, "data", f"_tmp_{file_id}.pdf")
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        urllib.request.urlretrieve(dl_url, tmp_path)
    except Exception as e:
        return t("stmt_download_fail", err=str(e))

    # 解析 PDF
    try:
        result = parse_pdf(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except:
            pass

    if not result or "error" in result:
        err = result.get("error", "未知错误") if result else "解析返回空"
        return t("stmt_parse_fail", err=err)

    date_str = result.get("statement_date")
    if not date_str:
        return t("stmt_no_date", filename=filename)

    if load_statement(date_str):
        return t("stmt_already_exists", date=date_str)

    save_statement(date_str, result)

    missing = get_missing_dates()
    lines   = [t("stmt_saved",
                 date=date_str,
                 trades=len(result.get("trades", [])),
                 fees=result.get("fees_total", 0))]
    if missing:
        lines += ["", t("stmt_still_missing", n=len(missing))]
        for ds in missing[:3]:
            lines.append(f"  {ds}")
        if len(missing) > 3:
            lines.append(f"  ... 共 {len(missing)} 天")
    else:
        lines.append(t("stmt_all_complete"))
    return "\n".join(lines)


def check_statement_gaps():
    """
    检查对账单缺口，早9点推送时调用
    Returns: 提醒文本 或 None
    """
    if not HAS_PARSER:
        return None
    missing = get_missing_dates()
    if not missing:
        return None
    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    lines = [t("stmt_reminder_title")]
    if yesterday in missing:
        lines.append(t("stmt_reminder_yesterday", date=yesterday))
    older = [d for d in missing if d != yesterday]
    if older:
        lines.append(t("stmt_reminder_older", n=len(older)))
    lines += ["", t("stmt_reminder_how")]
    return "\n".join(lines)

def handle(text, wl):
    if not text.startswith("/"):
        return None
    parts = text[1:].split()
    cmd   = parts[0].split("@")[0].lower()
    args  = parts[1:]

    if cmd == "add":             return cmd_add(args, wl)
    if cmd == "remove":          return cmd_remove(args, wl)
    if cmd == "list":            return cmd_list(wl)
    if cmd == "signal":          return cmd_signal(args, wl)

    if cmd == "order":
        if not args:
            return "用法: /order TICKER\n例如: /order RKLZ"
        etf_o = args[0].upper().replace("US.", "")
        try:
            from core.focus.pusher import format_order_text
            order_text = format_order_text(etf_o)
            return order_text or f"⚠️ {etf_o} 没有最近的交易计划,等下一个信号"
        except ImportError:
            return "❌ Focus pusher 模块未加载"

    if cmd in ("modules", "versions"):
        lines = [
            f"📦 <b>MagicQuant 模块版本</b>",
            f"━━━━━━━━━━━━━━",
            f"主程序:         v{VERSION}",
            f"bot_controller: {BOT_CONTROLLER_VERSION} ({BOT_CONTROLLER_DATE})",
        ]
        try:
            from core.focus.focus_manager import get_version_info
            info = get_version_info()
            lines.append(f"focus_manager:     {info.get('focus_manager','?')} "
                         f"({info.get('focus_manager_date','—')})")
            lines.append(f"pusher:            {info.get('pusher','?')}")
            lines.append(f"market_clock:      {info.get('market_clock','?')}")
            # v0.5.11 新增
            lines.append(f"activity_profile:  {info.get('activity_profile','?')}")
            lines.append(f"event_calendar:    {info.get('event_calendar','?')}")
            lines.append(f"proactive_reminder:{info.get('proactive_reminder','?')}")
        except Exception as e:
            lines.append(f"focus modules:  加载失败 ({e})")
        try:
            from core.focus.market_clock import format_market_status
            lines += ["", format_market_status()]
        except:
            pass
        # v0.5.11 新增:当前 profile 行
        try:
            from core.focus.activity_profile import format_profile_line
            lines.append(format_profile_line())
        except:
            pass
        return "\n".join(lines)

    if cmd == "detail":
        if not args:
            return t("detail_usage")
        ticker_d      = args[0].upper()
        force_refresh = len(args) > 1 and args[1].lower() == "fresh"
        now_ts        = time.time()
        last_ts       = detail_cooldown.get(ticker_d, 0)
        if now_ts - last_ts < 60:
            remaining = int(60 - (now_ts - last_ts))
            return f"⏳ {ticker_d} 分析正在进行中，{remaining}秒后可再次触发。"
        detail_cooldown[ticker_d] = now_ts
        send_tg(f"⏳ 正在分析 {ticker_d}，请稍候...")
        return cmd_detail(args[0], force_refresh=force_refresh)
    if cmd == "account":         return cmd_account()
    if cmd == "positions":       return cmd_positions()
    if cmd == "history":         return cmd_history()
    if cmd == "pdt":             return cmd_pdt()
    if cmd == "usage":           return cmd_usage()
    if cmd == "pnl":             return cmd_pnl()
    if cmd == "ai_positions":   return cmd_ai_positions()
    if cmd == "ai_trades":      return cmd_ai_trades()
    if cmd == "ai_report":      return cmd_ai_report()
    if cmd == "summary":        return cmd_summary()
    # ── Focus 盯盘模式(v0.3.0)──────────────────────────
    if cmd == "focus":
        if not HAS_FOCUS:
            return "❌ Focus 模块未加载,请检查 core/focus/"
        if is_focused():
            return "⚠️ 已有盯盘运行中,请先 /unfocus"
        master = args[0].upper() if args else "RKLB"
        if not master.startswith("US."):
            master = "US." + master
        # v0.5.9: 手动 /focus 设 manual_mode=True,不受休市静默影响
        return focus_start(master=master, send_tg_fn=send_tg, manual_mode=True)
    if cmd == "unfocus":
        if not HAS_FOCUS:
            return "❌ Focus 模块未加载"
        return focus_stop()
    if cmd == "status":
        if not HAS_FOCUS:
            return "❌ Focus 模块未加载"
        return get_focus_status()

    # ── v0.5.11: /profile 查看机会密度画像 ──────────────
    if cmd == "profile":
        try:
            from core.focus.activity_profile import (
                get_current_profile, format_profile_line, format_profile_forecast,
            )
            from core.focus.event_calendar import format_event_line
        except ImportError:
            return "❌ activity_profile 模块未加载 (core/focus/activity_profile.py)"

        # 默认显示未来 12 小时;可选参数 /profile 24 显示 24 小时
        hours = 12
        if args:
            try:
                hours = max(1, min(48, int(args[0])))
            except (ValueError, TypeError):
                pass

        p = get_current_profile()
        lines = [
            "📊 <b>当前机会密度画像</b>",
            "━━━━━━━━━━━━━━",
            format_profile_line(p),
            "",
            f"等级: <b>{p['level']}</b>  ({p['reason']})",
            f"轮询: {p['poll_sec']} 秒/次",
        ]
        if p["scale"] is not None:
            lines.append(f"阈值系数: ×{p['scale']:.2f}")
        if p.get("event"):
            lines.append(f"事件: {p['event']}")
            ev_line = format_event_line()
            if ev_line:
                lines.append(ev_line)
        if p.get("monday_boost"):
            lines.append("加速: ⚡ 周一加速 50% 已启用")

        # 今日提醒计划
        try:
            from core.focus.proactive_reminder import format_reminder_schedule
            lines += ["", format_reminder_schedule()]
        except ImportError:
            pass

        # 未来时间线
        lines += ["", format_profile_forecast(hours=hours)]

        return "\n".join(lines)

    # ── AI 智囊团开关 (v0.3.5) ──────────────────────────
    if cmd == "ai_advise_on":
        if not HAS_AI_ADVISOR:
            return "❌ AI 智囊团模块未加载 (core/focus/ai_advisor.py)"
        set_ai_advise(True)
        return "✅ AI 智囊团已开启\nFocus 每次触发都会召集 3 顾问 + Opus Leader 给建议"
    
    if cmd == "ai_advise_off":
        if not HAS_AI_ADVISOR:
            return "❌ AI 智囊团模块未加载"
        set_ai_advise(False)
        return "✅ AI 智囊团已关闭\nFocus 仍会推送触发信号,但不调用 AI"
    
    if cmd == "ai_advise_status":
        if not HAS_AI_ADVISOR:
            return "❌ AI 智囊团模块未加载"
        enabled = is_ai_advise_enabled()
        return (
            f"🤖 AI 智囊团状态: {'✅ 开启' if enabled else '⏸️ 关闭'}\n"
            f"\n"
            f"当开启时,Focus 每次触发会:\n"
            f"  1. 并行调用 Haiku/DeepSeek/GPT-5 顾问\n"
            f"  2. Opus Leader 汇总决策\n"
            f"  3. 推送最终建议到 TG\n"
            f"\n"
            f"每次花费约 $0.04,一晚 20 次触发 ≈ $0.80"
        )

    # ════════════════════════════════════════════════════════
    # v0.3.6: 手动召集智囊团 + 心跳监控
    # ════════════════════════════════════════════════════════

    if cmd == "ai_test":
        if not HAS_MANUAL_CONSULT:
            return "❌ 手动召集模块未加载 (core/focus/manual_consult.py)"
        if not HAS_FOCUS:
            return "❌ Focus 模块未加载"
        try:
            from core.focus.focus_manager import (
                _current_session, _indicators_cache_global,
            )
        except ImportError:
            return "❌ 无法读取 Focus session 状态"

        if _current_session is None or not _current_session.active:
            return (
                "⚠️ 当前没有运行中的 Focus 盯盘\n"
                "请先 /focus 启动盯盘,再用 /ai_test 召集智囊团.\n\n"
                "💡 /ai_test 不受触发器限制,随时可用"
            )

        reason = " ".join(args) if args else "主动询问 AI 意见"
        send_tg("🤖 正在召集 AI 智囊团...约 20 秒\n多位顾问 + Opus Leader 并行思考中")

        try:
            result = manual_consult(
                session=_current_session,
                indicators_cache=_indicators_cache_global,
                reason=reason,
                send_tg_fn=send_tg,
            )
            if result.get("error"):
                return f"❌ {result['error']}"
            return None   # manual_consult 内部已推送
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"❌ 召集失败: {str(e)[:150]}"

    # ── 心跳监控 ─────────────────────────────────────────
    if cmd == "heartbeat":
        if not HAS_HEARTBEAT:
            return "❌ 心跳模块未加载 (core/focus/heartbeat.py)"
        return get_heartbeat_text()

    if cmd == "heartbeat_on":
        if not HAS_HEARTBEAT:
            return "❌ 心跳模块未加载"
        interval = 15
        if args:
            try:
                interval = int(args[0])
            except:
                return "❌ 用法: /heartbeat_on [分钟],比如 /heartbeat_on 15"
        return start_heartbeat_loop(send_tg, interval)

    if cmd == "heartbeat_off":
        if not HAS_HEARTBEAT:
            return "❌ 心跳模块未加载"
        return stop_heartbeat_loop()

    if cmd == "heartbeat_status":
        if not HAS_HEARTBEAT:
            return "❌ 心跳模块未加载"
        enabled = is_heartbeat_enabled()
        interval = get_heartbeat_interval()
        return (
            f"💓 心跳状态: {'✅ 每 ' + str(interval) + ' 分钟推送' if enabled else '⏸️ 关闭'}\n\n"
            f"💡 /heartbeat        立即查一次\n"
            f"💡 /heartbeat_on N   每 N 分钟自动推送\n"
            f"💡 /heartbeat_off    关闭定时推送"
        )

    # ════════════════════════════════════════════════════════
    # v0.4: Risk Engine 指令
    # ════════════════════════════════════════════════════════

    # ════════════════════════════════════════════════════════
    # v0.4.1: /t 做 T 决策面板 — 秒出结果,零 AI 花费
    # ════════════════════════════════════════════════════════
    if cmd == "t":
        try:
            from core.focus import HAS_TACTICAL_PANEL, build_tactical_panel
            from core.focus import focus_manager as _fm
        except ImportError as e:
            return f"❌ 做T面板模块未加载: {e}"
        
        if not HAS_TACTICAL_PANEL:
            return "❌ 做T面板模块未加载 (core/focus/tactical_panel.py)"
        
        session = _fm._current_session
        if session is None or not getattr(session, "active", False):
            return (
                "⚠️ 当前没有 Focus 盯盘在运行\n"
                "请先 /focus RKLB 启动盯盘,再用 /t 查做T决策"
            )
        
        import time as _time
        cache = _fm._last_indicators_cache or {}
        cache_age = (_time.time() - _fm._last_indicators_time) if _fm._last_indicators_time else 0
        
        try:
            return build_tactical_panel(session, cache, cache_age)
        except Exception as e:
            import traceback; traceback.print_exc()
            return f"❌ /t 执行失败: {e}"

    if cmd == "risk":
        if not HAS_RISK_ENGINE:
            return "❌ 风控引擎未加载 (core/risk_engine/)"
        # 查当前风控状态(账户维度)
        return _build_risk_status_text()

    if cmd == "risk_test":
        if not HAS_RISK_ENGINE:
            return "❌ 风控引擎未加载"
        try:
            result = run_all_fixtures()
            return format_test_result_for_tg(result)
        except Exception as e:
            return f"❌ 测试失败: {e}"

    if cmd == "risk_stats":
        if not HAS_RISK_ENGINE:
            return "❌ 风控引擎未加载"
        days = 7
        if args:
            try:
                days = max(1, min(int(args[0]), 30))
            except:
                pass
        try:
            stats = risk_compute_stats(days=days)
            out = risk_format_stats(stats)
            # 附加 override 统计
            if HAS_OVERRIDE_LOG:
                ov_stats = compute_override_stats(days=days)
                out += "\n\n" + format_override_stats_for_tg(ov_stats)
            return out
        except Exception as e:
            return f"❌ 统计失败: {e}"

    if cmd == "risk_check":
        # 手动检查一个假想交易: /risk_check RKLZ 100 15.42 15.30 15.80
        if not HAS_RISK_ENGINE:
            return "❌ 风控引擎未加载"
        if len(args) < 5:
            return (
                "用法: /risk_check TICKER QTY ENTRY STOP TARGET\n"
                "例如: /risk_check RKLZ 100 15.42 15.30 15.80"
            )
        try:
            ticker = args[0].upper()
            if not ticker.startswith("US."):
                ticker = "US." + ticker
            qty    = int(args[1])
            entry  = float(args[2])
            stop   = float(args[3])
            target = float(args[4])

            # 从当前 Focus session 拉 context(如果可用)
            ctx = {"pdt_used": 0, "cash": 18000, "confidence": 0.72,
                   "market_session": "main"}
            try:
                from core.focus.focus_manager import _current_session
                if _current_session and _current_session.active:
                    ctx["positions"] = dict(
                        _current_session.positions_snapshot or {}
                    )
            except:
                pass

            result = can_trade(
                action_type="new_entry",
                ticker=ticker, qty=qty,
                entry=entry, stop=stop, target=target,
                direction="long",
                context=ctx,
            )
            # 写日志
            try:
                log_risk_check(result, ctx)
            except:
                pass
            return format_result_for_tg(result, verbose=True)
        except Exception as e:
            import traceback; traceback.print_exc()
            return f"❌ /risk_check 失败: {e}"

    # ── AI 虚拟操盘大赛(v0.3.4)─────────────────────────
    if cmd == "race":
        if not HAS_RACE:
            return "❌ AI 大赛模块未加载,请检查 core/agents/"
        if is_race_active():
            return get_race_summary()
        interval = 180   # 默认 3 分钟
        if args:
            try:
                interval = max(30, int(args[0]))
            except:
                pass
        return race_start(send_tg_fn=send_tg, interval=interval)

    if cmd == "race_stop":
        if not HAS_RACE:
            return "❌ AI 大赛模块未加载"
        return race_stop(send_tg_fn=send_tg)

    if cmd == "race_stats":
        if not HAS_RACE:
            return "❌ AI 大赛模块未加载"
        return get_race_summary()

    if cmd == "race_reset":
        if not HAS_RACE:
            return "❌ AI 大赛模块未加载"
        return race_reset()

    if cmd == "race_cost":
        if not HAS_RACE:
            return "❌ AI 大赛模块未加载"
        portfolios = race_portfolios()
        if not portfolios:
            return "📊 尚未有大赛数据"
        total_cost = 0.0
        total_tokens = 0
        total_calls = 0
        lines = ["💰 AI 算力成本累计"]
        providers = race_providers()
        for name, p in portfolios.items():
            summary = p.summary({})
            cost = summary["ai_cost_usd"]
            tokens = summary["ai_tokens"]
            calls = summary.get("ai_calls", 0)
            display = providers[name].display_name if name in providers else name
            lines.append(
                f"• {display}: ${cost:.4f} · {tokens:,} tok · {calls} 次"
            )
            total_cost += cost
            total_tokens += tokens
            total_calls += calls
        lines += [
            f"",
            f"═════════════════════",
            f"总成本: ${total_cost:.4f}",
            f"总 tokens: {total_tokens:,}",
            f"总调用: {total_calls}",
        ]
        return "\n".join(lines)

    if cmd == "race_providers":
        if not HAS_RACE:
            return "❌ AI 大赛模块未加载"
        available = build_all_providers()
        if not available:
            return (
                "❌ 当前没有可用的 AI Provider\n\n"
                "请在 .env 文件配置以下任一 API Key:\n"
                "• ANTHROPIC_API_KEY  (Claude)\n"
                "• OPENAI_API_KEY     (GPT-5)\n"
                "• DEEPSEEK_API_KEY   (DeepSeek V3)\n"
                "• MOONSHOT_API_KEY   (Kimi K2)"
            )
        lines = ["✅ 可用的 AI Providers:"]
        for name, p in available.items():
            lines.append(
                f"• {p.display_name} ({name})\n"
                f"  价格: ${p.price_input_per_m}/M输入 · ${p.price_output_per_m}/M输出"
            )
        return "\n".join(lines)
    # ── 定时推送开关(v0.3.0)──────────────────────────
    if cmd == "push_on":
        globals()["SCHEDULED_PUSH_ENABLED"] = True
        return "✅ 定时推送已开启\n将在 " + ", ".join(PUSH_TIMES) + " 自动推送"
    if cmd == "push_off":
        globals()["SCHEDULED_PUSH_ENABLED"] = False
        return "✅ 定时推送已关闭\n只响应主动指令(/signal /focus 等)"
    if cmd == "ask":
        if not args:            return "用法：/ask TSLL 现在能加仓吗"
        return cmd_ask(args)
    if cmd == "refresh_account": return cmd_refresh_account()
    if cmd == "version":         return get_changelog_text(latest_only=True)
    if cmd == "about":           return get_logo()
    if cmd == "refresh":
        refresh()
        return t("refresh_done")
    if cmd in ("help", "start"): return cmd_help(args)
    return t("unknown_cmd", cmd=cmd)


def check_alerts(signals):
    """止损/盈亏警报 / Stop-loss and P&L alerts"""
    for s in signals:
        if "error" in s or not s.get("risk"):
            continue
        ticker_short = s["ticker"].replace("US.", "")
        p   = s["price"]
        sl  = s["risk"].get("stop_loss", 0)
        pos = s.get("position")

        # ── 止损警报 ──────────────────────────────────────────────
        key = f"sl_{ticker_short}_{sl}"
        if key not in sent_alerts:
            if (s["signal"] != "SELL" and p <= sl) or (s["signal"] == "SELL" and p >= sl):
                sent_alerts.add(key)
                msg = (
                    f"🚨 【止损警报】 {ticker_short}\n"
                    f"当前价: ${p:.2f}  止损价: ${sl}\n"
                    f"请立即处理！"
                )
                if pos and pos.get("qty", 0) > 0:
                    qty     = pos["qty"]
                    cost    = pos["cost_price"]
                    pl_val  = pos["pl_val"]
                    pl_pct  = pos["pl_pct"]
                    cur_val = round(qty * p, 2)
                    ps      = "+" if pl_val >= 0 else ""
                    msg += (
                        f"\n\n"
                        f"持仓: {qty} 股  成本: ${cost}\n"
                        f"现价市值: ${cur_val:,.2f}\n"
                        f"盈亏: {ps}${pl_val:,.2f}  ({ps}{pl_pct:.1f}%)"
                    )
                send_tg(msg)
                print(f"  StopLoss alert: {ticker_short}")

        # ── 盈亏警报（仅有实际持仓时触发）───────────────────────
        if not pos or pos.get("qty", 0) <= 0:
            continue

        qty     = pos["qty"]
        cost    = pos["cost_price"]
        pl_val  = pos["pl_val"]
        pl_pct  = pos.get("pl_pct", 0)
        cur_val = round(qty * p, 2)
        ps      = "+" if pl_val >= 0 else ""
        is_profit = pl_val >= 0

        def _build_alert(level_n: int, ticker=ticker_short, qty=qty, cost=cost,
                         p=p, cur_val=cur_val, pl_val=pl_val, pl_pct=pl_pct,
                         ps=ps, sl=sl, is_profit=is_profit, s=s) -> str:
            if is_profit:
                header = f"📈 盈利 {level_n}级 提醒 | {ticker}"
                urgent = ""
            else:
                header = f"📉 亏损 {level_n}级 警告！| {ticker}"
                urgent = "\n⚠️ 请立即处理！"

            return (
                f"{header}\n"
                ""
                f"持仓: {qty} 股  成本: ${cost}\n"
                f"现价: ${p:.2f}  市值: ${cur_val:,.2f}\n"
                f"盈亏: {ps}${pl_val:,.2f}  ({ps}{pl_pct:.1f}%)\n"
                f"止损参考: ${sl}"
                f"{urgent}"
            )

        def _send_alert_with_ai(level_n, ticker=ticker_short, s=s,
                                build_fn=_build_alert):
            """发警报 + 异步请求 Claude 操作建议"""
            send_tg(build_fn(level_n))
            if not CLAUDE_API_KEY:
                return
            def _ai():
                ind  = s.get("indicators", {})
                t1   = s["risk"].get("target1", "?")
                t2   = s["risk"].get("target2", "?")
                rsi  = ind.get("rsi", "?")
                macd = ind.get("macd_hist", 0)
                volr = ind.get("vol_ratio", 0)
                pctb = ind.get("pct_b", 0)

                if is_profit:
                    prompt = (
                        f"我持有 {ticker} {qty} 股，成本 ${cost}，现价 ${p:.2f}，"
                        f"当前盈利 {pl_pct:.1f}%（共 +${pl_val:.2f}）。\n"
                        f"技术指标：\n"
                        f"  RSI(相对强弱) {rsi}，"
                        f"MACD柱(动量) {macd:+.4f}，"
                        f"量比(成交量倍数) {volr}x，"
                        f"布林%B(价格位置) {pctb:.2f}\n"
                        f"目标价1: ${t1}  目标价2: ${t2}  止损: ${sl}\n\n"
                        "请给出止盈操作建议，格式严格如下（不要其他内容）：\n"
                        "操作：卖出 XX 股 / 持有观望\n"
                        "理由：一句话，指标名称用【中文名(数值)】格式\n"
                        f"注意：若建议卖出，股数必须是 1 到 {qty} 之间的整数"
                    )
                else:
                    prompt = (
                        f"我持有 {ticker} {qty} 股，成本 ${cost}，现价 ${p:.2f}，"
                        f"当前亏损 {pl_pct:.1f}%（共 ${pl_val:.2f}）。\n"
                        f"技术指标：\n"
                        f"  RSI(相对强弱) {rsi}，"
                        f"MACD柱(动量) {macd:+.4f}，"
                        f"量比(成交量倍数) {volr}x\n"
                        f"止损价: ${sl}  目标价1: ${t1}\n\n"
                        "请给出操作建议，格式严格如下（不要其他内容）：\n"
                        f"操作：止损卖出 {qty} 股 / 持有观望等反弹\n"
                        "理由：一句话，指标名称用【中文名(数值)】格式\n"
                        "风险：一句话"
                    )

                try:
                    payload = json.dumps({
                        "model":      CLAUDE_MODEL,
                        "max_tokens": 120,
                        "system":     (
                            "你是专业美股交易员助理，只输出操作建议，"
                            "严格按用户要求的格式，不加任何额外说明。"
                        ),
                        "messages": [{"role": "user", "content": prompt}],
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        "https://api.anthropic.com/v1/messages",
                        data=payload,
                        headers={
                            "Content-Type":      "application/json",
                            "x-api-key":         CLAUDE_API_KEY,
                            "anthropic-version": "2023-06-01",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        result = json.loads(resp.read())
                    ai_text = "".join(
                        b["text"] for b in result.get("content", [])
                        if b.get("type") == "text"
                    ).strip()
                    usage    = result.get("usage", {})
                    tin      = usage.get("input_tokens", 0)
                    tout     = usage.get("output_tokens", 0)
                    cost_usd = tin * CLAUDE_PRICE_IN + tout * CLAUDE_PRICE_OUT
                    record_usage(ticker, tin, tout, cost_usd)

                    # Agent 分析扩展按钮（下一阶段实现）
                    buttons = [[
                        {"text": f"🔬 {ticker} Agent 深度分析",
                         "callback_data": f"agent_{ticker}"}
                    ]]
                    send_tg(
                        f"🤖 AI 助理建议 | {ticker}\n"
                        ""
                        f"{ai_text}\n"
                        f"─\n"
                        f"AI算力成本: {tout}tok / {cost_usd*100:.3f}¢",
                        buttons=buttons,
                    )
                except Exception as e:
                    print(f"  Alert AI error: {e}")
            threading.Thread(target=_ai, daemon=True).start()

        if abs(pl_pct) >= 10 and f"w10_{ticker_short}" not in sent_alerts:
            sent_alerts.add(f"w10_{ticker_short}")
            _send_alert_with_ai(4)
        elif abs(pl_pct) >= 5 and f"w5_{ticker_short}" not in sent_alerts:
            sent_alerts.add(f"w5_{ticker_short}")
            _send_alert_with_ai(3)


def scheduled_push(wl, push_type):
    now    = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = {"morning": t("push_morning"), "us_open": t("push_us_open")}.get(push_type, t("push_scheduled"))
    data   = load_signals()
    if not data:
        return
    send_tg(f"{header} | {now}\n" + t("urgency_explain"))
    tickers_list = all_tickers(wl)
    for idx, tk in enumerate(tickers_list, 1):
        s = next((x for x in data["signals"] if x["ticker"] == tk and "error" not in x), None)
        if s:
            ticker_short = tk.replace("US.", "")
            buttons = [[{"text": t("btn_detail", ticker=ticker_short),
                         "callback_data": f"detail_{ticker_short}"}]]
            send_tg(fmt_signal(s, idx=idx), buttons=buttons)

    # AI 虚拟操盘：同步决策
    if HAS_AI_TRADER:
        def _ai_trade():
            try:
                executed = ai_run_once()
                for rec in executed:
                    ticker_short = rec["ticker"].replace("US.", "")
                    action_label = "买入" if rec["action"] == "BUY" else "卖出"
                    pnl_line = ""
                    if "pnl" in rec:
                        ps = "+" if rec["pnl"] >= 0 else ""
                        pnl_line = f"\n实现盈亏: {ps}${rec['pnl']:.2f}"
                    msg = (
                        f"🤖 AI 虚拟操盘 | {ticker_short}\n"
                        ""
                        f"操作: {action_label} {rec['qty']} 股 @ ${rec['price']:.2f}\n"
                        f"依据: {rec.get('reason','')}"
                        f"{pnl_line}\n"
                        f"信心: {rec.get('confidence',0)}%"
                    )
                    if rec.get("cost_usd", 0) > 0:
                        msg += f"\nAI算力成本: {rec.get('tokens',0)}tok / {rec['cost_usd']*100:.3f}¢"
                    send_tg(msg)
            except Exception as e:
                print(f"  AI trade error: {e}")
        threading.Thread(target=_ai_trade, daemon=True).start()


def main():
    global last_update_id
    print(get_logo())
    wl = load_watchlist()
    print(f"  Watchlist: {all_tickers(wl)}")
    
    # v0.5.9 启动消息含版本 + 市场状态
    try:
        from version import VERSION, BUILD_DATE
    except ImportError:
        VERSION, BUILD_DATE = "?", "?"

    tickers_str = ", ".join(tk.replace("US.", "") for tk in all_tickers(wl))

    startup_lines = [
        f"🚀 <b>MagicQuant v{VERSION}</b> 已启动  ({BUILD_DATE})",
        f"bot_controller {BOT_CONTROLLER_VERSION} · {BOT_CONTROLLER_DATE}",
    ]
    try:
        from core.focus.focus_manager import get_version_info
        vinfo = get_version_info()
        startup_lines.append(
            f"focus {vinfo.get('focus_manager','?')} · "
            f"pusher {vinfo.get('pusher','?')} · "
            f"clock {vinfo.get('market_clock','?')}"
        )
    except Exception as e:
        startup_lines.append(f"focus 模块: 加载失败 ({e})")

    try:
        from core.focus.market_clock import format_market_status, get_market_status as _gms
        startup_lines.append(format_market_status())
        _startup_mkt = _gms()
    except:
        _startup_mkt = None

    startup_lines += [
        "",
        f"跟踪: {tickers_str}",
    ]
    if HAS_RISK_ENGINE:
        startup_lines.append("🛡️ Risk Engine 就绪  /risk_test 验证 28/28")
    if HAS_HEARTBEAT:
        startup_lines.append("💓 /heartbeat 实时状态")
    if HAS_MANUAL_CONSULT:
        startup_lines.append("🤖 /ai_test 主动召集 AI 智囊团")
    startup_lines.append("")
    startup_lines.append("发送 /help 查看所有指令  ·  /modules 查看版本")

    send_tg("\n".join(startup_lines))

    # ── v0.5.9 开盘自动启动 Focus ──────────────────────────
    # v0.5.10: overnight 也自动启动,24h 盯盘闭环
    if HAS_FOCUS:
        try:
            if _startup_mkt == "regular":
                focus_start(master="US.RKLB", send_tg_fn=send_tg, manual_mode=False)
                send_tg(
                    "🟢 <b>美股盘中 · 已自动启动盯盘</b>\n"
                    "━━━━━━━━━━━━━━\n"
                    "主标: RKLB  |  ETF: RKLX(多) / RKLZ(空)\n"
                    "频率: 2秒/次\n\n"
                    "/status 查看  ·  /unfocus 手动退出"
                )
            elif _startup_mkt in ("pre", "post", "overnight"):
                period_map = {"pre": "盘前", "post": "盘后", "overnight": "夜盘"}
                emoji_map  = {"pre": "🟡",   "post": "🟠",   "overnight": "🌃"}
                period = period_map[_startup_mkt]
                emoji  = emoji_map[_startup_mkt]
                focus_start(master="US.RKLB", send_tg_fn=send_tg, manual_mode=False)
                if _startup_mkt == "pre":
                    extra = "  ·  9:30 ET 切换高频"
                elif _startup_mkt == "overnight":
                    extra = "  ·  流动性差注意假信号"
                else:
                    extra = ""
                send_tg(
                    f"{emoji} <b>美股{period} · 已自动启动盯盘(低频)</b>\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"主标: RKLB  |  频率 10秒/次{extra}\n\n"
                    f"/status 查看  ·  /unfocus 手动退出"
                )
            else:
                send_tg(
                    "🌙 <b>美股休市 · Focus 未自动启动</b>\n"
                    "━━━━━━━━━━━━━━\n"
                    "如需盯盘请手动 /focus\n"
                    "（休市手动开启不受静默影响）"
                )
        except Exception as e:
            print(f"  [startup] auto-focus error: {e}")
    # ───────────────────────────────────────────────────────
    loop = 0
    while True:
        try:
            updates = get_updates(last_update_id + 1)
            for u in updates:
                last_update_id = u["update_id"]
                msg  = u.get("message", {})
                text = msg.get("text", "")
                cid  = str(msg.get("chat", {}).get("id", ""))
                if abs(int(cid)) == abs(int(CHAT_ID)):
                    # 文字指令
                    if text:
                        print(f"  CMD: {text}")
                        try:
                            reply = handle(text, wl)
                            if reply:
                                send_tg(reply)
                        except Exception as cmd_err:
                            import traceback
                            err_msg = f"❌ 指令出错: {text}\n{traceback.format_exc()[-300:]}"
                            print(err_msg)
                            send_tg(err_msg)
                    # PDF 文件（对账单）
                    if msg.get("document"):
                        reply = handle_document(msg)
                        if reply:
                            send_tg(reply)
                # inline 按钮回调
                cb = u.get("callback_query")
                if cb:
                    cb_cid = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                    if abs(int(cb_cid)) == abs(int(CHAT_ID)):
                        reply = handle_callback(cb, wl)
                        if reply:
                            send_tg(reply)

            # 网页按钮触发指令（轮询 web_trigger.json）
            trigger_file = os.path.join(BASE_DIR, "data", "web_trigger.json")
            if os.path.exists(trigger_file):
                try:
                    pending = json.load(open(trigger_file, encoding="utf-8"))
                    if pending:
                        # 清空触发文件
                        json.dump([], open(trigger_file, "w", encoding="utf-8"))
                        for item in pending:
                            cmd_text = item.get("cmd", "").strip()
                            if cmd_text:
                                print(f"  WEB_TRIGGER: {cmd_text}")
                                try:
                                    reply = handle(cmd_text, wl)
                                    if reply:
                                        send_tg(reply)
                                except Exception as we:
                                    print(f"  Web trigger error: {we}")
                except Exception as e:
                    print(f"  Trigger file error: {e}")

            # ── 定时推送(v0.3.0 默认关闭)─────────────────────
            # 开启方式:在 settings.py 加 PUSH_SCHEDULED = True
            # 或临时用 /push_on 指令
            now_hm = datetime.now().strftime("%H:%M")
            scheduled_enabled = globals().get("SCHEDULED_PUSH_ENABLED", False)
            if scheduled_enabled and now_hm in PUSH_TIMES and now_hm not in pushed_times:
                pushed_times.add(now_hm)
                if len(pushed_times) > 8:
                    pushed_times.clear()
                pt = "morning" if now_hm == "09:00" else "us_open" if now_hm in ("21:30", "22:30") else "scheduled"
                refresh()
                wl = load_watchlist()
                scheduled_push(wl, pt)
                # 早9点额外推送对账单缺口提醒
                if now_hm == "09:00":
                    gap_msg = check_statement_gaps()
                    if gap_msg:
                        send_tg(gap_msg)

            if loop % 12 == 0:
                # v0.3.2: 关闭老的 check_alerts 机制
                # 原因: 与 Focus 盯盘的 drawdown/profit_target 触发器重复
                #       老机制会每 60 秒扫一次全部持仓,刷屏 + 每次调 AI
                # 替代: 使用 /focus 后由 Focus 系统主动监控
                # 如需恢复: 在 settings.py 加 LEGACY_ALERTS_ENABLED = True
                if globals().get("LEGACY_ALERTS_ENABLED", False):
                    data = load_signals()
                    if data:
                        check_alerts(data.get("signals", []))

            if loop % 60 == 0 and loop > 0:
                wl = load_watchlist()

            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Running (loop {loop})", end="\r")
            loop += 1
            time.sleep(5)

        except KeyboardInterrupt:
            print("\n  Stopped.")
            send_tg(t("bot_stopped"))
            # 🆕 停止焦点盯盘(v0.3.0)
            if HAS_FOCUS and is_focused():
                try:
                    focus_stop()
                except:
                    pass
            # 🆕 清理 Futu 连接(v0.2.1)
            if HAS_REALTIME:
                try:
                    close_quote_client()
                except:
                    pass
            break
        except Exception as e:
            print(f"\n  Error: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
