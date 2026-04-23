# MagicQuant — 当前线上状态快照

> **最后更新**: 2026-04-23 晚 (复盘日志系统上线)
> **维护原则**: 每次改完代码立即更新本文件(AI 自动生成,无需用户手改)。
> **这是新对话 AI 理解项目的第一手资料**,比完整项目文档更实时,比读代码更便宜。

---

## 🎯 生产版本清单(已部署,正在跑)

| 文件 | 路径 | 版本 |
|---|---|---|
| realtime_quote.py | core/ | v0.5.4 |
| **focus_manager.py** | core/focus/ | **v0.5.10** 🆕 |
| **pusher.py** | core/focus/ | **v0.5.13** 🆕 |
| swing_detector.py | core/focus/ | v0.5.4 |
| market_clock.py | core/focus/ | v0.2.0 |
| event_calendar.py | core/focus/ | v0.1.0 |
| activity_profile.py | core/focus/ | v0.1.0 |
| proactive_reminder.py | core/focus/ | v0.1.0 |
| context.py | core/focus/ | v0.5.2 |
| pairs.py | core/focus/ | 无版本号 |
| **bot_controller.py** | bot/ | **v0.5.13** 🆕 |

**GitHub**: https://github.com/WinkYang1979/MagicQuant

---

## 💰 账户真实状态(2026-04-23)

| 项 | 值 |
|---|---|
| **USD 可用现金** | **$3,537.93** (美股交易能用的钱) |
| **USD 购买力** | **$3,537.93** (现金账户,无融资) |
| **USD 美股总资产** | **$7,933.52** |
| **PDT 状态** | **受限** ⚠️ (USD < $25k,每 5 日最多 3 次日内交易) |
| 券商 | Moomoo AU 综合账户 6018 |
| 主币种 | HKD (多币种综合账户) |

### ⚠️ 重要区分(HKD 聚合 vs USD)

`accinfo_query` 默认返回 **HKD 聚合值**:
- HKD cash ~27,704 (≈ USD $3,538,**这是同一笔钱的不同币种显示**)
- HKD total_assets ~62,086 (≈ USD $7,934,**这是所有持仓+现金的折算**)

**编写代码处理账户数据时**: 优先用 `us_cash` / `usd_assets` 等 USD 字段,**不要用 `cash` / `total_assets`**(那是 HKD 聚合)。

---

## 📊 当前持仓(2026-04-23)

| 标的 | 数量 | 成本价 | 现价 | 浮盈 | 说明 |
|---|---|---|---|---|---|
| TSLL | 251 | $22.275 | ~$13 | **-$2,313 (-41%)** | 套牢仓,Tesla 2x 多 ETF。**不操作** |
| RKLZ | 300 | $11.08 | ~$10.98 | -$29 | 2 倍空 RKLB,做 T 对冲 |

*昨晚复盘:听系统建议割 RKLZ,但后续反弹。复盘结论待明天日志到位后产出。*

---

## 🎯 交易策略 / 标的池

### 核心交易对
- **主信号源**: US.RKLB (Rocket Lab)
- **做多工具**: US.RKLX (2x 多 RKLB ETF)
- **做空工具**: US.RKLZ (2x 空 RKLB ETF)

### 其他跟踪
- US.TSLA / US.TSLL (有套牢仓,仅观察)

### 风控参数
- **单笔最大仓位**: 40% (v0.5.13 写入 AI prompt 硬约束)
- **最低保留现金**: 10% 应对滑点
- **止损原则**: ATR 的 1.5x (swing 风格) 或 1.0x (daytrader 风格)

---

## ✅ 已修复 bug 清单

### 2026-04-23 修复(P0 全清)

| # | Bug | 修复版本 |
|---|---|---|
| #1 | 推送信号遮蔽 / Step 2 缺失 (RKLB 看多+持 RKLZ 时只推平仓) | pusher v0.5.12 |
| #2 | 持仓浮盈/浮亏显示不含手续费 | pusher v0.5.12 |
| #3 | PEAK 时段 /detail 失灵 (Snapshot failed) | bot v0.5.13 |
| #4 | AI 凭空编造仓位金额 (建议 69 股 $6,210,用户只有 $3,537) | bot v0.5.13 |

### 2026-04-23 晚 基础设施

| # | 改进 | 实现版本 |
|---|---|---|
| 日志 | 每条推送自动写 `data/review/YYYY-MM-DD/triggers.json` | pusher v0.5.13 |
| 归档 | 盘后自动存 1 分钟 K 线 + session summary | focus_manager v0.5.10 |

### 2026-04-22 修复

| # | Bug | 修复版本 |
|---|---|---|
| - | 夜盘价卡在 RTH 收盘价 | realtime_quote v0.5.1 |
| - | Moomoo AU 需要 security_firm=FUTUAU | realtime_quote v0.5.1 |
| - | 持仓 current_price 和 pl_pct 显示为 0 | realtime_quote v0.5.2 |
| - | `__main__` 子命令被误判为 ticker | realtime_quote v0.5.2 |
| - | HKD 聚合导致现金错误显示 $27,705 | realtime_quote v0.5.3 |
| - | total_assets/market_val 也是 HKD 聚合 | realtime_quote v0.5.4 |
| - | `/ai_test` 无法读取 Focus session | focus_manager v0.5.9 |

---

## 🐛 剩余 bug / 待改进(按优先级)

### P1 — 本周
1. **PEAK+ 频率 vs Futu 配额平衡评估**
   0.5s 轮询可能超 Futu 免费版上限,需要回测或下调到 0.75s/1.0s
   *注*: v0.5.13 通过 /detail 读 Focus cache 缓解了大部分,但主循环本身的配额问题还在

2. **审查报告的 P0 改动**(另一个 AI 做的 code review)
   - stop_focus() 锁内 join() 的风险
   - fetch_account() 加 source + sanity check
   - `_current_session` / `_indicators_cache_global` 提供快照式读取
   - 统一 get_client() / close_client() 的单例互斥

### P2 — 中长期
3. 清理 .bak 文件(多版本备份)
4. fetch_many() 改真正的 get_market_snapshot 批量(目前是伪并发)
5. 拆 `_focus_loop()` 为子步骤(目前有"上帝函数"趋势)
6. 从模块级全局状态演进到 FocusRuntime 实例

### 复盘能力建设(本周 - 周末)
7. **本地化复盘分析器**(避免每次复盘烧钱)
   - 计划位置: `core/review_analyzer.py`
   - 输入: triggers.json + kline_1m_*.json
   - 输出: review_summary.md (2-5 KB 文本摘要)
   - 价值: 每次复盘成本从 $1.50 → $0.05
   - 状态: 未开始

### 新功能(修完所有 P1 后启动)
8. 🏁 **AI Race 赛马**: 4 AI 各 $20k 虚拟账户,周一-周五比赛
   - 参赛者: Claude Haiku / Claude Opus / GPT-5 / DeepSeek
   - 决策周期 15 分钟
   - 预算约 $4-5/周
   - 代码位置: `DEPLOY_AI_RACE/` 和 `core/agents/`(待确认用哪个)

---

## 🔧 架构要点(给 AI 读的速览)

### Focus 主循环数据流
```
Moomoo FutuOpenD
    ↓ fetch_many() / fetch_one()
realtime_quote.QuoteClient
    ↓ update_price / update_quote / update_positions / update_cash
FocusSession (core/focus/context.py)
    ↓ calc_all_micro
indicators_cache (模块级 + session)
    ↓ run_all_triggers(session, master, followers, indicators, params)
swing_detector (7 触发器)
    ↓ hits
pusher.format_trigger_message(hit, session)
    ├─ Telegram 推送
    └─ v0.5.13: 写 data/review/YYYY-MM-DD/triggers.json (复盘日志)
```

### 机会密度系统(v0.5.12)
PEAK+ / PEAK / HIGH / MEDIUM / LOW / MINIMAL / CLOSED 七档,自动切换:
- 轮询频率 (0.5s → 60s)
- 触发器阈值缩放 (0.60x → 1.80x)
- 主动提醒(开盘前 / 收盘前 / 周一 / 巫日)

### 关键 session 字段(context.py v0.5.2)
```
session.cash_available       # USD 真实可用现金(60s 一刷)
session.cash_power           # USD 购买力
session.positions_snapshot   # {ticker: {qty, cost_price, pl_val, ...}}
session.prices               # {ticker: [(ts, price), ...]} 近 30 分钟
session.quote_snapshot       # {ticker: quote_dict} 最新快照
session.first_data_ts        # 首次收到报价的时间
session.last_any_trigger_ts  # 全局互斥计时
```

### v0.5.13 新增:AI 访问数据的三级 fallback 路径
```
/detail / /ask 等 AI 指令获取 cash:
  1. Focus session (get_current_session().cash_available)   最优先
  2. realtime_quote.fetch_account                          次优
  3. data/account_data.json                                JSON 快照
  4. ACCOUNT_SIZE (config 默认 $20000)                     兜底(打印警告)

/detail 获取 quote:
  1. Focus session (get_last_price + get_quote)            最优先
  2. realtime_quote.fetch_one                              次优
  3. JSON signals 原值                                      兜底

目的:PEAK 时段避开 Futu 配额打爆
```

### v0.5.13 复盘日志系统架构
```
每次 Focus 推送:
  pusher.format_trigger_message()
    └─ _log_trigger()  → data/review/YYYY-MM-DD/triggers.json
       (记录:时间/触发器/方向/强度/profile/价格快照/持仓/现金)

每天市场收盘:
  focus_manager._focus_loop()
    └─ 检测 market_status 切到 closed
       └─ _archive_daily_klines()  → data/review/YYYY-MM-DD/
            ├─ kline_1m_{TICKER}.json  (每只票当日 1 分钟 K 线)
            └─ session_summary.json    (当日 session 统计)

第二天复盘:
  用户发 triggers.json 给 AI → AI 识别异常模式
  若需要深度,再发 kline 片段(精准时间窗口)
```

---

## 📖 新对话接手模板

**新对话开头贴这段**:

```
# MagicQuant 接手 - [日期]

按 Project Knowledge 里的 CURRENT_STATE.md + COLLABORATION_RULES.md 走。

今天要做: [一句话]
```

就这两行。AI 读本文件和 COLLABORATION_RULES.md 就能完全进入状态,不需要任何重复解释。

---

## 📋 更新本文件的时机

**每次改完代码,AI 自动生成新版,用户直接下载覆盖**。不再让用户手改。

更新的 5 个地方:
1. 生产版本清单(文件路径 + 新版本号)
2. 已修复 bug 清单(移到"已修复"段)
3. 剩余 bug 清单(完成的划掉,新发现的加入)
4. 账户真实状态(如果账户有变化)
5. 持仓(如果仓位变化)

---

## 📜 版本历史速览

| 日期 | 重大版本变化 |
|---|---|
| 2026-04-22 | v0.5.13 完整部署:机会密度系统 + 事件日历 + 主动提醒 + HKD 聚合修复 |
| 2026-04-23 上午 | pusher v0.5.12:双路推送 + 手续费 + 信心指数 |
| 2026-04-23 下午 | bot v0.5.13:Focus cache 优先 + AI 三级 fallback + 硬约束 prompt |
| 2026-04-23 晚 | pusher v0.5.13 + focus_manager v0.5.10:复盘日志系统 |
| **下次变更** | v0.5.14(本地 review_analyzer.py?)或 v0.6.0(AI Race 启动) |

---

## 📂 复盘日志目录结构(2026-04-23 晚 上线)

```
data/review/
└── YYYY-MM-DD/                    ← 每日独立文件夹
    ├── triggers.json              ← 所有推送的详细记录 ⭐
    ├── kline_1m_RKLB.json        ← RKLB 全天 1 分钟 K 线
    ├── kline_1m_RKLX.json
    ├── kline_1m_RKLZ.json
    ├── kline_1m_TSLA.json
    ├── kline_1m_TSLL.json
    └── session_summary.json      ← 当日 session 统计(循环数/推送数/持仓)
```

**复盘时**: 用户只需发送 `triggers.json` + `session_summary.json`(约 30 KB)给 AI,AI 判断是否需要看具体 K 线时段再追加发送。单次复盘成本 $0.05-0.30。
