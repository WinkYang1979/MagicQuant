# SimWeekly Duel — 归属地图与协作边界

> **PK 原则:策略各改各的,公共部分谁都可改但须写明原因并登记。**
> Claude 负责 Claude 侧,OpenAI(Codex)负责 OpenAI 侧。交易算法/择时/仓位/止损各自完善,**互不修改对方选手**。

---

## 一、归属地图

### 🟦 一区 — Claude 专属(Claude 自由改,无需知会)

| 文件 | 内容 |
|---|---|
| `core/sim_weekly/strategy.py` | Claude 5m EMA/VWAP/RSI 信号 + conviction(方向/选标的/止损带) |
| `core/sim_weekly/contestants.py` → `ClaudeRuleContestant` | Claude 选手主体(信念定仓/ATR跟踪止损/抗横跳/回撤降挡) |
| `core/sim_weekly/deciders.py` | Claude 决策层(RuleDecider/codex veto/committee),仅 Claude 链用 |
| `core/sim_weekly/engine.py` 的 **Claude 决策/记分逻辑** | import strategy/deciders 那条链(⚠️ 但 `_load_5m/_week_days/TICKERS/RTH_END` 是公共数据层,见三区) |
| `data/sim_weekly/claude_adaptive_*.json`、`claude_adjustment_log.json` | Claude 自适应配置/状态/留痕 |
| `scripts/sim_weekly_claude_nightly_review.py` | Claude 夜间复盘 |

### 🟥 二区 — OpenAI 专属(Claude 绝不修改,只读)

| 文件 | 内容 |
|---|---|
| `core/sim_weekly/openai_contestant.py` | OpenAI 选手(trend long/guard short/超卖禁开/14:30禁开/保本锁/禁同bar反手)。**v1.3 边界(2026-05-30 通报): RKLB 只作信号源, 不交易; 只交易 RKLX/RKLZ。** 这是 OpenAI 的策略选择, 非公共契约; Claude 仍可自主决定是否交易 RKLB。 |
| `data/sim_weekly/openai_adaptive_*.json`、`openai_adjustment_log.json` | OpenAI 自适应配置/状态/留痕 |
| `scripts/sim_weekly_openai_nightly_review.py` | OpenAI 夜间复盘 |

### 🟩 三区 — 公共契约(任一方可改,但须写明原因 + 登记变更日志)

| 文件 | 为何公共 |
|---|---|
| `core/sim_weekly/duel.py` | 中立 harness + `_score`(计分裁判),公平核心 |
| `core/sim_weekly/portfolio.py` | 成交/持仓/盈亏记账,两边共用 |
| `core/sim_weekly/fees.py` | 手续费/滑点模型 |
| `core/sim_weekly/indicators.py` | EMA/RSI/ATR/VWAP 公共指标库 |
| `core/sim_weekly/tg_format.py` | 统一推送格式(角色标签/纸面后缀/防刷屏/humanize_reason) |
| `scripts/sim_weekly_duel_run.py` | 实时 PK runner(喂数据/时间窗/周末结算),对双方对等执行 |
| `core/sim_weekly/engine.py` 的 `_load_5m/_week_days/TICKERS/RTH_END` | 公共数据加载/时间窗工具,被 duel.py 复用 |
| `scripts/sim_weekly_meta_scorecard.py` | 主裁判(夜间调整命中率) |
| `DUEL_TESTSET_2026-05-29.md`、`DUEL_CHARTER_2026-05-29.md` | 冻结测试集 / 章程 |

---

## 二、公共部分修改权限(允许改,但有纪律)

**任一方都有权修改三区文件**,前提是满足以下全部:

1. **只改"对双方对等生效"的东西** —— 数据、费用、滑点、时间窗、结算时序、计分口径、显示格式、bug 修复。
   ❌ 不得借公共文件夹塞入只利于自己一方的逻辑(那属于把策略藏进公共区,违规)。
2. **写明原因** —— 在下方「公共变更日志」登记:日期 / 改动方 / 文件 / 改了什么 / 为何 / 对双方影响是否对等。
3. **跑通三测试** —— `test_sim_weekly` / `test_duel_harness` / `test_openai_adaptive` 全过。
4. **知会对方** —— commit 后由用户转发对方;对方有权复核公平性(如本次 Claude 复核了 Codex 的结算修复)。

判定速记:
- 影响 **某一方怎么交易** → 改自己区;不准碰对方区。
- 影响 **双方看同样市场/同样费用/同样被记分** → 三区,按上述纪律改。

---

## 三、公共变更日志(三区每次改动登记于此)

| 日期 | 改动方 | 文件 | 改了什么 | 原因 | 双方对等? | 复核 |
|---|---|---|---|---|---|---|
| 2026-05-30 | Claude | `tg_format.py` | 新增 `humanize_reason()`:理由速记→大白话(conv79→信心79 等),买入按标的补方向结论 | 用户反馈推送看不懂(违反 CLAUDE.md 大白话规范) | ✅ 仅显示层翻译,不改交易语义/计分;两边推送同等受益 | 待 OpenAI 知会 |
| 2026-05-30 | OpenAI(Codex) | `sim_weekly_duel_run.py` | all-hours 周末结算 bug 修复:settle 先于 trade-window 判断,周末支持 catch-up flatten | 原逻辑周末不结算导致持仓悬空 | ✅ `account.settle` 对任一 account 同一方法/价格/时间触发 | ✅ Claude 已复核:未触及 Claude 逻辑,对双方对等 |

> 二区(选手策略)改动不登记此表,各自记在自己的 `*_adjustment_log.json`。
> 参考:Codex 本次二区改动 = OpenAIContestant 新增 RKLZ 超卖禁开 / 14:30 后禁开 RKLZ / 浮盈保本锁 / 禁同 bar 反手(Claude 不干预)。
