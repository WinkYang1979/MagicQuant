"""
MagicQuant arena_backfill tests.
VERSION : v1.0.0
DEPENDS : csv, pathlib, tempfile, arena_backfill
"""
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena_backfill import reconstruct, write_outputs


def _write_fixture(path: Path, days: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 5, 9, 30)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["time_key", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for day in range(days):
            price = 10.0 + day
            cursor = start + timedelta(days=day)
            for minute in range(390):
                ts = cursor + timedelta(minutes=minute)
                close = price + minute * 0.01
                writer.writerow(
                    {
                        "time_key": ts.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": round(close - 0.01, 4),
                        "high": round(close + 0.02, 4),
                        "low": round(close - 0.02, 4),
                        "close": round(close, 4),
                        "volume": 1000 + minute,
                    }
                )


def test_reconstruct_outputs_daily_arena_records():
    with TemporaryDirectory() as tmp:
        hist = Path(tmp) / "RKLB_1m.csv"
        _write_fixture(hist, days=4)
        records = reconstruct(3, hist)
        assert len(records) == 3
        assert records[0].champion_signal in {"LONG", "SHORT", "HOLD"}
        assert len(records[0].strategy_votes) == 7
        assert "gpt" in records[0].ai_votes
        assert isinstance(records[0].family_contributions, dict)


def test_write_outputs_creates_required_jsonl_files():
    with TemporaryDirectory() as tmp:
        hist = Path(tmp) / "RKLB_1m.csv"
        _write_fixture(hist, days=3)
        records = reconstruct(3, hist)
        paths = write_outputs(records, Path(tmp) / "arena")
        assert paths["champion_history"].exists()
        assert paths["arena_decisions"].exists()
        assert paths["historical_trial_results"].exists()
        assert paths["fitness_scores"].exists()
        assert len(paths["champion_history"].read_text(encoding="utf-8").splitlines()) == 3


if __name__ == "__main__":
    test_reconstruct_outputs_daily_arena_records()
    test_write_outputs_creates_required_jsonl_files()
    print("Arena backfill tests passed")
