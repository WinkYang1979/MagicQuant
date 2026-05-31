"""
MagicQuant RKLB Native Candidate Review tests.
VERSION : v1.0.0
DEPENDS : pathlib, tempfile, research.rklb_native_behavior_study,
          research.rklb_native_candidate_review
"""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.rklb_native_behavior_study import EventResult  # noqa: E402
from research.rklb_native_candidate_review import (  # noqa: E402
    NEEDS_MORE_RESEARCH,
    generate_review,
    render_review,
)


def _event(name: str, idx: int, pnl: float) -> EventResult:
    return EventResult(
        name=name,
        date=f"2026-06-{idx:02d}",
        signal_time="10:00",
        direction="LONG",
        entry_price=100.0,
        returns={"20m": pnl, "30m": pnl, "60m": pnl},
        max_adverse_60m=-2.0,
        details="test event",
    )


def test_review_renders_decisions_without_approving_live_arena():
    events = [_event("Horse 1 Opening Volume Breakout", idx, 2.0) for idx in range(1, 8)]
    events += [_event("Horse 2 Gap-Up VWAP Breakdown", idx, 1.5) for idx in range(1, 8)]
    report = render_review(events)
    assert "Candidate Review: RKLB Native Behavior" in report
    assert NEEDS_MORE_RESEARCH in report
    assert "does not approve live trading" in report
    assert "Final Recommendation" in report


def test_generate_review_writes_file():
    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "CANDIDATE_REVIEW_RKLB_NATIVE_BEHAVIOR.md"
        path = generate_review(out)
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "Shadow Arena admission only" in text


if __name__ == "__main__":
    test_review_renders_decisions_without_approving_live_arena()
    test_generate_review_writes_file()
    print("RKLB Native Candidate Review tests passed")
