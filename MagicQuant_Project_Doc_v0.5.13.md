# MagicQuant 慧投 — Project Documentation v0.5.13

**智慧投资,数据驱动**

> 2026-04-22 | Owner: Zhen Yang | happy.yz@gmail.com
> *"Dare to dream. Data to win. 梦想终究是要有的,万一实现了呢?"*

---

## 1. 项目背景

MagicQuant(慧投)是一个基于 Futu/Moomoo OpenAPI 的个人量化交易助手系统,通过 Telegram Bot 推送实时信号并接收操作指令,**24 小时全时段盯盘**,重点服务于 **RKLB / RKLX / RKLZ 三联波段 T+0 策略**。

用户老杨(Zhen Yang)位于澳大利亚墨尔本,通过 Moomoo AU 账户交易美股。

### 账户概况 (2026-04-22 更新)

| 项目 | 详情 |
|---|---|
| 券商 | Moomoo AU(澳大利亚,多币种综合账户 6018) |
| **USD 现金(可用)** | **$3,537.93** (美股交易真正能用的钱) |
| **USD 购买力** | **$3,537.93** (现金账户,无融资) |
| **USD 资产(美股市值+现金)** | **$7,933.52** |
| 跨币种总资产(HKD 聚合) | ~62,086 HKD ≈ AUD $11,078 ≈ USD $7,934 |
| 其中 AUD 现金 | $0.00 |
| 其中 HKD 现金 | $0.00 |
| **PDT 状态** | **受限** ⚠️ (USD < $25k,每 5 日最多 3 次日内交易) |
| 主策略 | RKLB 波段做 T,用 RKLX/RKLZ 二倍 ETF 执行 |
| FutuOpenD | 127.0.0.1:11111(本地) |

> **2026-04-22 诊断教训**: Moomoo APP "综合账户" 默认显示的 HKD 聚合值
> ($27,704 HKD cash / $62,086 HKD total)不是美元现金。美股交易必须看
> "现金明细 · USD" 那一行 ($3,537.93),也是 `accinfo_query` 的 `us_cash` 字段。
> 详见 `realtime_quote.py` v0.5.3 的 HKD 聚合 bug 修复记录。

### 当前持仓 (2026-04-22)

| 标的 | 数量 | 成本价 | 现价 | 浮盈 | 说明 |
|---|---|---|---|---|---|
| **TSLL** | 251 | $22.275 | $13.06 | **-$2,312.94 (-41.37%)** | 套牢仓,Tesla 2x 多 ETF |
| **RKLZ** | 100 | $11.43 | $11.10 | -$33.00 (-2.89%) | 2 倍做空 RKLB 的 ETF |

---

## 2. 技术栈

| 组件 | 版本/说明 |
|---|---|
| Python | 3.13,Windows PC `C:\MagicQuant\` |
| Futu OpenAPI | `moomoo-api`,本地 FutuOpenD 进程 |
| Telegram Bot | urllib 轮询,主要交互界面 |
| Flask Dashboard | localhost:5000,本地 Web 面板 |
| Claude API | claude-sonnet-4-20250514,`/detail` AI 分析 |
| OpenAI API | 可选,外部 Agent 使用 |

---

## 3. 文件结构 (v0.5.13)

```
C:\MagicQuant\
├── bot\
│   └── bot_controller.py                # v0.5.11 Telegram Bot 主控
├── core\
│   ├── realtime_quote.py                # v0.5.3 Futu 行情+账户+持仓(USD 修复)
│   └── focus\
│       ├── __init__.py                  # 模块导出
│       ├── context.py                   # v0.5.2 FocusSession 状态容器
│       ├── focus_manager.py             # v0.5.9 盯盘主循环(+ ai_test 修复)
│       ├── pusher.py                    # v0.5.11 智能推送格式化
│       ├── swing_detector.py            # v0.5.4 7 大触发器
│       ├── market_clock.py              # v0.2.0 市场时段识别(含夜盘)
│       ├── event_calendar.py            # v0.1.0 巫日/月度 Opex 日历 🆕
│       ├── activity_profile.py          # v0.1.0 机会密度画像 🆕
│       ├── proactive_reminder.py        # v0.1.0 主动提醒系统 🆕
│       ├── micro_indicators.py          # 5M K 线指标
│       ├── pairs.py                     # 标的配对
│       └── feedback.py                  # 反馈收集
├── config\
│   └── settings.py                      # 全局配置
├── data\
│   ├── signals_latest.json              # 最新信号数据
│   └── account_data.json                # 账户/持仓快照
├── version.py                           # 版本管理
├── i18n.py                              # 国际化(zh/en)
└── MagicYang.bat                        # 一键启动脚本
```

---

## 4. 版本历史 (当前 v0.5.13)

| 版本 | 日期 | 核心改动 |
|---|---|---|
| **v0.5.13** | **2026-04-22** | **🐛 修复关键 bug:HKD 聚合导致现金显示错误 + ai_test session 错误** |
| v0.5.12 | 2026-04-22 | A+B+C+D 机会密度系统:动态频率/阈值/主动提醒/巫日识别 |
| v0.5.11 | 2026-04-22 | `/profile` 指令 + `/status` 升级显示 profile |
| v0.5.10 | 2026-04-22 | 夜盘自动启动 Focus,24h 盯盘闭环 |
| v0.5.9 | 2026-04-22 | 开盘自动启动 Focus;加仓门槛修复 $500 |
| v0.5.8 | 2026-04-22 | 推送加手动指令备用行;`/order TICKER` 指令 |
| v0.5.7 | 2026-04-22 | 仓位冲突 ABCD 四场景;反向持仓两步操作链 |
| v0.5.6 | 2026-04-22 | 合并 RKLB/RKLX/RKLZ 三联推送 |
| v0.5.5 | 2026-04-22 | market_clock 集成;休市静默/开盘恢复 |
| v0.5.4 | 2026-04-22 | 真实可用现金从 Futu 查;双时间戳心跳 |
| v0.5.3 | 2026-04-22 | 冷却 key 立刻锁定;全局互斥 60s |
| v0.5.2 | 2026-04-22 | `NoneType.__format__` 全面修复 |
| v0.5.0 | 2026-04-22 | Focus 系统重写:固定美金目标制 |
| v0.4.0 | 2026-04-21 | Risk Engine 28 条规则 |
| v0.2.1 | 2026-04-20 | Claude AI `/detail` 接入 |
| v0.1.0 | 2026-04-19 | 首次发布 |

---

## 5. 🆕 机会密度系统 (v0.5.12+ 核心升级)

基于真实市场研究数据,把一天切成不同"机会密度"时段,**动态调整盯盘频率、触发器灵敏度、主动推送提醒**。

### 5.1 机会密度等级

| 等级 | 轮询 | 阈值系数 | 含义 |
|---|---|---|---|
| 🔥🔥 **PEAK+** | 0.5s | ×0.60 | 巫时刻 / 周一开盘第一小时 |
| 🔥 **PEAK** | 1.0s | ×0.75 | RTH 开盘第一小时 / 收盘最后一小时 |
| 🟢 **HIGH** | 2.0s | ×0.90 | 盘前 08:00+ / 盘后 16:00-17:00 / RTH 第二小时 |
| ⚪ **MEDIUM** | 3.0s | ×1.00 | RTH 普通时段(基准) |
| 🔵 **LOW** | 10.0s | ×1.30 | 盘前 04:00-08:00 / 盘后 17:00-20:00 / RTH 午间 |
| 🌃 **MINIMAL** | 30.0s | ×1.80 | 夜盘(流动性差,过滤假信号) |
| 🌙 **CLOSED** | 60.0s | — | 真休市(周末/节假日/空档) |

### 5.2 时段 → 等级 映射 (ET 美东时间)

| 时段 | 墨尔本 | 等级 | 根据 |
|---|---|---|---|
| **09:30-10:30** | 23:30-00:30 | 🔥 PEAK | S&P 500 学术研究:第 1 小时波动最高 |
| **15:00-16:00** | 05:00-06:00 | 🔥 PEAK | DOW 下午波动 0.38-0.43%,机构调仓 |
| 10:30-11:30 | 00:30-01:30 | 🟢 HIGH | 第 1 midday session,次活跃 |
| 14:00-15:00 | 04:00-05:00 | 🟢 HIGH | 收盘前第二小时 |
| 11:30-14:00 | 01:30-04:00 | 🔵 LOW | 午间低迷(高脚杯形态) |
| 08:00-09:30 | 22:00-23:30 | 🟢 HIGH | 盘前活跃时段 |
| 16:00-17:00 | 06:00-07:00 | 🟢 HIGH | 盘后第 1 小时(财报集中) |
| 04:00-08:00 | 18:00-22:00 | 🔵 LOW | 盘前早时段,流动性低 |
| 17:00-20:00 | 07:00-10:00 | 🔵 LOW | 盘后中后段 |
| 20:00-03:50 | 10:00-17:50 | 🌃 MINIMAL | 夜盘 |
| 周一 09:30-10:30 | 周二 23:30-00:30 | 🔥🔥 PEAK+ | 周末消息集中释放 |

### 5.3 事件日自动升级

| 事件 | 2026 日期 | 等级影响 |
|---|---|---|
| 🧙 **三重巫日全天** | 3/20, **6/18**, 9/18, 12/18 | 全天升 1 级(最高到 PEAK) |
| 🧙🧙 **巫时刻** (15:00-16:00) | 同上,最后 1 小时 | 直升 PEAK+ (0.5s / ×0.60) |
| 📆 **月度期权到期** | 每月第 3 周五 | 巫时刻升到 PEAK,其他时段不动 |
| 📅 **周度期权到期** | 每周五 | 标签提示,不升级 |

> **特殊**: 2026-06-19 原本是 Q2 巫日,但撞上 Juneteenth 休市,巫日提前到 **6-18 周四**(NYSE 官方日历)。

### 5.4 触发器阈值缩放 (swing_detector v0.5.4 字段)

**缩放的字段**(所有百分比类阈值和冷却时间):
- `profit_target_pct` / `profit_target_usd` — 浮盈达标
- `drawdown_pct` — 回撤告警
- `rapid_move_pct` — 快速异动
- `trend_day_change_pct` — 方向趋势
- `near_high_pct_*` / `near_low_pct_*` — 波段顶底距离
- `swing_cooldown_*` / `rapid_move_cooldown` / `trend_cooldown_sec` / `global_mutex_sec`

**不缩放的字段**(数学或业务语义固定):
- RSI 所有阈值:`rsi_overbought_*`, `rsi_oversold_*`, `trend_rsi_*` (50-70 有数学意义)
- 时间窗:`rapid_move_window` (120 秒)
- 量比:`breakout_vol_ratio` (1.5x)

### 5.5 主动提醒 (5 个提醒点)

每个提醒每 ET 日只推一次,session 级去重:

| 提醒 | ET 时间 | 墨尔本 | 触发条件 |
|---|---|---|---|
| 🟢 RTH 开盘前 15 分钟 | 09:15 | 23:15 | 每个交易日 |
| 🟠 RTH 收盘前 30 分钟 | 15:30 | 次日 05:30 | 每个交易日 |
| ⚡ 周一开盘前 45 分钟 | 08:45 | 22:45 | 仅周一(多给 15 分钟消化周末新闻) |
| 🧙 巫日开盘前 45 分钟 | 08:45 | 22:45 | 仅三重巫日 |
| 🧙🧙 巫时刻前 15 分钟 | 14:45 | 04:45 | 仅三重巫日 |

---

## 6. 市场状态 (market_clock v0.2.0)

| 状态 | 时段 (ET) | 轮询频率 | 默认行为 |
|---|---|---|---|
| 🟢 盘中 | 09:30-16:00 | profile 决定(PEAK 1s / HIGH 2s / MEDIUM 3s / LOW 10s) | 完整盯盘 |
| 🟡 盘前 | 04:00-09:30 | profile 决定(HIGH 2s / LOW 10s) | 完整盯盘 |
| 🟠 盘后 | 16:00-20:00 | profile 决定(HIGH 2s / LOW 10s) | 完整盯盘 |
| 🌃 **夜盘** | **20:00-03:50** | **30s** | **完整盯盘**(v0.5.10 新增) |
| ⚪ 空档 | 03:50-04:00 | 60s | 静默(夜盘结算窗) |
| 🌙 休市 | 其他 | 60s | 手动 `/focus` 不受静默影响 |

2026+2027 年美股节假日已内置。

---

## 7. 推送格式 (pusher v0.5.11)

每条推送抬头新增 **profile tag**(机会密度 + 事件 + 周一加速):

```
📡 23:14:22  ·  📈 23:14:20  ·  🔥黄金 🧙 ⚡周一
━━━━━━━━━━━━━━
RKLB $87.35 (-2.36%)
RKLX $45.15 (-4.70%)
RKLZ $11.55 (+4.65%) · 100股 +$28
RSI 42.1 · VWAP $87.45 · 量比 1.15x

[两步操作链 / ABCD 场景建议]

💬 手动:  /order RKLZ · /detail RKLB
⚙️ swing v0.5.4 · pusher v0.5.11 · 轮询 1.0s · 阈值×0.75
```

---

## 8. Telegram 指令

### 核心盯盘
| 指令 | 功能 |
|---|---|
| `/focus [TICKER]` | 启动盯盘(默认 RKLB);手动不受休市静默 |
| `/unfocus` | 停止盯盘 |
| `/status` | 状态 + 市场 + profile + 事件 |
| **`/profile [hours]`** | **🆕 机会密度画像 + 未来时间线(默认 12h)** |
| `/order TICKER` | 显示最近该 ETF 的交易计划 |
| `/modules` | 查看所有模块版本 + 当前 profile |

### 行情信号
| 指令 | 功能 |
|---|---|
| `/signal [TICKER]` | 查看信号 |
| `/detail TICKER` | Claude AI 深度分析(~$0.02/次) |
| `/ask TICKER 问题` | 自定义问 AI |

### 账户持仓
| 指令 | 功能 |
|---|---|
| `/account` | 账户现金 |
| `/positions` | 实时持仓 |
| `/history` | 历史 |
| `/pdt` | PDT 使用(USD $3.5k < $25k,每 5 日最多 3 次日内交易) |
| `/usage` | AI 调用累计费用 |
| `/pnl` | 盈亏统计 |

### Watchlist
| 指令 | 功能 |
|---|---|
| `/list` | 查看跟踪列表 |
| `/add TICKER` | 加入 Watchlist |
| `/remove TICKER` | 移除 |

### 心跳与其他
| 指令 | 功能 |
|---|---|
| `/heartbeat` | 立即推心跳 |
| `/heartbeat_on N` | 每 N 分钟定时心跳 |
| `/help` | 全部指令 |

---

## 9. 标的配对 (pairs.py)

| 主标 | 做多工具 | 做空工具 | 说明 |
|---|---|---|---|
| **US.RKLB** (Rocket Lab) | **US.RKLX** (2x 多) | **US.RKLZ** (2x 空) | 核心交易对,日内 T+0 策略 |
| US.TSLA | — | — | Watch only,不做 T |
| US.TSLL | — | — | 套牢仓 251 股 @$22.27(-41%),不操作 |

RKLX/RKLZ 不作为信号源,只用于执行。信号仅由 RKLB 触发,ETF 价格合并显示在推送里。

---

## 10. Moomoo AU 费率 (基于对账单实测)

| 方向 | Platform | Settlement | SEC/TAF | 总计(100 股参考) |
|---|---|---|---|---|
| 买入 | $0.99 | $0.30 | — | **固定 $1.29** |
| 卖出 | $0.99 | $0.30 | SEC: 成交额 × 0.0000278<br>TAF: 股数 × $0.000166 | 约 $1.35 ($11 股价 100 股) |
| **往返** | — | — | — | **约 $2.64** |

---

## 11. 开发原则

| 原则 | 说明 |
|---|---|
| 改动最小化 | 补丁式修改,不重写现有功能;每次只改必要的文件 |
| 版本头必须 | 每个文件头写 VERSION / DATE / CHANGES / DEPENDS |
| DEPENDS 字段 | 明确列出依赖哪些文件的最低版本 |
| 中文优先 | 界面、注释中文为主;代码变量英文 |
| 费用可控 | Claude API 只在手动触发时调用;外部 Agent 一律手动 |
| i18n 注意 | `t()` 函数不能和循环变量重名,循环变量统一用 `tk` |
| 路径管理 | 用 `BASE_DIR` 统一管理,不写死路径 |
| Token 安全 | 密钥在 `.env` 文件,不进 Git |

---

## 12. 已知问题 + 待办

| 优先级 | 事项 | 状态 |
|---|---|---|
| ~~**高**~~ | ~~account 货币聚合问题(HKD/USD)~~ | **✅ v0.5.13 已修复** — realtime_quote v0.5.3 优先用 us_cash 字段 |
| 高 | HTML Dashboard 价格不实时 | 待修:focus 实时价需回写 signals_latest.json |
| 中 | backtest.py 阈值回测工具 | 计划:拉 3 个月 5M K 线测各阈值组合胜率 |
| 中 | Risk Engine 规则维持 $20k 档 | USD 实际现金仅 $3.5k,远低于原设定 |
| 低 | TSLL 套牢仓处理 | 用户决策,系统不主动建议 |
| 低 | 多账户支持(丈人的 RKLX) | 两个账户独立,暂不整合 |
| 低 | Project Doc 自动化更新 | 改文件 + 改文档 两步合一 |

---

## 13. 数据流图 (v0.5.13)

```
Moomoo APP (你看到的)
      ↓
FutuOpenD (本地 127.0.0.1:11111)
      ↓ (QuoteContext)  ↓ (TradeContext)
realtime_quote v0.5.3
  ├── fetch_one() ────── 夜盘价识别 (overnight_price/pre_price/after_price)
  ├── fetch_positions() ─ nominal_price / pl_ratio / can_sell_qty
  └── fetch_account() ─── us_cash (真实USD) / raw_hkd_cash (聚合参考)
      ↓
focus_manager v0.5.9
  ├── _indicators_cache_global  ← 供 /ai_test 跨模块读取
  ├── get_current_profile() ← activity_profile v0.1.0
  │                        ↙ ↓ ↘
  │     market_clock v0.2.0  event_calendar v0.1.0  proactive_reminder v0.1.0
  │       │                     │                        │
  │       五种时段               🧙 巫日                   5 个提醒点
  │   + overnight                📆 月度Opex              每日去重
  │                              📅 周度Opex
  │
  ├── scale_params(DEFAULT_PARAMS, profile.scale)
  ├── run_all_triggers(..., params=scaled_params)  ← swing_detector v0.5.4
  ├── check_and_fire_reminders(session, send_tg)
  └── interval = profile.poll_sec (0.5s-30s)
      ↓
pusher v0.5.11
  └── 推送抬头带 🔥黄金 / 🧙 / ⚡周一 标签
      ↓
bot_controller v0.5.11 → Telegram
  └── /focus /unfocus /status /profile /modules /order 等
```

---

## 14. 新对话初始化提示

在新的 Claude 对话中,可作为第一条消息发送:

```
# MagicQuant 项目接手
基于最新项目文档 v0.5.13:

bot_controller v0.5.11 | focus_manager v0.5.9
pusher v0.5.11 | swing_detector v0.5.4
market_clock v0.2.0 | event_calendar v0.1.0
activity_profile v0.1.0 | proactive_reminder v0.1.0
realtime_quote v0.5.3 | context v0.5.2

账户: 墨尔本 Moomoo AU 综合账户 · USD Cash $3,537.93 (PDT 受限 <$25k)
主策略: RKLB 波段 T,用 RKLX(多)/RKLZ(空) 执行
套牢仓: TSLL 251股 @$22.27 -41% (不操作)
当前仓: RKLZ 100股 @$11.43 -2.89%

开发原则:
- 改动最小化,补丁式修改
- 每个文件头写 VERSION/DATE/CHANGES/DEPENDS
- 中文优先,直接给代码
- i18n t() 不能和循环变量重名,循环变量用 tk
```

---

*End of v0.5.13 Documentation*
