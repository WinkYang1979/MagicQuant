# MagicQuant 数据共享与公平 PK 改造任务 v1.1

请先阅读：

- `CLAUDE.md`
- `DESIGN.md`
- 当前 `core/focus/`
- 当前 `bot/bot_controller.py`
- 当前 Futu / realtime_quote / focus_manager 相关代码

---

## 背景

现在有两套 MagicQuant 系统在晚上同时运行，用于比较不同 AI/策略表现。

目标不是互相替代，而是公平 PK：

1. 两边都可以输出自己的方向判断、交易票和复盘。
2. 但不要两边同时高频读取 Futu，避免触发接口频率限制。
3. 请让当前 Claude 系统承担“行情与账户数据主读取者”的角色。
4. 另一套系统可以读取 Claude 生成的本地共享快照做分析。

---

## 本次目标

新增一个只读共享数据输出层。

Claude 盯盘系统在运行 `/focus RKLB` 时，定期把当前已经读取到的数据写入本地 JSON 文件，供其他系统读取。

**不要新增真实下单。**
**不要修改 broker 凭证。**
**不要改变现有交易策略核心。**
**不要大规模重构。**

---

## 共享快照文件

请输出到：

```text
C:\MagicQuant\data\shared\market_snapshot.json
```

如目录不存在，请自动创建：

```text
C:\MagicQuant\data\shared\
```

写入方式：先写临时文件再原子替换，避免另一套系统读到半截 JSON：

```text
market_snapshot.tmp -> market_snapshot.json
```

---

## 快照内容要求

```json
{
  "schema_version": "1.1",
  "source": "claude_focus",
  "updated_at": "2026-05-11 12:00:00",
  "market_status": "regular",
  "activity_profile": {
    "level": "PEAK",
    "poll_sec": 1.0,
    "scale": 0.75,
    "reason": "RTH 开盘第一小时"
  },
  "master": "US.RKLB",
  "followers": ["US.RKLX", "US.RKLZ"],
  "quotes": {
    "US.RKLB": {
      "price": 0,
      "change": 0,
      "change_pct": 0,
      "high": 0,
      "low": 0,
      "volume": 0,
      "update_time": ""
    },
    "US.RKLX": {},
    "US.RKLZ": {}
  },
  "account": {
    "cash": 0,
    "power": 0,
    "total_assets": 0,
    "market_val": 0,
    "currency": "USD",
    "fetched_at": ""
  },
  "positions": {
    "US.RKLX": {
      "qty": 0,
      "cost_price": 0,
      "current_price": 0,
      "market_val": 0,
      "pl_val": 0,
      "pl_pct": 0
    }
  },
  "indicators": {
    "rsi_5m": 0,
    "vwap": 0,
    "vol_ratio": 0,
    "session_high": 0,
    "session_low": 0,
    "dist_high": 0,
    "dist_low": 0,
    "data_ok": true
  },
  "last_signal": {
    "trigger": "direction_trend",
    "direction": "long",
    "strength": "STRONG",
    "confidence": 82,
    "bias": "bullish",
    "action_intent": "watch_pullback",
    "is_trade_entry": true,
    "is_risk_warning": false,
    "ts": "2026-05-11 00:40:00"
  },
  "focus": {
    "loop_count": 0,
    "push_count": 0,
    "error_count": 0,
    "trend_lock": null,
    "trend_lock_direction": null,
    "trend_lock_since": null,
    "heartbeat_enabled": true
  },
  "producer": {
    "system": "claude",
    "module": "focus_manager",
    "version": "当前 focus_manager 版本"
  },
  "notes": [
    "This file is read-only for other systems.",
    "No order placement is performed by this export.",
    "If updated_at is older than 120s during CLOSED session, or 15s during active session, consider fallback to direct Futu query."
  ]
}
```

**必须包含的字段**：

- `updated_at`
- `source`
- `market_status`
- `quotes`
- `account`
- `positions`
- `indicators`
- `activity_profile`
- `last_signal`
- `focus.loop_count`
- `focus.push_count`
- `focus.error_count`
- `producer`

---

## 写入频率（节流控制）

不要每次主循环都写文件，按市场时段节流：

| 时段 | 写入间隔 |
|---|---|
| PEAK / PEAK+ | 每 5 秒最多写一次 |
| HIGH | 每 10 秒最多写一次 |
| MEDIUM | 每 15 秒最多写一次 |
| LOW / MINIMAL | 每 30 秒最多写一次 |
| CLOSED | 每 60 秒最多写一次 |

写文件失败只打印 warning，不影响盯盘主循环。

---

## 超时 Fallback 约定

另一套系统读取快照时的超时判断：

| 时段 | 超时阈值 | 超时后行为 |
|---|---|---|
| 活跃时段（PEAK/HIGH/MEDIUM） | 15 秒 | 回退到自己的 Futu 读取 |
| 低频时段（LOW/MINIMAL） | 60 秒 | 回退到自己的 Futu 读取 |
| 休市时段（CLOSED） | 120 秒 | 回退到自己的 Futu 读取 |

---

## last_signal 字段说明

每次 Focus 推送信号后，更新 `last_signal` 字段：

```json
"last_signal": {
  "trigger": "direction_trend",
  "direction": "long",
  "strength": "STRONG",
  "confidence": 82,
  "bias": "bullish",
  "action_intent": "watch_pullback",
  "is_trade_entry": true,
  "is_risk_warning": false,
  "ts": "2026-05-11 00:40:00"
}
```

这样另一套系统可以对比“同一时刻我的判断 vs Claude 的判断”，PK 才有实际意义。

---

## 接入位置

在 `core/focus/focus_manager.py` 里新增小函数：

```python
def _write_shared_market_snapshot(session, quotes, indicators_cache, profile, last_signal=None):
    """
    写入共享市场快照到 data/shared/market_snapshot.json
    供其他系统读取，只读输出，不下单。
    """
    ...
```

在 `_focus_loop` 每轮更新 quotes / indicators / positions / cash 之后，根据节流条件调用此函数写入。

**保持改动小，不要重构 focus 主循环。**

---

## 风险控制

1. 只读共享输出，不调用 `place_order` / `modify_order` / `cancel_order`
2. 不改变原有 focus 触发器策略
3. 不改变 broker 凭证读取方式
4. 写文件失败只打印 warning，不影响盯盘
5. JSON 使用 `ensure_ascii=False`
6. 路径使用 `BASE_DIR` 推导，不硬编码
7. 不写任何贬低其他系统的内容，只提供客观共享数据

---

## 公平 PK 标识

```json
"producer": {
  "system": "claude",
  "module": "focus_manager",
  "version": "当前 focus_manager 版本"
}
```

另一套系统输出时应填写自己的 system 名称，保持公平对比。

---

## 测试要求

完成后请输出：

1. 修改了哪些文件
2. 共享快照输出路径
3. 快照字段示例（真实数据填充）
4. 如何启动验证
5. 如何确认没有新增真实下单
6. 如何确认写入频率不会打爆磁盘或接口

**验证流程**：

```text
1. 启动 MagicYang.bat
2. 发送 /focus RKLB
3. 等待 10 秒
4. 检查 C:\MagicQuant\data\shared\market_snapshot.json 是否存在且持续更新
5. 检查 updated_at 字段是否在持续变化
6. 检查 last_signal 字段是否在推送后更新
```

---

## 后续约定

另一套系统会读取：

```text
C:\MagicQuant\data\shared\market_snapshot.json
```

作为优先数据源，按上方超时阈值判断是否需要 fallback。

两边公平 PK 策略，不重复高频打 Futu 接口。
