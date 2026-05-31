# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
## MagicQuant Project-Specific Guidelines

### Architecture
- All files must include version header with DEPENDS declared
- Python files under C:\MagicQuant\ — do not restructure module hierarchy
- Bot entry: bot\bot_controller.py | Core: core\focus\ | Config: config\

### Code Style
- Comments: bilingual (Chinese + English)
- i18n: use t() for display strings; NEVER use `t` as a loop variable (use `tk`)
- BASE_DIR for all path management — no hardcoded absolute paths

### Trading Logic (Critical)
- RKLB/RKLX/RKLZ = one economic event, not three independent signals
- Position sizing MUST use fetch_account() real cash — never hardcoded amounts
- MIN_BUDGET_USD ($2000) ≠ MIN_ADD_BUDGET_USD ($500) — never conflate these
- Push frequency: minimal is law — no spam alerts
- Strategy changes must update docs/STRATEGY_SCORECARD.md with benchmark comparison.
- Keep the current best live strategy version as benchmark; do not tune from emotion or one screenshot.
- Before accepting a strategy change, replay prior review logs and report before/after signal quality.

### UI
- All HTML/CSS must follow C:\MagicQuant\DESIGN.md

### Futu API 常见问题与规范

**1. K 线缓存冻结**
- 原因：`get_cur_kline` 调用前必须先 `subscribe(KLType.K_5M)`，否则返回空或过期快照
- 规范：每次调用前检查订阅状态；用 `dict` 记录已订阅的 `(ticker, ktype)`，定期强制重订阅（建议每 25 min）

**2. 账户现金读取错误（HKD 聚合）**
- 原因：`accinfo_query` 默认返回 HKD 聚合值，`cash`/`total_assets` 字段是多币种合并数，不是 USD
- 规范：必须指定 `currency='USD'` 参数，或直接读 `us_cash` 字段；禁止使用 `cash`/`total_assets`

**3. `fetch_positions` 偶发返回 list**
- 原因：Futu SDK 在特定错误路径下返回 `list` 而非 `dict`
- 规范：使用前必须检查类型；list 转 dict：`{p['ticker']: p for p in positions if isinstance(p, dict) and 'ticker' in p}`

**4. Snapshot failed（配额打爆）**
- 原因：PEAK 时段主循环频繁调用 snapshot，耗尽 Futu 免费版 API 配额
- 规范：`/detail` 等手动指令优先读 Focus session cache，不打 API；仅 cache miss 时才调 snapshot

**5. `get_cur_kline` 返回 str 而非 DataFrame**
- 原因：`ret == -1` 时 SDK 返回错误字符串（表示未订阅或网络错误）
- 规范：拿到返回值先 `isinstance(result, str)` 检查；是 str 则打印内容并 `return None`，不做后续处理

**6. 浮盈达标误触发**
- 原因：`check_profit_target` 未检查 `pl_val` 正负，亏损状态也会触发
- 规范：`pl_val <= 0` 时直接 `return None`，不进入后续逻辑

**7. VWAP 重启后不重置（跨日污染）**
- 原因：`kline_cache` 重启后延续上次数据，VWAP 混入昨日 K 线
- 规范：计算 VWAP 前过滤 `time_key` 的 ET 日期，只保留当天数据；若当天无数据则回退全量（盘前兜底）

## 数据获取规则（强制执行）

### 优先级
1. Futu OpenAPI（已连接券商，数据最准）
2. Moomoo/Futu 其他接口
3. Polygon.io（次选，需要额外 API key）
4. Yahoo Finance / 其他公开源（最后选项）

### 开发规范
- 新增任何数据获取功能前，先确认 Futu OpenAPI 是否有对应接口
- Futu 有的接口必须优先使用，不允许绕过用第三方
- 每个数据获取函数必须包含：
  1. 成功日志：打印获取到的关键数据
  2. 失败日志：打印具体错误原因
  3. Telegram 播报：关键数据获取失败时推送告警

### 错误处理模板
```python
try:
    data = futu_ctx.get_xxx(...)
    if ret != 0:
        msg = f"⚠️ 数据获取失败: {data}"
        print(msg)
        send_tg(msg)
        return None
    print(f"[数据名] 获取成功: {关键字段}")
    return data
except Exception as e:
    msg = f"⚠️ 数据获取异常: {e}"
    print(msg)
    send_tg(msg)
    return None
```

### 测试要求
- 每个新接口写完必须先测试：python test_xxx.py
- 确认返回数据格式正确再集成
- 测试脚本保留在 tests/ 目录

### 回测数据完整性（强制执行）
**回测/回放发现数据不全时，必须优先用 Futu 接口补足，再做评分；不许用截断数据下结论。**

- 根因教训：`data/review/{date}/kline_*.json` 是盘中滚动 200 根快照，会在保存时刻截断，
  尾段（尤其晚于保存时刻的隔夜/盘后柱）缺失。直接拿它做前向打分会得出**偏悲观的假结论**
  （2026-05-29 用截断数据评出"±0.1% 边缘信号"，补足后实为方向命中 ~65-71%）。
- 规范：任何回放/回测前先校验所需时间窗是否被 K 线完整覆盖（首尾 `time_key` 是否含完整前向窗口）；
  缺口先用 Futu `request_history_kline` 补足落盘，再评分。
- **隔夜/盘前柱必须带 `extended_time=True` + `session=Session.ALL`**，否则默认只回常规时段（RTH），
  漏掉 00:00–04:00 隔夜段（这正是波段拐点回放最关键的时段）。
- 数据源优先级同上：Futu 补足 > 截断的 live 快照；live 快照只代表"机器人当时看到了什么"，不是回测基准。
- 补足工具：`research/backfill_futu_session.py`（已带 extended_time+session=ALL）。

## Telegram 推送规范（强制执行）

### 核心原则
所有 Telegram 推送的技术参数必须配套大白话解读和结论。
纯参数堆砌没有意义，用户看不懂等于没推送。

### 不允许的格式
❌ 只列技术指标和数字：
```
RSI 73.4
MACD +6.43
Max Pain $83
Put/Call 0.78
```

### 必须的格式
✅ 技术参数 + 解读 + 结论：
```
RSI 73.4（严重超买，注意回调风险）
MACD +6.43 金叉确认（多头动能强）
Max Pain $83（短期庄家压制目标）
Put/Call 0.78（市场情绪偏多）

→ 综合结论: 一句话告诉用户该做什么
```

### 适用范围
- 开盘简报
- 盘中信号推送
- 复盘报告
- 风险提醒
- 期权 / 技术面 / 基本面 所有数据展示

### 测试标准
推送内容拿给一个不懂量化的人看，他能理解：
1. 现在是什么状况
2. 应该做什么
3. 风险在哪里

做不到这三点，**重写**。
