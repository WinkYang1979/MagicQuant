# 代码审查报告 — v0.5.34/35 P0 数据门禁

**审查日期**: 2026-05-18
**审查范围**: Codex 提交的 P0 数据门禁修改
**审查者**: Claude (Opus 4.7)

## 审查文件清单

1. `core/focus/data_quality.py` (新增, 329 行)
2. `core/focus/swing_detector.py` (修改, +345/-? 行)
3. `core/focus/pusher.py` (修改, +349/-? 行)
4. `core/focus/heartbeat.py` (修改, +153/-? 行)
5. `core/focus/focus_manager.py` (修改, +466/-? 行)

---

## ⛔ 立即注意：两个阻断级问题

1. **冻结阈值 = 3 → 5m K 柱内必然误报**。这正是 v0.5.33 紧急把 IFD 阈值从 5→30 又直接 kill switch 的根因，Codex 重新引入了相同 bug，阈值还更激进。
2. **静默删除了 v0.5.32 P0#2 (R/R 闸门) 和 P0#3 (RKLX/RKLZ 追多封顶)**，pusher.py header 版本号回退到 v0.5.30。这两个是已验证的安全网，本次"加数据门禁"任务不应触及。

---

## 通过的检查

- ✅ **时区处理正确**：`data_quality.evaluate_data_quality` 内部统一用 ET 计算，`_market_session` 接收 naive ET datetime 时主动 `replace(tzinfo=ET)`，再调 `get_market_status`。无时区混用。
- ✅ **夜盘跨日识别正确**：`_same_trading_day` 处理 `now.hour < 4 and last_bar==(now-1d)`，能识别 0:00-4:00 ET 用上一日 overnight bar。
- ✅ **两层 Gate 结构合理**：detector 侧 `run_all_triggers` 早返回 risk-only + pusher 侧 `format_trigger_message` 最终防线。
- ✅ **None 守卫齐全**：`format_trigger_message` 全部生产调用点都做了 None 守卫；`core/focus/focus_manager.py:1371` 用 `if not msg: continue`。
- ✅ **异常 fail-closed**：`_quality_for_push` try/except 内不抛出（打印后 return None），不会让主循环崩。
- ✅ **`closed` 状态正确阻断**：`market_session == "closed"` → 所有 entry/exit 都拦，符合预期。
- ✅ **bad_data_mode 止损纯净**：`check_stop_loss_warning(bad_data_mode=True)` 不读 `_target_state`、不算 ATR，纯按 `pl_pct` 判，符合"坏数据只看真金白银"的设计。
- ✅ **`_fmt_stop_loss_warning` 正确处理 stop=None** 的 bad_data_mode 分支，不会因 None 崩。
- ✅ **Follower rapid_move 删除符合 CLAUDE.md 规则**（"RKLB/RKLX/RKLZ = one economic event"）。
- ✅ **blocked_signals 双层落盘**：`_record_blocked_signal` + `log_blocked_signal` 落盘 `data/review/{date}/blocked_signals.json`，可复盘。
- ✅ **`_strip_order_buttons` 安全处理** None/empty buttons。
- ✅ **测试 `test_signal_upgrade_v0_5_34.py` 覆盖 05-18 fixture**，关键路径有回归。

---

## 发现的问题

### 严重（阻断上线）

#### [问题 1] 冻结检测阈值 3 → 5m K 柱内必然误报，复刻 v0.5.32→v0.5.33 已修复过的同款 bug

**文件:行号**:
- `core/focus/swing_detector.py:253` — `"indicator_stale_repeat": 3`
- `core/focus/data_quality.py:210` — `repeat_threshold: int = 3`

**描述**:
- `POLL_INTERVAL_REGULAR = 2`s (focus_manager.py:234), `KLINE_FETCH_INTERVAL = 30`s (:238)
- RSI/vol_ratio 由 `calc_all_micro` 从 K_5M 全量 close/vol 计算 (micro_indicators.py:152-153)，单根 5m K 柱内值天然不变
- 阈值=3 意味着 ~6 秒内 3 次相同就 stale=True，远小于 5m 柱周期 300s

**影响**:
- 正常行情下 80%+ 时间方向信号被误判冻结而静默
- 与用户 memory `feedback_silence_vs_spam.md`（"两类失败用户都不容忍：熄火 = 刷屏"）正面冲突
- 与 memory `project_v0_5_33_rollback.md` 记录的 IFD kill switch 完全同源

**修复建议**:
- 阈值至少 30（≈跨 3 根 5m 柱）
- 或改为"每根 bar 内最多触发一次"的 bar-level 检测（用 `time_key` 而非 poll count）
- data_quality 模块同步改

---

#### [问题 2] 静默删除 v0.5.32 P0#2 (R/R 闸门) 和 P0#3 (RKLX/RKLZ 追多封顶)

**文件:行号**:
- `core/focus/pusher.py` — `_compute_rr` 函数整段删 (原 v0.5.32/33 位置)
- `core/focus/pusher.py:1810-1888` — `_fmt_signal_with_conflict` 内 R/R 闸门 + chase-warn 整段删

**描述**:
- pusher.py 头部 VERSION 从 v0.5.33 回退到 v0.5.30；运行时 `VERSION = "v0.5.34"` 但 `_compute_rr` 不复存在
- 这两个闸门是 commit `2eb9355` (v0.5.32 P0#2) 和 `6a09623` (v0.5.32 P0#3) 专门为 RKLX/RKLZ 加杠杆 ETF 追多保护加上的
- commit `36648f2` (v0.5.33 P0 v2) 还在此基础上加了 STRONG 信号豁免

**影响**:
- R/R<1.5 的信号会推（这正是 2026-05-15 248 条 trigger 里 0 条 swing_bottom 的反向修复对象）
- RKLX/RKLZ 单日 +13% 后仍可能推 [强烈] 95% 看多
- 本任务（"P0 数据门禁"）和 R/R/追多闸门是正交的，Codex 不应顺手删

**修复建议**:
- 保留 v0.5.32 R/R 闸门 + v0.5.33 STRONG 豁免 + v0.5.32 chase-warn 三段
- 如确认要删需用户授权

---

### 重要（建议上线前修）

#### [问题 3] swing_bottom 三连收紧 → 实战难以触发

**文件:行号**: `core/focus/swing_detector.py:1037-1048`

**描述**:
- WEAK 一律静默（`if strength == "WEAK": ... return None`）
- STRONG 也要 `_strong_bottom_confirmations` 4 项中至少 3 项过：`support_valid`、`rsi_rebound`、`above_vwap`、`volume_confirm`
- 真实底部 price 大概率 < VWAP（刚跌完），`above_vwap=False`，必须靠其余 3 项全过 → 极难

**影响**:
- 与 v0.5.33 P0 v2 (commit 36648f2) "STRONG 豁免 R/R 闸门，解 swing_bottom 仍堵" 的修复方向完全相反
- 用户当时刚因此事故反弹

**修复建议**:
- 保留 WEAK 跳过即可
- STRONG 不另加 confirmations 闸门，或把 `required` 降到 2

---

#### [问题 4] `_check_signal_followup` 绕过 Gate 直接 send_tg_fn

**文件:行号**: `core/focus/focus_manager.py:1042`

**描述**: 跟进推送"⚠️ 上一条信号可能失效"直接 `send_tg_fn(msg)`，未经 pusher.format_trigger_message，因此不过 Gate。

**影响**: 若 followup 触发时数据已 stale，会推一条无 untrusted note 的告警，且无防御模式按钮策略。

**修复建议**:
- followup 触发前先 `evaluate_data_quality(session, session._last_indicators_cache, update_repeat=False)`
- 坏数据时附 untrusted note 或跳过

---

#### [问题 5] IFD 完全删除但 heartbeat 仍引用 `session._indicator_freeze`

**文件:行号**: `core/focus/heartbeat.py:62` (`freeze = getattr(session, "_indicator_freeze", None)`)

**描述**: `IndicatorFreezeDetector` 类、`_IFD_DISABLED` 常量、`session._indicator_freeze = indicator_freeze` 赋值在 focus_manager 中全部删除。heartbeat 的分支永远 freeze=None，dead branch。不会崩，但状态机推导第一档"风险提醒中(指标冻结)"永远不显示。

**修复建议**: heartbeat 改为读 `session._last_data_quality`（由 swing_detector run_all_triggers 设置）；或删 dead 分支。

---

### 一般（可上线后修）

#### [问题 6] `SESSION_KLINE_MAX_AGE_SEC` 有死键 `premarket`/`afterhours`

**文件:行号**: `core/focus/data_quality.py:40-49`

**描述**: `market_clock.get_market_status` 返回 `pre`/`post`，不返回 `premarket`/`afterhours`。这两个 key 永远 match 不上。

**修复建议**: 删两行，避免后续误用。

---

#### [问题 7] `_quality_for_push` fail-open 静默

**文件:行号**: `core/focus/pusher.py:1056-1064`

**描述**: `session._last_indicators_cache` 为空时返回 None → bad_quality=False → 不拦。生产路径 focus_manager.py:1195 总会设置，但任何手动/外部调用 format_trigger_message 都会 fail-open。

**修复建议**:
- 返回一个 `level="UNKNOWN"` 的 DataQuality 让 Gate 决定行为
- 或显式日志

---

#### [问题 8] focus_manager.py 头部 banner 版本号回退（v0.5.33 → v0.5.22）但代码实际是新的

**文件:行号**: `core/focus/focus_manager.py:4, 219`

**描述**: banner 写 v0.5.28 / FOCUS_MGR_VERSION 写 v0.5.22，但代码引入了 data_quality + warmup mode 等新功能（实际是 v0.5.34/35）。版本号反映不出真实状态。

**修复建议**: 统一 VERSION 为 v0.5.34 + 在 CHANGES 写明本次改动。

---

#### [问题 9] `_push_system_warning` 退回到 v0.5.22 旧格式

**文件:行号**: `core/focus/focus_manager.py:540`

**描述**: v0.5.33 commit `96be98e` "数据异常告警统一格式" 被一并回退，恢复到 `"⚠️ 系统警告\n[{type}] {detail}\n时间"` 单行旧式。CLAUDE.md 强调 TG 推送要"参数+解读+结论"，统一格式正是为此。

**修复建议**: 保留 v0.5.33 统一格式。

---

## 风险点（不算 bug 但需要注意）

- **冷却 30 min 改回 15 min**: `_TG_WARN_INTERVAL = 15 * 60`。若上线后 IFD 或别的 detector 高频触发，告警会更频繁。建议保留 30 min。
- **near_support 改 long → neutral**: weak_market 时 `direction="neutral"`、`action_intent="support_watch"`。下游 `analyze_position_conflict` 等是否能识别 "neutral" 方向值需要回归。
- **`_data_quality_repeat_state` 与 `_indicator_stale_state` 是两套独立状态机但同款逻辑**: 调试时容易混淆，未来可考虑合并。
- **`_order_buttons_allowed` 在 session.start_time 不存在时 fail-open**: 测试场景安全，但若 session 重建路径漏赋值会导致 warmup 跳过。
- **`evaluate_data_quality` 调用 `_market_session(now)` 然后又用 wall clock 时间**: 在长时间不重启的场景下，session 切换在边界附近（如 09:29:58→09:30:01）可能用旧 session 判 max_age。影响很小。

---

## 实战场景模拟（05-18）

复盘 `tests/test_signal_upgrade_v0_5_34.py:198-238` 已锁定的 fixture：

| 场景 | Gate 行为 | 评估 |
|---|---|---|
| 14:03 强烈看空 direction_trend（stale K_5M） | `quality.ok=False`，run_all_triggers 不返回 direction_trend；pusher.format_trigger_message 返回 None | ✅ 设计如期 |
| 14:03-18:03 坏数据期 entry/exit triggers | 全部 detector 侧拦掉，只走 `_risk_only_hits` 推 stop_loss_warning（带 untrusted note，无按钮） | ✅ 设计如期 |
| 19:30 Gate 恢复 | `quality.ok=True` → 信号恢复推送；warmup 60 min 内一键按钮仍禁用 | ✅ 设计如期 |
| **常规交易日 2s poll 内 ~6s 触发 stale=True** | 80%+ 时间方向信号被误拦 | **❌ 问题 1 影响** |

---

## 总体建议

**不建议上线。**

数据门禁框架本身（DataQuality 类、ENTRY/EXIT/RISK 分类、两层 Gate、blocked_signals 落盘、bad_data_mode stop_loss）**架构合理、测试覆盖好**，确实解决了 05-18 stale K 推送的事故。

但本次 PR 同时引入了：

1. **同款已修复 bug（问题 1）**: 阈值 3 直接复刻 v0.5.32 IFD 刷屏事故，且更激进
2. **删除已验证安全网（问题 2）**: v0.5.32/33 R/R 闸门 + RKLX/RKLZ 追多封顶，与本任务目标无关
3. **方向相反的收紧（问题 3）**: swing_bottom 三连收紧 vs 用户刚做的 36648f2 STRONG 豁免

### 建议路径

1. 让 Codex 先单独修问题 1-3:
   - 阈值改 30 (或 bar-level 检测)
   - 保留 R/R 闸门 + chase-warn
   - swing_bottom STRONG 不加 confirmations
   - 数据门禁框架本身可以保留
2. 修完后再跑一遍 `tests/test_signal_upgrade_v0_5_34.py` 确认 05-18 fixture 仍通过
3. 上线前手动验证: 在 RTH 时段开 bot 10 分钟，看打印日志里 `[swing] indicator_stale=True` 是否高频出现；若是，阈值还要再调
