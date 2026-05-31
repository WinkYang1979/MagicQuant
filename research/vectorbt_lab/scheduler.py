"""
MagicQuant scheduler.py
VERSION : v0.1.2
DEPENDS : research.vectorbt_lab.fetch_1m_data, run_candidate_scan, report, strategy_miner_multi_run, _tg_notify

Isolated scheduler for vectorbt research jobs.
隔离研究调度器：只运行 research/vectorbt_lab，不接入实盘盯盘。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from _tg_notify import send as send_tg, send_review


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1]
STATE_PATH = BASE_DIR / "state" / "scheduler_state.json"
DEFAULT_TICKERS = "RKLB,LUNR,ASTS,IONQ"
LOCAL_TZ = datetime.now().astimezone().tzinfo or ZoneInfo("Australia/Sydney")
ET = ZoneInfo("America/New_York")
DAILY_AFTER = dt_time(7, 0)
DAILY_REVIEW_AFTER = dt_time(8, 0)
WEEKLY_AFTER = dt_time(9, 0)
FETCH_TIMEOUT_SEC = 300
WEEKLY_STEP_TIMEOUT_SEC = 900
WEEKLY_DEEP_TIMEOUT_SEC = 5400
SIM_STATUS_TIMEOUT_SEC = 120
DEEP_MINER_SEEDS = "11,22,33,44,55,66,77,88,99,111"


@dataclass
class StepResult:
    name: str
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    skipped: bool = False
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.skipped or self.returncode == 0


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def iso_week_key(now: datetime) -> tuple[int, int]:
    iso = now.isocalendar()
    return int(iso.year), int(iso.week)


def load_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def is_rth(now: datetime) -> bool:
    et_now = now.astimezone(ET)
    if et_now.weekday() >= 5:
        return False
    return dt_time(9, 30) <= et_now.time() < dt_time(16, 0)


def should_run_daily(now: datetime, state: dict, force: bool = False) -> bool:
    if is_rth(now):
        return False
    if force:
        return True
    if now.time() < DAILY_AFTER:
        return False
    today = now.date().isoformat()
    last = state.get("last_daily_run") or {}
    return last.get("date") != today


def should_run_weekly(now: datetime, state: dict, force: bool = False) -> bool:
    if is_rth(now):
        return False
    if force:
        return True
    if now.weekday() != 6 or now.time() < WEEKLY_AFTER:
        return False
    year, week = iso_week_key(now)
    last = state.get("last_weekly_run") or {}
    same_week = last.get("iso_year") == year and last.get("iso_week") == week
    if not same_week:
        return True
    return last.get("success") is False


def should_run_daily_review(now: datetime, state: dict, force: bool = False) -> bool:
    if is_rth(now):
        return False
    if force:
        return True
    if now.time() < DAILY_REVIEW_AFTER:
        return False
    today = now.date().isoformat()
    last = state.get("last_daily_review") or {}
    return last.get("date") != today


def reset_daily(state: dict) -> None:
    state.pop("last_daily_run", None)


def reset_weekly(state: dict) -> None:
    state.pop("last_weekly_run", None)


def reset_daily_review(state: dict) -> None:
    state.pop("last_daily_review", None)


def command_display(command: list[str]) -> str:
    return " ".join(str(part) for part in command)


def resolve_step_script(script_name: str) -> Path:
    script = Path(script_name)
    if script.is_absolute():
        return script
    lab_script = BASE_DIR / script_name
    if lab_script.exists():
        return lab_script
    return PROJECT_ROOT / script_name


def run_step(name: str, command: list[str], timeout_sec: int) -> StepResult:
    print(f"[step] {name}: {command_display(command)}")
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
        if completed.stdout:
            print(completed.stdout[-2000:])
        if completed.stderr:
            print(completed.stderr[-2000:])
        return StepResult(name, command, completed.returncode, completed.stdout, completed.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return StepResult(name, command, None, stdout, stderr, reason=f"timeout after {timeout_sec}s")
    except Exception as exc:
        return StepResult(name, command, None, "", "", reason=str(exc))


def parse_manifest_rows_added() -> dict[str, int]:
    path = BASE_DIR / "data" / "manifest.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(item.get("symbol")): int(item.get("rows_added", 0)) for item in payload.get("results", [])}
    except Exception:
        return {}


def mark_daily_started(state: dict, now: datetime, trigger: str) -> None:
    state["last_daily_run"] = {
        "date": now.date().isoformat(),
        "started_at": now.isoformat(),
        "success": None,
        "trigger": trigger,
    }


def mark_weekly_started(state: dict, now: datetime, trigger: str) -> None:
    year, week = iso_week_key(now)
    state["last_weekly_run"] = {
        "iso_year": year,
        "iso_week": week,
        "started_at": now.isoformat(),
        "success": None,
        "trigger": trigger,
    }


def mark_daily_review_started(state: dict, now: datetime, trigger: str) -> None:
    state["last_daily_review"] = {
        "date": now.date().isoformat(),
        "started_at": now.isoformat(),
        "success": None,
        "trigger": trigger,
    }


def finish_daily(state: dict, now: datetime, success: bool, step: StepResult, rows_added: dict[str, int]) -> None:
    daily = state.setdefault("last_daily_run", {})
    daily.update({
        "finished_at": now.isoformat(),
        "success": success,
        "rows_added": rows_added,
        "command": command_display(step.command),
        "returncode": step.returncode,
        "error": step.reason or (step.stderr[-1000:] if not success else ""),
    })


def finish_weekly(state: dict, now: datetime, success: bool, steps: list[StepResult], out_dir: Path) -> None:
    weekly = state.setdefault("last_weekly_run", {})
    weekly.update({
        "finished_at": now.isoformat(),
        "success": success,
        "out_dir": str(out_dir),
        "steps": [
            {
                "name": step.name,
                "command": command_display(step.command),
                "returncode": step.returncode,
                "skipped": step.skipped,
                "reason": step.reason,
            }
            for step in steps
        ],
        "outputs": [str(path) for path in out_dir.glob("*")] if out_dir.exists() else [],
        "error": next((step.reason or step.stderr[-1000:] for step in steps if not step.ok), ""),
    })


def finish_daily_review(state: dict, now: datetime, success: bool, steps: list[StepResult]) -> None:
    review = state.setdefault("last_daily_review", {})
    review.update({
        "finished_at": now.isoformat(),
        "success": success,
        "steps": [
            {
                "name": step.name,
                "command": command_display(step.command),
                "returncode": step.returncode,
                "skipped": step.skipped,
                "reason": step.reason,
            }
            for step in steps
        ],
        "error": next((step.reason or step.stderr[-1000:] for step in steps if not step.ok), ""),
    })


def run_daily_pipeline(state: dict, trigger: str, dry_run: bool = False) -> bool:
    current = now_local()
    command = [
        sys.executable,
        str(BASE_DIR / "fetch_1m_data.py"),
        "--incremental",
        "--tickers",
        DEFAULT_TICKERS,
    ]
    if dry_run:
        print(f"[dry-run] daily: {command_display(command)}")
        return True
    mark_daily_started(state, current, trigger)
    save_state(state)
    step = run_step("fetch_incremental", command, FETCH_TIMEOUT_SEC)
    ok = step.ok
    rows_added = parse_manifest_rows_added() if ok else {}
    finish_daily(state, now_local(), ok, step, rows_added)
    save_state(state)
    if not ok:
        send_tg("⚠️ VectorBT daily research fetch failed\n" + (step.reason or step.stderr[-800:] or "unknown error"))
    return ok


def run_daily_review_pipeline(state: dict, trigger: str, dry_run: bool = False) -> bool:
    current = now_local()
    steps: list[StepResult] = []
    fetch_command = [
        sys.executable,
        str(BASE_DIR / "fetch_1m_data.py"),
        "--incremental",
        "--tickers",
        DEFAULT_TICKERS,
    ]
    review_command = [
        sys.executable,
        str(BASE_DIR / "daily_rklb_review.py"),
        "--telegram",
    ]
    sim_status_command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "sim_weekly_status.py"),
        "--telegram",
    ]
    duel_daily_command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "sim_weekly_duel_daily_report.py"),
        "--telegram",
    ]
    claude_nightly_command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "sim_weekly_claude_nightly_review.py"),
        "--telegram",
    ]
    openai_nightly_command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "sim_weekly_openai_nightly_review.py"),
        "--telegram",
    ]
    if dry_run:
        steps = [
            StepResult("fetch_incremental", fetch_command, 0, "", "", skipped=True, reason="dry-run"),
            StepResult("daily_rklb_review", review_command, 0, "", "", skipped=True, reason="dry-run"),
            StepResult("sim_weekly_status", sim_status_command, 0, "", "", skipped=True, reason="dry-run"),
            StepResult("duel_daily_report", duel_daily_command, 0, "", "", skipped=True, reason="dry-run"),
            StepResult("claude_nightly_review", claude_nightly_command, 0, "", "", skipped=True, reason="dry-run"),
            StepResult("openai_nightly_review", openai_nightly_command, 0, "", "", skipped=True, reason="dry-run"),
        ]
        for step in steps:
            print(f"[dry-run] daily_review {step.name}: {command_display(step.command)}")
        return True
    mark_daily_review_started(state, current, trigger)
    save_state(state)

    for name, command, timeout_sec in [
        ("fetch_incremental", fetch_command, FETCH_TIMEOUT_SEC),
        ("daily_rklb_review", review_command, WEEKLY_STEP_TIMEOUT_SEC),
        ("sim_weekly_status", sim_status_command, SIM_STATUS_TIMEOUT_SEC),
        ("duel_daily_report", duel_daily_command, SIM_STATUS_TIMEOUT_SEC),
        ("claude_nightly_review", claude_nightly_command, SIM_STATUS_TIMEOUT_SEC),
        ("openai_nightly_review", openai_nightly_command, SIM_STATUS_TIMEOUT_SEC),
    ]:
        step = run_step(name, command, timeout_sec)
        steps.append(step)
        if not step.ok:
            break
    success = all(step.ok for step in steps)
    finish_daily_review(state, now_local(), success, steps)
    save_state(state)
    if not success:
        bad = next((step for step in steps if not step.ok), steps[-1])
        send_tg(f"⚠️ RKLB daily review failed\nStep: {bad.name}\n{bad.reason or bad.stderr[-800:] or 'unknown error'}")
    return success


def maybe_step(name: str, script_name: str, args: list[str], timeout_sec: int) -> StepResult:
    script = resolve_step_script(script_name)
    command = [sys.executable, str(script), *args]
    if not script.exists():
        return StepResult(name, command, None, "", "", skipped=True, reason="script missing")
    return run_step(name, command, timeout_sec)


def _run_weekly_pipeline_legacy(state: dict, trigger: str, dry_run: bool = False) -> bool:
    current = now_local()
    out_dir = BASE_DIR / "output" / current.strftime("%Y-%m-%d")
    send_review(f"🧪 VectorBT weekly research started\n{current.strftime('%Y-%m-%d %H:%M')}")

    step_specs = [
        ("dependency_update", "scripts/weekly_dependency_update.py", [], WEEKLY_STEP_TIMEOUT_SEC),
        ("fetch_incremental", "fetch_1m_data.py", ["--incremental", "--tickers", DEFAULT_TICKERS], FETCH_TIMEOUT_SEC),
        ("candidate_scan", "run_candidate_scan.py", ["--out-dir", str(out_dir)], WEEKLY_STEP_TIMEOUT_SEC),
        ("optuna_rklb", "optuna_optimize_breakout.py", ["--symbol", "RKLB", "--trials", "40", "--out-dir", str(out_dir / "optuna")], WEEKLY_STEP_TIMEOUT_SEC),
        ("strategy_miner_multi_run", "strategy_miner_multi_run.py", ["--trials", "80", "--out-dir", str(out_dir / "strategy_miner_multi_run"), "--telegram", "--scorecard"], WEEKLY_STEP_TIMEOUT_SEC * 2),
        ("vwap_reclaim_scan", "run_vwap_reclaim_scan.py", ["--out-dir", str(out_dir)], WEEKLY_STEP_TIMEOUT_SEC),
        ("report", "report.py", ["--out-dir", str(out_dir)], WEEKLY_STEP_TIMEOUT_SEC),
        ("duel_weekly_report", "scripts/sim_weekly_duel_weekly_report.py", ["--telegram"], SIM_STATUS_TIMEOUT_SEC),
    ]
    steps: list[StepResult] = []
    if dry_run:
        for name, script, args, _timeout in step_specs:
            command = [sys.executable, str(resolve_step_script(script)), *args]
            steps.append(StepResult(name, command, 0, "", "", skipped=True, reason="dry-run"))
            print(f"[dry-run] weekly {name}: {command_display(command)}")
        finish_weekly(state, now_local(), True, steps, out_dir)
        save_state(state)
        return True

    success = True
    for name, script, args, timeout_sec in step_specs:
        step = maybe_step(name, script, args, timeout_sec)
        steps.append(step)
        if not step.ok:
            success = False
            break

    finish_weekly(state, now_local(), success, steps, out_dir)
    save_state(state)
    if success:
        send_review(f"✅ VectorBT weekly research completed\nOutput: {out_dir}")
    else:
        bad = next((step for step in steps if not step.ok), steps[-1])
        send_review(f"⚠️ VectorBT weekly research failed\nStep: {bad.name}\n{bad.reason or bad.stderr[-800:] or 'unknown error'}")
    return success


def _weekly_strategy_summary(out_dir: Path) -> str:
    """Return miner summary for weekly Telegram. / 返回周报里的策略挖掘摘要。"""
    path = out_dir / "strategy_miner_multi_run" / "strategy_miner_multi_run_summary.json"
    if not path.exists():
        return "Strategy miner summary: not generated."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        best = payload.get("best") or {}
        if not best:
            return f"Strategy miner: {payload.get('decision', 'no_result')}"
        return (
            "Strategy miner summary\n"
            f"Best: {best.get('strategy')}\n"
            f"OOS median PnL: ${float(best.get('median_oos_pnl', 0.0)):.2f}\n"
            f"Cross cells: {best.get('cross_positive_cells')}/{best.get('cross_total_cells')}\n"
            f"Trades/PF: {best.get('median_oos_trades')} / {best.get('median_profit_factor')}\n"
            f"Decision: {payload.get('decision')}\n"
            f"Meaning: {payload.get('reason')}"
        )
    except Exception as exc:
        return f"Strategy miner summary: unreadable ({exc})"


def run_weekly_pipeline(state: dict, trigger: str, dry_run: bool = False, deep: bool = False) -> bool:
    """Run weekly research; dry-run prints only. / 运行周末研究；dry-run 只打印不落盘。"""
    current = now_local()
    out_dir = BASE_DIR / "output" / current.strftime("%Y-%m-%d")
    miner_args = ["--trials", "80", "--out-dir", str(out_dir / "strategy_miner_multi_run"), "--scorecard"]
    miner_timeout = WEEKLY_STEP_TIMEOUT_SEC * 2
    if deep:
        miner_args = ["--trials", "200", "--seeds", DEEP_MINER_SEEDS, "--out-dir", str(out_dir / "strategy_miner_multi_run"), "--scorecard"]
        miner_timeout = WEEKLY_DEEP_TIMEOUT_SEC
    step_specs = [
        ("dependency_update", "scripts/weekly_dependency_update.py", [], WEEKLY_STEP_TIMEOUT_SEC),
        ("fetch_incremental", "fetch_1m_data.py", ["--incremental", "--tickers", DEFAULT_TICKERS], FETCH_TIMEOUT_SEC),
        ("candidate_scan", "run_candidate_scan.py", ["--out-dir", str(out_dir)], WEEKLY_STEP_TIMEOUT_SEC),
        ("optuna_rklb", "optuna_optimize_breakout.py", ["--symbol", "RKLB", "--trials", "40", "--out-dir", str(out_dir / "optuna")], WEEKLY_STEP_TIMEOUT_SEC),
        ("strategy_miner_multi_run", "strategy_miner_multi_run.py", miner_args, miner_timeout),
        ("vwap_reclaim_scan", "run_vwap_reclaim_scan.py", ["--out-dir", str(out_dir)], WEEKLY_STEP_TIMEOUT_SEC),
        ("report", "report.py", ["--out-dir", str(out_dir)], WEEKLY_STEP_TIMEOUT_SEC),
        ("duel_weekly_report", "scripts/sim_weekly_duel_weekly_report.py", ["--telegram"], SIM_STATUS_TIMEOUT_SEC),
    ]
    steps: list[StepResult] = []
    if dry_run:
        for name, script, args, _timeout in step_specs:
            command = [sys.executable, str(resolve_step_script(script)), *args]
            steps.append(StepResult(name, command, 0, "", "", skipped=True, reason="dry-run"))
            print(f"[dry-run] weekly {name}: {command_display(command)}")
        return True

    mark_weekly_started(state, current, trigger)
    save_state(state)
    mode = "deep" if deep else "standard"
    send_review(f"VectorBT weekly research started\nMode: {mode}\n{current.strftime('%Y-%m-%d %H:%M')}")
    success = True
    for name, script, args, timeout_sec in step_specs:
        step = maybe_step(name, script, args, timeout_sec)
        steps.append(step)
        if not step.ok:
            success = False
            break

    finish_weekly(state, now_local(), success, steps, out_dir)
    save_state(state)
    if success:
        send_review(f"VectorBT weekly research completed\nOutput: {out_dir}\n\n{_weekly_strategy_summary(out_dir)}")
    else:
        bad = next((step for step in steps if not step.ok), steps[-1])
        send_review(f"VectorBT weekly research failed\nStep: {bad.name}\n{bad.reason or bad.stderr[-800:] or 'unknown error'}")
    return success


def parse_args():
    parser = argparse.ArgumentParser(description="VectorBT lab scheduler.")
    parser.add_argument("--force-daily", action="store_true", help="Run daily fetch now, except during RTH.")
    parser.add_argument("--force-review", action="store_true", help="Run daily RKLB review now, except during RTH.")
    parser.add_argument("--force-weekly", action="store_true", help="Run weekly research now, except during RTH.")
    parser.add_argument("--deep", action="store_true", help="Run weekly strategy miner in deep mode with longer timeout.")
    parser.add_argument("--reset-daily", action="store_true", help="Clear daily state marker.")
    parser.add_argument("--reset-review", action="store_true", help="Clear daily RKLB review state marker.")
    parser.add_argument("--reset-weekly", action="store_true", help="Clear weekly state marker.")
    parser.add_argument("--dry-run", action="store_true", help="Print decisions and commands without running jobs.")
    parser.add_argument("--once", action="store_true", help="Evaluate once and exit.")
    parser.add_argument("--sleep-sec", type=int, default=1800, help="Daemon sleep interval.")
    return parser.parse_args()


def print_decision(current: datetime, state: dict, args) -> None:
    print(f"[scheduler] now={current.isoformat()} et={current.astimezone(ET).isoformat()} rth={is_rth(current)}")
    print(
        f"[scheduler] daily_due={should_run_daily(current, state, args.force_daily)} "
        f"review_due={should_run_daily_review(current, state, args.force_review)} "
        f"weekly_due={should_run_weekly(current, state, args.force_weekly)}"
    )


def run_once(args) -> None:
    state = load_state()
    if args.reset_daily:
        reset_daily(state)
    if args.reset_review:
        reset_daily_review(state)
    if args.reset_weekly:
        reset_weekly(state)
    if args.reset_daily or args.reset_review or args.reset_weekly:
        save_state(state)

    current = now_local()
    print_decision(current, state, args)
    if is_rth(current) and (args.force_daily or args.force_review or args.force_weekly):
        print("[scheduler] force blocked during RTH")
        return

    if should_run_daily(current, state, args.force_daily):
        run_daily_pipeline(state, "force" if args.force_daily else "scheduled", dry_run=args.dry_run)
        state = load_state()
    if should_run_daily_review(current, state, args.force_review):
        run_daily_review_pipeline(state, "force" if args.force_review else "scheduled", dry_run=args.dry_run)
        state = load_state()
    if should_run_weekly(current, state, args.force_weekly):
        run_weekly_pipeline(state, "force" if args.force_weekly else "scheduled", dry_run=args.dry_run, deep=args.deep)


def main() -> int:
    args = parse_args()
    while True:
        try:
            run_once(args)
        except Exception as exc:
            print(f"[scheduler] loop error: {exc}")
            send_tg(f"⚠️ VectorBT scheduler loop error\n{exc}")
        if args.once:
            return 0
        time.sleep(max(60, args.sleep_sec))


if __name__ == "__main__":
    raise SystemExit(main())
