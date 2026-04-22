"""
MagicQuant 慧投 — 国际化语言包
Internationalization (i18n) language pack

支持语言 / Supported languages:
  "zh"  — 中文（默认）
  "en"  — English

用法 / Usage:
  from i18n import t, set_lang
  set_lang("en")        # 切换语言（程序启动时调用一次）
  print(t("list_title"))
"""

_lang = "zh"  # 默认语言，由 settings.py 的 LANGUAGE 决定


def set_lang(lang: str):
    global _lang
    if lang in _STRINGS:
        _lang = lang


def t(key: str, **kwargs) -> str:
    """
    获取当前语言的字符串，支持 {占位符} 格式化。
    Get localized string, supports {placeholder} formatting.
    """
    val = _STRINGS.get(_lang, _STRINGS["zh"]).get(key)
    if val is None:
        # 降级到中文 / fallback to zh
        val = _STRINGS["zh"].get(key, key)
    return val.format(**kwargs) if kwargs else val


# ══════════════════════════════════════════════════════════════════
#  语言字符串定义 / String definitions
# ══════════════════════════════════════════════════════════════════

_STRINGS = {

# ──────────────────────────────────────────────────────────────────
"zh": {

    # 信号标签 signal labels
    "sig_buy":          "【买入】",
    "sig_sell":         "【卖出/做空】",
    "sig_hold":         "【持有】",
    "sig_unknown":      "【?】",
    "action_buy":       "建议买入",
    "action_sell":      "建议卖出/做空",
    "action_hold":      "建议持有观望",
    "action_unknown":   "操作建议",

    # 信号标题行（新格式）
    "stock_idx":        "股票 {n} ",
    "stock_no_idx":     "",
    "signal_header":    "{prefix}{ticker} ({name})   建议{sig}  级别: {lvl}  信心: {conf}%",
    "urgency_explain":  "级别 1(最低) ~ 5(最紧急)",

    # 跟踪列表 /list
    "list_title":       "=== 跟踪列表 ===",
    "list_no_data":     "暂无数据",
    "list_footer_pos":  "[P] = 有持仓（自动跟踪）",
    "list_total":       "共: {n} 只",
    "list_sig_buy":     "买入",
    "list_sig_sell":    "卖出",
    "list_sig_hold":    "持有",
    "list_urgency":     "级别{lvl}",

    # 信号摘要 fmt_signal
    "sep":              "==============================",
    "urgency_label":    "紧急度: 级别{lvl}（1最低/5最紧急）  信心: {conf}%",
    "price_line":       "当前价格: ${price:.2f}  {cs}{chg:.2f} ({cs}{pct:.2f}%)",
    "stop_loss":        "止损价:   ${val}",
    "target1":          "目标价1:  ${val}",
    "target2":          "目标价2:  ${val}",
    "risk_per_share":   "风险/股:  ${val}",
    "suggest_shares":   "建议手数: {n} 股",
    "unit_price":       "单价:     ${price:.2f}",
    "total_cost":       "预计金额: ${total:,.2f}",
    "section_fees":     "— 富途手续费明细（已验证）—",
    "fee_platform":     "  平台费:    $USD {val:.2f}",
    "fee_settlement":   "  结算费:    $USD {val:.2f}",
    "fee_taf":          "  TAF监管费: $USD {val:.2f}  (仅卖出)",
    "fee_this_trade":   "  本次合计:  $USD {val:.2f}",
    "fee_roundtrip":    "  买+卖往返: $USD {val:.2f}",
    "section_tech":     "--- 技术指标 ---",
    "candlestick":      "K线形态: {name} — {desc}",
    "section_position": "--- 当前持仓 ---",
    "pos_qty":          "持仓数量: {qty} 股",
    "pos_cost":         "持仓成本: ${cost}",
    "pos_pl":           "持仓盈亏: {sign}${pl} ({sign}{pct}%)",
    "signal_reason":    "信号依据: {reason}",

    # 详细分析 cmd_detail
    "detail_title":     "【{sig}】 {ticker} 详细分析",
    "section_reasons":  "--- 信号依据 ---",
    "section_full_tech":"--- 完整技术指标 ---",
    "rsi_overbought":   "(超买区)",
    "rsi_oversold":     "(超卖区)",
    "rsi_normal":       "(正常区间)",
    "macd_bull":        "(多头)",
    "macd_bear":        "(空头)",
    "bb_upper":         "(近上轨)",
    "bb_lower":         "(近下轨)",
    "bb_mid":           "(中轨区)",
    "vol_high":         "(放量)",
    "vol_low":          "(缩量)",
    "vol_normal":       "(均量)",
    "atr_label":        "ATR:    {val}  (平均波动幅度)",
    "section_risk":     "--- 风险管理 ---",
    "stop_detail":      "止损价:  ${val}  (下跌超过此价止损)",
    "t1_detail":        "目标1:   ${val}  (第一目标获利)",
    "t2_detail":        "目标2:   ${val}  (第二目标获利)",
    "pos_short":        "持仓: {qty} 股  成本: ${cost}",
    "pos_pl_short":     "盈亏: {sign}${pl} ({sign}{pct}%)",
    "updated_at":       "更新时间: {t}",
    "no_data_futu":     "暂无数据，请确认 FutuOpenD 在运行。",
    "no_data_ticker":   "未找到 {ticker} 的数据。",
    "data_error":       "{ticker} 数据错误: {err}",

    # Claude AI 分析
    "claude_analyzing":    "⏳ {ticker} — 正在调用 Claude AI 深度分析，请稍候...",
    "claude_estimating":        "💰 {ticker} — 预估费用: {cost:.3f}¢ (USD)，正在分析...",
    "claude_estimating_search": "🔍 {ticker} — Claude 正在联网搜索+分析，预计需要 30-60 秒，预估费用: {cost:.3f}¢...",
    "claude_result_header":"🤖 {ticker} — Claude AI 深度分析",
    "claude_cost_note":    "─\nAI算力成本: 输入{tin}tok + 输出{tout}tok = {cost:.3f}¢ | 发送 /usage 查看累计",
    "claude_no_key":       "⚠️ 未配置 CLAUDE_API_KEY，请在 config/settings.py 中填入 API Key。",
    "claude_no_key_hint":  "💡 配置 CLAUDE_API_KEY 后，/detail 将自动附带 AI 深度分析。",
    "claude_api_error":    "❌ Claude API 错误 {code}: {msg}",
    "claude_timeout":      "❌ Claude API 超时或网络错误: {err}",

    # /pnl 盈亏分析
    "pnl_no_parser":    "⚠️ 需要安装 pdfplumber：pip install pdfplumber",
    "pnl_no_data":      "暂无对账单数据，请先上传 PDF 对账单。",
    "pnl_title":        "=== 盈亏分析 | {date_range} ===",
    "pnl_trade_days":   "交易日: {n} 天",
    "pnl_total_trades": "总成交: {n} 笔",
    "pnl_total_fees":   "总手续费: $USD {fee:.2f}",
    "pnl_total":        "净盈亏:   {sign}$USD {pnl:.2f}",
    "pnl_by_ticker":    "--- 按股票 ---",
    "pnl_row":          "{ticker}: 买${buy:,.0f} 卖${sell:,.0f} 费${fee:.2f} → {sign}${pnl:.2f}",
    "pnl_missing_hint": "⚠️ 有 {n} 天对账单缺失，盈亏数据不完整:",
    "pnl_upload_hint":  "直接发送 PDF 对账单到此群即可补录。",

    # 对账单处理
    "stmt_parsing":          "⏳ 正在解析: {filename}",
    "stmt_download_fail":    "❌ 文件下载失败: {err}",
    "stmt_parse_fail":       "❌ PDF 解析失败: {err}",
    "stmt_no_date":          "❌ 无法识别日期，请确认是富途对账单: {filename}",
    "stmt_already_exists":   "ℹ️ {date} 的对账单已存在，跳过。",
    "stmt_saved":            "✅ {date} 对账单已入库\n   交易: {trades} 笔  手续费: $USD {fees:.2f}",
    "stmt_still_missing":    "📋 还有 {n} 天缺失，建议补传:",
    "stmt_all_complete":     "✅ 所有对账单已完整！",

    # 早9点缺口提醒
    "stmt_reminder_title":     "📋 对账单提醒",
    "stmt_reminder_yesterday": "昨日 {date} 对账单未上传",
    "stmt_reminder_older":     "另有 {n} 天历史对账单缺失",
    "stmt_reminder_how":       "富途App → 我的 → 资产明细 → 对账单 → 下载PDF\n直接发到此群即可自动入库",
    "usage_calls":      "本月调用次数: {n} 次",
    "usage_tokens":     "Token 消耗: 输入 {tin:,} + 输出 {tout:,}",
    "usage_cost":       "本月费用: ${cost:.4f} USD ≈ ¥{cost_cny:.2f}",
    "usage_recent":     "最近5次调用:",
    "usage_note":       "模型: claude-sonnet-4 | 定价: $3/输入M + $15/输出M token",

    # 信号推送 cmd_signal
    "signal_title":     "=== 信号更新 | {now} ===",
    "detail_hint":      ">> 发送 /detail {ticker} 查看详细分析（含AI）",
    "btn_detail":       "📊 {ticker} 详细分析",
    "no_signal_data":   "暂无信号数据，请确认 FutuOpenD 在运行。",
    "warn_overbought":  "【警告】超买: {tickers} RSI>70，注意回调",
    "hint_oversold":    "【机会】超卖: {tickers} RSI<30，反弹机会",
    "pdt_reminder":     "【PDT提醒】账户<$25k，每5日最多3次日内交易",

    # /add /remove
    "add_usage":        "用法: /add TSLA 或 /add TSLA NVDA",
    "added":            "已添加: {tickers}",
    "already_in_list":  "已在列表: {tickers}",
    "remove_usage":     "用法: /remove TSLA",
    "removed":          "已移除: {tickers}",
    "protected":        "有持仓无法移除: {tickers}",
    "not_found":        "不在列表: {tickers}",

    # /detail usage
    "detail_usage":     "用法: /detail RKLB",

    # /account
    "account_title":    "=== 账户资产 | {t} ===",
    "total_assets":     "总资产:     ${val:>12,.2f}",
    "cash":             "可用资金:   ${val:>12,.2f}",
    "market_val":       "持仓市值:   ${val:>12,.2f}",
    "frozen":           "冻结资金:   ${val:>12,.2f}",
    "buy_power":        "购买力:     ${val:>12,.2f}",
    "unrealized_pl":    "未实现盈亏: {sign}${val:>11,.2f}",
    "account_note":     "【提醒】数据更新时间: {t}",
    "account_refresh":  "发送 /refresh_account 获取最新数据",
    "no_account_data":  "暂无账户数据，请先运行 python futu_data_collector.py",
    "account_empty":    "账户数据为空，请运行 python futu_data_collector.py 刷新",

    # /positions
    "positions_title":  "=== 当前持仓 | {t} ===",
    "pos_row1":         "  持仓: {qty:.0f} 股  成本: ${cost:.2f}  现价: ${price:.2f}",
    "pos_row2":         "  市值: ${mkt:,.2f}",
    "pos_row3":         "  盈亏: {sign}${pl:,.2f} ({sign}{pct:.2f}%)",
    "pos_total_pl":     "总未实现盈亏: {sign}${pl:,.2f}",
    "no_positions":     "当前无持仓",

    # /history
    "history_title":    "=== 近{days}天交易记录 ===",
    "history_total":    "总交易笔数: {n} 笔",
    "history_fee":      "总手续费:   ${fee:,.2f}",
    "section_by_ticker":"--- 按股票统计 ---",
    "history_row":      "{ticker}: {n}笔  买入${buy:,.0f}  卖出${sell:,.0f}  手续费${fee:.2f}",
    "section_recent":   "--- 最近10笔成交 ---",
    "deal_buy":         "买入",
    "deal_sell":        "卖出",
    "deal_row":         "{t}  {side} {ticker} {qty:.0f}股 @ ${price:.2f}",
    "no_history":       "近{days}天无成交记录",
    "no_account_data2": "暂无账户数据",

    # /pdt
    "pdt_title":        "=== PDT 日内交易计数 ===",
    "pdt_account_size": "账户规模: <$25,000（PDT限制适用）",
    "pdt_window":       "滚动5个交易日内:",
    "pdt_used":         "  已用日内交易次数: {n} / 3",
    "pdt_remaining":    "  剩余可用次数:     {n}",
    "pdt_records":      "日内交易记录:",
    "pdt_warn_zero":    "⚠️ 警告: 已达PDT限制！今日不可再进行日内交易",
    "pdt_warn_freeze":  "违规将导致账户被限制交易90天",
    "pdt_warn_one":     "⚠️ 注意: 仅剩1次日内交易机会，请谨慎使用",
    "pdt_ok":           "✅ PDT余量充足，可正常交易",
    "pdt_no_deals":     "暂无成交记录，无法计算 PDT",

    # /refresh_account
    "refresh_ok":       "✅ 账户数据已刷新！发送 /account 查看最新数据",
    "refresh_fail":     "刷新失败: {err}",
    "refresh_error":    "刷新出错: {err}",

    # 定时推送 scheduled_push
    "push_morning":     "【早间信号】",
    "push_us_open":     "【美股开市】",
    "push_scheduled":   "【信号更新】",
    "push_urgency_note":"紧急度说明: 级别1(最低) ~ 级别5(最紧急)",

    # 止损/盈亏警报 check_alerts
    "alert_stoploss":   "【止损警报】 {ticker}\nPrice: ${price:.2f} | Stop: ${stop}\n请立即处理！",
    "alert_pl_l4":      "【盈亏警报 L4】 {ticker}\n盈亏: {sign}{pl:.1f}%\nPrice:${price:.2f} Stop:${stop}",
    "alert_pl_l3":      "【盈亏提醒 L3】 {ticker}\n盈亏: {sign}{pl:.1f}%\nPrice:${price:.2f}",

    # 启动/停止
    "bot_started":      "MagicQuant已启动！\n跟踪: {tickers}\n发送 /help 查看所有指令。",
    "bot_stopped":      "MagicQuant已停止。",
    "refresh_done":     "数据已刷新！",
    "unknown_cmd":      "未知指令: /{cmd}\n发送 /help 查看所有指令。",

    # /help
    "help_text": (
        "=== MagicQuant 慧投 v0.2.0 ===\n\n"
        "/add TSLA        添加跟踪股票\n"
        "/add TSLA NVDA   同时添加多只\n"
        "/remove TSLA     移除跟踪\n"
        "/list            查看跟踪列表\n"
        "/signal          推送全部信号\n"
        "/signal TSLA     推送单只信号\n"
        "/refresh         立即刷新数据\n"
        "/detail RKLB     详细分析（含 Claude AI 联网）\n"
        "/ask TSLL 问题   随时向AI咨询（联网回答）\n"
        "/pnl             盈亏分析（需上传对账单）\n"
        "/ai_positions    AI虚拟持仓\n"
        "/ai_trades       AI交易记录\n"
        "/ai_report       AI阶段性报告\n"
        "/account         账户资产总览\n"
        "/positions       当前持仓详情\n"
        "/history         近30天交易记录\n"
        "/pdt             PDT日内交易计数\n"
        "/usage           Claude API 费用统计\n"
        "/refresh_account 刷新账户数据\n"
        "/version         版本更新日志\n"
        "/about           关于 MagicQuant\n"
        "/help            显示帮助\n\n"
        "有持仓的股票自动跟踪，无法移除。\n"
        "紧急度: 级别1(低) 到 级别5(最紧急)"
    ),
},  # end zh


# ──────────────────────────────────────────────────────────────────
"en": {

    # signal labels
    "sig_buy":          "[BUY]",
    "sig_sell":         "[SELL/SHORT]",
    "sig_hold":         "[HOLD]",
    "sig_unknown":      "[?]",
    "action_buy":       "Action: BUY",
    "action_sell":      "Action: SELL / SHORT",
    "action_hold":      "Action: HOLD",
    "action_unknown":   "Action",

    # signal header (new format)
    "stock_idx":        "Stock {n} ",
    "stock_no_idx":     "",
    "signal_header":    "{prefix}{ticker} ({name})   {sig}  L{lvl}  Conf: {conf}%",
    "urgency_explain":  "Urgency: L1 (lowest) ~ L5 (most urgent)",

    # /list
    "list_title":       "=== Watchlist ===",
    "list_no_data":     "No data",
    "list_footer_pos":  "[P] = Position held (auto-tracked)",
    "list_total":       "Total: {n}",
    "list_sig_buy":     "BUY",
    "list_sig_sell":    "SELL",
    "list_sig_hold":    "HOLD",
    "list_urgency":     "L{lvl}",

    # fmt_signal
    "sep":              "==============================",
    "urgency_label":    "Urgency: L{lvl} (1=low/5=urgent)  Confidence: {conf}%",
    "price_line":       "Price: ${price:.2f}  {cs}{chg:.2f} ({cs}{pct:.2f}%)",
    "stop_loss":        "Stop Loss:  ${val}",
    "target1":          "Target 1:   ${val}",
    "target2":          "Target 2:   ${val}",
    "risk_per_share":   "Risk/Share: ${val}",
    "suggest_shares":   "Suggested:  {n} shares",
    "unit_price":       "Price:      ${price:.2f}",
    "total_cost":       "Est. Total: ${total:,.2f}",
    "section_fees":     "— Moomoo AU Fees (verified) —",
    "fee_platform":     "  Platform:    $USD {val:.2f}",
    "fee_settlement":   "  Settlement:  $USD {val:.2f}",
    "fee_taf":          "  TAF:         $USD {val:.2f}  (sell only)",
    "fee_this_trade":   "  This trade:  $USD {val:.2f}",
    "fee_roundtrip":    "  Round-trip:  $USD {val:.2f}",
    "section_tech":     "--- Technical Indicators ---",
    "candlestick":      "Candlestick: {name} — {desc}",
    "section_position": "--- Current Position ---",
    "pos_qty":          "Qty:  {qty} shares",
    "pos_cost":         "Cost: ${cost}",
    "pos_pl":           "P&L:  {sign}${pl} ({sign}{pct}%)",
    "signal_reason":    "Reason: {reason}",

    # cmd_detail
    "detail_title":     "[{sig}] {ticker} Detailed Analysis",
    "section_reasons":  "--- Signal Rationale ---",
    "section_full_tech":"--- Full Technical Indicators ---",
    "rsi_overbought":   "(overbought)",
    "rsi_oversold":     "(oversold)",
    "rsi_normal":       "(normal)",
    "macd_bull":        "(bullish)",
    "macd_bear":        "(bearish)",
    "bb_upper":         "(near upper band)",
    "bb_lower":         "(near lower band)",
    "bb_mid":           "(mid band)",
    "vol_high":         "(high volume)",
    "vol_low":          "(low volume)",
    "vol_normal":       "(avg volume)",
    "atr_label":        "ATR:    {val}  (avg true range)",
    "section_risk":     "--- Risk Management ---",
    "stop_detail":      "Stop Loss: ${val}  (exit if price falls below)",
    "t1_detail":        "Target 1:  ${val}  (first profit target)",
    "t2_detail":        "Target 2:  ${val}  (second profit target)",
    "pos_short":        "Position: {qty} shares @ ${cost}",
    "pos_pl_short":     "P&L: {sign}${pl} ({sign}{pct}%)",
    "updated_at":       "Updated: {t}",
    "no_data_futu":     "No data. Please make sure FutuOpenD is running.",
    "no_data_ticker":   "No data found for {ticker}.",
    "data_error":       "{ticker} data error: {err}",

    # Claude AI
    "claude_analyzing":    "⏳ {ticker} — Calling Claude AI for deep analysis...",
    "claude_estimating":        "💰 {ticker} — Estimated cost: {cost:.3f}¢ (USD), analyzing...",
    "claude_estimating_search": "🔍 {ticker} — Claude searching web + analyzing, est. 30-60 sec, cost: {cost:.3f}¢...",
    "claude_result_header":"🤖 {ticker} — Claude AI Analysis",
    "claude_cost_note":    "─\nAI算力成本: in:{tin}tok + out:{tout}tok = {cost:.3f}¢ | /usage for monthly total",
    "claude_no_key":       "⚠️ CLAUDE_API_KEY not set. Please add it to config/settings.py.",
    "claude_no_key_hint":  "💡 Set CLAUDE_API_KEY in settings.py to enable AI analysis with /detail.",
    "claude_api_error":    "❌ Claude API error {code}: {msg}",
    "claude_timeout":      "❌ Claude API timeout or network error: {err}",

    # /pnl
    "pnl_no_parser":    "⚠️ pdfplumber not installed: pip install pdfplumber",
    "pnl_no_data":      "No statement data yet. Please upload PDF statements first.",
    "pnl_title":        "=== P&L Analysis | {date_range} ===",
    "pnl_trade_days":   "Trading days: {n}",
    "pnl_total_trades": "Total fills:  {n}",
    "pnl_total_fees":   "Total fees:   $USD {fee:.2f}",
    "pnl_total":        "Net P&L:      {sign}$USD {pnl:.2f}",
    "pnl_by_ticker":    "--- By Ticker ---",
    "pnl_row":          "{ticker}: Buy${buy:,.0f} Sell${sell:,.0f} Fee${fee:.2f} → {sign}${pnl:.2f}",
    "pnl_missing_hint": "⚠️ {n} day(s) missing — P&L data incomplete:",
    "pnl_upload_hint":  "Send PDF statements directly to this chat to import.",

    # statement handling
    "stmt_parsing":          "⏳ Parsing: {filename}",
    "stmt_download_fail":    "❌ Download failed: {err}",
    "stmt_parse_fail":       "❌ PDF parse failed: {err}",
    "stmt_no_date":          "❌ Cannot detect date, check it's a Moomoo statement: {filename}",
    "stmt_already_exists":   "ℹ️ Statement for {date} already exists, skipped.",
    "stmt_saved":            "✅ {date} statement imported\n   Trades: {trades}  Fees: $USD {fees:.2f}",
    "stmt_still_missing":    "📋 Still missing {n} day(s):",
    "stmt_all_complete":     "✅ All statements complete!",

    # morning gap reminder
    "stmt_reminder_title":     "📋 Statement Reminder",
    "stmt_reminder_yesterday": "Yesterday {date} statement not uploaded",
    "stmt_reminder_older":     "{n} older statement(s) also missing",
    "stmt_reminder_how":       "Moomoo App → Me → Assets → Statements → Download PDF\nSend here to auto-import",
    "usage_calls":      "Calls this month: {n}",
    "usage_tokens":     "Tokens: in {tin:,} + out {tout:,}",
    "usage_cost":       "Monthly cost: ${cost:.4f} USD",
    "usage_recent":     "Last 5 calls:",
    "usage_note":       "Model: claude-sonnet-4 | Pricing: $3/in-M + $15/out-M tokens",

    # cmd_signal
    "signal_title":     "=== Signal Update | {now} ===",
    "detail_hint":      ">> Send /detail {ticker} for full analysis (with AI)",
    "btn_detail":       "📊 {ticker} Detail",
    "no_signal_data":   "No signal data. Please make sure FutuOpenD is running.",
    "warn_overbought":  "[WARN] Overbought: {tickers} RSI>70, watch for pullback",
    "hint_oversold":    "[OPP] Oversold: {tickers} RSI<30, possible bounce",
    "pdt_reminder":     "[PDT] Account <$25k: max 3 day trades per 5 rolling days",

    # /add /remove
    "add_usage":        "Usage: /add TSLA or /add TSLA NVDA",
    "added":            "Added: {tickers}",
    "already_in_list":  "Already in list: {tickers}",
    "remove_usage":     "Usage: /remove TSLA",
    "removed":          "Removed: {tickers}",
    "protected":        "Cannot remove (position held): {tickers}",
    "not_found":        "Not in list: {tickers}",

    # /detail usage
    "detail_usage":     "Usage: /detail RKLB",

    # /account
    "account_title":    "=== Account Summary | {t} ===",
    "total_assets":     "Total Assets:   ${val:>12,.2f}",
    "cash":             "Cash:           ${val:>12,.2f}",
    "market_val":       "Position Value: ${val:>12,.2f}",
    "frozen":           "Frozen Cash:    ${val:>12,.2f}",
    "buy_power":        "Buying Power:   ${val:>12,.2f}",
    "unrealized_pl":    "Unrealized P&L: {sign}${val:>11,.2f}",
    "account_note":     "[Note] Data as of: {t}",
    "account_refresh":  "Send /refresh_account to update.",
    "no_account_data":  "No account data. Please run python futu_data_collector.py first.",
    "account_empty":    "Account data empty. Please run python futu_data_collector.py to refresh.",

    # /positions
    "positions_title":  "=== Positions | {t} ===",
    "pos_row1":         "  Qty: {qty:.0f}  Cost: ${cost:.2f}  Price: ${price:.2f}",
    "pos_row2":         "  Mkt Val: ${mkt:,.2f}",
    "pos_row3":         "  P&L: {sign}${pl:,.2f} ({sign}{pct:.2f}%)",
    "pos_total_pl":     "Total Unrealized P&L: {sign}${pl:,.2f}",
    "no_positions":     "No open positions.",

    # /history
    "history_title":    "=== Last {days} Days Trade History ===",
    "history_total":    "Total Trades: {n}",
    "history_fee":      "Total Fees:   ${fee:,.2f}",
    "section_by_ticker":"--- By Ticker ---",
    "history_row":      "{ticker}: {n} trades  Buy${buy:,.0f}  Sell${sell:,.0f}  Fee${fee:.2f}",
    "section_recent":   "--- Last 10 Fills ---",
    "deal_buy":         "BUY",
    "deal_sell":        "SELL",
    "deal_row":         "{t}  {side} {ticker} {qty:.0f}sh @ ${price:.2f}",
    "no_history":       "No trades in the last {days} days.",
    "no_account_data2": "No account data.",

    # /pdt
    "pdt_title":        "=== PDT Day Trade Counter ===",
    "pdt_account_size": "Account size: <$25,000 (PDT rules apply)",
    "pdt_window":       "Rolling 5 trading days:",
    "pdt_used":         "  Day trades used:      {n} / 3",
    "pdt_remaining":    "  Day trades remaining: {n}",
    "pdt_records":      "Day trade log:",
    "pdt_warn_zero":    "⚠️ WARNING: PDT limit reached! No more day trades today.",
    "pdt_warn_freeze":  "Violation may result in 90-day trading restriction.",
    "pdt_warn_one":     "⚠️ CAUTION: Only 1 day trade remaining. Use wisely.",
    "pdt_ok":           "✅ PDT headroom OK. Normal trading allowed.",
    "pdt_no_deals":     "No trade records. Cannot calculate PDT.",

    # /refresh_account
    "refresh_ok":       "✅ Account data refreshed! Send /account to view.",
    "refresh_fail":     "Refresh failed: {err}",
    "refresh_error":    "Refresh error: {err}",

    # scheduled_push
    "push_morning":     "[Morning Signal]",
    "push_us_open":     "[US Market Open]",
    "push_scheduled":   "[Signal Update]",
    "push_urgency_note":"Urgency: L1 (lowest) ~ L5 (most urgent)",

    # check_alerts
    "alert_stoploss":   "[STOP LOSS ALERT] {ticker}\nPrice: ${price:.2f} | Stop: ${stop}\nPlease act now!",
    "alert_pl_l4":      "[P&L ALERT L4] {ticker}\nP&L: {sign}{pl:.1f}%\nPrice:${price:.2f} Stop:${stop}",
    "alert_pl_l3":      "[P&L NOTICE L3] {ticker}\nP&L: {sign}{pl:.1f}%\nPrice:${price:.2f}",

    # bot lifecycle
    "bot_started":      "MagicQuant started!\nTracking: {tickers}\nSend /help for commands.",
    "bot_stopped":      "MagicQuant stopped.",
    "refresh_done":     "Data refreshed!",
    "unknown_cmd":      "Unknown command: /{cmd}\nSend /help to see all commands.",

    # /help
    "help_text": (
        "=== MagicQuant v0.2.0 ===\n\n"
        "/add TSLA        Add stock to watchlist\n"
        "/add TSLA NVDA   Add multiple stocks\n"
        "/remove TSLA     Remove from watchlist\n"
        "/list            View watchlist\n"
        "/signal          Push all signals\n"
        "/signal TSLA     Push single stock signal\n"
        "/refresh         Refresh data now\n"
        "/detail RKLB     Detailed analysis (with AI)\n"
        "/pnl             P&L analysis (requires statements)\n"
        "/account         Account summary\n"
        "/positions       Current positions\n"
        "/history         Last 30 days trade history\n"
        "/pdt             PDT day trade counter\n"
        "/usage           Claude API usage & cost\n"
        "/refresh_account Refresh account data\n"
        "/version         Version changelog\n"
        "/about           About MagicQuant\n"
        "/help            Show this help\n\n"
        "Stocks with open positions are auto-tracked and cannot be removed.\n"
        "Urgency: L1 (low) to L5 (most urgent)"
    ),
},  # end en

}  # end _STRINGS
