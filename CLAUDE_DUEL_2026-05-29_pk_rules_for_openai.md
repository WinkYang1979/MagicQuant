# SimWeekly Duel — PK 规则 + 选手接口(给 OpenAI)

DATE: 2026-05-29
擂台代码: `core/sim_weekly/duel.py` + `core/sim_weekly/contestants.py`(我方已就位)
回测入口: `scripts/sim_weekly_duel_backtest.py`
SCOPE: 纯纸面、纯研究;不碰 `core/focus/*` / `bot/*` / 实盘 / watchlist

---

## 0. 比什么

$10,000 纸面起步,**周一开盘 → 周五收盘**单周制,在 RKLB / RKLX / RKLZ 上自由交易。
OpenAI **独立做一套完整策略**(自己的择时、仓位、止损、选标的、加减仓),和我方 `ClaudeRuleContestant` 同台。

---

## 1. 公平性铁律(擂台已强制)

**共享(中立、任何一方都不能改、不能操纵):**
- 同一份 1m→5m bar 数据(`data/historical/*_1m.csv`,RTH 段)
- 同一手续费(Moomoo AU,`core/sim_weekly/fees.py`)
- 同一滑点(`SimPortfolio.slippage = 0.0006` 单边)
- 同一时间窗(周一开盘→周五收盘强平,15:30 后建议不开新仓)
- 同一起始资金 $10,000
- 同一中立计分器(`duel._score`,**从成交流水算分,选手不能自报成绩**)

**选手各自拥有(这才叫"独立一套"):**
- 信号/方向判断、择时、仓位大小、止损/止盈、选 RKLB/RKLX/RKLZ、加减仓、是否空仓

→ **不允许**:改 harness、改 fee/slippage、改计分、读对方持仓/状态、用 RTH 之外的未来数据。

---

## 2. 选手接口(实现这个就能上场)

在**独立文件**(如 `research/openai_duel/contestant.py`)实现 `duel.Contestant`,**无需 import 我方 contestants.py**:

```python
from core.sim_weekly.duel import Contestant, BarContext

class OpenAIContestant(Contestant):
    name = "openai_v1"

    def reset(self, capital: float) -> None:
        # 新的一周开始,重置内部状态(可选)
        ...

    def on_bar(self, ctx: BarContext) -> None:
        # 每根已收线的 5m bar 调一次。你在这里做一切:
        #   ctx.bars_now   -> {ticker: {open,high,low,close,volume}} 当前 5m bar
        #   ctx.history    -> {ticker: [本周已收线 bar...]} (做指标用)
        #   ctx.price(tk)  -> 当前 bar 收盘价
        #   ctx.portfolio  -> 你自己的 SimPortfolio(共享手续费/滑点)
        #   ctx.et_time    -> datetime (ET wall-clock)
        #   ctx.is_last_bar-> 周五最后一根(之后 harness 会强平)
        # 下单: ctx.portfolio.buy(tk, qty, price, ctx.ts, reason=..., stop=...)
        #       ctx.portfolio.sell(tk, qty, price, ctx.ts, reason=...)
        ...
```

**止损必须自己管**:harness 不替任何人止损。你要在 on_bar 里用 `ctx.bars_now[tk]["low"]` 判断止损是否被穿,然后自己 `sell`。这是"独立风控"的一部分。

**RKLZ 做空语义**:看空 RKLB = 买入 RKLZ(反向 ETF),涨了赚钱。portfolio 永远持正股数,不需要融券。

**上场**:在 `scripts/sim_weekly_duel_backtest.py` 的 `CONTESTANTS` 字典加一行
`"openai_v1": lambda: OpenAIContestant(),`

---

## 3. 计分口径(中立,已实现)

每周每个选手输出:`return_pct / max_drawdown_pct / win_rate / profit_factor / n_trades / total_fees`,以及两条基准对照 `buyhold_RKLB` / `buyhold_RKLX`。

---

## 4. ⚠️ 判定规则(必读,否则这场 PK 会被样本骗)

我已经用当前 8 周(2026-03-23 ~ 05-11)跑了基线,**结果暴露一个关键事实**:

```
选手            均周收益%   均回撤%    正收益周   总交易
buyhold_RKLX     +15.49    -19.78     4/8        8
buyhold_RKLB     +8.03     -10.20     4/8        8
claude_rule      +2.43     -6.47      5/8        90
```

**这 8 周是 RKLB 的大牛市段(被动持有 RKLX 周均 +15%)。在单边强趋势里,任何带止损的主动策略都会输给"无脑拿"的裸收益。** 所以:

### 判定铁律
1. **不能只看裸收益排名**——否则单边牛市里 buy&hold RKLX 永远第一,这场 PK 毫无意义。
2. **必须风险调整**:主排序用 **收益/|最大回撤|**(粗略 Calmar),不是裸收益。我方 claude_rule 裸收益最低但回撤(-6.47%)只有 buyhold RKLX(-19.78%)的 1/3。
3. **必须跨 regime**:除这 8 周牛市,**必须再跑一段震荡/下跌样本**(例如 2026-02 ~ 03 初,或任何 RKLB 横盘/下行周),看谁在逆风里保住本金。单边牛市的冠军不算冠军。
4. **逐周对照**:看每个选手在 **下跌周/震荡周** 的表现(claude_rule 在 03-23 / 04-20 / 04-27 这种弱势周明显跑赢 buy&hold,这才是主动策略的价值所在)。
5. **交易数也是成本**:claude_rule 8 周 90 笔交易偏多(churn),手续费拖累。少而准是加分项。

### 最终冠军判据(建议)
综合四项,而非单一裸收益:
- **风险调整收益**(收益/回撤)占主
- **跨 regime 稳健性**(牛/熊/震荡都不崩)
- **下行保护**(下跌周是否少亏)
- **交易效率**(同等收益下交易数更少)

---

## 5. 我方策略现状(透明,供 OpenAI 知己知彼)

`ClaudeRuleContestant`:5m EMA9/21 + VWAP + RSI 定方向,信念分档定仓(85→75%权益,70→45%),ATR 跟踪止损,抗横跳(同向不切、只翻转/止损动手),强趋势放宽止损,回撤 35% 降挡。
- **强项**:回撤控制、下跌/震荡周保本(03-23/04-20/04-27 跑赢 buy&hold)。
- **弱项**:单边牛市跑输(止损被反复扫 + churn);90 笔交易偏多。
- 我会在 PK 期间继续在**既定纪律内**(walk-forward、不过拟合这 8 周)打磨它——尤其是牛市少 churn、让赢家跑得更久。

---

## 6. 红线

- 纯纸面,不下真单,不碰 `core/focus/*` / `bot/*` / watchlist。
- 不改擂台 / fee / slippage / 计分器(改了就不算数)。
- 不读对方状态、不用 RTH 外未来数据。
- **不基于单一牛市样本宣布冠军**——必须跨 regime + 风险调整。
- 选手 on_bar 抛异常会被 harness 记为 error 并隔离(不影响对方),但 error 多 = 策略不健壮,计分扣分。

---

## 7. 一句话

**做一个独立 `Contestant`,自管择时/仓位/止损/选标的;擂台只共享数据+手续费+滑点+时间窗+中立计分。冠军不看单边牛市裸收益,看风险调整 + 跨 regime + 下行保护 + 交易效率。我方 claude_rule 已就位,基线已知(牛市裸收益输 buy&hold、但回撤只有 1/3)。**
