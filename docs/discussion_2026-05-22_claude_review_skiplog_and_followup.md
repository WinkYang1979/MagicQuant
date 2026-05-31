# Claude 复盘与讨论 — 2026-05-22

范围:(A) direction_skip 日志复盘 / (B) 对 `PositionFollowupMonitor` 讨论稿的意见 / (C) 两条轨别混。
原则:本文只给观点与口径,不含代码改动。

---

## Part A — direction_skip 日志复盘(05-22)

### 主结论:别松方向 guard
全天 **505 条 skip,全是 short 意图,500 right_skip / 5 wrong_skip(99%)**。
blocked_by:`rsi_too_high_for_short` 232 / `vol_too_low_short` 133 / `flip_short_not_confirmed` 81 / `rsi_oversold_guard` 59。
→ "先上日志、不松参数"得到了它该得到的答案:**今天的安静 99% 是对的,方向 guard 没问题,不要因为"没明确方向信号"去松看空门槛。**

### 5 条 wrong_skip 是分类口径漏洞,不是 guard 太严
5 条全挤在 05:04–05:09,全是 `rsi_oversold_guard` 在 **RSI 20–26**(day −4.7%、量比冲到 2.2x)挡 short。RSI 20 追空本就是错的(反弹区),guard 挡得对。是 `skip_class` 规则太糙(只看"持续下行+非震荡+price<vwap"就判 wrong)。
**建议:skip_class 加"别追极端"豁免——oversold/overbought guard 在 RSI<30 / >70 时的拦截一律归 right_skip。** 加完今天真正的 wrong_skip = 0。

### "开盘没信号"是半真
早段(00:00–01:35)确实只有 WEAK 的 near_support/crash_rebound_watch;但全天 54 条、**8 条 STRONG,叙事其实跟得上盘**:
```
04:10 breakdown_warning short STRONG (跌破预警 rsi29.6)
06:05 crash_rebound_watch long c75   (砸完盯反弹)
10:05/10:15 overbought_surge short STRONG (反弹到超买 rsi80-88,别追)
12:53/13:32 intraday_reversal long STRONG (转强确认)
18:08 swing_bottom long STRONG
```
"无动于衷"更多是早段只有 WEAK + 把观察类信号当成没信号。

### 真正的缺口(不是看空 guard):暴跌见底后"做多反弹"信号浮现太晚
用户做多(RKLX)。今天 RSI-20 洗盘底在 **05:04(~124)**,但:
- 最近反弹提示是 **06:05 一条 WEAK** crash_rebound_watch c75(已弹到 126.4);
- **STRONG 的 intraday_reversal/long 拖到 12:53(130.39)** 才出——底到这已涨 5%;
- `intraday_reversal/long` 在 skip 时刻被检测到 **212 次,实际只推 2 次**。
→ 真正被压住、且正是用户想要的,是"见底→做多"反弹信号的**浮现/节流**,不是看空信号。

### 建议的下一个只读诊断(long-rebound 浮现延迟)
测:每次洗盘见底(RSI 极低 + 随后 N 分钟止跌回升)之后,**第一条 STRONG 做多反弹信号隔了多久浮现、被哪一层压住**(cooldown / run_all_triggers top-1 / mutex / 强度未达标)。先量化,再决定动不动。

### 小提醒:退出噪音
今天 **11 条 stop_loss_warning**(skip 时刻 also_emitted 里 stop_loss 出现 239 次),RKLX 今天 −9.6% 用户在扛。这跟"裁退出侧噪音"是同一件事——见 Part B。

---

## Part B — 对 `PositionFollowupMonitor` 的意见

### 总体:赞成,方向对
独立模块 / 持仓才工作 / 1m 只确认不定方向 / 5m 定主结构 / 状态机 + 状态变化才推——这套跟用户诉求("方向优先、波顶及时提示、有的赚就行、卖出自己决定")和我之前对 1m 的判断一致。可以做。

### 但有 6 个会决定成败的细节要拧紧

**1.(最关键)INVALIDATED 的"失效位"必须复用刚修好的 ATR 止损,否则重演 78.8 割肉。**
那笔亏损(79.96 买、78.8 割、反弹到 87.93)的根因是**盘前的过近止损**。如果 INVALIDATED 用一个偏紧的"跌破 VWAP/支撑"就触发,会在**同样的盘前噪音**里再喊一次退出 = 同样的坑。
→ INVALIDATED 的失效价**必须 = 新 ATR 止损那套**(那笔是 ~77.08),并且**盘前/低流动性要打折**(盘前不轻易判失效)。验收必须包含:79.96 这笔在 78.8 那一下**不触发 INVALIDATED**。

**2. 状态机要同等重视"亏损持仓"侧,别只服务"盈利→波顶"。**
TOP_WATCH / TAKE_PROFIT_ZONE 都假设"持有盈利、接近顶"。但用户最近真正的痛是**扛亏损**(79.96→78.8;今天 RKLX −9.6%)。亏损时要回答的不是"波顶",是"这下跌是噪音(拿住)还是真失效(退出)"。
→ 亏损分支(HOLD_OK ↔ INVALIDATED)要和盈利分支一样严谨,且和"区分噪音 vs 失效"绑定(用 ATR 带 + 5m 结构,而不是一碰就喊)。

**3.(第二关键)防"越描越多":持仓时必须 SUBSUME 现有退出侧触发器,而不是叠加。**
现在已经有 `stop_loss_warning`(今天 11 条)/ `drawdown_from_peak` / `profit_target_hit` / `near_resistance` / `overbought_surge` / `swing_top` 在做退出侧提示。PositionFollowupMonitor 再加 TOP_WATCH/TAKE_PROFIT/INVALIDATED,**如果并行,用户会收到更多退出声音,跟"少催卖"的目标背道而驰。**
→ 持仓期间应让 PositionFollowupMonitor **统一这一个声音**(接管/抑制上述退出侧触发器),否则噪音更糟。这是最大设计风险,必须先定清楚归并关系。

**4. 1m 取数(回答待讨论 #1/#2):持仓才启用、60s、隔离订阅、带 staleness guard。**
- 只在有持仓时拉 1m(别全程跑)。
- 60s 足够:1m bar 本就每 60s 才收一根,sub-60s 轮询对 bar 级信号没增益(盘中用最新 tick 即可)。
- **隔离**:复用 `core/focus/ai_judge.py` 那套独立 K_1M 拉取,别动主策略的 K_5M 订阅。
- 这套系统有冻结史,1m 多一条流也会冻——复用 last-bar age/staleness 检测,陈旧就降级回 5m,别拿陈旧 1m 喊失效。

**5. 待讨论 #4/#5:不给股数比例、不要一键卖出。**
用户明确"买卖自己决定、保守、有的赚就行"。
- TAKE_PROFIT_ZONE 只说"可考虑锁定部分利润 + 关键位",**不给比例**。
- INVALIDATED 只给"失效依据 + 失效位",**不要一键卖出按钮**(他自己决定)。
- 待讨论 #3:TOP_WATCH 只进心跳/低调展示;**只有 TAKE_PROFIT_ZONE 和 INVALIDATED 上 Telegram**(状态升级才推),控制推送量。

**6. 验收要加"噪音侧"指标,不能只测"有没有抓到顶/失效"。**
回放 05-19~05-22 时,除了"波顶前给没给 TOP_WATCH""反转给没给 INVALIDATED",必须加:
- **每天 PositionFollowupMonitor 主动推送条数**(目标是 *少*,证明比现状更安静而不是更吵);
- **盘前噪音不触发 INVALIDATED**(79.96/78.8 案例);
- 与被它接管的旧触发器**合计**推送数 before/after(确认总噪音下降)。

---

## Part C — 两条轨别混
- **入场/机会侧**:Part A 的结论是"方向 guard 没问题",真缺口是"暴跌见底后做多反弹浮现太晚"——这是**主策略侧**的下一个只读诊断。
- **持仓/退出侧**:`PositionFollowupMonitor` 管"拿住/减仓/退出"。
两个独立模块,别互相借口径。followup 模块**不碰** `check_direction_trend` / `check_intraday_reversal` / dispatch / 置信度(这点 Codex 稿里已写明,保持)。

---

## Part D — 下一个只读诊断规格:long-rebound 浮现延迟

目的:量化"暴跌见底后,第一条 STRONG 做多反弹信号隔多久才浮现、被哪一层压住"。**纯只读分析,不改任何策略/触发器/参数。** 可先用现有日志做 v1。

### D.1 锚点(05-22 实例)
RSI-20 洗盘底在 **05:04(~124)**;最近的反弹提示是 06:05 一条 **WEAK** crash_rebound_watch c75;**STRONG 的 intraday_reversal/long 拖到 12:53(130.39)**;而 `intraday_reversal/long` 在 skip 时刻被检测到 **212 次,只推 2 次**。说明"反弹做多"是**被压住/没升级**,不是没看到。

### D.2 方法(复用已修好的 session 切分,别跨夜)
1. **找洗盘底**:每个 session 段内,定位"局部低点 + RSI 极端超卖(≤30)+ 随后 Y 分钟内价格回升 ≥X"(确认是个真发生过的可交易反弹,而不是继续阴跌)。X/Y 做参数(起步 X≥1×ATR 或 ≥1.5%,Y≤30min)。
2. **找首条 STRONG 做多浮现**:在 triggers.json 里,该底之后第一条**实际推送**的 `direction_trend/long/STRONG` 或 `intraday_reversal/long/STRONG` 或 `swing_bottom/long/STRONG`。
3. **算两个数**:`latency_min`(底 → 首条 STRONG 做多)和 `missed_pct`(到那时价格已从底部走了多少 = 错过幅度)。

### D.3 关键:把"为什么晚"归层(用现有数据即可)
在"底 → 首条 STRONG 做多浮现"这段窗口里,交叉 `direction_skips.json` 的 `also_emitted` 和 triggers.json,把延迟归到某一层:
- `not_produced`:窗口内检测器压根没产出任何 long-rebound 候选 → **入场阈值太严**。
- `produced_weak`:产出了但全程只到 WEAK(如这段一直有 crash_rebound_watch/intraday_reversal long 但没升 STRONG)→ **强度门槛太严**(05-22 像这类)。
- `suppressed_top1`:产出过 STRONG 候选,但 `run_all_triggers` 选了更高优先级的中性/风险信号(如 stop_loss_warning)顶掉 → **优先级问题**。
- `suppressed_cooldown` / `suppressed_mutex`:被冷却或反向互斥压住。

> v1 用现有日志(triggers.json + direction_skips.json 的 also_emitted)就能区分 `not_produced` / `produced_weak` / 大致的 `suppressed_*`。若需要精确区分 STRONG 候选被哪层吃掉,v2 再加一条轻量"候选强度 trace"(像 skip 日志一样的纯记录,不改发射)。

### D.4 输出与判定门
- 每个洗盘底一条记录:`{bottom_ts, bottom_price, rsi_at_bottom, first_strong_long_ts, latency_min, missed_pct, delay_layer}`。
- 落 `data/review/<date>/rebound_latency.json` + 日级汇总。
- **预设决策门**(攒齐 05-19/20/21/22 这几个有暴跌腿的日子再下结论,别用 1 天):
  - 若延迟主因是 `produced_weak` / `suppressed_top1` → 杠杆在**升级/优先级**(让真实反弹更早升 STRONG、或风险告警别把做多机会顶掉),**不是加新信号、也不是松看空 guard**。
  - 若主因是 `not_produced` → 才考虑反弹入场阈值。
- 不改任何东西,先出这张表。

### D.5 别碰
不改 `check_*` / dispatch / 置信度 / 任何阈值;只新增只读分析脚本与(可选)纯记录日志。`PYTHONIOENCODING=utf-8` 跑。

---

## 一句话
- skip 日志:**别松方向 guard**(今天 99% 该挡);修个分类小漏洞(RSI 极端拦截归 right_skip);真缺口是反弹做多信号浮现太晚 + 退出噪音。
- PositionFollowupMonitor:**可以做**,但成败在三点——INVALIDATED 复用新 ATR 止损+盘前打折、亏损分支同等严谨、**持仓时统一退出声音(接管而非叠加)**。否则会把"少催卖"做成"更吵"。
