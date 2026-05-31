# RKLX 97 Trade Review - 2026-05-22

VERSION : v0.1.0
DATE    : 2026-05-23
DEPENDS : data/review/2026-05-23/futu_recent_deals.json, data/review/2026-05-23/kline_1m_RKLX.json, data/review/2026-05-23/kline_1m_RKLB.json, data/review/2026-05-23/triggers.json

## Scope

This is a read-only incident review. It does not change strategy code.

本复盘只核对周五晚间 RKLX 97 买入后一路回撤到 90.25 卖出的交易路径、信号提示和系统缺口，不直接修改策略。

## Trade Timeline

| ET Time | Action | Qty | Price | Gross Result |
|---|---:|---:|---:|---:|
| 2026-05-22 04:33:03 | BUY | 20 | 86.21 | - |
| 2026-05-22 09:16:54 | SELL | 14 | 87.60 | +19.46 |
| 2026-05-22 09:26:23 | BUY | 28 | 88.70 | - |
| 2026-05-22 09:36:09 | SELL | 34 | 94.00 | +195.14 |
| 2026-05-22 10:01:53 | BUY | 35 | 92.00 | - |
| 2026-05-22 10:27:03 | SELL | 35 | 94.80 | +98.00 |
| 2026-05-22 10:44:43 | BUY | 34 | 97.00 | - |
| 2026-05-22 12:55:48 | SELL | 34 | 90.25 | -229.50 |
| 2026-05-22 14:10:05 | BUY | 33 | 92.61 | - |
| 2026-05-22 15:55:09 | SELL | 33 | 93.72 | +36.63 |

粗略看，前几笔方向跟随效果很好，最后 97.00 买入后在 90.25 割肉，是当天最大伤害来源。

## 1m Price Path Around The 97 Entry

| Window | RKLX Path | Interpretation |
|---|---|---|
| 10:25-10:44 ET | 92.40 low -> 98.58 high | 买入前 18 分钟已经拉升约 6.7%，属于波段末端追入风险区。 |
| 10:44-11:02 ET | 98.09 high -> 93.37 low | 买入后 18 分钟快速回撤约 4.8%，短线结构明显失效。 |
| 11:02-12:15 ET | 93.37 low -> 97.225 high | 曾反弹回到接近成本位置，这是系统应该重点提示“回到成本附近，重新处理仓位”的窗口。 |
| 12:15-12:47 ET | 97.225 high -> 90.01 low | 反弹失败后进入第二段下跌。 |
| 10:44-12:55 ET | 98.09 high -> 90.01 low | 持仓窗口最大不利波动约 -7.2%，最终 90.25 卖出。 |

## Signal Audit

### Before Entry

- 10:32 ET: `large_day_gain / neutral / WEAK`
  - Message: 大涨后回调风险增加，建议逐步锁定利润，不建议此时追加买入。
  - 这是有效风险提示，但它不是方向失效信号，也没有直接压制后续追多。
- 10:43 ET: `near_resistance / neutral / WEAK`
  - Message: 准备卖出预警，持有 RKLX 建议准备分批止盈，不要等到顶。
  - 这条非常接近高点，方向上是对的，但强度和文案仍偏“准备”，没有明确标注“此处不适合新开多”。
- 10:44 ET: `direction_trend / long / STRONG`
  - RKLB 1m 波段复盘把它标成下跌波段中的 wrong-side STRONG。
  - 这是本次最关键的误导信号：它在 10:43 顶部后 1 分钟仍给出看多强信号。

### During Holding

- 10:51 ET: `stop_loss_warning` RKLX -2.1%，接近止损。
- 10:58 ET: `stop_loss_warning` RKLX -3.1%，已破止损。
- 12:12 ET: `direction_trend / long / STRONG`，提示继续持有。
- 12:24 ET: `large_day_gain / neutral / WEAK`，再次提示回调风险。
- 12:25/12:33/12:43 ET: 连续止损/减仓提示。

问题不在于完全没有提示，而在于提示语义分裂：

- 入场前有顶部/止盈观察，但后续又立刻出现 STRONG 看多。
- 持仓后有止损提示，但缺少“方向是否失效”和“反弹回成本附近如何处理”的统一判断。
- 11:02-12:15 的反弹窗口没有被清晰总结为“从低位反弹到成本附近，若不能继续突破，应重新评估/降低风险”。

## RKLB Wave Coverage

Using Futu 1m bars for local review date 2026-05-23:

- Wave 1: 10:00-10:43 ET, RKLB +3.20%, TIMELY.
- Wave 2: 10:43-11:02 ET, RKLB -2.98%, TIMELY, but contains one wrong-side STRONG:
  - 10:44 ET `direction_trend/long/STRONG/conf=70`.
- Wave 3: 11:02-12:15 ET, RKLB +2.29%, TIMELY.
- Wave 4: 12:15-13:21 ET, RKLB -4.49%, MISS.
- Wave 5: 13:21-14:27 ET, RKLB +3.78%, LATE.
- Wave 6: 14:27-17:20 ET, RKLB -2.71%, WRONG_SIDE, with four wrong-side STRONG long signals.

This confirms the same structural issue seen in prior reports: direction_trend can keep issuing strong long after the top when day_change remains high.

## Root Cause

1. Entry-side and exit-side messages conflict.
   - A risk/near-resistance warning appears, then a STRONG long appears almost immediately after.

2. direction_trend is still too dependent on day_change.
   - At a fresh intraday top, day_change remains very strong, so the detector can still label the market as strong long even after microstructure turns.

3. The bot lacks a position-aware follow-up state machine.
   - For an active RKLX position, the system should output a single state:
     - HOLD_OK
     - TOP_WATCH
     - COST_RETEST
     - INVALIDATED
     - DATA_UNTRUSTED
   - Instead, the current output is a mix of generic entry signals, stop-loss warnings, and neutral risk notes.

4. The stop-loss path is reactive, not explanatory.
   - The user receives “接近止损/已破止损”, but not a higher-level explanation such as:
     - “10:44 追高后，价格已跌破 5m 结构，反弹回成本附近未能继续突破，持仓方向降级。”

## Recommendations For Discussion

### P0: Direction Confidence Cap

Do not silence direction_trend, but cap confidence when the signal is mostly supported by day_change while microstructure is no longer confirming.

Candidate wording:

> 方向偏多，但价格刚从高位回落，微结构未确认，信心封顶中等。

This would have reduced the damage of the 10:44 STRONG long without deleting all long signals.

### P0: PositionFollowupMonitor

For active positions, publish one concise holding state instead of scattered exit alerts.

Minimum states:

- HOLD_OK: direction and structure still support the position.
- TOP_WATCH: near high/resistance, new entry not recommended, consider locking profit.
- COST_RETEST: after drawdown, price rebounds near entry/cost; this is a decision window.
- INVALIDATED: structure breaks; current position thesis no longer holds.
- DATA_UNTRUSTED: indicator data stale; only use price/ATR protection.

For the 97 trade, the missing state was mainly COST_RETEST around 11:02-12:15 and INVALIDATED after the 12:15 failure.

### P1: Entry Suppression At Fresh Top

When a near_resistance / large_day_gain risk warning fires, a following long STRONG signal within a short window should be forced to re-check:

- price still making higher highs?
- price above VWAP?
- RSI slope not rolling over?
- last 3 1m or 5m highs not lower-high?

If not confirmed, keep the signal, but downgrade the wording from “强烈” to “观察/中等”.

## Bottom Line

The 97 trade loss was not just an execution problem. The signal stream gave useful warnings, but then contradicted them with a late STRONG long at the top and did not provide a clean holding-state narrative afterward.

Next engineering work should focus on holding-state follow-up and confidence honesty, not broad strategy rewrites.
