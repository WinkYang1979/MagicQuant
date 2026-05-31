"""
MagicQuant RKLB Native Behavior Study tests.
VERSION : v1.0.0
DEPENDS : datetime, pathlib, tempfile, research.rklb_native_behavior_study
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.rklb_native_behavior_study import (  # noqa: E402
    Bar,
    detect_events,
    generate_report,
    render_report,
)


def _bars(day: str, prev_close: float = 100.0):
    start = datetime.strptime(day + " 09:30:00", "%Y-%m-%d %H:%M:%S")
    rows = []
    price = prev_close
    for idx in range(390):
        ts = start + timedelta(minutes=idx)
        price += 0.01
        volume = 1000.0
        if idx < 30:
            volume = 5000.0
        if idx == 31:
            price += 2.0
        if 150 <= idx < 210:
            price = rows[-1].close if rows else price
        if idx == 211:
            price += 3.0
            volume = 3000.0
        if idx == 331:
            price += 2.0
            volume = 4000.0
        rows.append(Bar(ts, price - 0.05, price + 0.05, price - 0.05, price, volume))
    return rows


def test_detect_events_and_render_report():
    days = {f"2026-06-{idx:02d}": _bars(f"2026-06-{idx:02d}") for idx in range(1, 8)}
    events = detect_events(days, max_days=7)
    assert events
    report = render_report(events)
    assert "RKLB Native Behavior Study" in report
    assert "Horse 1 Opening Volume Breakout" in report
    assert "Research Queue Status: WAITING_FOR_HUMAN_REVIEW" in report


def test_generate_report_writes_file_and_queue():
    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "REPORT_RKLB_NATIVE_BEHAVIOR.md"
        path, events = generate_report(out)
        assert path.exists()
        assert isinstance(events, list)


if __name__ == "__main__":
    test_detect_events_and_render_report()
    test_generate_report_writes_file_and_queue()
    print("RKLB Native Behavior Study tests passed")
