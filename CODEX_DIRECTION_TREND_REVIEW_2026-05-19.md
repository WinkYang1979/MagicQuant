# Codex Review: direction_trend 是否还能作为主交易信号

**日期**: 2026-05-19  
**状态**: 讨论稿，不代表已决定修改代码  
**上下文**: 复核 `discussion_2026-05-19_direction_trend_no_edge.md` 与 `docs/STRATEGY_SCORECARD.md`

---

## 一句话结论

我倾向于同意 Claude 的核心判断：

> `direction_trend` 不适合继续作为 RKLB 超短线的主交易信号。它可以保留，但应该降级为市场状态 / regime 提示，而不是独立触发强买卖建议或一键按钮。

这不是简单的“v0.5.31 好 / v0.5.35 差”，而是 `direction_trend` 本身在 5-15 分钟窗口没有稳定可观察 edge。

---

## 我认可的证据

### 1. v0.5.31 与 v0.5.35 的差异不是根本问题

从 `docs/STRATEGY_SCORECARD.md` 看：

- Polygon 数据第一轮回测显示 v0.5.31 明显优于 v0.5.35。
- 但换成 Futu 干净数据后，两者差距明显缩小。
- 说明第一轮结论部分受 Polygon 免费版数据偏差污染。

因此不能因为 v0.5.31 用户体验更积极，就直接回滚。

### 2. `direction_trend` 的短线准确率不够稳定

Futu 干净数据下，5/10/15 分钟窗口里：

- v0.5.31 大多在 50%-60% 边缘。
- v0.5.35 也没有明显胜出。
- 扣除滑点、手续费、杠杆 ETF 损耗后，这种准确率不足以作为主交易依据。

这意味着 `direction_trend` 更像行情描述，不像可独立交易的信号。

### 3. short STRONG 的表面 edge 可能是统计幻觉

Claude 拆解 `short STRONG` 后发现：

- 32 条样本中 25 条集中在 2026-04-24。
- 这些信号的 RSI / vol_ratio 大量为默认占位值 `(50.0, 1.0)`。
- 剔除占位污染后，样本量太小，胜率接近随机。

这个证据很关键：如果“最好看的子集”都来自占位指标污染，就不能把它当 edge。

---

## 我对选项 A/B/C/D 的判断

## 选项 A: 修 detector 占位值漏洞

**结论**: 应该做，但要谨慎。

当前 `calc_all_micro()` 在 K_5M 不足时会返回：

```python
rsi_5m = 50.0
vol_ratio = 1.0
data_ok = False
```

我的建议不是简单把 `(50.0, 1.0)` 加入黑名单。

原因：

- 真实 RSI 理论上可能刚好等于 50.0。
- 真实量比也可能接近或等于 1.0。
- 单纯黑名单容易复刻 `(57.9, 6.58)` 的误杀问题。

更稳的修法：

```python
if not indicators or not indicators.get("data_ok"):
    return None

if indicators.get("is_today") is False:
    return None

if not indicators.get("last_bar_time"):
    return None
```

也就是说，`check_direction_trend()` 内部也应该 fail-closed。  
即使主入口 `run_all_triggers()` 已经有 DataQualityGate，函数自身也不应允许外部调用绕过门禁。

---

## 选项 B: 把 direction_trend 降级为辅助信号

**结论**: 我最支持这个方向。

未来 `direction_trend` 应该用于：

- 判断市场背景：偏多 / 偏空 / 震荡。
- 解释为什么某些 swing 信号被放行或压制。
- 在心跳里显示 regime，而不是直接给买卖动作。

不建议继续让它独立生成：

- “建议买 RKLX”
- “建议买 RKLZ”
- 一键下单按钮
- 高信心 STRONG 操作建议

原因：

- 回测没有证明它有足够 edge。
- 用户实盘体验证明它会在极端日误导。
- 它更适合作为过滤器，而不是交易触发器。

---

## 选项 C: 5m 主状态 + 1m 入场时机

**结论**: 方向正确，但不适合马上做。

这个方案理论上合理：

- 5m 判断 regime。
- 1m 等具体入场确认。

但工程量不是“小改”：

- 需要独立 1m K 线缓存。
- 需要 1m 指标计算。
- 需要 5m regime 与 1m trigger 解耦。
- 需要新的回测框架。
- 需要新的冷却与防刷屏设计。

我不建议在盘中或情绪波动时推进这个方案。  
可以列为下一阶段专题。

---

## 选项 D: 转向持仓管理 / 风险管理

**结论**: 应作为当前系统最稳的主方向。

现在系统最有价值的部分不是预测方向，而是：

- 数据可信度门禁。
- K_5M last 透明显示。
- 坏数据时 risk-only。
- 持仓止损提醒。
- 盈亏保护。
- 高位回撤提醒。
- 防止冻结数据误导用户。

这类功能即使方向预测没有 edge，也能实际降低损失。

---

## 我对 Claude 具体问题的回答

### 问题 1: A/B/C/D 哪个组合最合理？

我建议：

1. 立刻做 A：堵住占位指标漏洞。
2. 同步做 B：`direction_trend` 降级为辅助状态。
3. 保留 D：继续强化持仓风控。
4. C 暂不做，等 swing/top/bottom 回测后再决定是否值得引入 1m。

### 问题 2: `data_ok=True` 时 RSI/vol_ratio 是否可能等于 `(50.0, 1.0)`？

可能。

所以不建议把 `(50.0, 1.0)` 当绝对黑名单。  
更可靠的是检查：

- `data_ok`
- `is_today`
- `last_bar_time`
- DataQualityGate 的 `can_direction`

占位值可以作为日志诊断，不应作为唯一阻断依据。

### 问题 3: swing_bottom / swing_top 是否测过？

目前不能假设它们有 edge。  
我建议先用 Futu 1m 数据做专门回测：

- `swing_bottom WEAK`
- `swing_bottom STRONG`
- `swing_top WEAK`
- `swing_top STRONG`
- 5/10/15/30min MFE/MAE
- 分市场状态：trend / choppy / weak_market / strong_market

没有这个结果前，不应该把它们直接升为主信号。

### 问题 4: K_1M 架构改造工程量如何？

不是一两行。  
只下载 1m 数据很简单，但要进入实盘策略，需要：

- 1m 数据订阅。
- 1m 缓存。
- 1m 指标。
- 1m/5m 状态同步。
- 新触发器。
- 新回测。
- 新防刷屏策略。

我建议先不动生产逻辑。

### 问题 5: heartbeat 共享态 bug + OpenD 监控是否今晚修？

heartbeat 共享态 bug 已经处理：

- `focus_manager.py` 的心跳优先读 `session._last_data_quality`。
- `heartbeat.py` 也优先读 `session._last_data_quality`。

OpenD / K_5M stale 监控仍值得做，但应该保持简单：

- 不改交易策略。
- 只在 `last_bar_time` 超过阈值时告警。
- 不自动重构策略。

---

## 我建议的下一步

### P0: 不改变交易风格，只修安全漏洞

1. `check_direction_trend()` 内部加 fail-closed：
   - `data_ok=False` 不触发。
   - `is_today=False` 不触发。
   - `last_bar_time` 缺失不触发。

2. `direction_trend` 推送降级：
   - 不给一键下单按钮。
   - 文案改为“市场背景: 偏多/偏空”。
   - 不再显示“建议买 RKLX/RKLZ”。

3. 在 scorecard 中记录：
   - `direction_trend` 暂不作为主交易信号。
   - 后续恢复主信号地位必须有 Futu 数据回测证明。

### P1: 回测 swing_top / swing_bottom

用现有 Futu 1m 数据，复用 `backtest_v0531_vs_v0535.py` 的评分逻辑，改成按 trigger 分组。

重点回答：

- 哪类 trigger 有真实 edge？
- 哪类只会制造噪音？
- 哪类只适合持仓管理，不适合开仓？

### P2: 再考虑 1m 入场系统

只有当 P1 找到可用 edge 后，才值得设计 1m 入场确认。

---

## 最终态度

我不建议：

- 直接回滚 v0.5.31。
- 继续盲目放宽 v0.5.35。
- 盘中热修 1m 双层系统。
- 继续把 `direction_trend STRONG` 当作主交易入口。

我建议：

- 先承认 `direction_trend` 没有足够短线 edge。
- 把它降级为市场背景。
- 用 Futu 1m 数据寻找真正有 edge 的 trigger。
- 让持仓风控和数据质量门禁继续作为系统核心保护层。

一句话：

> 不是 v0.5.31 更好，也不是 v0.5.35 更好，而是 `direction_trend` 本身不够资格继续当主交易信号。

