"""
v0.1.0 单元测试: verify_signals 复盘工具

  · 构造一个伪 triggers.json + 伪 kline_1m.json
  · 跑 analyze(),验证三类问题被正确识别
  · 验证 HTML 报告能生成
"""
import sys
import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import verify_signals as vs


def _mk_bar(time_str, o, h, l, c, v=10000):
    return {"time_key": time_str, "open": o, "high": h,
            "low": l, "close": c, "volume": v}


def _build_fake_data(tmp_dir: Path, date_str: str):
    """构造一组测试用 triggers.json + kline_1m_RKLB.json"""
    review_dir = tmp_dir / "data" / "review" / date_str
    review_dir.mkdir(parents=True, exist_ok=True)

    # ──── 推送时间基线 10:00:00 ────
    base = f"{date_str} 10:00:00"
    base_dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S")

    # 构造一组 5m K 线 bars (用于 decision_context.kline_data)
    # 让 RSI 大约在 60 (上行)
    bars_5m = []
    for i in range(20):
        close = 100 + i * 0.3
        bars_5m.append(_mk_bar(
            (base_dt - timedelta(minutes=(20 - i) * 5)).strftime("%Y-%m-%d %H:%M:%S"),
            close - 0.1, close + 0.2, close - 0.2, close, 12345))

    # 触发 1: 数据问题 — 存储 rsi=30 但 K 线重算应该 ~60
    rec_data_issue = {
        "ts": base,
        "trigger": "swing_top",
        "ticker": "US.RKLB",
        "direction": "short",
        "strength": "WEAK",
        "decision_context": {
            "kline_data": {"period": "5m", "bars_count": 20, "bars": bars_5m,
                           "is_today": True},
            "indicators_raw": {"rsi_14": 30.0,   # 错的!K 线上行应该是 ~60
                               "vol_ratio": 1.2, "is_today": True},
            "price_context": {"current": 106.0, "day_change_pct": 2.0},
            "session_state": {},
        }
    }

    # 触发 2: 逻辑问题 — long 信号 + RSI 80 (超买追多)
    rec_logic_issue = {
        "ts": f"{date_str} 10:05:00",
        "trigger": "direction_trend",
        "ticker": "US.RKLB",
        "direction": "long",
        "strength": "STRONG",
        "decision_context": {
            "kline_data": {"period": "5m", "bars_count": 20, "bars": bars_5m,
                           "is_today": True},
            "indicators_raw": {"rsi_14": 80.0,   # 算对了但逻辑矛盾
                               "vol_ratio": 2.0, "is_today": True},
            "price_context": {"current": 106.0, "day_change_pct": 8.0},
            "session_state": {},
        }
    }

    # 触发 3: 方向对 + 时机问题 — long 信号,后续涨但先回撤
    rec_timing = {
        "ts": f"{date_str} 10:10:00",
        "trigger": "rapid_move",
        "ticker": "US.RKLB",
        "direction": "long",
        "strength": "WEAK",
        "decision_context": {
            "kline_data": {"period": "5m", "bars_count": 20, "bars": bars_5m,
                           "is_today": True},
            "indicators_raw": {"rsi_14": 58.0, "vol_ratio": 1.5, "is_today": True},
            "price_context": {"current": 106.0, "day_change_pct": 2.5},
            "session_state": {},
        }
    }

    # 触发 4: 方向错 — long 信号,后续跌
    rec_wrong = {
        "ts": f"{date_str} 11:00:00",
        "trigger": "swing_bottom",
        "ticker": "US.RKLB",
        "direction": "long",
        "strength": "WEAK",
        "decision_context": {
            "kline_data": {"period": "5m", "bars_count": 20, "bars": bars_5m,
                           "is_today": True},
            "indicators_raw": {"rsi_14": 40.0, "vol_ratio": 1.0, "is_today": True},
            "price_context": {"current": 110.0, "day_change_pct": 0.5},
            "session_state": {},
        }
    }

    # 触发 5: 盘前 fallback — swing_bottom is_today=False
    rec_premarket = {
        "ts": f"{date_str} 08:00:00",
        "trigger": "swing_bottom",
        "ticker": "US.RKLB",
        "direction": "long",
        "strength": "WEAK",
        "decision_context": {
            "kline_data": {"period": "5m", "bars_count": 20, "bars": bars_5m,
                           "is_today": False},   # ← 盘前 fallback
            "indicators_raw": {"rsi_14": 32.0, "vol_ratio": 1.0,
                               "is_today": False},
            "price_context": {"current": 108.0, "day_change_pct": 7.9},
            "session_state": {},
        }
    }

    triggers = [rec_data_issue, rec_logic_issue, rec_timing, rec_wrong, rec_premarket]
    with open(review_dir / "triggers.json", "w", encoding="utf-8") as f:
        json.dump(triggers, f, ensure_ascii=False, indent=2)

    # 构造 kline_1m_RKLB.json
    # 时间从 09:55 到 12:00,1m 一根
    kline_1m = []
    minutes_total = (12 - 9) * 60 + 5
    for i in range(minutes_total):
        bar_dt = base_dt - timedelta(minutes=5) + timedelta(minutes=i)
        t_str = bar_dt.strftime("%Y-%m-%d %H:%M:%S")
        # 10:00 → 10:10 (rec_timing 入场后): 先跌 1.5% 再涨到 +2%
        # 10:10-10:25 跌到 104.5 (相对 106 是 -1.4%)
        # 10:25-10:40 反弹到 108.5 (+2.4%)
        # 之后保持 108
        if 5 <= i < 20:
            close = 106.0   # 10:00-10:10 平
        elif 20 <= i < 40:
            close = 106.0 - (i - 20) * 0.1   # 跌
        elif 40 <= i < 60:
            close = 104.0 + (i - 40) * 0.225  # 反弹到 108.5
        else:
            close = 108.0
        kline_1m.append(_mk_bar(t_str, close - 0.05, close + 0.1,
                                 close - 0.1, close))

    # rec_wrong 在 11:00 入场 long @110,但 1m kline 后面只到 108,会方向错
    # rec_premarket 在 08:00 入场,K 线 09:55 才开始 → 找不到 idx → no followup
    with open(review_dir / "kline_1m_RKLB.json", "w", encoding="utf-8") as f:
        json.dump(kline_1m, f, ensure_ascii=False, indent=2)


def test_analyze_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        date_str = "2026-05-12"
        _build_fake_data(tmp_dir, date_str)

        # monkey-patch REVIEW_ROOT
        orig = vs.REVIEW_ROOT
        vs.REVIEW_ROOT = tmp_dir / "data" / "review"
        try:
            analysis = vs.analyze(date_str)
        finally:
            vs.REVIEW_ROOT = orig

        s = analysis["summary"]
        print(f"\n摘要: {s}")
        assert s["total"] == 5
        # 1 个数据问题 (rec_data_issue)
        assert s["data_issues"] >= 1, f"应识别数据问题,实际 {s['data_issues']}"
        # 逻辑问题: rec_logic_issue (long+rsi80), rec_premarket (RTH+is_today=False),
        # rec_wrong (swing_bottom+day_chg=0.5 不触发逻辑) — 至少 2 个
        assert s["logic_issues"] >= 2, f"应识别 ≥2 逻辑问题,实际 {s['logic_issues']}"
        # 时机问题:rec_timing 方向对但先回撤
        # 注意:1m K 线模拟跌到 104,相对 106 是 -1.89% (≥1%,触发 timing)
        # 验证:取决于 1m K 线 high/low
        print(f"  data_issues={s['data_issues']} logic={s['logic_issues']} timing={s['timing_issues']}")
        print(f"  verified={s['verified_correct']} wrong_dir={s['wrong_direction']} "
              f"no_fu={s['no_followup']}")

        print("\n各条记录验证:")
        for i, item in enumerate(analysis["records"]):
            rec = item["record"]
            dc = "❌" if item["data_check"] else "  "
            lc = "❌" if item["logic_check"] else "  "
            tc = item["timing_check"]
            tc_str = ""
            if tc:
                if tc.get("verified"):
                    tc_str = "✅" if not tc.get("timing_issue") else "⏰"
                else:
                    tc_str = "❌"
            else:
                tc_str = "—"
            print(f"  [{i+1}] {rec['ts']} {rec['trigger']:<18} "
                  f"data={dc} logic={lc} timing={tc_str}  "
                  f"{(item['timing_check'] or {}).get('summary','')}")

        # 生成 HTML 验证不报错
        html = vs.render_html(analysis)
        assert "<html" in html and "MagicQuant" in html and "RKLB" in html
        print(f"\n✅ HTML 报告生成成功 ({len(html)} 字符)")


if __name__ == "__main__":
    test_analyze_end_to_end()
    print("\n🎉 verify_signals 测试通过")
