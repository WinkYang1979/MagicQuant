"""OpenAI duel nightly adaptive review.
VERSION: v0.1.0
DEPENDS: data/sim_weekly/duel_ledger_*.json, data/sim_weekly/live_duel_openai_v1.json,
         core/sim_weekly/openai_contestant.py

Paper-only nightly learning loop for OpenAI duel contestant.
OpenAI 纸面 PK 夜间学习循环：观察 -> 假设 -> 明天试法 -> 留痕。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "sim_weekly"
LEDGER_GLOB = "duel_ledger_*.json"
STATE_PATH = SIM_DIR / "openai_adaptive_state.json"
CONFIG_PATH = SIM_DIR / "openai_adaptive_config.json"
LOG_PATH = SIM_DIR / "openai_adjustment_log.json"
OPENAI_LIVE_STATE = SIM_DIR / "live_duel_openai_v1.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sim_weekly.openai_contestant import DEFAULT_ADAPTIVE_CONFIG
from core.sim_weekly.tg_format import send_private


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _latest_ledger(date_label: str | None) -> Path | None:
    if date_label:
        path = SIM_DIR / f"duel_ledger_{date_label}.json"
        return path if path.exists() else None
    files = sorted(SIM_DIR.glob(LEDGER_GLOB), key=lambda item: item.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _score_for(payload: dict, name: str) -> dict:
    return (payload.get("contestants") or {}).get(name) or {}


def _regime_observation(ledger: dict) -> dict:
    openai = _score_for(ledger, "openai_v1")
    claude = _score_for(ledger, "claude_rule")
    benchmark = openai.get("benchmark_buyhold_RKLB_pct")
    if benchmark is None:
        benchmark = claude.get("benchmark_buyhold_RKLB_pct")
    try:
        bench = float(benchmark or 0.0)
    except Exception:
        bench = 0.0
    if bench >= 3.0:
        regime = "bull"
    elif bench <= -3.0:
        regime = "bear"
    else:
        regime = "chop"
    return {
        "date": ledger.get("date"),
        "benchmark_buyhold_RKLB_pct": round(bench, 2),
        "observed_regime": regime,
        "openai_return_pct": openai.get("return_pct"),
        "openai_max_drawdown_pct": openai.get("max_drawdown_pct"),
        "openai_trades": openai.get("n_trades"),
        "claude_return_pct": claude.get("return_pct"),
    }


def _update_regime_state(state: dict, obs: dict) -> dict:
    history = list(state.get("observations") or [])
    if not history or history[-1].get("date") != obs.get("date"):
        history.append(obs)
    history = history[-20:]
    last_two = history[-2:]
    confirmed = None
    if len(last_two) == 2 and last_two[0].get("observed_regime") == last_two[1].get("observed_regime"):
        confirmed = last_two[-1].get("observed_regime")
    state["observations"] = history
    state["confirmed_regime"] = confirmed or state.get("confirmed_regime") or "unknown"
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return state


def _config_for_regime(regime: str) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_ADAPTIVE_CONFIG))
    params = cfg["params"]
    if regime == "bull":
        cfg["profile"] = "bull_ride"
        cfg["hypothesis_id"] = "bull_ride_v1"
        params.update({
            "rklx_fraction": 0.66,
            "rklb_fraction": 0.40,
            "rklx_stop_pct": 0.085,
            "rklb_stop_pct": 0.055,
            "cooldown_bars": 2,
            "bull_long_rsi_max": 84,
            "bull_gap_atr": 0.45,
            "avoid_shorts_in_bull": True,
        })
    elif regime == "bear":
        cfg["profile"] = "defensive"
        cfg["hypothesis_id"] = "bear_defense_v1"
        params.update({
            "rklx_fraction": 0.30,
            "rklb_fraction": 0.24,
            "rklx_stop_pct": 0.052,
            "rklb_stop_pct": 0.034,
            "short_fraction": 0.30,
            "short_stop_pct": 0.060,
            "cooldown_bars": 5,
            "avoid_shorts_in_bull": False,
        })
    else:
        cfg["profile"] = "neutral"
        cfg["hypothesis_id"] = "neutral_guard_v1"
    cfg["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return cfg


def _hypothesis_text(obs: dict, confirmed_regime: str, profile: str) -> dict:
    if profile == "bull_ride":
        return {
            "observation": f"连续确认 bull；RKLB 基准 {obs['benchmark_buyhold_RKLB_pct']:+.2f}%，主动策略此前容易过早下车。",
            "hypothesis": "牛市里减少 5m churn、放宽 RKLX/RKLB 跟踪止损，让赢家跑，会改善次日前向表现。",
            "tomorrow_trial": "启用 bull_ride: RKLX 仓位上调、止损放宽、冷却缩短、避免正周反向 RKLZ。",
        }
    if profile == "defensive":
        return {
            "observation": f"连续确认 bear；RKLB 基准 {obs['benchmark_buyhold_RKLB_pct']:+.2f}%，下行保护优先。",
            "hypothesis": "熊市里降低多头预算、保留较小 RKLZ 防守，会降低回撤。",
            "tomorrow_trial": "启用 defensive: 多头降仓、止损收紧、允许 RKLZ 防守。",
        }
    return {
        "observation": f"regime 未连续确认或为 {confirmed_regime}；RKLB 基准 {obs['benchmark_buyhold_RKLB_pct']:+.2f}%。",
        "hypothesis": "单日信号不足以换挡；保持 neutral 防止 whipsaw。",
        "tomorrow_trial": "保持 neutral_guard，不因单日盈亏反向。",
    }


def _result_for_previous(obs: dict) -> dict:
    openai_ret = obs.get("openai_return_pct")
    claude_ret = obs.get("claude_return_pct")
    try:
        beat_claude = float(openai_ret or 0.0) > float(claude_ret or 0.0)
    except Exception:
        beat_claude = False
    try:
        positive = float(openai_ret or 0.0) > 0
    except Exception:
        positive = False
    return {
        "evaluated_on": obs.get("date"),
        "openai_return_pct": openai_ret,
        "openai_max_drawdown_pct": obs.get("openai_max_drawdown_pct"),
        "openai_trades": obs.get("openai_trades"),
        "claude_return_pct": claude_ret,
        "beat_claude": beat_claude,
        "positive_day": positive,
        "quality_note": "helped if beat_claude or positive_day; judge after multiple forward days",
    }


def run_review(date_label: str | None = None, apply: bool = True) -> dict:
    ledger_path = _latest_ledger(date_label)
    if not ledger_path:
        return {"ok": False, "reason": "no ledger"}
    ledger = _read_json(ledger_path, {})
    obs = _regime_observation(ledger)
    state = _update_regime_state(_read_json(STATE_PATH, {}), obs)
    confirmed = state.get("confirmed_regime") or "unknown"
    profile_regime = confirmed if confirmed in ("bull", "bear") else "neutral"
    config = _config_for_regime(profile_regime)
    text = _hypothesis_text(obs, confirmed, config["profile"])
    entry = {
        "date": obs.get("date"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ledger": str(ledger_path),
        "confirmed_regime": confirmed,
        "next_profile": config["profile"],
        "hypothesis_id": config["hypothesis_id"],
        **text,
        "tomorrow_config": config,
        "next_day_result": None,
    }
    log = _read_json(LOG_PATH, [])
    if not isinstance(log, list):
        log = []
    if log and log[-1].get("date") != entry.get("date") and log[-1].get("next_day_result") is None:
        log[-1]["next_day_result"] = _result_for_previous(obs)
    if not log or log[-1].get("date") != entry.get("date"):
        log.append(entry)
    else:
        log[-1] = entry
    if apply:
        _write_json(STATE_PATH, state)
        _write_json(CONFIG_PATH, config)
        _write_json(LOG_PATH, log[-200:])
    return {"ok": True, "entry": entry, "state": state, "config": config}


def _telegram_text(result: dict) -> str:
    if not result.get("ok"):
        return f"📊 OpenAI 夜间复盘跳过\n原因: {result.get('reason')}\n(纸面模拟)"
    entry = result["entry"]
    return (
        "📊 <b>OpenAI 夜间自适应复盘</b>\n"
        f"日期: {entry['date']}\n"
        f"确认 regime: {entry['confirmed_regime']}\n"
        f"明日 profile: {entry['next_profile']}\n"
        f"观察: {entry['observation']}\n"
        f"假设: {entry['hypothesis']}\n"
        f"明天试法: {entry['tomorrow_trial']}\n"
        "(纸面模拟)"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenAI duel nightly adaptive review.")
    parser.add_argument("--date", help="Ledger date YYYY-MM-DD. Defaults to latest ledger.")
    parser.add_argument("--dry-run", action="store_true", help="Print decision without writing config/log.")
    parser.add_argument("--telegram", action="store_true", help="Send private Telegram summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_review(args.date, apply=not args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if args.telegram:
        send_private(_telegram_text(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
