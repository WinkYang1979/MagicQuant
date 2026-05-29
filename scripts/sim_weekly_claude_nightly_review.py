"""Claude 纸面 PK 夜间学习循环 —— 观察 → 假设 → 明天试法 → 留痕。

与 OpenAI 侧(sim_weekly_openai_nightly_review.py)对称:
  读 duel_ledger_*.json + live_duel_claude_rule.json
  → 观察昨日表现 + 当前 regime(需多日确认才换挡)
  → 形成假设、写明天的 claude_adaptive_config.json
  → 调整 + 理由 + 次日结果 留痕到 claude_adjustment_log.json

纪律(对应 DUEL 章程"活的夜间自适应"三护栏):
  1. 假设驱动:每条调整写 observation/hypothesis/tomorrow_try
  2. regime 多日确认:连续 2 日同 regime 才换挡(防 whipsaw)
  3. 留痕:不重犯学过的错,可回看夜间调整净帮忙还是净添乱
只作用于纸面 duel,不碰 core/focus 实盘。
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "sim_weekly"
CONFIG_PATH = SIM_DIR / "claude_adaptive_config.json"
STATE_PATH = SIM_DIR / "claude_adaptive_state.json"
LOG_PATH = SIM_DIR / "claude_adjustment_log.json"
LIVE_STATE = SIM_DIR / "live_duel_claude_rule.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from core.sim_weekly.tg_format import send_private

# 两套 profile 的参数(neutral=守, bull_ride=骑趋势放宽/降churn/避空)
PROFILES = {
    "neutral": {
        "entry_conv": 70, "frac_strong": 0.75, "frac_weak": 0.45,
        "stop_mult": 1.0, "cooldown_bars": 3,
        "avoid_shorts_in_bull": False, "bull_long_rsi_max": 80,
    },
    "bull_ride": {
        "entry_conv": 68, "frac_strong": 0.90, "frac_weak": 0.55,
        "stop_mult": 1.8, "cooldown_bars": 6,
        "avoid_shorts_in_bull": True, "bull_long_rsi_max": 84,
    },
}


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _latest_ledger(date_label):
    if date_label:
        p = SIM_DIR / f"duel_ledger_{date_label}.json"
        return p if p.exists() else None
    files = sorted(glob.glob(str(SIM_DIR / "duel_ledger_*.json")))
    return Path(files[-1]) if files else None


def _observe_regime(ledger: dict) -> dict:
    """从 ledger 的 RKLB buy&hold 基准粗判当日 regime。"""
    sc = (ledger.get("contestants") or {}).get("claude_rule", {})
    bench = sc.get("benchmark_buyhold_RKLB_pct")
    bench = float(bench) if bench is not None else 0.0
    if bench >= 2.0:
        regime = "bull"
    elif bench <= -2.0:
        regime = "bear"
    else:
        regime = "chop"
    return {"date": ledger.get("date"), "observed_regime": regime,
            "claude_return": sc.get("return_pct"), "bench_rklb": bench}


def _confirm_regime(state: dict, obs: dict) -> str | None:
    hist = list(state.get("observations") or [])
    hist.append(obs)
    state["observations"] = hist[-10:]
    last2 = hist[-2:]
    if len(last2) == 2 and last2[0]["observed_regime"] == last2[1]["observed_regime"]:
        return last2[-1]["observed_regime"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="ledger 日期 YYYY-MM-DD,缺省取最新")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--telegram", action="store_true", help="发送纸面 PK 私聊摘要")
    args = ap.parse_args()

    ledger_path = _latest_ledger(args.date)
    if not ledger_path:
        print("[claude-nightly] 无 ledger,跳过(focus/duel 未跑过盘?)")
        return 0
    ledger = _read_json(ledger_path, {})
    obs = _observe_regime(ledger)
    state = _read_json(STATE_PATH, {})
    confirmed = _confirm_regime(state, obs)

    cfg = _read_json(CONFIG_PATH, {"profile": "neutral", "params": PROFILES["neutral"]})
    prev_profile = cfg.get("profile", "neutral")

    # 多日确认才换挡;牛市确认→bull_ride,其余→neutral(守)
    if confirmed == "bull":
        new_profile = "bull_ride"
    elif confirmed in ("bear", "chop"):
        new_profile = "neutral"
    else:
        new_profile = prev_profile   # 未确认,维持

    hypothesis = {
        "bull_ride": "确认连续2日牛市:放宽止损×1.8、加仓、降churn、避免反向RKLZ — 假设能吃到牛市趋势而非churn亏掉。",
        "neutral":   "非牛市或未确认:回守势,正常止损/仓位,熊市靠RKLZ防守,震荡少动。",
    }[new_profile]

    record = {
        "date": obs["date"],
        "observation": f"昨日 claude {obs['claude_return']}% / RKLB基准 {obs['bench_rklb']}% / 观察regime={obs['observed_regime']} / 确认regime={confirmed}",
        "hypothesis": hypothesis,
        "tomorrow_try": f"profile {prev_profile} -> {new_profile}",
        "prev_profile": prev_profile,
        "new_profile": new_profile,
        "reviewed_at": str(args.date or ledger.get("date") or ""),
    }

    print(f"[claude-nightly] {record['observation']}")
    print(f"[claude-nightly] 假设: {hypothesis}")
    print(f"[claude-nightly] 明日 profile: {prev_profile} -> {new_profile}")
    tg_text = (
        "📊 <b>Claude 夜间自适应复盘</b>\n"
        f"日期: {obs['date']}\n"
        f"观察: {record['observation']}\n"
        f"假设: {record['hypothesis']}\n"
        f"明天试法: {record['tomorrow_try']}\n"
        "(纸面模拟)"
    )

    if args.dry_run:
        print("[claude-nightly] dry-run,不写配置")
        if args.telegram:
            send_private(tg_text)
        return 0

    new_cfg = {
        "profile": new_profile,
        "hypothesis_id": f"{new_profile}_v1",
        "params": PROFILES[new_profile],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_json(CONFIG_PATH, new_cfg)
    _write_json(STATE_PATH, state)
    log = _read_json(LOG_PATH, [])
    if not isinstance(log, list):
        log = []
    log.append(record)
    _write_json(LOG_PATH, log[-200:])
    print(f"[claude-nightly] 已写 {CONFIG_PATH.name} + 留痕 {LOG_PATH.name}")
    if args.telegram:
        send_private(tg_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
