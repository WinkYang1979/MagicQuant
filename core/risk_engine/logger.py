"""
MagicQuant Risk Engine — 日志模块
Dare to dream. Data to win.

data/risk_log.jsonl 每行一条 JSON.
字段:
  check_id, timestamp, ticker, action_type,
  allowed, severity, primary_reason_code,
  all_checks, metrics, context, outcome
"""

import os
import json
import threading
from datetime import datetime


_lock = threading.Lock()
_log_file_path = None


def _get_log_path() -> str:
    global _log_file_path
    if _log_file_path:
        return _log_file_path
    
    try:
        from config.settings import BASE_DIR
        data_dir = os.path.join(BASE_DIR, "data")
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(here, "..", "..", "data")
    
    os.makedirs(data_dir, exist_ok=True)
    _log_file_path = os.path.join(data_dir, "risk_log.jsonl")
    return _log_file_path


def log_risk_check(result, context: dict = None):
    """
    把一次 risk check 结果落盘.
    
    参数:
        result: RiskCheckResult 或 dict
        context: 原始输入 context(可选,默认空)
    """
    from .config_loader import get_risk_config
    cfg = get_risk_config()
    
    if not cfg.get("log_to_jsonl", True):
        return
    
    if hasattr(result, "to_dict"):
        result_dict = result.to_dict()
    else:
        result_dict = dict(result) if result else {}
    
    record = {
        "check_id":            result_dict.get("check_id"),
        "timestamp":           result_dict.get("timestamp"),
        "ticker":              result_dict.get("ticker"),
        "action_type":         result_dict.get("action_type"),
        "allowed":             result_dict.get("allowed"),
        "severity":            result_dict.get("severity"),
        "primary_reason_code": result_dict.get("primary_reason_code"),
        "all_checks":          result_dict.get("all_checks", []),
        "metrics":             result_dict.get("metrics", {}),
        "context":             _snapshot_context(context or {}),
        "outcome": {
            "user_action":       None,
            "actual_pnl_15m":    None,
            "actual_pnl_60m":    None,
            "risk_call_correct": None,
        },
    }
    
    path = _get_log_path()
    max_bytes = cfg.get("log_max_bytes", 10 * 1024 * 1024)
    
    with _lock:
        try:
            # 滚动日志: 超过 max_bytes 轮替
            if os.path.exists(path) and os.path.getsize(path) > max_bytes:
                rotated = path.replace(".jsonl", f".{datetime.now().strftime('%Y%m%d')}.jsonl")
                try:
                    os.rename(path, rotated)
                except:
                    pass
            
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"  [risk_log] 写入失败: {e}")


def _snapshot_context(context: dict) -> dict:
    """精简 context,避免写入过大对象"""
    snapshot = {}
    
    # 基础状态
    for k in ("pdt_remaining", "pdt_used", "daily_pnl", "cash",
              "drawdown_from_peak", "consecutive_losses",
              "market_session", "confidence", "ai_consensus",
              "spread_pct", "trigger_id", "focus_session_id"):
        if k in context:
            snapshot[k] = context[k]
    
    # positions 简化
    positions = context.get("positions", {})
    if positions:
        snapshot["positions_summary"] = {
            tk: {"qty": p.get("qty", 0) or p.get("qty_held", 0),
                 "cost_price": p.get("cost_price", 0)}
            for tk, p in positions.items()
            if (p.get("qty", 0) or p.get("qty_held", 0)) > 0
        }
    
    return snapshot


# ══════════════════════════════════════════════════════════════════
#  读取/统计
# ══════════════════════════════════════════════════════════════════

def read_recent_logs(n: int = 10) -> list:
    """读最近 N 条"""
    path = _get_log_path()
    if not os.path.exists(path):
        return []
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        recent = lines[-n:]
        return [json.loads(l) for l in recent if l.strip()]
    except Exception as e:
        print(f"  [risk_log] 读取失败: {e}")
        return []


def compute_stats(days: int = 7) -> dict:
    """最近 N 天的统计"""
    logs = read_recent_logs(n=5000)  # 最多读 5000 条
    if not logs:
        return {"total": 0}
    
    # 过滤时间
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)
    
    recent = []
    for log in logs:
        try:
            ts = datetime.fromisoformat(log.get("timestamp", "").replace("Z", "+00:00").split("+")[0])
            if ts >= cutoff:
                recent.append(log)
        except:
            pass
    
    if not recent:
        return {"total": 0}
    
    # 分类统计
    by_severity = {}
    by_reason = {}
    by_action = {}
    allowed_count = 0
    
    for log in recent:
        sev = log.get("severity", "unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        
        code = log.get("primary_reason_code", "unknown")
        by_reason[code] = by_reason.get(code, 0) + 1
        
        act = log.get("action_type", "unknown")
        by_action[act] = by_action.get(act, 0) + 1
        
        if log.get("allowed"):
            allowed_count += 1
    
    return {
        "total":           len(recent),
        "days":            days,
        "allowed":         allowed_count,
        "blocked":         len(recent) - allowed_count,
        "by_severity":     by_severity,
        "by_reason":       dict(sorted(by_reason.items(),
                                        key=lambda x: -x[1])[:10]),
        "by_action_type":  by_action,
    }


def format_stats_for_tg(stats: dict) -> str:
    """格式化统计结果"""
    if stats.get("total", 0) == 0:
        return "📊 最近 7 天无风控记录"
    
    lines = [
        f"📊 风控统计 · 最近 {stats.get('days', 7)} 天",
        "━━━━━━━━━━━━━━━━━━━━",
        f"总检查: {stats['total']} 次",
        f"放行:   {stats['allowed']} 次 ({stats['allowed']/stats['total']*100:.0f}%)",
        f"拦截:   {stats['blocked']} 次",
        "",
        "📈 按严重度:",
    ]
    
    for sev in ("block", "warn", "advisory", "pass"):
        n = stats["by_severity"].get(sev, 0)
        if n:
            lines.append(f"  {sev}: {n}")
    
    lines.append("")
    lines.append("🎯 Top 原因:")
    for reason, n in list(stats["by_reason"].items())[:5]:
        lines.append(f"  {reason}: {n}")
    
    lines.append("")
    lines.append("📋 按动作:")
    for act, n in stats["by_action_type"].items():
        lines.append(f"  {act}: {n}")
    
    return "\n".join(lines)
