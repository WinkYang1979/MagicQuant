"""决策器抽象:RuleDecider(默认,离线确定性) / AgentCommitteeDecider(可选,接 LLM 委员会)。

engine 只依赖 decide(ctx)->target 的接口。回放/测试用 RuleDecider 保持离线、可复现。
AgentCommitteeDecider 仅实时模式用;任何失败(无 key/网络/解析)都回退 RuleDecider,
绝不让 sim 因 agent 问题崩。**不在 import 期触碰 core.agents(惰性 import)。**
"""
from __future__ import annotations

from typing import List, Optional

from . import strategy as strat


class RuleDecider:
    name = "rule"

    def decide(self, ctx: dict) -> dict:
        return strat.decide(ctx)


class CodexDecider:
    """Codex paper-trading overlay. / Codex 纸面操盘覆盖层。

    Research-only: start from the proven rule signal, then veto low-confidence
    RKLZ shorts when RKLB has already turned up for the week.
    仅研究：沿用已有规则信号，在 RKLB 本周转强时过滤低置信 RKLZ 做空。
    """
    name = "codex_overlay_v1"

    def decide(self, ctx: dict) -> dict:
        target = strat.decide(ctx)
        if target.get("direction") != "short":
            return target

        bars = ctx.get("rklb_bars") or []
        if len(bars) < 2:
            return target
        try:
            price = float(bars[-1]["close"])
            week_open = float(bars[0]["open"])
            week_change = (price - week_open) / week_open * 100.0 if week_open > 0 else 0.0
            conviction = int(target.get("conviction") or 0)
        except Exception:
            return target

        # In an up week, weak/medium RKLZ shorts were the main paper-trade drag.
        # 本周已转强时，低/中信心 RKLZ 做空是历史回放主要亏损来源。
        if week_change > 0.0 and conviction < 85:
            return {
                "direction": "flat",
                "instrument": None,
                "conviction": 0,
                "stop_pct": 0.0,
                "reason": f"codex veto weak short in up week ({week_change:+.1f}%)",
            }
        return target


class AgentCommitteeDecider:
    """多模型投票:方向取多数,信念取同向加权均值;工具按信念档(复用 strategy 口径)。"""
    name = "agent_committee"

    def __init__(self, rule_fallback: bool = True, max_tokens: int = 300):
        self.fallback = RuleDecider() if rule_fallback else None
        self.max_tokens = max_tokens

    def _providers(self):
        try:
            from core.agents import race_manager  # 惰性,失败即回退
            return race_manager.get_providers()
        except Exception:
            return {}

    def _prompt(self, ctx: dict) -> str:
        bars = ctx["rklb_bars"][-12:]
        rows = " | ".join(f"{b['time'][11:16]} c{float(b['close']):.2f}" for b in bars)
        rule = strat.decide(ctx)
        return (
            "你是短线交易决策器。标的 RKLB(及其 2x 多 RKLX / 2x 空 RKLZ)。\n"
            f"最近 5m 收盘: {rows}\n"
            f"规则层参考: {rule['direction']} conv{rule['conviction']} ({rule['reason']})\n"
            "只回 JSON: {\"direction\":\"long|short|flat\",\"conviction\":0-100,\"reason\":\"...\"}"
        )

    def decide(self, ctx: dict) -> dict:
        providers = self._providers()
        if not providers:
            return self.fallback.decide(ctx) if self.fallback else strat.decide(ctx)
        votes: List[dict] = []
        prompt = self._prompt(ctx)
        for name, prov in providers.items():
            try:
                from core.agents.prompt import parse_decision
                raw = prov.call("你是严格的交易决策器,只输出 JSON。", prompt, self.max_tokens, 20)
                d = parse_decision(raw) if isinstance(raw, str) else (raw or {})
                direction = (d.get("direction") or d.get("action") or "flat").lower()
                if direction in ("buy", "long"):
                    direction = "long"
                elif direction in ("sell", "short"):
                    direction = "short"
                elif direction not in ("long", "short"):
                    direction = "flat"
                votes.append({"name": name, "direction": direction,
                              "conviction": int(d.get("conviction", 60) or 60)})
            except Exception:
                continue
        if not votes:
            return self.fallback.decide(ctx) if self.fallback else strat.decide(ctx)

        # 聚合
        tally = {"long": 0, "short": 0, "flat": 0}
        for v in votes:
            tally[v["direction"]] += 1
        direction = max(tally, key=tally.get)
        if direction == "flat":
            return {"direction": "flat", "instrument": None, "conviction": 0,
                    "stop_pct": 0.0, "reason": f"committee flat ({len(votes)} votes)"}
        same = [v["conviction"] for v in votes if v["direction"] == direction]
        conv = int(sum(same) / len(same)) if same else 60
        if direction == "long":
            inst = "RKLX" if conv >= strat.RKLX_CONV else "RKLB"
        else:
            inst = "RKLZ"
        return {"direction": direction, "instrument": inst, "conviction": conv,
                "stop_pct": strat.STOP_PCT[inst],
                "reason": f"committee {tally['long']}L/{tally['short']}S/{tally['flat']}F"}
