# P0-1a Guard Analysis - 2026-05-21

VERSION : v0.1.0
DEPENDS : data/review_reports/signal_coverage_2026-05-19.md, data/review_reports/signal_coverage_2026-05-20.md, data/review_reports/signal_coverage_2026-05-21.md

本文只分析 P0-1a 是否值得做，不包含策略代码改动。

## 结论

P0-1a 值得先做，但不能只用“从日内高点回撤 >= 2.5%”。

三天干净复盘后，错误最伤的信号集中在两类：

1. `direction_trend/long/STRONG`
   - 典型：05-21 Wave 3 / Wave 5
   - 问题：日内涨幅仍为正，系统继续把它当趋势多。
   - 关键发现：05-21 Wave 5 的错误强多在触发时距离日内高点只回撤约 1%，所以单靠 high_drawdown>=2.5% 抓不住。

2. `intraday_reversal/long/STRONG`
   - 典型：05-20 Wave 7 / Wave 9
   - 问题：系统把弱反弹当成强反转，尤其在长时间下跌/横盘里重复给高置信看多。
   - 关键发现：错误信号常见特征是离日内高点已有 2%~3% 回撤，且近 10-15 分钟动能走弱。

因此 P0-1a 的目标应是“抑制错误高置信做多”，不是新增做空信号。

## 三天复盘后的关键数字

### 2026-05-19

- 波段: 19
- TIMELY 2 / LATE 2 / MISS 14 / WRONG_SIDE 1
- Wrong-side STRONG: 4
- 主要问题:
  - 13:16 ET `direction_trend/long/STRONG conf=80`
    - 当时日内 +3.12%
    - 价格低于 VWAP
    - 距日内高点回撤约 2.9%
    - 近 10-15 分钟走弱

### 2026-05-20

- 波段: 12
- TIMELY 6 / LATE 1 / MISS 3 / WRONG_SIDE 2
- Wrong-side STRONG: 14
- 主要问题:
  - 多条 `intraday_reversal/long/STRONG conf=85~95`
  - 下跌或长横盘过程中反复把反抽当强反转
  - 典型信号:
    - 13:48 ET `intraday_reversal/long/STRONG conf=85`
    - 16:02 ET `intraday_reversal/long/STRONG conf=95`
  - 多数错误信号满足:
    - 距日内高点回撤约 2% 以上
    - 近 10-15 分钟不强，甚至走弱

### 2026-05-21

- 波段: 12
- TIMELY 6 / LATE 1 / MISS 1 / WRONG_SIDE 4
- Wrong-side STRONG: 7
- 主要问题:
  - Wave 3: 下跌 -2.97%，仍有 `direction_trend/long/STRONG conf=65/85`
  - Wave 5: 下跌 -4.86%，仍有 4 条 `direction_trend/long/STRONG conf=80~90`
  - Wave 9: 下跌 -3.94%，末端出现 `swing_bottom/long/STRONG conf=75`

## 为什么不能只用 high_drawdown >= 2.5%

05-21 Wave 5 是最典型的反例：

| ET | Signal | Conf | Price | Day Chg | High DD | 10-15m 动能 |
|---|---|---:|---:|---:|---:|---|
| 15:49 | direction_trend/long/STRONG | 90 | 133.95 | +5.22% | ~1.03% | 10m -0.83%, 15m -0.56% |
| 16:31 | direction_trend/long/STRONG | 80 | 133.87 | +5.15% | ~1.09% | 短线弱反弹 |
| 16:49 | direction_trend/long/STRONG | 80 | 134.28 | +5.47% | ~0.79% | 短线反抽 |
| 17:15 | direction_trend/long/STRONG | 80 | 134.60 | +5.73% | ~0.55% | 10m 小幅走弱 |

如果 guard 只写成 `high_drawdown >= 2.5%`，这些最伤的错误多头几乎全部漏掉。

更合理的判断是：

- `day_chg > 0` 说明系统还在按“日内强势”看多；
- 但如果价格已经不是在推进新高，而是短线动能转弱；
- 此时继续给 `STRONG long` 会误导用户追在回落段。

## 建议的 P0-1a guard 口径

先做“内部抑制”，不新增推送。

### 适用对象

- `direction_trend/long/STRONG`
- 暂时也可观测 `intraday_reversal/long/STRONG`，但不建议第一版直接强行改太多。

### 建议规则 v1

当以下条件同时满足时，不允许继续发 `STRONG long`，降级为静默或 WEAK：

1. `day_chg > +2%`
2. `session_high_drawdown >= 1.0%`
3. 近 10 分钟或 15 分钟动能转弱：
   - `move_10m <= -0.5%` 或
   - `move_15m <= -0.5%` 或
   - 最近 5 根 1m/近似 bars 中至少 3 根收低

说明：

- `1.0%` 看起来低，但 RKLB/RKLX 是高波动标的；05-21 W5 的错误高置信看多就是在回撤约 1% 时开始出现。
- 这个 guard 只压 `STRONG long`，不直接生成 short，因此刷屏风险低。
- 如果触发后要发文案，应该是“多头动能转弱观察”，不是“强空”。

### 可选更保守规则 v0

如果担心误杀上涨段，可以先只在下列更窄场景启用：

1. `day_chg > +2%`
2. `session_high_drawdown >= 1.0%`
3. `move_10m <= -0.5%`
4. `vol_ratio < 1.5`

这会更偏向“抑制低量回落中的高置信做多”。

## 不建议现在做的事

1. 不建议直接新增强空信号。
   - 当前目标是先减少反向误导，而不是把系统改成积极做空。

2. 不建议单独做 dispatch 重排。
   - `intraday_reversal` 和 `breakdown_warning` 自身阈值也会卡住。
   - 单独重排不能解决 W3/W5 的主要错误。

3. 不建议直接放宽 `swing_top` RSI floor。
   - 这可能增加空头提示，但刷屏风险高，需要离线回放。

## 下一步验证标准

实施 P0-1a 后，必须回放至少：

- 2026-05-19
- 2026-05-20
- 2026-05-21
- 2026-05-14
- 2026-05-16
- 2026-05-18

通过条件：

1. 05-21 Wave 3 / Wave 5 的 `direction_trend/long/STRONG` 明显减少。
2. 05-20 的 `intraday_reversal/long/STRONG` 错误高置信需要单独统计，不能被掩盖。
3. 上涨段 TIMELY 不能明显下降。
4. Telegram 推送数量不能明显刷屏。
5. 更新 `docs/STRATEGY_SCORECARD.md`，记录 before/after。

## 当前建议

先做 P0-1a 的离线模拟，不直接上线。

如果离线模拟显示：

- wrong-side STRONG 明显下降；
- 正确上涨段 TIMELY 基本保留；

再把 guard 接入 `check_direction_trend`。

