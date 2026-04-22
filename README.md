# MagicQuant 慧投

> 智慧投资,数据驱动 · *Dare to dream. Data to win.*

个人量化交易助手,基于 Futu / Moomoo OpenAPI + Telegram Bot,为**美股波段 T+0 策略**提供 24 小时盯盘 + 智能信号推送。

**当前版本**: v0.5.13 (2026-04-22)

---

## 🎯 核心功能

- **24 小时盯盘** — 覆盖盘中 / 盘前 / 盘后 / 夜盘,自动切换轮询频率
- **机会密度系统** — 根据时段 + 事件日动态调整触发器灵敏度(PEAK+ 0.5s / MINIMAL 30s 七档)
- **7 大触发器** — 浮盈达标 / 回撤告警 / 波段顶底 / 方向趋势 / 快速异动 / 全局互斥
- **巫日识别** — 三重巫日 / 月度期权到期自动升档
- **主动提醒** — RTH 开盘前 15min / 收盘前 30min / 周一加速 / 巫时刻提前预警
- **Claude AI 分析** — `/detail` 指令召集 AI 做深度分析
- **Telegram 交互** — 全部操作在 Telegram Bot 上完成

---

## 🏗️ 技术栈

- Python 3.13 (Windows)
- [moomoo-api](https://openapi.moomoo.com/) · 本地 FutuOpenD 进程
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Claude API](https://www.anthropic.com/api) · `/detail` AI 分析
- Flask · localhost:5000 Web Dashboard

---

## 📂 项目结构

```
MagicQuant/
├── bot/
│   └── bot_controller.py         # Telegram Bot 主控
├── core/
│   ├── realtime_quote.py         # Futu 行情 + 账户 + 持仓封装
│   ├── signal_engine.py          # 技术指标 + 信号生成
│   └── focus/                    # 盯盘核心模块
│       ├── focus_manager.py      # 主循环
│       ├── swing_detector.py     # 7 大触发器
│       ├── pusher.py             # 推送格式化
│       ├── market_clock.py       # 市场时段识别(含夜盘)
│       ├── event_calendar.py     # 三重巫日 / 月度 Opex 日历
│       ├── activity_profile.py   # 机会密度画像
│       ├── proactive_reminder.py # 主动提醒系统
│       └── micro_indicators.py   # 5M K 线指标
├── config/
│   ├── settings.py               # 全局配置
│   └── watchlist.json            # 跟踪标的
├── data/                         # 运行时数据(gitignore)
└── MagicYang.bat                 # 一键启动
```

---

## 🎯 当前策略

**核心交易对**: RKLB (Rocket Lab) 波段做 T

| 角色 | 标的 | 说明 |
|---|---|---|
| 主信号源 | US.RKLB | 所有信号由 RKLB 触发 |
| 做多工具 | US.RKLX | 2 倍多 RKLB 的 ETF |
| 做空工具 | US.RKLZ | 2 倍空 RKLB 的 ETF |

---

## 🧠 机会密度系统(v0.5.12+ 核心升级)

根据市场时段 + 事件日动态调整 7 个等级:

| 等级 | 轮询 | 阈值系数 | 典型时段 |
|---|---|---|---|
| 🔥🔥 PEAK+ | 0.5s | ×0.60 | 巫时刻 / 周一开盘第一小时 |
| 🔥 PEAK | 1.0s | ×0.75 | RTH 开盘第一小时 / 收盘前一小时 |
| 🟢 HIGH | 2.0s | ×0.90 | 盘前 08:00+ / 盘后 16:00-17:00 |
| ⚪ MEDIUM | 3.0s | ×1.00 | RTH 普通时段(基准) |
| 🔵 LOW | 10.0s | ×1.30 | 盘前早段 / 盘后中后段 / RTH 午间 |
| 🌃 MINIMAL | 30.0s | ×1.80 | 夜盘(流动性差,过滤假信号) |
| 🌙 CLOSED | 60.0s | — | 真休市 |

---

## 🤖 Telegram 指令速查

### 核心盯盘
```
/focus [TICKER]      启动盯盘(默认 RKLB)
/unfocus             停止盯盘
/status              查看盯盘状态
/profile [hours]     机会密度画像 + 未来时间线
/order TICKER        最近该 ETF 的交易计划
/modules             所有模块版本
```

### 行情分析
```
/signal [TICKER]     信号概览
/detail TICKER       Claude AI 深度分析
/ask TICKER 问题     自定义问 AI
```

### 账户持仓
```
/account             美元现金 / 购买力
/positions           当前持仓
/pnl                 盈亏统计
/pdt                 PDT 日内交易次数
```

---

## 🚀 部署说明

> ⚠️ 本项目是个人学习用途,不承担任何投资决策责任

### 前置要求
- Windows PC
- Python 3.13
- Moomoo AU 账户 + FutuOpenD 客户端
- Telegram Bot Token
- (可选)Anthropic Claude API Key

### 环境变量
在项目根目录创建一个叫 `env` 的文件(**不要 commit 到 git**),格式:
```
TELEGRAM_BOT_TOKEN=xxxx
TELEGRAM_CHAT_ID=xxxx
ANTHROPIC_API_KEY=xxxx
OPENAI_API_KEY=xxxx
FUTU_HOST=127.0.0.1
FUTU_PORT=11111
```

### 启动
```bash
# 1. 启动 FutuOpenD
# 2. 双击 MagicYang.bat
```

---

## 📖 文档

完整项目文档见 [`MagicQuant_Project_Doc_v0.5.13.md`](./MagicQuant_Project_Doc_v0.5.13.md),包含:
- 账户配置
- 机会密度系统详解
- 事件日历(2026/2027 巫日日期)
- 数据流图
- 开发原则与协作守则

---

## 🔧 开发原则

1. **改动最小化** — 补丁式修改,不轻易重写现有功能
2. **版本必记** — 每个文件头有 `VERSION / DATE / CHANGES / DEPENDS`
3. **费用可控** — Claude API 只手动触发,外部 Agent 一律手动
4. **中文优先** — 界面 / 注释中文,代码变量英文
5. **一次对话一件事** — 避免 AI context 爆炸

---

## ⚠️ 免责声明

本项目为**个人学习与研究用途**,所有信号 / 建议均不构成投资建议。作者不对任何交易结果负责。使用前请确保理解代码逻辑并自行承担风险。

---

## 📝 License

Personal Use Only · © 2026 Zhen Yang
