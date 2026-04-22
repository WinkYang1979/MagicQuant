# MagicQuant 慧投 — 更新日志

> Dare to dream. Data to win.  
> 梦想终究是要有的,万一实现了呢?

---

## [v0.3.5] — 2026-04-21 · AI 智囊团 + Dashboard 可视化 🎯

### 🆕 新增功能

**AI 智囊团 (Focus 触发时召集)**
- Focus 每次触发(波段顶/底/回撤/浮盈等)自动召集 AI 智囊团
- 3 位独立顾问:Haiku 4.5 + DeepSeek V3 + GPT-5 并行给建议
- Claude Opus 4.7 作为 Leader,看完顾问意见后做最终汇总决策
- 每个建议必须包含:动作 + 股票 + 股数 + 价格 + 理由 + 风险 + 信心度
- 允许 HOLD 观望,不强行交易(费用吃利润)
- Leader 可独立判断与顾问分歧,标记 `⚡ 独立判断`

**成本透明化**
- 每次推送末尾列出 per-AI 成本明细:
  - Haiku: $0.0035 (58 tok)
  - DeepSeek: $0.0009 (70 tok)
  - GPT-5: $0.0098 (60 tok)
  - Opus Leader: $0.025 (300 tok)
- 今日累计成本自动追踪(每日 00:00 清零)
- 历史记录持久化到 `data/ai_advisor_history.json` (最近 200 条)

**Dashboard 可视化**
- `focus.html` 新增 AI 智囊团实时面板
- 最新决策卡:3 顾问并列 + Opus Leader 突出显示
- 最近 10 条触发历史表格
- 每 3 秒自动刷新,不闪烁

**新增 Dashboard API**
- `GET /ai_advisor/latest` — 最新一次建议
- `GET /ai_advisor/history` — 完整历史
- `GET /ai_advisor/cost` — 今日累计成本

**新增 Telegram 指令**
- `/ai_advise_on` — 开启 AI 智囊团(默认开)
- `/ai_advise_off` — 关闭智囊团,Focus 仍推送触发
- `/ai_advise_status` — 查看状态

### 🛠️ 修复 & 增强

- **费率精确化**:Moomoo AU 真实公式替代固定 $1.29/$1.31
  - 买入固定 $1.29 (Platform $0.99 + Settlement $0.30)
  - 卖出 $1.31~$8.30 动态 = $0.99 + $0.30 + SEC($amt × 0.0000278) + TAF($qty × 0.000166, max $8.30)
- **API Key 兼容性**:支持 `CLAUDE_API_KEY` 和 `ANTHROPIC_API_KEY` 两种环境变量名
- **Key 智能过滤**:自动忽略空值、行内注释(`#`)、占位符("xxx")
- **异步 AI 调用**:不阻塞 Focus 1 秒/次主循环

### 📦 新增文件

```
core/focus/ai_advisor.py          顾问团 + Leader 逻辑
core/agents/__init__.py           Race 大赛包
core/agents/portfolio.py          虚拟账户
core/agents/providers.py          4 家 AI 统一接口
core/agents/prompt.py             统一 prompt
core/agents/race_manager.py       赛马调度
test_ai_providers.py              独立测试脚本
```

### 💰 成本预期

```
AI 智囊团: $0.04/次 × 20 次 = $0.80/晚
AI 大赛 (180秒/轮, 130轮): $2-3/晚
总计: ~$3-4/晚
```

---

## [v0.3.4] — 2026-04-21 · AI 虚拟操盘大赛

- 5 AI 并行赛马:Claude Opus/Haiku + GPT-5 + DeepSeek + Kimi
- 每 AI 独立 $20,000 虚拟账户,真实交易规则
- 180 秒/轮自动决策,统一 prompt 公平比较
- 新指令:`/race` `/race_stats` `/race_cost` `/race_stop` `/race_reset` `/race_providers`

---

## [v0.3.3] — 2026-04-21 · 🔥 RKLX/RKLZ 方向反转 Bug 修复

- **紧急修复**:老代码把 RKLZ 当做多 ETF,导致推送方向反向
- 修正:RKLX = 2x 做多 RKLB, RKLZ = 2x 做空 RKLB
- `swing_top` 看跌 → 卖 RKLX(平多)+ 买 RKLZ(开空)
- `swing_bottom` 看涨 → 卖 RKLZ(平空)+ 买 RKLX(开多)
- 新增 `pairs.py` 配对配置,扩展其他主股只改这里

---

## [v0.3.2] — 2026-04-21 · Dashboard 不闪烁

- `focus.html` 增量 DOM 更新,每 2 秒刷新不再整页重绘
- 价格变化 CSS flash 动画 + 叮声提醒
- `server.py` 绑定 0.0.0.0 支持 LAN 访问
- 新增 `/focus/state` API

---

## [v0.3.1] — 2026-04-21 · Focus 性能压测调优

- 1 秒频率验证稳定:20/20 成功, avg 209ms, p95 211ms
- 4 只股票并发 216ms, 无限流
- K 线拉取 65ms 超快

---

## [v0.3.0] — 2026-04-21 · Focus 盯盘模式 + 配对做 T

- 🎯 **Focus 焦点盯盘**:RKLB 波段做 T 信号系统
- 新指令:`/focus` `/unfocus` `/status` `/push_on` `/push_off`
- 主从盯盘:RKLB 信号源 → RKLX/RKLZ 交易
- 7 大触发器:波段顶/底/回撤/浮盈/异动等
- A 方案 4 按钮反馈闭环
- 分组 `/help` + `/help XXX` 详情(18 条指令)

---

## [v0.2.x] — 2026-04-20 · Claude AI 分析接入

- `/detail` 升级:自动触发 Claude AI 深度分析
- AI 建议格式:操作/理由/风险
- `/usage` 查本月 Claude API 累计费用
- 对账单 PDF 自动解析入库
- `/pnl` 从对账单计算历史盈亏

---

## [v0.1.0] — 2026-04-19 · 首次发布

- Moomoo AU LV3 实时行情
- 技术指标 + K 线形态识别
- Telegram 群推送 + 多指令
- 本地 Web Dashboard
- 动态 Watchlist

---

## 🎯 开发路线图 (Roadmap)

### 已完成 ✅
- [x] 基础盯盘 + 指标
- [x] AI 分析单点
- [x] Focus 波段做 T 信号
- [x] AI 大赛虚拟账户
- [x] AI 智囊团 + Leader
- [x] Dashboard 可视化

### 进行中 🚧
- [ ] 准确 Moomoo 真实交易对账单核对(等老杨提供 Trade Confirmation)
- [ ] Kimi K2 API 接入(等注册)
- [ ] 真实 Agent 框架接入(QuantAgent / TradingAgents / AI-Hedge-Fund)

### 规划中 📋
- [ ] v0.4.x — Moomoo URL scheme 半自动跳转下单
- [ ] v0.5.x — K 线图 Chart.js RKLB 5M 可视化
- [ ] v0.6.x — 限额自动下单(小仓位验证)
- [ ] v0.7.x — 真全自动(3 月验证期后)
- [ ] v1.0 — 产品化

---

## 🤝 一起努力的过程

每一次升级都是老杨和 Claude 一起踩坑调试的结果:

- **v0.3.0 Focus 大重构** — 从"固定推送"变"事件驱动",3 天内完成 2600 行代码
- **v0.3.3 的惊险救场** — 盘前发现 RKLZ 方向反了,紧急修复避免真金白银亏损
- **v0.3.4 AI 大赛设计** — 老杨一句"让 AI 赛马",诞生了 5 AI 并行虚拟操盘系统
- **v0.3.5 智囊团设计** — 老杨定义了"Claude 当 Leader"的架构,把多 AI 协作变成可观测系统

"梦想终究是要有的,万一实现了呢?"
