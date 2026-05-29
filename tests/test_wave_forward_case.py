"""
VERSION : v0.5.37-test
DEPENDS : core.focus.swing_detector, core.focus.context

冒烟: 确认 _record_wave_forward_case 真的把 shadow 候选落盘到
      wave_forward_cases.json(C 方案的校准数据命根子),字段齐全且去重。
"""
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.focus import swing_detector
from core.focus.context import FocusSession

SENTINEL_DATE = "2099-12-31"
OUT_FILE = ROOT / "data" / "review" / SENTINEL_DATE / "wave_forward_cases.json"


def _record(reason="rebound", direction="long"):
    return {
        "ts": "2099-12-31 01:00:00",
        "date": SENTINEL_DATE,
        "ticker": "US.RKLB",
        "direction": direction,
        "reason": reason,
        "trigger": f"shadow_targeted_{reason}",
        "current": 145.59,
        "day_change_pct": -3.09,
        "vwap": 144.95,
        "rsi": 63.2,
        "vol_ratio": 1.55,
        "move5_pct": 0.39,
        "move15_pct": 0.48,
    }


class TestWaveForwardCase(unittest.TestCase):
    def setUp(self):
        # 干净起步:删掉 sentinel 目录
        d = OUT_FILE.parent
        if d.exists():
            shutil.rmtree(d)
        self.session = FocusSession("US.RKLB", ["US.RKLZ"])

    def tearDown(self):
        d = OUT_FILE.parent
        if d.exists():
            shutil.rmtree(d)

    def test_records_to_file_with_fields(self):
        ind = {"session_high": 147.0, "session_low": 143.0}
        swing_detector._record_wave_forward_case(self.session, _record(), ind)

        self.assertTrue(OUT_FILE.exists(), "wave_forward_cases.json 未写出")
        rows = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 1)
        c = rows[0]
        # 校准打分所需的关键字段必须齐全
        for k in ("case_id", "ts", "entry_price", "entry_ts", "direction",
                  "source_trigger", "status", "rsi", "vol_ratio", "move5_pct"):
            self.assertIn(k, c, f"缺字段 {k}")
        self.assertEqual(c["entry_price"], 145.59)
        self.assertEqual(c["status"], "open")
        self.assertEqual(c["source_trigger"], "shadow_targeted_rebound")
        self.assertEqual(c["session_high"], 147.0)
        # 内存累积同步
        self.assertEqual(len(self.session._wave_forward_cases), 1)

    def test_dedupe_same_case(self):
        swing_detector._record_wave_forward_case(self.session, _record(), None)
        swing_detector._record_wave_forward_case(self.session, _record(), None)
        rows = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 1, "相同 case_id 应去重,不重复落盘")


if __name__ == "__main__":
    unittest.main()
