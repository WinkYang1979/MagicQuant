# MagicQuant P0.1 今晚开盘前防御修复说明（Codex）

日期：2026-05-18  
范围：在 P0 数据质量门禁基础上，采纳 Claude 二次反馈，补齐今晚实盘前最关键的安全防线。  

## 1. 本次目标

这次不继续优化收益策略，目标只有一个：防止系统在数据不可信时继续误导交易，并尽量不完全错过今晚行情。

具体目标：
- 坏 K_5M / 冻结指标不能产生方向、抄底、止盈、target_advance 等交易建议。
- 坏数据下仍保留持仓风险提醒，但只按真实浮亏，不再使用技术指标。
- 启动后前 60 分钟禁用一键下单按钮，让用户先观察 Gate 是否正常。
- 方向信号发出后，如果市场快速反向，主动提醒“上一条信号可能失效”。
- 所有被拦截信号落盘，便于第二天复盘。

## 2. 主要修改文件

- `core/focus/data_quality.py`
- `core/focus/swing_detector.py`
- `core/focus/pusher.py`
- `core/focus/focus_manager.py`
- `core/focus/heartbeat.py`
- `config/settings.py`
- `scripts/pre_open_check.py`
- `tests/test_signal_upgrade_v0_5_34.py`
- `tests/fixtures/review_2026_05_18_triggers.json`

## 3. DataQualityGate 分段阈值

K_5M 新鲜度不再统一用 10 分钟，而是按美股 session 分段：

- regular: 360 秒
- pre / post: 600 秒
- overnight: 1200 秒
- closed: 直接 BLOCK

检查项包括：
- `data_ok == True`
- `is_today == True`
- 最近 K_5M 时间属于当前交易日/可接受 overnight session
- K_5M 未超过当前 session 的最大年龄
- RSI + vol_ratio 没有连续 3 次完全相同

命中坏数据时：
- `direction_trend / swing_bottom / near_support / rapid_move / target_advance / profit_target_hit` 会被阻止
- `stop_loss_warning` 进入风险兜底模式

## 4. 坏数据止损改为纯浮亏模式

Claude 指出原方案里“坏数据下仍保留 stop_loss_warning”有隐患，因为技术止损位本身可能也是坏指标算出来的。现在已改为：

- `pl_pct <= -3%`: 风险提示
- `pl_pct <= -5%`: 强风险提醒
- `pl_pct <= -8%`: 立刻人工决策

坏数据模式下：
- 不使用 ATR
- 不使用 VWAP
- 不使用旧技术止损位
- `stop=None`
- 文案明确写明：技术指标不可用，本提醒只按真实持仓浮亏百分比触发，请人工判断。

## 5. 一键按钮防御

新增配置：

```python
ALLOW_ONE_CLICK_BUTTONS = True
ONE_CLICK_BUTTON_WARMUP_SEC = 3600
```

行为：
- 启动后前 60 分钟，方向信号可以显示，但所有 `focus_order_*` 一键按钮会被移除。
- 数据质量异常时，一键按钮也会禁用。
- 启动时会推 Telegram：

```text
⏱️ 防御模式启动
前 60 分钟一键按钮已禁用
仅推送信号供参考
60 分钟后数据正常才自动恢复
```

这条是为了防止 DataQualityGate 今晚第一次实战时漏过坏数据，避免用户一看到 STRONG 就直接点按钮。

## 6. blocked_signals 落盘

新增落盘路径：

```text
data/review/YYYY-MM-DD/blocked_signals.json
```

记录字段包括：
- `ts`
- `source`
- `trigger`
- `ticker`
- `direction`
- `strength`
- `reason`
- `last_bar_time`
- `would_have_pushed`
- `quality`

detector 前置门禁和 pusher 最终门禁都会记录。这样第二天复盘可以看见“系统本来想推什么，但被拦住了”。

## 7. SignalFollowupMonitor 轻量版

新增方向信号后的持仓看护：

- 推送 `direction_trend` 后，记录方向、RKLB 当时价格、目标 follower。
- 如果用户持有目标 follower：
  - RKLB 反向波动超过 1.5%，或
  - follower 浮亏超过 1%
  - 推送“上一条信号可能失效”

目的：补上 05-18 事故中 14:03 看空信号后，系统直到 18:03 才第一次止损提醒的空窗。

## 8. 开盘前健康检查脚本

新增：

```text
scripts/pre_open_check.py
```

检查：
- K_5M 订阅成功
- 最近 K 线时间小于 60 秒
- `has_indicators=True`
- `is_today=True`
- RSI 不是默认 50.0
- RSI/vol_ratio 不在历史冻结黑名单：
  - `(43.1, 4.94)`
  - `(43.1, 5.82)`
  - `(57.9, 6.58)`

失败：
- 打印 JSON 结果
- 推 Telegram 告警
- exit code = 1

成功：
- 推 Telegram 通过提示
- exit code = 0

注意：这个脚本需要在真实 Futu OpenD / moomoo SDK 环境运行。Codex bundled Python 没有券商 SDK，所以这里只做语法编译，未做实盘连接检查。

## 9. format_trigger_message 安全性

已审计当前运行主路径 `core/focus/focus_manager.py`：
- `format_trigger_message()` 返回 `None` 时会 `continue`
- 不会再把 `None` 当作消息发送

仓库里有历史备份/重复目录：
- `core_focus/`
- `core/agents/`
- `DEPLOY_AI_RACE/`
- `dashboard/`
- `files/`
- `.bak`

本次只修改 AGENTS.md 指定的主路径 `core/focus/`，避免误碰非运行路径。如果部署脚本实际使用了重复目录，需要另行同步。

## 10. 回归测试

保留并扩展三天事故样本：

- `tests/fixtures/review_2026_05_14_triggers.json`
- `tests/fixtures/review_2026_05_16_triggers.json`
- `tests/fixtures/review_2026_05_18_triggers.json`

新增覆盖：
- 05-18 第一条冻结 K_5M 强烈看空必须被 DataQualityGate 拦截
- pusher 最终门禁必须返回 `None`
- 坏数据 stop_loss_warning 可以推，但不能带按钮
- 坏数据止损只按真实浮亏触发，`stop=None`
- 启动 warmup 期间方向信号不能带一键下单按钮

验证结果：

```text
python -B -m unittest tests.test_signal_upgrade_v0_5_34
Ran 9 tests
OK
```

语法编译：

```text
compile ok
```

## 13. 中文乱码回归修复

Claude 复核发现：恢复 R/R 闸门时，`_fmt_signal_with_conflict()` 里重建 `conf_line / direction_line / lines` 的一段文案出现中文乱码，会影响所有方向类 Telegram 推送。

已修复：

- 删除旧乱码块，不再保留死代码。
- 用 UTF-8 正常中文重建：
  - `信心`
  - `盈亏比`
  - `高位追多,降级观察`
  - `方向`
  - `━━━━━━━━━━━━━━`
- `tests/test_signal_upgrade_v0_5_34.py` 增加断言：
  - 输出必须包含 `信心`
  - 输出必须包含 `方向`
  - 输出不得包含乱码片段 `淇`

验证：

```text
python -B -m unittest tests.test_signal_upgrade_v0_5_34
Ran 9 tests
OK

compile ok
```

## 11. 今晚使用建议

开盘前：
- 先运行 `scripts/pre_open_check.py`
- 任一检查失败，今晚不要按系统信号跟单

启动后：
- 前 60 分钟系统会自动禁用一键按钮
- 这段时间只观察信号和 Moomoo K 线是否一致
- 数据正常并且过了 warmup，按钮才会恢复

本次修复不承诺“系统可靠赚钱”，只承诺新增了几道防线：坏数据先静默，风险只按真实浮亏，一键下单先冷却，信号反向会早提醒。

## 12. Claude 复核后的阻断问题修正

Claude 复核指出了一个真正的阻断问题：`indicator_stale_repeat=3` 会在 2 秒轮询、5m K 线未换柱时把正常不变误判为冻结，等于复刻 v0.5.32/33 的假阳性问题。

已修正：

1. 冻结重复阈值从 3 改为 30：
   - `core/focus/swing_detector.py`
   - `core/focus/data_quality.py`
   这样不会在单根 5m K 线内几秒钟就误判冻结。

2. 恢复 R/R 闸门和 RKLX/RKLZ 高位追多封顶：
   - R/R < 1.5 时，WEAK 信号阻断，STRONG 信号豁免
   - 1.5 <= R/R < 2.0 时，信心上限 60
   - RKLX/RKLZ 单日涨幅 >= 10% 时，long 信号降级并提示高位追多

3. swing_bottom 收紧改为只在弱势行情中生效：
   - WEAK 仍然只记录不推送
   - STRONG 在非弱势行情中不额外加确认闸门
   - STRONG 在弱势行情中需要 2/4 条确认，避免 3/4 过严导致底部信号失效

4. `SignalFollowupMonitor` 推送前补数据质量复核：
   - 坏数据时不会伪装成正常技术判断
   - 文案会附加“技术指标不可用，只按实时价格/持仓盈亏判断”

5. heartbeat 改为读取 `session._last_data_quality`：
   - 不再依赖已删除的 `_indicator_freeze`

6. 系统告警冷却恢复为 30 分钟，避免告警刷屏。

7. `target_advance_trend_cooldown` 从 30 分钟加到 40 分钟：
   - 目的是在冻结阈值放宽后，05-14 趋势日仍然不会重新出现 target_advance/profit_target 过密。

复核后验证：

```text
python -B -m unittest tests.test_signal_upgrade_v0_5_34
Ran 9 tests
OK

compile ok
```
