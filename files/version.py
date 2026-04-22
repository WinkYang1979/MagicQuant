"""
慧投 HuiTou | MagicQuant
版本管理文件

Owner: Zhen Yang
Email: happy.yz@gmail.com
"""

APP_NAME_EN = "MagicQuant"
APP_NAME_CN = "慧投"
APP_SLOGAN_CN = "梦想终究是要有的，万一实现了呢？"
APP_SLOGAN_EN = "Dare to dream. Data to win."

VERSION     = "0.3.5"
BUILD_DATE  = "2026-04-21"

OWNER_NAME  = "Zhen Yang"
OWNER_EMAIL = "happy.yz@gmail.com"

CHANGELOG = [
    {
        "version": "0.3.5",
        "date": "2026-04-21",
        "title": "AI 智囊团 + Dashboard 可视化 + 费率精确化",
        "changes": [
            "🤖 AI 智囊团: Focus 每次触发自动召集 Haiku + DeepSeek + GPT-5 三顾问 + Opus Leader 汇总",
            "智囊团推送: 带具体股数 + 价格 + 理由 + 风险 + 信心度,允许 HOLD 不强行交易",
            "Opus Leader 展示: 清晰对比 3 位顾问原意见,可独立判断,含与顾问分歧标记",
            "成本透明: 每次推送明细每个 AI 花费 + tokens,今日累计自动追踪",
            "新指令: /ai_advise_on /ai_advise_off /ai_advise_status 控制开关",
            "Dashboard 新增 AI 智囊团面板: 实时显示最新决策 + 10 条历史记录",
            "Dashboard 新增 3 个 API: /ai_advisor/latest /ai_advisor/history /ai_advisor/cost",
            "🆕 AI 大赛: /race 5 AI 虚拟操盘赛马,每人 $20k 起始,真实 Moomoo 费率",
            "AI 大赛指令: /race /race_stats /race_cost /race_stop /race_reset /race_providers",
            "费率精确化: Moomoo AU 真实公式 - 买$1.29固定,卖$1.31~$8.30动态(SEC+TAF)",
            "支持 Claude/OpenAI/DeepSeek/Kimi 四家 AI,环境变量兼容 CLAUDE_/ANTHROPIC_",
            "test_ai_providers.py 独立测试脚本: 一键验证所有 AI 连通性",
            "AI Key 安全加载: 自动过滤空值/注释/占位符",
            "历史记录持久化: data/ai_advisor_history.json 存 200 条,ai_advisor_cost.json 日清零",
        ]
    },
    {
        "version": "0.3.4",
        "date": "2026-04-21",
        "title": "AI 虚拟操盘大赛",
        "changes": [
            "5 AI 并行赛马: Claude Opus/Haiku + GPT-5 + DeepSeek + Kimi",
            "每 AI 独立 $20,000 虚拟账户,执行真实交易规则",
            "180 秒/轮自动决策,统一 prompt 公平比较",
            "/race_cost 指令: 实时查看算力花费",
            "并行调用不等最慢的,提升响应速度",
        ]
    },
    {
        "version": "0.3.3",
        "date": "2026-04-21",
        "title": "RKLX/RKLZ 方向反转 Bug 修复",
        "changes": [
            "🔥 紧急修复: 老代码把 RKLZ 当作做多 ETF,导致推送方向反向",
            "修正: RKLX = 2x 做多 RKLB, RKLZ = 2x 做空 RKLB",
            "swing_top 看跌 → 卖 RKLX(平多)+ 买 RKLZ(开空)",
            "swing_bottom 看涨 → 卖 RKLZ(平空)+ 买 RKLX(开多)",
            "pairs.py 配对配置文件,未来扩展其他主股时只改这里",
        ]
    },
    {
        "version": "0.3.2",
        "date": "2026-04-21",
        "title": "Dashboard 丈人版不闪烁",
        "changes": [
            "focus.html 增量 DOM 更新,每 2 秒刷新不再整页重绘",
            "价格变化 CSS flash 动画 + 叮声提醒",
            "触发列表单独增量更新",
            "dashboard/server.py 绑定 0.0.0.0 支持 LAN 访问",
            "新增 /focus/state API 实时盯盘状态",
        ]
    },
    {
        "version": "0.3.1",
        "date": "2026-04-21",
        "title": "Focus 性能压测调优",
        "changes": [
            "1 秒频率验证稳定: 20/20 成功, avg 209ms, p95 211ms",
            "4 只股票并发 216ms, 无限流",
            "K 线拉取 65ms 超快",
            "更激进的盯盘频率不影响 Moomoo 限流",
        ]
    },
    {
        "version": "0.3.0",
        "date": "2026-04-21",
        "title": "Focus 盯盘模式 + 配对做 T",
        "changes": [
            "🎯 Focus 焦点盯盘模式: RKLB 波段做 T 信号系统",
            "新指令: /focus /unfocus /status /push_on /push_off",
            "主从盯盘(RKLB 信号源 → RKLZ/RKLX 交易)",
            "7 大触发器: 波段顶/底/回撤/浮盈/异动等",
            "智能 A/B/C 推送样式",
            "盘中 1 秒/次,盘外 5 秒/次",
            "A 方案 4 按钮反馈闭环: ✅已操作 ❌忽略 🔄重询 📊记录",
            "分组 /help + /help XXX 详情(18 条指令)",
            "关闭老 check_alerts (LEGACY_ALERTS_ENABLED 开关)",
            "去除所有 ───── 分隔线",
        ]
    },
    {
        "version": "0.2.3",
        "date": "2026-04-21",
        "title": "多币种账户修复",
        "changes": [
            "账户资金 HKD 聚合 bug 修复,多币种正确显示",
        ]
    },
    {
        "version": "0.2.2",
        "date": "2026-04-20",
        "title": "核心实时报价引擎",
        "changes": [
            "新增 core/realtime_quote 持仓/账户实时查询能力",
            "/signal 查询前同时刷新持仓,watchlist 外持仓也显示",
            "新持仓自动加入 watchlist,持久化到 watchlist.json",
            "signal_engine 每轮自动合并 watchlist ∪ 持仓,确保全量分析",
            "fmt_signal 兼容'仅持仓'票(无指标时显示简版)",
        ]
    },
    {
        "version": "0.2.1",
        "date": "2026-04-20",
        "title": "交互优化 + 盈亏警报 AI 建议",
        "changes": [
            "信号格式：每只股票加序号，级别说明只在开头显示一次",
            "信号标题改为：股票N  TICKER (名称)  建议【信号】 级别:X 信心:X%",
            "HOLD 持有时不显示操作建议块，BUY/SELL 显示手数+金额",
            "手续费明细：基于富途AU对账单实测（买$1.29/卖$1.31），显示往返参考",
            "技术指标加中文名：RSI相对强弱 / MACD柱状 / 量比 / 均线趋势",
            "止损/目标价加涨跌幅百分比和ATR依据说明",
            "仓位始终显示（无持仓显示0股$0.00，有持仓显示市值+盈亏）",
            "signal 信号每只单独推送并附带详细分析按钮（可点击）",
            "按钮点击加60秒冷却防重复，点击后立即回复确认消息",
            "盈亏警报区分：盈利X级提醒 / 亏损X级警告（不同标题+emoji）",
            "亏损警报加 ⚠️ 请立即处理！，止损警报附带持仓市值和盈亏",
            "警报触发后异步调用 Claude AI 给出具体操作建议",
            "AI 建议格式：操作/理由/风险",
            "AI算力成本统一显示在所有 AI 输出底部",
            "对账单 PDF 自动解析入库（Bot 直接接收 PDF）",
            "早9点推送顺带检查昨日对账单缺口并提醒上传",
            "/pnl 指令：从对账单计算历史盈亏汇总",
            "logo 改为简洁无框版，修复 Telegram 中文字体对齐问题",
            "修复指令出错时异常被静默吞掉的问题",
        ]
    },
    {
        "version": "0.2.0",
        "date": "2026-04-20",
        "title": "Claude AI 分析接入",
        "changes": [
            "/detail 升级：自动触发 Claude AI 深度分析（标准分析型，200-300字）",
            "AI 分析包含：综合判断 / 关键价位 / 操作建议 / 风险提示",
            "费用透明：调用前预估费用，调用后显示实际 token 消耗",
            "/usage 指令：查看本月 Claude API 累计费用",
            "无 API Key 时静默降级，/detail 仍正常推送技术面",
            "修复 bot_controller.py 中 t() 函数与变量名冲突的所有 bug",
        ]
    },
    {
        "version": "0.1.0",
        "date": "2026-04-19",
        "title": "首次发布",
        "changes": [
            "Moomoo AU LV3 实时行情接入(TSLA / SOXL / RKLB / RKLX)",
            "技术指标: RSI / MACD / 布林带 / MA / ATR / 量比",
            "K线形态识别: 锤子/流星/吞没/十字星",
            "止损价 / 目标价自动计算(基于 ATR)",
            "Telegram 群推送 + 多指令交互",
            "账户数据采集: 资产 / 持仓 / 历史订单 / PDT计数",
            "本地 Web Dashboard (Flask localhost:5000)",
            "动态 Watchlist,一键启动 MagicYang.bat",
        ]
    },
]


def get_version_string():
    return f"{APP_NAME_CN} {APP_NAME_EN} v{VERSION}"


def get_changelog_text(latest_only=True):
    logs = CHANGELOG[:1] if latest_only else CHANGELOG
    lines = []
    for log in logs:
        lines.append(f"{'='*40}")
        lines.append(f"慧投 MagicQuant v{log['version']} | {log['date']}")
        lines.append(f"更新内容 | Release Notes: {log['title']}")
        lines.append(f"{'='*40}")
        for i, change in enumerate(log['changes'], 1):
            lines.append(f"  {i:02d}. {change}")
        lines.append(f"")
        lines.append(f"作者 Owner: {OWNER_NAME} <{OWNER_EMAIL}>")
    lines.append(f"口号 Slogan: Dare to dream. Data to win.")
    return "\n".join(lines)


def get_logo():
    return (
        f"慧投 MagicQuant v{VERSION}\n"
        f"{'─'*28}\n"
        f"智慧投资，数据驱动\n"
        f"Dare to dream. Data to win.\n"
        f"梦想终究是要有的，万一实现了呢？\n"
        f"{'─'*28}\n"
        f"版本: v{VERSION}  日期: {BUILD_DATE}\n"
        f"作者: {OWNER_NAME}\n"
        f"邮箱: {OWNER_EMAIL}"
    )


if __name__ == "__main__":
    print(get_logo())
    print(get_changelog_text(latest_only=False))
