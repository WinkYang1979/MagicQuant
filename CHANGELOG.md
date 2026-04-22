# MagicQuant 慧投 — 更新日志

> Dare to dream. Data to win.  
> 梦想终究是要有的,万一实现了呢?

---

## [v0.4.0] — 2026-04-22 · Risk Engine 独立模块 🛡️

### 🎯 核心原则(Final Lock)

```
Risk Engine > Signal > AI
BLOCK entry, RARELY block exit
FULL_EXIT 永远允许
```

### 🆕 新增功能

#### 1. 统一风控引擎 `core/risk_engine/`

所有交易建议过 `can_trade()` 闸门:

```python
from core.risk_engine import can_trade

result = can_trade(
    action_type="new_entry",      # new_entry/add_position/partial_exit/full_exit/reverse
    ticker="US.RKLZ",
    qty=100, entry=15.42, stop=15.30, target=15.80,
    direction="long",
    context={"pdt_used": 0, "cash": 18000, "confidence": 0.72, ...},
)

if not result.allowed:
    # 拦截,推送 result.message
    pass
elif result.severity == "warn":
    # 警告但放行,TG 推送加覆盖按钮
    pass
```

#### 2. 15 个 reason_code 分 4 组

**HARD BLOCK** (severity=block, 硬拦截):
- `PDT_EXHAUSTED` — 今日 PDT 用完
- `INSUFFICIENT_CASH` — 现金不足
- `LEVERAGE_LIMIT` — 有效杠杆超标(含 2x ETF 放大)
- `DAILY_LOSS_LIMIT` — 单日亏损熔断
- `DRAWDOWN_LIMIT` — 最大回撤熔断

**QUALITY** (severity=warn, 质量警告):
- `FEE_NOT_WORTH` — 费用效率不达标(三维判断)
- `RR_TOO_LOW` — 风险收益比过低
- `SPREAD_TOO_WIDE` — 盘口价差过大
- `LOW_CONFIDENCE` — AI 信心不足
- `CONFLICTING_SIGNAL` — 多 AI 意见分歧

**CONTEXT** (severity=advisory, 仅提醒):
- `MARKET_CLOSED` — 非主盘时段
- `PRE_EARNINGS` — 财报前高风险
- `PDT_GUARD` — PDT 剩最后 1 次

**FLOW** (severity=warn, 流程控制):
- `COOLDOWN` — 触发器冷却中
- `DUPLICATE_SIGNAL` — 重复信号
- `POSITION_CONCENTRATION` — 单票集中度过高

#### 3. 结构化返回 `RiskCheckResult`

```python
{
  "allowed":              bool,
  "severity":             "pass"|"advisory"|"warn"|"block",
  "primary_reason_code":  "pdt_exhausted",
  "all_checks":           [...],   # 所有违规的完整清单
  "message":              "...",
  "metrics":              {"rr_ratio": 1.68, "fees_roundtrip": 2.64, ...},
  "actions":              {"suggested_min_qty": 51, "allow_exit": True},
  "check_id":             "abc123",  # 关联 override log
  "timestamp":            "...",
  "action_type":          "new_entry",
  "ticker":               "US.RKLZ",
}
```

#### 4. 4 个 Helper 函数

- `estimate_fees(qty, price)` — Moomoo AU 真实费率(含 SEC + TAF)
- `estimate_expected_net_profit(entry, target, qty, direction)`
- `compute_rr_ratio(entry, target, stop, qty, direction)`
- `min_profitable_qty(entry, target, min_net=5)` — 最小有意义仓位

#### 5. 28 个测试 Fixture

**✅ 28/28 通过**,跑 `/risk_test` 一键验证.

- 15 业务场景:正常入场 / PDT 用完 / 现金不足 / FULL_EXIT 豁免 / 反手 / 杠杆超标 ...
- 13 边界测试:RR 刚好 1.5 / 净利 4.99 vs 5.00 / PDT 整 0/1 / 爆仓日止损 ...

#### 6. 日志系统

**`data/risk_log.jsonl`** 每次 check 落盘:
- 完整 RiskCheckResult
- 精简 context 快照(PDT/cash/daily_pnl/positions/market_session/confidence)
- `outcome` 字段预留给 v0.5 事后回填

**`data/override_log.jsonl`** 用户行为日志:
- 自动分类 4 种 `override_type`:
  - `aligned_with_system` 和系统一致
  - `override_ai_only` 仅逆 AI
  - `override_risk_only` 仅逆风控
  - `override_risk_and_ai` 逆双方

#### 7. 配置外置 `config/risk_config.json`

所有阈值集中一处,热重载,调参**不改代码**:

```json
{
  "pdt_limit": 3,
  "daily_loss_limit_usd": -400.0,
  "max_drawdown_pct": -8.0,
  "min_rr_ratio": 1.5,
  "min_net_profit_usd": 5.0,
  "min_profit_over_fee_multiplier": 2.0,
  "max_effective_leverage": 1.8,
  "max_concentration_pct": 60.0,
  "min_confidence": 0.60,
  ...
}
```

#### 8. Telegram 指令

```
/risk               查看风控状态 + 当前阈值 + 最近 5 次检查
/risk_test          跑 28 个 fixture 回归测试
/risk_stats [天]     最近 N 天统计(含 override 分类)
/risk_check ...     手动测试:/risk_check RKLZ 100 15.42 15.30 15.80
```

### 🤝 多方协作决议

v0.4 是 Claude + OpenAI + DeepSeek 三方协作的成果:

- **OpenAI**:提出 8 + 7 条工程化建议(结构化输出、reason_code 分组、边界测试)
- **Claude**:基于实盘代码做修正(REVERSE 动作、20 个 code 扩充、min_profitable_qty)
- **DeepSeek**:务实认可 + 推进节奏
- **老杨**:定稿决策 + "Risk Engine > Signal > AI" 优先级原则

### 📦 包含 v0.3.6 全部功能

v0.4 基于 v0.3.6,包含:
- `/heartbeat` 心跳监控
- `/heartbeat_on [N]` 定时心跳推送
- `/ai_test` 主动召集智囊团

### 🗺️ 路线图

```
✅ v0.4.0  Risk Engine + Override Log + 测试 fixture(本版)
🚧 v0.4.1  Dashboard Risk 面板(下版补)
📋 v0.5    触发器胜率自评 + 微观状态记录(基于 v0.4 的 risk_log.jsonl)
📋 v0.6    decision_json 标准化 + 多 AI 投票
📋 v0.7+   账户 >$25k 后才考虑多 Agent 独立账户
```

---

## [v0.3.6] — 2026-04-21 · 告别沉默
新增 /ai_test 主动召集,/heartbeat 心跳监控

## [v0.3.5] — 2026-04-21 · AI 智囊团
Haiku + DeepSeek + GPT-5 + Opus Leader 四方决策

## [v0.3.0-0.3.4] — 2026-04-21 · Focus 盯盘
RKLB 波段做 T + 7 大触发器 + 配对做 T + 性能调优

## [v0.2.x] — 2026-04-20 · Claude AI 分析
/detail 深度分析 + 对账单 PDF 解析

## [v0.1.0] — 2026-04-19 · 首次发布
Moomoo LV3 + 技术指标 + Telegram Bot

---

*"系统方向正确,重点是收紧 + 结构化 + 可测试" — OpenAI v0.4 Final Lock*
