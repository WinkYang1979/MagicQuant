"""
MagicQuant weekly_dependency_update.py
VERSION : v0.1.1
DEPENDS : git, pip, research.vectorbt_lab._tg_notify

Weekend updater for approved external research dependencies.
周末外部依赖更新器：只更新白名单项目，并用状态文件避免重复执行。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parents[1]
STATE_PATH = BASE_DIR / "data" / "weekly_dependency_update_state.json"
LOCAL_TZ = datetime.now().astimezone().tzinfo or ZoneInfo("Australia/Sydney")
APPROVED_PIP_PACKAGES = ["vectorbt", "optuna", "pyarrow"]
TRADING_AGENTS_DIR = BASE_DIR / "TradingAgents"

RESEARCH_PATH = BASE_DIR / "research" / "vectorbt_lab"
if str(RESEARCH_PATH) not in sys.path:
    sys.path.insert(0, str(RESEARCH_PATH))

try:
    from _tg_notify import send_review
except Exception:
    send_review = None


@dataclass
class UpdateResult:
    name: str
    kind: str
    checked: bool
    updated: bool
    success: bool
    before: str = ""
    after: str = ""
    message: str = ""


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def iso_week_key(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso.year}-W{int(iso.week):02d}"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def weekend_allowed(now: datetime) -> bool:
    # Local weekend only. / 只在本地周末自动执行。
    return now.weekday() in (5, 6)


def already_done_this_week(state: dict, week_key: str) -> bool:
    last = state.get("last_update") or {}
    return last.get("iso_week") == week_key and last.get("success") is True


def run_cmd(command: list[str], cwd: Path = BASE_DIR, timeout: int = 240) -> tuple[int, str, str]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def git_sha(cwd: Path, ref: str = "HEAD") -> str:
    code, out, err = run_cmd(["git", "rev-parse", ref], cwd=cwd, timeout=30)
    return out.strip() if code == 0 else f"ERROR: {err}"


def update_trading_agents(dry_run: bool = False) -> UpdateResult:
    if not (TRADING_AGENTS_DIR / ".git").exists():
        return UpdateResult("TradingAgents", "git", False, False, True, message="missing git repo; skipped")

    before = git_sha(TRADING_AGENTS_DIR, "HEAD")
    code, _out, err = run_cmd(["git", "fetch", "--prune"], cwd=TRADING_AGENTS_DIR, timeout=180)
    if code != 0:
        return UpdateResult("TradingAgents", "git", True, False, False, before=before, message=err)

    branch_code, branch, branch_err = run_cmd(["git", "branch", "--show-current"], cwd=TRADING_AGENTS_DIR, timeout=30)
    if branch_code != 0 or not branch:
        msg = branch_err or "cannot detect branch"
        return UpdateResult("TradingAgents", "git", True, False, False, before=before, message=msg)

    upstream = f"origin/{branch}"
    upstream_sha = git_sha(TRADING_AGENTS_DIR, upstream)
    if upstream_sha == before:
        return UpdateResult("TradingAgents", "git", True, False, True, before=before, after=before, message="up to date")

    if dry_run:
        return UpdateResult(
            "TradingAgents",
            "git",
            True,
            True,
            True,
            before=before,
            after=upstream_sha,
            message="dry-run update available",
        )

    code, out, err = run_cmd(["git", "pull", "--ff-only"], cwd=TRADING_AGENTS_DIR, timeout=240)
    after = git_sha(TRADING_AGENTS_DIR, "HEAD")
    return UpdateResult("TradingAgents", "git", True, after != before, code == 0, before=before, after=after, message=out or err)


def package_version(package: str) -> str:
    code, out, _err = run_cmd([sys.executable, "-m", "pip", "show", package], timeout=60)
    if code != 0:
        return ""
    for line in out.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return ""


def update_pip_package(package: str, dry_run: bool = False) -> UpdateResult:
    before = package_version(package)
    if dry_run:
        return UpdateResult(package, "pip", True, False, True, before=before, after=before, message="dry-run")

    command = [sys.executable, "-m", "pip", "install", "--upgrade", package]
    code, out, err = run_cmd(command, timeout=300)
    after = package_version(package)
    return UpdateResult(package, "pip", True, before != after, code == 0, before=before, after=after, message=(out or err)[-1200:])


def run_updates(dry_run: bool = False) -> list[UpdateResult]:
    results = [update_trading_agents(dry_run=dry_run)]
    for package in APPROVED_PIP_PACKAGES:
        results.append(update_pip_package(package, dry_run=dry_run))
    return results


def notify(results: list[UpdateResult], dry_run: bool) -> None:
    if send_review is None:
        return
    changed = [item for item in results if item.updated]
    failed = [item for item in results if not item.success]
    if not changed and not failed and not dry_run:
        return

    lines = [
        "🧰 Weekly dependency update",
        f"Mode: {'dry-run' if dry_run else 'apply'}",
        f"Updated: {len(changed)} | Failed: {len(failed)}",
        "",
    ]
    for item in results:
        status = "UPDATED" if item.updated else "OK" if item.success else "FAIL"
        lines.append(f"- {item.name}: {status} {item.before} -> {item.after}")
        if item.message and not item.success:
            lines.append(f"  {item.message[:240]}")
    send_review("\n".join(lines))


def parse_args():
    parser = argparse.ArgumentParser(description="Weekly approved dependency updater.")
    parser.add_argument("--force", action="store_true", help="Run even if this week already succeeded.")
    parser.add_argument("--dry-run", action="store_true", help="Check without applying updates.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    current = now_local()
    week = iso_week_key(current)
    state = load_state()
    if not args.force and not weekend_allowed(current):
        print("[weekly-update] skipped: not local weekend")
        return 0
    if not args.force and already_done_this_week(state, week):
        print(f"[weekly-update] skipped: already completed {week}")
        return 0

    results = run_updates(dry_run=args.dry_run)
    success = all(item.success for item in results)
    state["last_update"] = {
        "iso_week": week,
        "checked_at": current.isoformat(),
        "success": success,
        "dry_run": args.dry_run,
        "results": [asdict(item) for item in results],
    }
    save_state(state)
    notify(results, args.dry_run)
    print(f"[weekly-update] success={success} results={len(results)}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
