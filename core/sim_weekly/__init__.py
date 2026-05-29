"""
SimWeekly — 独立周度模拟盘(自主·收益最大化版)。

设计文档: docs/discussion_2026-05-22_sim_weekly_module.md

硬约束:
- 纯纸面,永不下真单。
- 完全独立:不 import core.focus / core.agents,不改任何现有模块。
- 自有状态目录 data/sim_weekly/,不碰 portfolio_*.json / race。
"""
VERSION = "v0.1.0"
