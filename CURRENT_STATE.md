# MagicQuant — 当前线上状态快照

> **最后更新**: 2026-05-11 (pusher v0.5.20 副驾驶语言规范)
> **维护原则**: 每次改完代码,AI 自动生成新版,用户直接下载覆盖,不手改。
> **新对话接手入口**: 读本文件 + COLLABORATION_RULES.md,两行搞定。

---

## 🎯 生产版本清单

| 文件 | 路径 | 版本 | 状态 |
|---|---|---|---|
| realtime_quote.py | core/ | v0.5.4 | ✅ 已部署 |
| context.py | core/focus/ | v0.5.2 | ✅ 已部署 |
| swing_detector.py | core/focus/ | v0.5.21 | ✅ 已部署 |
| **pusher.py** | core/focus/ | **v0.5.20** 🆕 | ⏳ 待部署 |
| **focus_manager.py** | core/focus/ | **v0.5.21** 🆕 | ⏳ 待部署 |
| market_clock.py | core/focus/ | v0.2.0 | ✅ 已部署 |
| event_calendar.py | core/focus/ | v0.1.0 | ✅ 已部署 |
| activity_profile.py | core/focus/ | v0.1.0 | ✅ 已部署 |
| proactive_reminder.py | core/focus/ | v0.1.0 | ✅ 已部署 |
| pairs.py | core/focus/ | 无版本号 | ✅ 已部署 |
| bot_controller.py | bot/ | v0.5.13 | ✅ 已部署 |
| **signal_engine.py** | core/ | **v0.1.0 [LEGACY]** 🆕 | ⏳ 待部署 |

**⏳ 待部署的 3 个文件**:
- `core/focus/pusher.py`
- `core/focus/focus_manager.py`
- `core/signal_engine.py`

**GitHub**: https://github.com/WinkYang1979/MagicQuant

---

## 💰 账户真实状态(2026-04-24)

| 项 | 值 |
|---|---|
| **USD 可用现金** | **$2,308.68** (盘后归档值) |
| **PDT 状态** | **无限制** ✅ (Moomoo AU 账户不受 PDT 规则约束) |
| 券商 | Moomoo AU 综合账户 6018 |

### ⚠️ HKD 聚合陷阱
`accinfo_query` 默认返回 HKD 聚合值,代码中**必须用 `us_cash` / `usd_assets`**,不要用 `cash` / `total_assets`。

---

## 📊 当前持仓(2026-04-24 盘后)

| 标的 | 数量 | 成本价 | 浮盈 | 说明 |
|---|---|---|---|---|
| TSLL | 251 | $22.275 | **-$2,556(-45.7%)** | 套牢,不操作 |
| RKLX | 50 | $46.35 | **-$140(-6.0%)** | 做多 RKLB,正在衰减中 |

**⚠️ RKLX 持仓警告**:RKLB 当前在 $85-86 震荡,RKLX 每天承受 2x ETF 衰减损失。如果 RKLB 无法在近期突破 $88+ 前高,需要考虑止损规则(详见下方 P2 #5)。

---

## 🎯 交易策略设定

- **主信号源**: US.RKLB
- **做多工具**: US.RKLX (2x 多)
- **做空工具**: US.RKLZ (2x 空)
- **单笔最大仓位**: 40%(v0.5.13 写入 AI prompt 硬约束)
- **STRONG 信号门槛**: 日内涨跌 ≥ 2.0%(v0.5.5 升级,原 1.5%)
- **rapid_move 阈值**: 0.8% / 120s(v0.5.5 升级,原 0.4%)

---

## ✅ 已修复 bug 清单

### 2026-05-11
| # | 改动 | 版本 |
|---|---|---|
| #7 | 删除 `ACCOUNT_SIZE_USD=20000` 硬编码；`get_available_cash(None)` 改返回 0 | pusher v0.5.20 |
| #8 | 信号推送软化语言：`🛒 买入` → `📋 可考虑介入` + "仓位由你决定" | pusher v0.5.20 |
| #9 | 信号格式加行情/方向/免责三行；风险提醒加"不是卖出信号"声明 | pusher v0.5.20 |
| #10 | signal_engine.py 加 [LEGACY] 标记，修复硬编码路径 | signal_engine |

### 2026-04-24
| # | Bug | 修复版本 |
|---|---|---|
| #5 | direction_trend 全天刷 STRONG 看空(RSI/vol 为默认值,指标未算出) | swing v0.5.5 |
| #6 | rapid_move 震荡市每小时触发 5-6 次噪声 | swing v0.5.5 |

### 2026-04-23
| # | Bug | 修复版本 |
|---|---|---|
| #1 | 推送信号遮蔽 / Step 2 缺失 | pusher v0.5.12 |
| #2 | 浮盈/浮亏不含手续费 | pusher v0.5.12 |
| #3 | PEAK 时段 /detail 失灵 | bot v0.5.13 |
| #4 | AI 凭空编造仓位金额 | bot v0.5.13 |
| - | 复盘日志系统上线 | pusher v0.5.13 + focus_manager v0.5.10 |

### 2026-04-22
| # | Bug | 修复版本 |
|---|---|---|
| - | 夜盘价卡 RTH / HKD 聚合 / 持仓字段为 0 等 | realtime_quote v0.5.1-v0.5.4 |
| - | /ai_test 无法读取 Focus session | focus_manager v0.5.9 |

---

## 🐛 剩余 bug / 待改进

### P1 — 本周
1. **PEAK+ 频率 vs Futu 配额**:0.5s 主循环可能超免费版上限,需评估
2. **审查报告遗留**:stop_focus() 锁内 join / fetch_account sanity check / 单例互斥
3. **swing 指标根因**:has_indicators 永远 False 的深层原因未定位(v0.5.5 已加 workaround)
4. **复盘报告新格式**（MagicQuant_update_v2.md Req 8）:需新增 review_analyzer.py，P2 推迟

### P2 — 中长期
4. 清理 .bak 文件
5. **RKLX 持仓止损规则**:设定"若 N 天内 RKLB 未突破 $88,止损 RKLX"明确规则
6. fetch_many() 改真正批量 / _focus_loop() 拆分

### 复盘能力建设
7. **local review_analyzer.py**:本地预处理,避免复盘烧钱(未开始)

### 新功能(P1 全清后)
8. **策略独立文件架构** (`core/strategy/`)
9. **历史数据拉取**:RKLB 2 年 1m K 线
10. **AI Race**:4 AI 各写策略 + 回测引擎赛马

---

## 🔧 架构速览

### Focus 主循环
```
Futu OpenD → realtime_quote → FocusSession → indicators
  → swing_detector.run_all_triggers()
      ├─ check_direction_trend  ← v0.5.5 震荡过滤 + 二次确认
      ├─ check_swing_top/bottom
      ├─ check_rapid_move       ← v0.5.5 阈值 0.8%,冷却 20min
      └─ check_profit_target / drawdown
  → pusher.format_trigger_message()
      ├─ Telegram 推送
      └─ 写 data/review/YYYY-MM-DD/triggers.json  ← v0.5.13
  → 盘后: _archive_daily_klines()                 ← v0.5.10
```

### v0.5.5 震荡过滤
```
_is_choppy(): high-low(近10点) / |总涨跌| > 3.0 → 压制信号
_recent_price_direction(): 近5点方向需与 day_chg 一致
has_indicators=False 时: 只推 WEAK,不推 STRONG
```

### v0.5.13 AI 三级 fallback
```
cash: Focus session → fetch_account → JSON 快照 → 默认值(警告)
quote: Focus session cache → fetch_one(免 PEAK 时段 Futu 配额)
```

---

## 📂 复盘日志结构(2026-04-23 上线)

```
data/review/YYYY-MM-DD/
  triggers.json          ← 推送详细记录 ⭐
  kline_1m_{TICKER}.json ← 全天 1m K 线
  session_summary.json   ← 当日统计
```

**复盘成本**:只发 triggers.json + session_summary.json(约 30KB),单次 $0.10-0.30。

---

## 📊 策略调研摘要(详见 strategy_research.md)

- RKLB: beta 2.2+,日均波动 6.76%,事件驱动型
- RKLX/RKLZ: 震荡市年衰减 40-50%,只适合短线
- 最适合 RKLB 的业界策略: Ernie Chan 日内动量
- PDT 新规 2026-06-04:$25k 门槛降至 ~$2k

---

## 📖 新对话接手模板

```
# MagicQuant 接手 - [日期]
按 Project Knowledge 里的 CURRENT_STATE.md + COLLABORATION_RULES.md 走。
今天要做: [一句话]
```

---

## 📜 版本历史

| 日期 | 变更 |
|---|---|
| 2026-04-22 | realtime_quote v0.5.4 / focus v0.5.9 / swing v0.5.4 基础稳定 |
| 2026-04-23 上午 | pusher v0.5.12:双路推送 + 手续费 + 信心指数 |
| 2026-04-23 下午 | bot v0.5.13:Focus cache + AI 三级 fallback + 40% 约束 |
| 2026-04-23 晚 | pusher v0.5.13 + focus_manager v0.5.10:复盘日志 |
| 2026-04-24 | swing v0.5.5:降噪 84%,震荡过滤 + rapid_move 提高阈值 |
| 2026-05-06~09 | swing v0.5.17-v0.5.21:多空过滤升级 + 风险提醒触发器 |
| 2026-05-09 | focus_manager v0.5.20:趋势锁定机制上线 |
| 2026-05-11 | pusher v0.5.19:T1/T2/止损目标价 + 信心进度条 + 仓位分级 |
| 2026-05-11 | pusher v0.5.20:副驾驶语言规范 — 去强制指令 + 免责声明 + 行情/方向标签 |
| **2026-05-11** | **focus_manager v0.5.21:共享市场快照输出 data/shared/market_snapshot.json** |
| 下次变更 | review_analyzer.py 或 core/strategy/ 架构 |
