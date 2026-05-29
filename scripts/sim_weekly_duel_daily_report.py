"""SimWeekly Duel daily Telegram report sender.
VERSION: v0.1.0
DEPENDS: data/sim_weekly/duel_ledger_*.json, core/sim_weekly/tg_format.py

Find a live duel ledger and send the unified daily Telegram summary.
查找实时 PK ledger，并发送统一格式的每日私聊总结。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "sim_weekly"
MARKER = SIM_DIR / "duel_daily_report_sent.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sim_weekly.tg_format import fmt_daily, send_private


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _ledger_for(date_label: str | None) -> Path | None:
    if date_label:
        path = SIM_DIR / f"duel_ledger_{date_label}.json"
        return path if path.exists() else None
    files = sorted(SIM_DIR.glob("duel_ledger_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return files[0] if files else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send SimWeekly duel daily report from ledger.")
    parser.add_argument("--date", help="Ledger date YYYY-MM-DD. Defaults to latest ledger.")
    parser.add_argument("--telegram", action="store_true", help="Send private Telegram report.")
    parser.add_argument("--force", action="store_true", help="Ignore sent marker and send again.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ledger_path = _ledger_for(args.date)
    if not ledger_path:
        print("[duel-daily] skipped: no duel ledger found")
        return 0
    payload = _read_json(ledger_path, {})
    scores = payload.get("contestants") or {}
    date_label = payload.get("date") or ledger_path.stem.replace("duel_ledger_", "")
    if not scores:
        print(f"[duel-daily] skipped: empty contestants in {ledger_path}")
        return 0
    marker = _read_json(MARKER, {})
    if not args.force and marker.get("last_sent_date") == date_label:
        print(f"[duel-daily] skipped: already sent {date_label}")
        return 0
    text = fmt_daily(date_label, scores)
    print(text)
    if args.telegram:
        ok = send_private(text)
        print(f"[duel-daily] telegram sent={ok}")
        if ok:
            _write_json(MARKER, {"last_sent_date": date_label, "source": str(ledger_path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
