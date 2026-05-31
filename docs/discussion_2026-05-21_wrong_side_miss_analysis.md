# 2026-05-21 WRONG_SIDE / MISS 波段拆解

VERSION : v0.1
DEPENDS : data/review/2026-05-21/triggers.json, data/review/2026-05-21/blocked_signals.json, data/review/2026-05-21/kline_1m_RKLB.json

## 结论先说

今天复盘里最明显的问题不是“上涨反弹不够敏感”，而是：

1. **盘中从高位回落时，系统仍按较昨收涨幅继续看多。**
   - `direction_trend` 主要依据 `day_change_pct`，也就是当前价相对昨收的涨跌。
   - 当 RKLB 仍然比昨收高 `+3% ~ +5%`，但已经从盘中高点回落 `3% ~ 5%` 时，系统仍容易给 `direction_trend/long/STRONG`。

2. **`direction_trend` 优先级过高，挡住了转弱/破位检查。**
   - 当前调度逻辑是先跑 `check_direction_trend`。
   - 如果 `trend_hit` 已经出现，`check_intraday_reversal` 和 `check_breakdown_warning` 就不会再跑。
   - 所以在 “较昨收仍上涨，但盘中已经明显回落” 的状态，系统会先发看多，然后没有机会发转弱。

3. **急跌段里 near_support / swing_bottom 仍会过早出现。**
   - `near_support` 有时只是“靠近支撑”，但在连续急跌中会变成接飞刀提示。
   - `swing_bottom/long/STRONG` 在 19:50 ET 出现在下跌波段末端，价格确实接近底部，但文案/方向上仍显得像提前看多，容易和持续下跌冲突。

4. **17:40-18:10 ET 的 MISS 不是完全没识别，而是被 DataQualityGate 拦了。**
   - blocked_signals 里有两条 `direction_trend/short/STRONG`。
   - 拦截原因：`indicators are not from current trading day`
   - K_5M last: `2026-05-15 16:00:00`
   - 也就是说，系统当时“想发看空”，但 K_5M 又短暂回到了上周五旧数据，门禁正确拦截了它。

## 波段逐条归因

### W3: 12:06-13:18 ET，下跌 -2.97%，状态 WRONG_SIDE

价格：
- $134.04 → $130.47，约 `-2.67%`
- 15 分钟内已经跌 `-1.25%`

系统实际推送：
- 12:08 `direction_trend/long/STRONG`，conf=65，price=$133.53，RSI=67.6，vol=0.77，VWAP=$129.24，day=+4.89%
- 12:34 `direction_trend/long/STRONG`，conf=85，price=$132.24，RSI=56.1，vol=1.13，VWAP=$129.66，day=+3.87%

归因：
- 因为 `day_change_pct` 仍然是强正数，系统认为大方向仍看多。
- 当时价格仍在 VWAP 上方，所以 `intraday_reversal` 的 `current < vwap` 条件不满足。
- 回落幅度约 2.8%，低于当前 `intraday_reversal_pct=5.0`。

判断：
- 这不是数据问题，是逻辑偏向问题。
- 应该加入 “高位回落观察 / 多头动能衰退” 的中间态，而不是直接继续 STRONG 看多。

## W5: 15:37-17:27 ET，下跌 -4.86%，状态 WRONG_SIDE

价格：
- $134.90 → $129.55，约 `-3.97%`
- 从高点 $135.35 到末端回落约 `-4.29%`

系统实际推送：
- 15:49 `direction_trend/long/STRONG`，conf=90，day=+5.22%
- 16:31 `direction_trend/long/STRONG`，conf=80，day=+5.15%
- 16:49 `direction_trend/long/STRONG`，conf=80，day=+5.47%
- 17:15 `direction_trend/long/STRONG`，conf=80，day=+5.73%

归因：
- 仍是 `day_change_pct` 过度主导。
- 盘后/低量时段，量比很低也没有把高位回落看多降级到“观察/转弱”。
- `direction_trend` 出现后，`breakdown_warning` 没机会执行。

判断：
- 这是今天最大的问题之一：较昨收强势不等于盘中继续看多。
- 需要 “从日内高点回撤” 覆盖 `day_change_pct` 的强看多。

## W6: 17:29-17:39 ET，急跌 -4.92%，状态 WRONG_SIDE

价格：
- $131.57 → $126.45，约 `-3.89%`
- 5 分钟内跌 `-3.71%`

系统实际推送：
- 17:32 `near_support/neutral/WEAK`，price=$127.70，vol=11.54，day=+0.31%
- 17:34 `near_support/neutral/WEAK`，price=$126.17，vol=14.98，day=-0.90%

归因：
- 急跌里 near_support 被触发，但这类提示在连续下杀时不该出现为“支撑机会”。
- 虽然 direction 是 neutral，但复盘里仍算作与下跌波段不匹配，因为它没有提示 “正在急跌/不要接”。

判断：
- near_support 需要新增 fast-drop guard。
- 在 5 分钟跌幅 > 2% 或 120 秒跌幅 > 1% 时，near_support 应该改成 `falling_knife_watch` 或静默，直到出现止跌确认。

## W7: 17:40-18:10 ET，下跌 -3.01%，状态 MISS

价格：
- $127.20 → $124.01，约 `-2.51%`
- 从前高回撤约 `-7.90%`

系统实际推送：
- 无

blocked_signals：
- 17:50 local 记录 `direction_trend/short/STRONG` 被拦
- 17:54 local 记录 `direction_trend/short/STRONG` 被拦
- 原因：`indicators are not from current trading day`
- K_5M last: `2026-05-15 16:00:00`

归因：
- 这里门禁是对的：旧 K_5M 不能放行方向信号。
- 但说明 K_5M 在盘后又发生了短暂回退/污染。

判断：
- 这不是策略阈值问题，是 K_5M 数据源稳定性问题。
- 需要单独追踪为什么已有 05-20 K_5M 后，某些时刻又回到 05-15。

## W9: 19:10-19:58 ET，下跌 -3.94%，状态 WRONG_SIDE

价格：
- $127.97 → $123.01，约 `-3.88%`
- 15 分钟内跌 `-1.54%`

系统实际推送：
- 19:13 `near_support/neutral/WEAK`
- 19:24 `near_support/neutral/WEAK`
- 19:50 `swing_bottom/long/STRONG`，price=$123.49，RSI=30.4，vol=1.39，day=-3.0%

归因：
- near_support 仍在下跌过程中出现。
- swing_bottom 出现在末段，价格接近低点，但因为仍在下跌波段内，被复盘归为 WRONG_SIDE。

判断：
- swing_bottom 不是完全错，但文案和分类太像“看多入场”。
- 在暴跌/弱势行情中，swing_bottom STRONG 应优先改成 `bottom_watch/反弹观察`，需要确认条件后再转为方向看多。

## W12: 05:24-07:03 ET，下跌 -2.48%，状态 LATE

系统实际推送：
- 05:37-06:33 连续 near_support/long
- 06:39 才出现 `target_advance/short/WEAK`

归因：
- 下跌一开始被 near_support 当作支撑机会。
- 真正偏空提示到 06:39 才出现，已经明显滞后。

判断：
- near_support 在弱势/低量/跌破 VWAP 时需要更严格。
- target_advance/short 不能作为主要下跌提示，它太被动。

## 建议的下一步修复方向

### P0: 不让 day_change 独占方向

新增一个“高位回落/多头失效”前置判断：

触发条件建议：
- `day_change_pct > +2%`
- 且从 `session_high` 回落 `>= 2.5%`
- 且最近 10-15 分钟价格为下降
- 或跌破 5m MA / VWAP 附近

输出：
- 不直接强看空。
- 先推：`多头动能转弱 / 高位回落观察`
- 如果继续跌破 VWAP 或 15min 跌幅扩大，再升级为 `breakdown_warning/short`

目的：
- 修 W3/W5 这种“仍较昨收大涨，但盘中正在下跌”的误判。

### P0: 调整 trigger 优先级

现在：
- `trend_hit` 存在时，`intraday_reversal` 和 `breakdown_warning` 不跑。

建议：
- 先计算 `intraday_reversal` / `breakdown_warning`，或者至少允许它们覆盖 long trend。
- 当出现 `long trend` 与 `high_drawdown` 冲突时，降级 long 为观察，不推 STRONG 看多。

### P1: near_support 增加 falling-knife guard

触发以下任一条件时，near_support 不应推“买入/看多机会”：
- 5 分钟跌幅 <= -2%
- 120 秒跌幅 <= -1%
- 从日内高点回撤 >= 5%
- 价格低于 VWAP 且仍在创新低

替代输出：
- `支撑观察，仍在下跌，不接`
- 或直接静默，直到 5m K 线出现止跌/收回。

### P1: swing_bottom 在弱势行情中改名

在日内跌幅 < -2.5%、价格低于 VWAP、或刚经历急跌时：
- 不叫 `swing_bottom/long/STRONG`
- 改成 `bottom_watch/反弹观察`
- 文案强调：等站回 VWAP / 放量反弹 / 前高突破。

### P2: K_5M 回退专项

17:50-17:54 ET 的 blocked 说明：
- 今天不是只有 05-18 出现 K_5M 冻结。
- 05-21 当天也出现过 K_5M 回退到 `2026-05-15 16:00:00`。

建议单独记录：
- 每次 `last_bar_time` 倒退
- 当前订阅状态
- get_cur_kline 返回来源
- 是否发生 unsubscribe/resubscribe

这属于数据源稳定性，不建议和策略阈值混在一起改。

## 本次不建议立刻做的事

- 不建议简单降低 short 阈值。
- 不建议把所有 near_support 静默。
- 不建议回滚掉 DataQualityGate。
- 不建议用一个截图直接调大/调小 RSI 阈值。

更稳的顺序：

1. 先改高位回落覆盖 day_change 的逻辑。
2. 再改 near_support falling-knife guard。
3. 用 `2026-05-21` 复盘重跑，看 W3/W5/W6/W9/W12 是否改善。
4. 再拿 `2026-05-14 / 2026-05-16 / 2026-05-18 / 2026-05-20` 回放，确认没有把上涨日误杀。

