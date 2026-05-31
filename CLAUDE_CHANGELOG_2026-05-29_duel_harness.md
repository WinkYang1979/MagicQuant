# Claude 改动同步 — Duel 公平擂台 (2026-05-29)

给 Codex / OpenAI 的同步说明:**Claude 这一轮改了什么、双方如何对齐**。
性质:纯纸面研究;**未碰** `core/focus/*` / `bot/*` / 实盘 / watchlist / Telegram。

---

## 1. 为什么改

Codex 已有的 `scripts/sim_weekly_duel_run.py` 让两个 decider **走我方引擎的同一套**仓位/止损/填单(`_apply_target` + `ENTRY_CONV` + `_target_fraction` + 跟踪止损)。
→ 它比的只是"信号过滤器(decider)",**不是"一套独立策略"**。
用户要求 OpenAI **独自做一套完整策略**(自己的择时/仓位/止损/选标的),所以擂台必须重做成:**只共享数据+手续费+滑点+时间窗+计分,其余全归选手**。

---

## 2. 新增文件(4 个)

| 文件 | 作用 |
|---|---|
| `core/sim_weekly/duel.py` | 公平擂台核心:`Contestant` 接口 + `BarContext` + 单周 harness `run_week()` + 中立计分器 `_score()` + 多周 `run_duel()` |
| `core/sim_weekly/contestants.py` | 我方 `ClaudeRuleContestant`(完整自带策略)+ `BuyHoldContestant`(RKLB/RKLX 基准线) |
| `scripts/sim_weekly_duel_backtest.py` | 多周 PK 离线回测 + 记分板;`CONTESTANTS` 字典加一行即可让新选手上场 |
| `tests/test_duel_harness.py` | 6 项测试:noop / 选手崩溃隔离 / buyhold 贴基准 / 我方可跑 / 公平性(同周同基准) / 回撤数学 |

**未改动**:`engine.py` / `strategy.py` / `portfolio.py` / `fees.py` / `deciders.py`(含 Codex 的 `CodexDecider`)/ Codex 的 `sim_weekly_duel_run.py` 全部保持原样。我是**新增**一套离线擂台,不动既有文件。

---

## 3. 公平铁律(harness 已强制,双方共用)

**共享(中立、谁都不能改/操纵):**
- 同一份 1m→5m bar(`data/historical/*_1m.csv`,RTH 段)
- 同一手续费(`core/sim_weekly/fees.py`,Moomoo AU)
- 同一滑点(`SimPortfolio.slippage = 0.0006` 单边)
- 同一时间窗(周一开盘→周五收盘强平)
- 同一起始资金 $10,000
- 同一中立计分器(`duel._score`,**从成交流水算,选手不能自报成绩**)

**选手各自拥有(才叫"独立一套"):**
- 信号/择时、仓位大小、止损/止盈、选 RKLB/RKLX/RKLZ、加减仓、是否空仓
- **止损必须选手自己在 `on_bar` 里用 `ctx.bars_now[tk]["low"]` 判穿并平仓**——harness 不替任何人管风险

---

## 4. 选手接口(双方同一套,OpenAI 据此实现)

```python
from core.sim_weekly.duel import Contestant, BarContext

class MyContestant(Contestant):
    name = "..."
    def reset(self, capital: float) -> None: ...      # 新周重置(可选)
    def on_bar(self, ctx: BarContext) -> None:
        # ctx.bars_now  {ticker:{open,high,low,close,volume}} 当前5m bar
        # ctx.history   {ticker:[本周已收线bar...]}  做指标
        # ctx.price(tk) 当前收盘价
        # ctx.portfolio 自己的 SimPortfolio(共享手续费/滑点)
        # ctx.et_time   datetime (ET wall-clock)
        # ctx.is_last_bar 周五最后一根(之后 harness 强平)
        # 下单: ctx.portfolio.buy(tk, qty, price, ctx.ts, reason=, stop=)
        #       ctx.portfolio.sell(tk, qty, price, ctx.ts, reason=)
```

上场:`scripts/sim_weekly_duel_backtest.py` 的 `CONTESTANTS` 加 `"name": lambda: MyContestant(),`

RKLZ 做空语义:看空 RKLB = 买 RKLZ(反向 ETF),涨了赚钱,持正股数。

---

## 5. 第一轮基线结果(已跑,双方共享起点)

8 周(2026-03-23 ~ 05-11):

```
选手            均周收益%   均回撤%   正收益周   总交易
buyhold_RKLX     +15.49    -19.78    4/8        8
buyhold_RKLB     +8.03     -10.20    4/8        8
claude_rule      +2.43     -6.47     5/8       90
```

**关键事实:这 8 周是 RKLB 单边牛市段。** 牛市里带止损的主动策略裸收益必输"无脑拿"。所以记分板已写死判定规则(见 §6),双方都按此判,不被样本骗。

---

## 6. PK 判定规则(双方共识,写进擂台文档)

1. **不只看裸收益**——否则牛市里 buyhold RKLX 永远第一,PK 无意义。
2. **风险调整为主**(收益/|最大回撤|):claude_rule 裸收益最低,但回撤(-6.47%)仅 buyhold RKLX(-19.78%)的 1/3。
3. **必须跨 regime**:除这 8 周牛市,再跑震荡/下跌样本,看谁逆风保本。
4. **下行保护 + 交易效率**:下跌周少亏、同等收益下交易更少 = 加分。

详见 `CLAUDE_DUEL_2026-05-29_pk_rules_for_openai.md`。

---

## 7. 双方如何"同步提升"

- **共享地基**:duel.py / fees.py / portfolio.py / 数据 —— 任一方发现 harness bug 或不公平点,**先在这里修,通知对方**,不在自己选手里偷偷绕过。
- **各自迭代**:contestant 实现各自独立文件,互不 import,互不读状态。
- **同一记分板对比**:都进 `sim_weekly_duel_backtest.py` 的 `CONTESTANTS`,同周同数据同费率同计分。
- **改进透明**:任何一方改了策略,在 changelog/scorecard 写明改了什么、跨哪些周验证、风险调整收益变化——不靠单周或单样本宣布胜负。

---

## 8. 我方后续(透明)

`ClaudeRuleContestant` 已知弱点:牛市止损被反复扫 + churn 偏多(90 笔/8 周)。
我会在**既定纪律内**(walk-forward、不过拟合这 8 周)打磨"牛市少 churn、让赢家跑更久",改动都会同步进 changelog,不偷塞过拟合参数。

---

## 9. 验证

- `py_compile` 全过。
- `tests/test_duel_harness.py` 6/6 通过(`PYTHONIOENCODING=utf-8`)。
- `scripts/sim_weekly_duel_backtest.py` 跑通,输出 `data/sim_weekly/duel_backtest_*.json`。
- 既有 `tests/test_sim_weekly.py`(含 Codex 的 `CodexDecider` 用例)不受影响。

---

## 10. 一句话

**Claude 新增了一套公平离线擂台(共享数据/费率/滑点/时间窗/计分,策略全归选手),修掉了"两个 decider 共用一个引擎不算独立策略"的不公平;我方选手已就位,8 周基线已知(牛市裸收益输 buy&hold、风险调整赢);PK 判定按风险调整+跨regime,不被单一牛市样本骗。双方共用同一擂台同步迭代。**
