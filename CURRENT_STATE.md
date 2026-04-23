# MagicQuant — 当前线上状态快照

> **最后更新**: 2026-04-23
> **维护原则**: 每次改完代码立即更新本文件。**这是新对话 AI 理解项目的第一手资料**,比完整项目文档更实时,比读代码更便宜。

---

## 🎯 生产版本清单(已部署,正在跑)

| 文件 | 路径 | 版本 |
|---|---|---|
| realtime_quote.py | core/ | **v0.5.4** |
| focus_manager.py | core/focus/ | **v0.5.9** |
| pusher.py | core/focus/ | v0.5.11 |
| swing_detector.py | core/focus/ | v0.5.4 |
| market_clock.py | core/focus/ | v0.2.0 |
| event_calendar.py | core/focus/ | v0.1.0 |
| activity_profile.py | core/focus/ | v0.1.0 |
| proactive_reminder.py | core/focus/ | v0.1.0 |
| context.py | core/focus/ | v0.5.2 |
| pairs.py | core/focus/ | 无版本号 |
| bot_controller.py | bot/ | v0.5.11 |

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

---

## 🎯 交易策略 / 标的池

### 核心交易对
- **主信号源**: US.RKLB (Rocket Lab)
- **做多工具**: US.RKLX (2x 多 RKLB ETF)  
- **做空工具**: US.RKLZ (2x 空 RKLB ETF)

### 其他跟踪
- US.TSLA / US.TSLL (有套牢仓,仅观察)

---

## 🐛 已知 bug / 待修(按优先级)

### P0 — 今天修复中(2026-04-23)
1. **推送信号遮蔽 / 双路建议缺失** ⭐⭐⭐⭐  
   现象: RKLB 看多 + 持 RKLZ(反向) 时,只推"平 RKLZ",不推"用现金建多 RKLX"  
   根因: pusher.py `_build_action_plan` scenario B 的 Step 2 在释放现金未计入时被误判 insufficient  
   状态: **修复中**,pusher.py 将升级到 v0.5.12

2. **持仓浮盈显示不含手续费** ⭐⭐⭐  
   现象: "浮亏 $-29" 不包含买卖手续费 $2.72  
   状态: **修复中**,同上 v0.5.12

3. **AI 分析凭空编造仓位金额** ⭐⭐⭐  
   现象: AI 建议买 69 股 $6,210,但用户只有 $3,537  
   根因: prompt 没注入真实账户 context  
   状态: **未开始**,下一批

### P1 — 本周
4. **Futu Quote API PEAK 时段配额打爆**  
   现象: PEAK 时段 (1s 轮询) /detail 指令返回 Snapshot failed  
   修复方向: Focus 共享 cache,手动指令优先读 cache(10s 内)  
   状态: 未开始

5. **PEAK+ 频率 vs Futu 配额平衡评估**  
   0.5s 轮询可能超 Futu 免费版上限,需要回测或下调到 0.75s/1.0s

### P2 — 中长期
6. stop_focus() 锁内 join() 风险  
7. fetch_account() 加 source + sanity check  
8. 清理 .bak 文件  
9. fetch_many() 改真正的 get_market_snapshot 批量

### 新功能(修完 P0/P1 后)
- 🏁 **AI Race 赛马**: 4 AI 各 $20k 虚拟账户,周一-周五比赛。待周末启动。

---

## 🔧 架构要点(给 AI 读的速览)

### Focus 主循环数据流
```
Moomoo FutuOpenD
    ↓ fetch_many()
realtime_quote.QuoteClient
    ↓ update_price / update_quote / update_positions / update_cash
FocusSession (core/focus/context.py)
    ↓ calc_all_micro
indicators_cache
    ↓ run_all_triggers(session, master, followers, indicators, params)
swing_detector (7 触发器)
    ↓ hits
pusher.format_trigger_message(hit, session)
    ↓ Telegram
```

### 机会密度系统 (v0.5.12)
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

---

## 📖 新对话接手模板

**新对话开头贴这段**(自动从本文件读到所有内容):

```
# MagicQuant 接手 - [日期]

按 Project Knowledge 里的 CURRENT_STATE.md + COLLABORATION_RULES.md 走。

今天的目标:[一句话]
```

就这两行。AI 读 CURRENT_STATE.md 和 COLLABORATION_RULES.md 就能完全进入状态,不需要任何重复解释。

---

## 📋 更新本文件的时机

**每次改代码后立即更新本文件的这几处**:
1. 生产版本清单(文件路径 + 新版本号)
2. 已知 bug 清单(完成的划掉,新发现的加入)
3. 账户真实状态(如果账户有变化)
4. 持仓(如果仓位变化)

**更新后 git commit + push**。这份文件在 Project Knowledge 里会自动读到,比代码 fetch 便宜得多。
