---
name: rklb-atr-skip-followup
description: 2026-05-22 这周 focus 策略迭代的结论、决策、待办与关键文档
metadata: 
  node_type: memory
  type: project
  originSessionId: b3e0d466-bd83-4405-b900-11f506fc2812
---

## 用户交易画像(贯穿所有设计)
- 用 RKLX/RKLZ(≈2x 杠杆)执行对 RKLB 的方向观点;**只在 STRONG 信号出手,卖出自己决定,保守"有的赚就行"**。
- 红线:**熄火和刷屏都不能容忍**(见 feedback_silence_vs_spam)。
- 真实亏损案例(反复用作验收):RKLX 79.96 买、78.8 参考止损割肉、随后反转到 87.93。

## 已落地:ATR 止损/目标修复(pusher `_calc_price_targets`)
- 根因:旧版拿"最近 20 个 tick(20s~3min)的 stdev"当波动率 → 永远落到 sub-1% 地板 → 止损/目标贴太近,79.96 那笔割在 77→79 噪音里。
- 新版:**per-ticker 日线 ATR(读本地 1m 归档聚合,缓存),盘前安全**;`atr=0.6×dailyATR`,`stop=entry−atr`;地板 杠杆 2.5%/RKLB 1.2%;rr_floor 杠杆 1.6。
- 验收 PASS:RKLX 79.96 → stop **77.08**(<78.8,那笔不会被扫)。
- 注意:日线 ATR 被 cap(杠杆 6%/RKLB 4%)**封顶**,而 RKLB/RKLX 实测 8.68%/14.54% 都超 cap → 实际是"固定 4%/6% 带"。**RKLZ 日线 ATR 算出 81% 是脏数据**(被 cap 盖住,RKLZ_1m.csv 待查)。
- Codex 顺手塞了 `_premarket_low_volume_downgrade`(盘前低量看多 conf 封 65,只降不静默)——属置信度轨,无害但越界。

## 已闭环:direction_skip 诊断日志
- 结论:**方向 guard 不用松**。05-22:505 skip,500 right_skip/5 wrong_skip。"没信号"多是早段只有 WEAK + 用户把观察类当没信号(全天其实 8 条 STRONG)。
- 5 条 wrong_skip 是分类漏洞:`rsi_oversold_guard` 在 RSI20 挡空是对的。**待修:skip_class 加"别追极端"豁免(RSI<30/>70 的拦截归 right_skip)**。

## 已结论(更早):direction_trend 用置信度封顶,不用结构闸门
23 天标定:RTH direction_trend 错误/正确多单在 VWAP/RSI/结构上重叠,无干净分界 → 结构闸门误杀重且回补不可执行 → **走 confidence/STRONG 封顶(只降信心不静默)**,别加硬结构闸门。

## 待办 / 下一步(都在 docs 里写了规格)
1. **long-rebound 浮现延迟**(只读诊断):暴跌见底后第一条 STRONG 做多隔多久、被哪层压住(not_produced/produced_weak/suppressed_top1/cooldown/mutex)。05-22 证据(intraday_reversal/long 内部 212 次只推 2 次)指向 **produced_weak/suppressed → 杠杆在升级/优先级,不是加信号、不是松看空 guard**。
2. **PositionFollowupMonitor**(Codex 提案,未建):持仓看护状态机。成败三点 = **接管而非叠加旧退出触发器**(否则更吵,今天 11 条 stop_loss)、INVALIDATED 复用新 ATR 止损+盘前打折、亏损分支与盈利分支同等严谨。1m 只持仓启用/60s/隔离(复用 ai_judge K_1M)。不给股数比例、不要一键卖出。

## 关键文档
- `docs/discussion_2026-05-22_claude_review_skiplog_and_followup.md`(我的:skip 复盘 + followup 意见 + rebound 延迟规格)
- `docs/discussion_2026-05-22_position_followup_monitor.md`(Codex 的 followup 提案)
- `docs/discussion_2026-05-21_strong_long_calibration_v2.md`(23 天标定 → 置信度封顶)
