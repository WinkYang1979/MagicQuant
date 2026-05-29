"""Duel 元记分卡 —— 不比收益,比"谁的夜间调整更高质量"。

读双方 adjustment_log(每晚的 观察/假设/调整)+ 历史 ledger(次日实际结果),
统计每次夜间调整之后,该选手次日表现是否真的变好(净帮忙 vs 净添乱)。

这是"哪个 AI 更会学"的主裁判:活的自适应,关键不是某天赢,是夜间调整的命中率。
纯只读,不碰 core/focus,不改任何配置。

用法: python scripts/sim_weekly_meta_scorecard.py [--tg]
"""
from __future__ import annotations

import glob
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "sim_weekly"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CONTESTANTS = {
    "claude_rule": SIM_DIR / "claude_adjustment_log.json",
    "openai_v1":   SIM_DIR / "openai_adjustment_log.json",
}


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _ledger_return(date_label: str, contestant: str):
    p = SIM_DIR / f"duel_ledger_{date_label}.json"
    led = _read_json(p, {})
    sc = (led.get("contestants") or {}).get(contestant, {})
    r = sc.get("return_pct")
    return float(r) if r is not None else None


def _next_trading_date(date_label: str) -> str | None:
    """下一个有 ledger 的日期(跳过周末/休市)。"""
    try:
        d = datetime.strptime(date_label, "%Y-%m-%d")
    except Exception:
        return None
    for i in range(1, 6):
        cand = (d + timedelta(days=i)).strftime("%Y-%m-%d")
        if (SIM_DIR / f"duel_ledger_{cand}.json").exists():
            return cand
    return None


def _analyze(contestant: str, log_path: Path) -> dict:
    log = _read_json(log_path, [])
    if not isinstance(log, list):
        log = []
    changes = 0           # 实际换挡的夜次
    helped = hurt = same = 0
    details = []
    for rec in log:
        prev = rec.get("prev_profile")
        new = rec.get("new_profile")
        date = rec.get("date")
        if not date:
            continue
        nxt = _next_trading_date(date)
        if not nxt:
            continue
        r_today = _ledger_return(date, contestant)
        r_next = _ledger_return(nxt, contestant)
        if r_today is None or r_next is None:
            continue
        delta = r_next - r_today
        changed = (prev != new)
        if changed:
            changes += 1
        if delta > 0.2:
            helped += 1; verdict = "helped"
        elif delta < -0.2:
            hurt += 1; verdict = "hurt"
        else:
            same += 1; verdict = "flat"
        details.append({"date": date, "switch": f"{prev}->{new}", "changed": changed,
                        "next": nxt, "r_today": r_today, "r_next": r_next,
                        "delta": round(delta, 2), "verdict": verdict})
    graded = helped + hurt + same
    hit = round(helped / graded * 100, 1) if graded else None
    return {"contestant": contestant, "reviews": len(log), "regime_switches": changes,
            "graded_nights": graded, "helped": helped, "hurt": hurt, "same": same,
            "adjust_hit_rate_pct": hit, "details": details[-10:]}


def main():
    show_tg = "--tg" in sys.argv
    results = {n: _analyze(n, p) for n, p in CONTESTANTS.items()}

    print("=== Duel 元记分卡:夜间调整质量(谁更会学)===\n")
    hdr = f"{'选手':<14}{'复盘次':>7}{'换挡次':>7}{'已评夜':>7}{'帮忙':>6}{'添乱':>6}{'命中率%':>9}"
    print(hdr); print("-" * len(hdr))
    for n, r in results.items():
        print(f"{n:<14}{r['reviews']:>7}{r['regime_switches']:>7}{r['graded_nights']:>7}"
              f"{r['helped']:>6}{r['hurt']:>6}{str(r['adjust_hit_rate_pct']):>9}")
    print("\n说明:命中率 = 夜间复盘后次日表现变好的比例(>+0.2% 算帮忙)。")
    print("样本不足(已评夜 < ~8)时命中率仅供参考,不作裁定。")

    if show_tg:
        from core.sim_weekly.tg_format import send_private
        lines = ["🧪 <b>Duel 元记分卡 · 夜间调整质量</b>"]
        for n, r in results.items():
            lines.append(f"<b>{n}</b> 命中率 {r['adjust_hit_rate_pct']}% "
                         f"(帮{r['helped']}/乱{r['hurt']}/平{r['same']}, 换挡{r['regime_switches']})")
        lines.append("(纸面模拟,样本不足仅供参考)")
        send_private("\n".join(lines))

    SIM_DIR.mkdir(parents=True, exist_ok=True)
    out = SIM_DIR / "meta_scorecard.json"
    json.dump({n: {k: v for k, v in r.items() if k != "details"} for n, r in results.items()},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(f"\n  saved -> {out}")


if __name__ == "__main__":
    main()
