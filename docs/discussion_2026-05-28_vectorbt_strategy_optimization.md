# VectorBT Strategy Optimization Plan / vectorbt 策略优化方案

VERSION : v0.2
DATE    : 2026-05-28
DEPENDS : research/vectorbt_lab/*, scripts/*replay*, data/review/*/triggers.json, docs/STRATEGY_SCORECARD.md

## 0. 结论先行

vectorbt 应作为 **离线策略质检台**，不是实盘信号引擎。

本轮执行目标：

- 先把 `vectorbt_lab` 的方法学地基修正到可信口径。
- 只围绕 RKLB 做验证，RKLB OOS 没跑正前不扩展候选股结论。
- 新模板最多只加一个：`vwap_reclaim_core`。
- 所有结论必须走 walk-forward、扣费、滑点、信号密度、SimWeekly / replay 交叉验证。

不做：

- 不碰 `core/focus/*`。
- 不碰 `bot/*`。
- 不触发 Telegram。
- 不让 LUNR / ASTS / IONQ 进入实盘 watchlist。
- 不在 vectorbt 结果出来当晚直接改实盘策略参数。

## 1. 已锁定的执行答案

| 问题 | 答案 | 理由 |
| --- | --- | --- |
| 第一阶段测 RKLB 还是带候选股？ | 只 RKLB；RKLB OOS 跑正后才扩候选股 | 当前 breakout_core 对 RKLB OOS 未跑正，没资格谈“找下一个 RKLB” |
| 盘前/盘中/盘后是否分开？ | 必须分段独立计分 | premarket / RTH / postmarket 是不同 regime |
| RKLX/RKLZ 是否单独回测？ | 方向用 RKLB，执行统计用 RKLX/RKLZ | 符合实际操作：RKLB 判断方向，RKLX/RKLZ 执行 |
| 收益目标 | 少亏 + 少错 + 稳定抓主波段 | 贴合当前实盘使用方式，不追最大收益 |
| benchmark | v0.5.36 safety base | 当前线上安全基线完整，v0.5.31/v0.5.33 只作历史参考 |

## 2. 前置地基：vectorbt_lab v0.1 P0 已收口

依据 `CLAUDE_REVIEW_2026-05-26_vectorbt_lab_fixes.md`，研究模块必须先完成 6 个 P0：

- P0.1 入场改 next-bar open。
- P0.2 加 0.08% 单边滑点。
- P0.3 walk-forward 切分。
- P0.4 共享参数：RKLB train 选参，候选股 test 套用。
- P0.5 输出 `signal_density_per_day`。
- P0.6 真 `false_breakout_rate`：入场后 5 根 1m 内 stop 比例。

当前状态：

- 已完成。
- 已重跑默认扫描。
- 新结论：`breakout_core` 在 RKLB OOS 上未跑正，因此当前不能用它回答“谁最像 RKLB 且适合复制打法”。

## 3. 第一阶段只加一个新模板：vwap_reclaim_core

新增文件：

`research/vectorbt_lab/vwap_reclaim_core.py`

不新增：

- `orb_core.py`
- `atr_exit_core.py`
- 多模板大网格

选择 VWAP reclaim 的理由：

- RKLB 常见结构是：盘前/早盘跌破 VWAP，随后重新站回 VWAP，再走一段趋势。
- 它比 opening range breakout 更贴近最近复盘里反复出现的“跌破后收复”机会。

硬门槛：

- `vwap_reclaim_core` 必须在 RKLB OOS 段 `fee_adjusted_pnl > 0`。
- `signal_density_per_day >= 0.3`。
- 未达标则不进入候选股横向比较。

## 4. ATR 倍数扫描：只产报告，不改 core

背景：

`_calc_price_targets` 已改成 daily ATR 体系，ATR 本身不再需要从零验证。下一步是扫倍数，看是否有比当前默认更稳的组合。

扫描对象：

- `stop_atr_mult`
- `tp_atr_mult`

输出：

`research/vectorbt_lab/output/atr_multiplier_sweep_YYYY-MM-DD.md`

报告必须包含：

- 每组倍数的 fee-adjusted PnL。
- max drawdown。
- 平均持仓时间。
- T1 命中率。
- stop 命中率。
- 止损后 5 根 1m 内反向 >= 1% 的比例。

红线：

- 这个扫描只给“候选默认值”。
- 不直接修改 `_calc_price_targets` 或任何 `core/focus` 文件。

## 5. 必须补齐的指标

### 5.1 signal_density_per_day

熄火红线：

- `< 0.3 / day` 的模板直接淘汰。
- 即使 PnL 好看，也不能用于实盘方向提示。

### 5.2 wrong_strong_within_held_window

持仓窗口内同方向 STRONG long 次数必须为 0。

这是 RKLX 97 那笔事故的核心：持仓浮亏时，系统继续给同向强信号，会干扰退出判断。

### 5.3 OOS 排序

所有研究报告排序只看：

- `oos_pnl`
- `fee_adjusted_pnl`
- signal density
- drawdown

不允许用全样本 best-of-grid 做主结论。

## 6. 门禁流程

### Step 1: vectorbt walk-forward

- RKLB 数据按时间切 60% train / 40% test。
- 参数只在 train 段挑。
- 报告只用 test 段主结论。

### Step 2: 实盘逻辑 replay

用真实 `run_all_triggers()` 路径复现历史推送。

必测日期：

- 2026-05-14
- 2026-05-16
- 2026-05-18
- 2026-05-19
- 2026-05-21
- 2026-05-22
- 最新交易日

### Step 3: Scorecard + SimWeekly 交叉验证

Step 3.1：

- 更新 `docs/STRATEGY_SCORECARD.md`。

Step 3.2：

- 用 SimWeekly 8 周回放验证同样改动。
- 如果 SimWeekly 平均周收益或最大回撤变差，不上线。

### Step 4: 硬数字上线门槛

任一条不过，不上线：

- `wrong-side STRONG` 不增加超过 `+1/day`。
- `missed-wave` 不增加超过 `+2/day`。
- 2026-05-19 missed-wave 不得高于改前。
- 持仓窗口内 `wrong_strong_within_held_window = 0`。
- `signal_density_per_day >= 0.3`。

## 7. 执行顺序

```text
1. vectorbt_lab v0.1 六个 P0 fix
   已完成

2. 新增 vwap_reclaim_core
   只测 RKLB train/test

3. 若 vwap_reclaim_core RKLB OOS 不跑正
   停止，不扩候选股

4. 若跑正
   才与 breakout_core 做 RKLB OOS 对比

5. 建 replay_live_strategy_vectorbt_bridge.py
   防研究/实盘漂移

6. 做 ATR 倍数扫描报告
   只读，不动 core

7. 写 scorecard + SimWeekly 交叉验证

8. 人工决定是否进入实盘策略讨论
```

## 8. 不允许做的事

- 不碰 `core/focus/*`。
- 不碰 `bot/*`。
- 不改 Telegram 文案。
- 不改 `direction_trend` / `intraday_reversal` 核心逻辑。
- 不把候选股加入实盘 watchlist。
- 不一晚加多个模板。
- 不因单日表现直接改实盘阈值。

## 9. 下一步执行建议

下一步只做一件事：

实现 `research/vectorbt_lab/vwap_reclaim_core.py`，并只在 RKLB 上跑 walk-forward。

交付物：

- `research/vectorbt_lab/vwap_reclaim_core.py`
- `research/vectorbt_lab/run_vwap_reclaim_scan.py`
- `research/vectorbt_lab/output/vwap_reclaim_rklb.md`
- 测试：`tests/test_vectorbt_vwap_reclaim.py`

如果 RKLB OOS 仍为负，本轮 vectorbt 研究结论就是：

> 当前两个简单短线模板（breakout / VWAP reclaim）都不足以替代或优化现有实盘策略，暂时只保留为研究工具，不进入策略改动。
