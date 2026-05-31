# 2026-05-23 修改记录: skip 分类修正 + 反弹延迟诊断

状态: 已实现  
范围: 数据/诊断层  
策略影响: 不改变任何方向阈值, 不改变任何触发器是否发射  

## 1. 今日修改原则

本次只处理两个已经达成共识的点:

1. `direction_skip` 的分类口径有误: 极端超卖/超买 guard 拦截不应被简单归为 `wrong_skip`
2. 暴跌后反弹信号浮现太晚, 需要先记录“为什么没浮现”, 不直接改策略

不做:

- 不松 `direction_trend` 参数
- 不改 RSI / VWAP / vol_ratio 阈值
- 不改 `run_all_triggers` 优先级
- 不改 Telegram 主信号文案
- 不实现 `PositionFollowupMonitor`

## 2. 修改 1: direction_skip 极端 RSI 豁免

文件:

- `core/focus/swing_detector.py`

新增函数:

- `_apply_extreme_rsi_skip_override`

逻辑:

- `rsi_oversold_guard` 且 `RSI < 30` 时, 强制归为 `right_skip`
- `rsi_overbought_guard` 且 `RSI > 70` 时, 强制归为 `right_skip`
- 记录 `skip_note`
  - `extreme_oversold_guard`
  - `extreme_overbought_guard`

原因:

极端 RSI 区间本身就是防追空/防追多的保护区。  
05-22 那 5 条所谓 `wrong_skip` 实际上全部发生在 RSI 20-26 的超卖区, 不应被当作 guard 太严。

## 3. 修改 2: rebound_delay 只读诊断日志

文件:

- `core/focus/swing_detector.py`

新增函数:

- `_persist_rebound_delay`
- `_log_rebound_delay`

新增落盘:

```text
data/review/YYYY-MM-DD/rebound_delay.json
```

记录对象:

- `crash_rebound_watch`
- `intraday_reversal_long`

记录字段包括:

- `source`
- `outcome`
- `primary_reason`
- `missing`
- `day_change_pct`
- `low_rebound_pct`
- `high_drawdown_pct`
- `move_pct`
- `rsi`
- `vol_ratio`
- `vwap`
- `vwap_reclaim`

典型 outcome:

- `not_produced`
- `cooldown`
- `produced_weak`
- `produced_strong`

用途:

用于回答:

```text
暴跌见底后, 为什么反弹信号没有及时浮现?
```

而不是马上改参数。

## 4. 测试覆盖

文件:

- `tests/test_signal_upgrade_v0_5_34.py`

新增测试:

1. `test_direction_skip_extreme_oversold_guard_is_right_skip`
   - 持续下跌 + price below VWAP
   - RSI=25
   - 被 `rsi_oversold_guard` 拦截
   - 结果必须是 `right_skip`

2. `test_rebound_delay_logs_missing_and_produced_events`
   - 构造暴跌后反弹不足
   - 确认写入 `not_produced`
   - 构造反弹条件满足
   - 确认写入 `produced_weak`

验证命令:

```powershell
$env:PYTHONIOENCODING='utf-8'
python tests/test_signal_upgrade_v0_5_34.py
```

结果:

```text
Ran 36 tests
OK
```

## 5. 后续使用方式

明天复盘时重点看:

```text
data/review/YYYY-MM-DD/rebound_delay.json
```

如果出现大量:

- `not_produced: low_rebound_below_reversal_pct`
- `not_produced: not_above_vwap`
- `not_produced: rsi_not_in_reversal_band`
- `cooldown`

就可以判断反弹信号到底晚在:

1. 反弹幅度不够
2. 没站回 VWAP
3. RSI 区间要求过窄
4. 冷却/节流压住

只有连续多日确认某个原因导致错过明显反弹, 才进入策略修改讨论。

## 6. 当前结论

本次修改继续遵守:

```text
数据和诊断优先
明确 bug 才修
策略大改先讨论
```

今天没有放宽任何交易信号, 只是让系统更清楚地记录“为什么没有出声”。
