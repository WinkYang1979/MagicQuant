"""
MagicQuant — Override Logger (v0.4)
Dare to dream. Data to win.

记录老杨每次违背 AI / Risk 建议的操作,3个月后分析直觉 vs 系统胜率.

override_type 自动分类:
  override_risk_and_ai    逆 AI + 逆风控
  override_risk_only      仅逆风控(AI 也说别做)  
  override_ai_only        仅逆 AI(风控放行)
  aligned_with_system     和系统一致(最常见)
"""

import os
import json
import threading
from datetime import datetime

_lock = threading.Lock()
_log_path = None


def _get_log_path() -> str:
    global _log_path
    if _log_path:
        return _log_path
    try:
        from config.settings import BASE_DIR
        data_dir = os.path.join(BASE_DIR, "data")
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(here, "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    _log_path = os.path.join(data_dir, "override_log.jsonl")
    return _log_path


def classify_override(user_action: str, ai_leader_action: str = None,
                      risk_allowed: bool = True) -> str:
    """
    自动分类覆盖类型.
    
    user_action:     "BUY" / "SELL" / "HOLD" / None
    ai_leader_action:"BUY" / "SELL" / "HOLD" / None
    risk_allowed:    True / False
    """
    if not user_action or user_action == "NONE":
        return "aligned_with_system"
    
    user_active = user_action != "HOLD"
    
    # 是否逆 AI
    against_ai = False
    if ai_leader_action:
        if ai_leader_action == "HOLD" and user_active:
            against_ai = True
        elif ai_leader_action.startswith("BUY") and user_action.startswith("SELL"):
            against_ai = True
        elif ai_leader_action.startswith("SELL") and user_action.startswith("BUY"):
            against_ai = True
    
    # 是否逆风控
    against_risk = (not risk_allowed) and user_active
    
    if against_ai and against_risk:
        return "override_risk_and_ai"
    if against_risk:
        return "override_risk_only"
    if against_ai:
        return "override_ai_only"
    return "aligned_with_system"


def log_override(
    ticker: str,
    user_action: str,
    user_qty: int = 0,
    user_price: float = 0.0,
    user_reason: str = "",
    ai_leader_action: str = None,
    ai_confidence: int = None,
    ai_consensus: str = None,
    risk_check_id: str = None,
    risk_allowed: bool = True,
    risk_severity: str = None,
    risk_reason_code: str = None,
    trigger_id: str = None,
):
    """
    记录一次用户行为(不论是否 override).
    
    event-sourcing 思路: 所有用户交易都记录,事后通过 override_type 字段过滤.
    """
    override_type = classify_override(user_action, ai_leader_action, risk_allowed)
    
    record = {
        "time":             datetime.now().isoformat(timespec="seconds"),
        "ticker":           ticker,
        # 用户行为
        "user_action":      user_action,
        "user_qty":         user_qty,
        "user_price":       user_price,
        "user_reason":      user_reason,
        # AI 决策
        "ai_leader_action": ai_leader_action,
        "ai_confidence":    ai_confidence,
        "ai_consensus":     ai_consensus,
        # 风控
        "risk_check_id":    risk_check_id,
        "risk_allowed":     risk_allowed,
        "risk_severity":    risk_severity,
        "risk_reason_code": risk_reason_code,
        # 关联
        "trigger_id":       trigger_id,
        # 分类
        "override_type":    override_type,
        # 事后回填(v0.5)
        "outcome_15m":      None,
        "outcome_60m":      None,
        "who_was_right":    None,   # user / ai / risk / all_wrong
    }
    
    path = _get_log_path()
    with _lock:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"  [override_log] 写入失败: {e}")
    
    return record


def read_recent_overrides(n: int = 20) -> list:
    path = _get_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [json.loads(l) for l in lines[-n:] if l.strip()]
    except:
        return []


def compute_override_stats(days: int = 7) -> dict:
    """最近 N 天 override 统计"""
    from datetime import timedelta
    logs = read_recent_overrides(n=1000)
    if not logs:
        return {"total": 0}
    
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for log in logs:
        try:
            ts = datetime.fromisoformat(log.get("time", "").split("+")[0])
            if ts >= cutoff:
                recent.append(log)
        except:
            pass
    
    if not recent:
        return {"total": 0}
    
    by_type = {}
    for log in recent:
        t = log.get("override_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    
    return {
        "total":           len(recent),
        "days":            days,
        "by_override":     by_type,
        "aligned_pct":     round(
            by_type.get("aligned_with_system", 0) / len(recent) * 100, 1
        ),
    }


def format_override_stats_for_tg(stats: dict) -> str:
    if stats.get("total", 0) == 0:
        return f"📋 最近 {stats.get('days', 7)} 天无 override 记录"
    
    lines = [
        f"📋 Override 统计 · 最近 {stats['days']} 天",
        "━━━━━━━━━━━━━━━━━━━━",
        f"总行为数: {stats['total']}",
        f"和系统一致: {stats['aligned_pct']}%",
        "",
        "📊 分类:",
    ]
    for t, n in sorted(stats["by_override"].items(), key=lambda x: -x[1]):
        emoji = {
            "aligned_with_system":   "✅",
            "override_ai_only":      "🤖",
            "override_risk_only":    "🛡️",
            "override_risk_and_ai":  "⚠️",
        }.get(t, "•")
        lines.append(f"  {emoji} {t}: {n}")
    
    return "\n".join(lines)
