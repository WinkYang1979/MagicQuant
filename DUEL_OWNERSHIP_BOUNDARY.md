# SimWeekly Duel — 文件归属与协作边界

> PK 原则:**各自只优化自己的选手,公共部分改动须经用户转发对方知会。**
> Claude 负责 Claude 侧,OpenAI(Codex)负责 OpenAI 侧。交易算法/策略各自完善,互不修改。

## 一、Claude 专属(Claude 可自由改,无需知会)

| 文件 | 内容 |
|---|---|
| `core/sim_weekly/strategy.py` | Claude 5m EMA/VWAP/RSI 信号 + conviction(决定方向/选标的/止损带) |
| `core/sim_weekly/contestants.py` → `ClaudeRuleContestant` | Claude 选手主体(信念定仓/ATR跟踪止损/抗横跳/回撤降挡)。**`BuyHoldContestant` 是中立基准,见公共区** |
| `core/sim_weekly/deciders.py` | Claude 决策层(RuleDecider / codex veto / committee),仅 Claude 链使用 |
| `core/sim_weekly/engine.py` 的 **Claude 决策/记分部分** | Claude 回放引擎逻辑(import strategy/deciders 那条链)。⚠️ 注意:engine 里的数据加载工具 `_load_5m / _week_days / TICKERS / RTH_END` 被 `duel.py` 复用 → 属**公共数据层(三区)**,改它们须转发;改 Claude 决策逻辑则自由。 |
| `data/sim_weekly/claude_adaptive_config.json` / `claude_adaptive_state.json` / `claude_adjustment_log.json` | Claude 夜间自适应配置/状态/留痕 |
| `scripts/sim_weekly_claude_nightly_review.py` | Claude 夜间复盘脚本 |

## 二、OpenAI 专属(Claude 绝不修改)

| 文件 | 内容 |
|---|---|
| `core/sim_weekly/openai_contestant.py` | OpenAI 选手(profile/trend long/guard short 等) |
| `data/sim_weekly/openai_adaptive_config.json` / `openai_adaptive_state.json` / `openai_adjustment_log.json` | OpenAI 自适应配置/状态/留痕 |
| `scripts/sim_weekly_openai_nightly_review.py` | OpenAI 夜间复盘脚本 |

## 三、公共契约(任何一方改动 → 提交给用户转发对方,不得单方面改)

> 改这些 = 改比赛规则/公平基础,必须双方知会,否则记分不可比。

| 文件 | 为何是公共 |
|---|---|
| `core/sim_weekly/duel.py` | 中立 harness + `_score`(计分裁判),公平性核心 |
| `core/sim_weekly/portfolio.py` | 成交/持仓/盈亏记账,两边共用同一套 |
| `core/sim_weekly/fees.py` | 手续费/滑点模型,公平前提 |
| `core/sim_weekly/indicators.py` | EMA/RSI/ATR/VWAP 公共指标库,两边都 import |
| `core/sim_weekly/tg_format.py` | 统一推送格式(角色标签/纸面后缀/防刷屏/`humanize_reason`) |
| 冻结测试集 `DUEL_TESTSET_2026-05-29.md` | 裁定口径,任何一方不得私改 |
| 章程 `DUEL_CHARTER_2026-05-29.md` | 规则总纲 |
| 元记分卡 `scripts/sim_weekly_meta_scorecard.py` | 主裁判(夜间调整命中率),裁判逻辑须双方认可 |

## 四、流程

1. Claude 改 **一区**:直接做,commit 即可。
2. Claude 发现 **三区(公共)**需改:**不直接改交易语义**;写明改动点+理由,commit 后告诉用户"这是公共部分,需转发 OpenAI"。
3. OpenAI 侧(二区)由 Codex 维护,Claude 只读不写。
4. 共享数据/手续费/滑点/时间窗/计分口径一律走公共契约。

## 五、判定速记

- "只影响 Claude 怎么交易" → 一区,自由改。
- "影响双方怎么被记分/看到同样的市场/同样的费用" → 三区,须转发。
- "OpenAI 怎么交易" → 二区,不碰。
