# STRONG Long Calibration - 2026-05-21

VERSION : v0.1.0
DEPENDS : signal_coverage_2026-05-19.md, signal_coverage_2026-05-20.md, signal_coverage_2026-05-21.md

本文是只读标定分析，不包含策略代码改动。

## 背景

Claude 指出一个重要问题：如果只把 guard 加在 `check_direction_trend` 内部，救不了 05-20。

复盘数据支持这个判断：

- 05-21 的 wrong-side STRONG 主要来自 `direction_trend/long/STRONG`
- 05-20 的 wrong-side STRONG 主要来自 `intraday_reversal/long/STRONG`

因此，问题不是一个触发器坏了，而是多个触发器都会在“结构已经转弱”时继续发高置信做多。

## 样本范围

抽取 05-19 / 05-20 / 05-21 三天全部 RKLB `STRONG long` 样本：

- `direction_trend/long/STRONG`
- `intraday_reversal/long/STRONG`
- `swing_bottom/long/STRONG`

并按所在波段归类：

- `correct_up`: 出现在上涨波段
- `wrong_down`: 出现在下跌波段
- `no_wave`: 不在当前 ZigZag 主要波段内

## 关键统计

### direction_trend/long/STRONG

| 类别 | 样本数 | high_dd 中位数 | move10 中位数 | move15 中位数 | price > VWAP |
|---|---:|---:|---:|---:|---:|
| correct_up | 13 | 0.79% | +0.40% | +0.85% | 12/13 |
| wrong_down | 10 | 1.09% | +0.15% | +0.11% | 6/10 |

判断：

- `high_dd` 有差异，但高度重叠。
- `move10/move15` 有差异，但也不干净。
- `price < VWAP` 能抓一部分错误，但抓不住 05-21 W5 那批最伤的错误，因为它们仍在 VWAP 上方。
- 所以 direction_trend 不能只靠单一阈值判断，尤其不能只靠 `high_dd >= 2.5%`。

### intraday_reversal/long/STRONG

| 类别 | 样本数 | high_dd 中位数 | move10 中位数 | move15 中位数 | price > VWAP |
|---|---:|---:|---:|---:|---:|
| correct_up | 5 | 0.40% | +0.58% | +0.99% | 5/5 |
| wrong_down | 9 | 2.24% | -0.47% | -0.47% | 9/9 |

判断：

- `intraday_reversal` 的正确/错误样本分界更清楚。
- 错误样本通常满足：
  - 已从日内高点回撤约 2% 以上；
  - 近 10-15 分钟动能不再向上；
  - 仍在 VWAP 上方，所以 `price < VWAP` 对它无效。
- 这说明 “VWAP 闸门” 不是通用解法。

### swing_bottom/long/STRONG

样本少，但 05-21 W9 那条：

- `swing_bottom/long/STRONG conf=75`
- 出现在下跌波段末端附近；
- 离真实底部不远，但仍在下跌过程中；
- 更像“底部观察/反弹待确认”，不应该按普通强做多处理。

## 重要校正：跨时段合并会污染标定

05-20 的 W9 是一个 764 分钟跨时段波段：

- 05-19 15:17 ET -> 05-20 04:01 ET
- 报告把很多夜间/盘前 `intraday_reversal long` 算进同一个下跌波段。

这会放大 wrong-side 统计，也会让 `high_dd` 参照几小时前的高点，阈值意义变弱。

所以在正式定策略阈值前，必须先修复复盘 labeler 的 session 切分：

- RTH
- premarket
- afterhours
- overnight

至少要把跨时段波段标记出来，并从策略阈值标定里排除。

## 对 P0-1a 的修正意见

原建议：“在 `check_direction_trend` 内部加 guard”范围太窄。

更合理的是做两层：

### 第一步：仍先做测量层

1. 给复盘 labeler 增加 session 切分或跨时段标记。
2. 重跑 05-19 / 05-20 / 05-21。
3. 对排除跨时段后的 RTH / 同 session 波段重新统计 wrong-side STRONG。

### 第二步：再做触发器无关的 STRONG-long 发射闸门

适用范围不应只限于 `direction_trend`：

- `direction_trend/long/STRONG`
- `intraday_reversal/long/STRONG`
- `swing_bottom/long/STRONG`

这类信号在真正发出前，统一过一个“结构否决”检查。

## 当前可候选的结构否决条件

以下只是候选，必须先离线回放：

### 对 direction_trend

方向正确/错误重叠较多，建议保守：

- `day_chg > +2%`
- `high_dd >= 1.0%`
- 且满足以下任一：
  - `move10 <= -0.5%`
  - `move15 <= -0.5%`
  - 近 15 分钟 high slope < 0 且 close slope < 0
  - `price < VWAP`

这个规则可以抓一部分明显转弱，但不保证抓完 05-21 W5 后半段。

### 对 intraday_reversal

分界更清楚，可以更果断：

- `high_dd >= 1.8%`
- 且 `move10 <= 0` 或 `move15 <= 0`

或者：

- `high_dd >= 2.0%`
- 且近 15 分钟 high slope <= 0

这类规则对 05-20 的错误 `intraday_reversal/long/STRONG` 更有效。

### 对 swing_bottom

不建议直接砍掉。

建议改成：

- 在下跌波段/弱势市场中，`swing_bottom STRONG` 文案降为“底部观察/反弹待确认”；
- 只有站回 VWAP 或出现明确 1m/5m 结构反转，再升级为做多方向。

## 当前结论

Claude 的提醒是对的：现在不应该直接上线 P0-1a。

正确顺序应改为：

1. 先修复 session 切分，解决跨时段合并污染。
2. 重跑 05-19 / 05-20 / 05-21。
3. 用排除跨时段污染后的样本，重新标定 STRONG-long 统一闸门。
4. 如果仍能稳定区分 wrong-side 与 correct-up，再做离线模拟。
5. 模拟通过后才接入策略代码。

## 对下一步的建议

下一步先做复盘 labeler 的 session 切分，这是纯测量层改动，策略风险为零。

不要现在直接改 `direction_trend` 或 `intraday_reversal`。

