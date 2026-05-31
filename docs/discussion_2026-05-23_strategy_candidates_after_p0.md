# Strategy Candidates After Weekend P0

VERSION: v0.1  
DATE: 2026-05-23  
DEPENDS: docs/weekend_p0_results_2026-05-23.md, docs/STRATEGY_SCORECARD.md  
STATUS: discussion_only

## 1. 当前结论

周末 P0 验证后，暂时不建议直接改主方向触发器。原因：

- ATR 止损/目标问题是明确 bug，已经按数据参考层修复并通过硬验收。
- RKLZ 历史 1m 有异常 TR 日，需要在 ATR 计算中跳过，避免脏数据污染参考价。
- rebound_delay 有足够历史底部候选，但还没完成与真实 trigger 的逐段对齐。
- direction_trend 置信度封顶规则只完成了“会影响多少条”的离线试跑，还没证明误伤率可接受。

因此，策略层先讨论三条候选，不直接上线。

## 2. 候选 A：direction_trend 置信度封顶

### 问题

`direction_trend` 容易在 day_change 很强时给出高信心，但微结构可能已经走弱。用户只在 STRONG 信号时更容易执行，所以 STRONG 必须诚实。

### 候选规则

当 `direction_trend` 已经准备推 STRONG，且：

- `abs(day_chg) >= 3%`
- 同时满足以下任一项：
  - price < VWAP
  - RSI slope <= 0
  - 最近 3 根 5m K 线 lower highs

则不静默、不改方向，只把信心封顶到中等，并在文案写清：

```text
方向倾向仍在，但微结构未确认，信心封顶为中等。
```

### 当前离线试跑

在 `docs/weekend_p0_results_2026-05-23.md` 中：

- 2026-05-21: 18 条 STRONG direction_trend，规则会封顶 7 条。
- 2026-05-22: 3 条 STRONG direction_trend，规则会封顶 1 条。

### 上线条件

上线前必须补：

- 这些被封顶的信号里，多少事后方向其实是对的。
- 如果封顶，会不会加重 05-19 那类“熄火”问题。
- 更新 `docs/STRATEGY_SCORECARD.md` 的 before/after。

## 3. 候选 B：反弹延迟诊断后再决定升级条件

### 问题

用户最痛的不是完全没提示，而是暴跌后的反弹提示升级不够及时。

### 当前数据

离线扫描近 90 天已经找到 207 个 RSI<=30 后 90 分钟内反弹 >=2% 的候选案例，样本足够继续分析。

### 下一步

对每个候选底部补：

- 第一条 long STRONG 出现时间。
- 从底部到第一条 long STRONG 错过了多少涨幅。
- 延迟来源：
  - not_produced
  - produced_weak
  - suppressed_top1
  - cooldown
  - mutex

### 暂不做

在没有 delay_layer 表之前，不直接降低 rebound / intraday_reversal 阈值。

## 4. 候选 C：PositionFollowupMonitor

### 问题

入场后缺少统一的持仓看护状态，旧的 `stop_loss_warning / drawdown_from_peak / profit_target_hit` 容易互相叠加，造成噪音。

### 候选状态

- HOLD_OK：方向仍成立，不主动推。
- TOP_WATCH：接近波顶，只提示观察。
- TAKE_PROFIT_ZONE：波顶初步确认，提示可考虑锁定利润。
- INVALIDATED：原方向失效，必须复用新 ATR 失效位。

### 关键约束

- 不能叠加旧退出侧触发器，必须接管或抑制它们。
- 不给卖出比例，不给一键卖出。
- 1m 只在持仓后用于确认，不进入主方向判定。
- 盘前低量时，INVALIDATED 要更谨慎，不能复刻 79.96 -> 78.8 割肉问题。

## 5. 当前建议顺序

1. 完成 rebound_delay 与 trigger 的离线对齐。
2. 完成 confidence cap 的误伤率统计。
3. 再讨论是否上线候选 A。
4. PositionFollowupMonitor 继续写详细规格，但等旧退出侧噪音梳理清楚后再动代码。

## 6. 红线

- 不用单日截图调阈值。
- 不直接放松方向 guard。
- 不让 1m 进入主方向判定。
- 不把止损/止盈重新做成贴得很近的机械价。

