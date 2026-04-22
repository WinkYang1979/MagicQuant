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

VERSION     = "0.5.7"
BUILD_DATE  = "2026-04-22"

OWNER_NAME  = "Zhen Yang"
OWNER_EMAIL = "happy.yz@gmail.com"

CHANGELOG = [
    {
        "version": "0.5.7",
        "date": "2026-04-22",
        "title": "仓位冲突检测 + 推送精简",
        "changes": [
            "Focus 推送合并 RKLB/RKLX/RKLZ 三联显示(不再分别刷屏)",
            "推送顶部加双时间戳(📡 推送时间 · 📈 行情时间)",
            "所有推送底部带模块版本号,方便排查",
            "仓位冲突检测 ABCD 四种场景:空仓/反向/顺势/双向分别给出不同建议",
            "反向持仓时强制分两步:先卖反向 → 再买顺势",
            "顺势持仓时给 A+B 并列(持有 vs 加仓),用户自己判断",
            "双向持仓 🚨 红警,强制先清理冲突",
            "交易计划按 Futu 真实可用现金动态算仓位,不再凭空假 $20k",
            "可用资金 < $2000 时不推买入,提示释放套牢资金",
            "按钮失效时支持手动指令:/order TICKER · /detail TICKER",
            "全局互斥按级别分档:URGENT 5min / WARN 10min / INFO 5min",
            "推送频率彻底压低:direction 20min / rapid 10min / swing WEAK 15min",
            "心跳间隔 5min → 10min,内容加可用现金+运行时长+近触发诊断",
        ]
    },
    {
        "version": "0.5.0",
        "date": "2026-04-22",
        "title": "Focus v0.5 重写 — 主动推送操作建议",
        "changes": [
            "信号推送改为固定美金目标制 (STRONG $100/$50 · WEAK $50/$30)",
            "STRONG 信号七成仓 · WEAK 信号半仓,按信号强度自动选",
            "触发器放宽:方向信号日内 ±0.8% / RSI 58/48 / 急动 0.4%",
            "K 线指标未就绪时方向信号仍能跑 (只看日内累计涨跌幅)",
            "空仓也推完整交易计划:入场/目标/止损/股数/RR",
            "新增按钮:📋 复制下单 / 🧠 AI 看看 / ⏳ 忽略",
            "pusher 与 swing_detector 独立版本号,方便模块化升级",
        ]
    },
    {
        "version": "0.4.0",
        "date": "2026-04-21",
        "title": "Risk Engine + Focus 按钮反馈体系",
        "changes": [
            "v0.4 Risk Engine:PDT/现金/集中度/超冷规则,/risk_test 验证",
            "Focus 按钮反馈:fb_done / fb_skip / fb_repx / fb_ai 四件套",
            "触发验证:下单后自动检查持仓变化,不再靠用户报备",
        ]
    },
    {
        "version": "0.2.1",
        "date": "2026-04-20",
        "title": "交互优化 + 盈亏警报 AI 建议",
        "changes": [
            "信号格式:每只股票加序号,级别说明只在开头显示一次",
            "HOLD 持有时不显示操作建议块,BUY/SELL 显示手数+金额",
            "手续费明细:基于富途AU对账单实测",
            "盈亏警报区分:盈利提醒 / 亏损警告",
            "对账单 PDF 自动解析入库",
        ]
    },
    {
        "version": "0.2.0",
        "date": "2026-04-20",
        "title": "Claude AI 分析接入",
        "changes": [
            "/detail 升级:自动触发 Claude AI 深度分析",
            "费用透明:调用前预估,调用后显示实际消耗",
            "/usage 本月 API 累计费用",
        ]
    },
    {
        "version": "0.1.0",
        "date": "2026-04-19",
        "title": "首次发布",
        "changes": [
            "Moomoo AU LV3 实时行情 + 技术指标 + K 线形态",
            "止损 / 目标价 / 建议手数自动计算",
            "Telegram 指令 + 定时推送 + 一键启动",
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
