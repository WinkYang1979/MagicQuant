"""
v0.5.31 vs v0.5.35 短线方向准确率回测 (v2 — 加入干净/脏数据分层)
─────────────────────────────────────────
候选集: data/review/{date}/triggers.json 中所有 direction_trend (04-24~05-15)
评分窗口: 5min / 10min / 15min (1m K 线)
评分方法: MFE (最有利移动) vs MAE (最不利移动) — 信号方向上 MFE>MAE 算"对"
价格源: data/historical/RKLB_1m.csv

关键洞察:
  - "v0.5.31 视角" = 历史 live (无 R/R/data_quality/chase 闸门) = 全部 250 都推
  - "v0.5.35 视角" = 应用新闸门后剩下的子集
"""
import json
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
REVIEW_DIR = ROOT / "data" / "review"
HIST_CSV = ROOT / "data" / "historical" / "RKLB_1m.csv"

SESSION_KLINE_MAX_AGE_SEC = {"regular": 360, "pre": 600, "post": 600, "overnight": 1200, "closed": 0}
FROZEN_VALUE_BLACKLIST = {(43.1, 4.94), (43.1, 5.82)}


def load_kline(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["dt"] = pd.to_datetime(df["time_key"])
    return df.set_index("dt").sort_index()


def score_signal(kl: pd.DataFrame, sig_ts: str, direction: str, window_min: int):
    ts = pd.to_datetime(sig_ts)
    end = ts + timedelta(minutes=window_min)
    fut = kl.loc[ts:end]
    if len(fut) < 2:
        return None
    entry = float(fut["close"].iloc[0])
    if entry <= 0:
        return None
    later = fut.iloc[1:]
    if len(later) == 0:
        return None
    hi = float(later["high"].max())
    lo = float(later["low"].min())
    close = float(later["close"].iloc[-1])
    if direction == "long":
        mfe = (hi - entry) / entry * 100
        mae = (entry - lo) / entry * 100
        ret = (close - entry) / entry * 100
    elif direction == "short":
        mfe = (entry - lo) / entry * 100
        mae = (hi - entry) / entry * 100
        ret = (entry - close) / entry * 100
    else:
        return None
    return {"entry": entry, "mfe": mfe, "mae": mae, "ret": ret, "win": mfe > mae}


def _market_session(ts: datetime) -> str:
    t = ts.time()
    if t < dtime(3, 50):
        return "overnight"
    if t < dtime(4, 0):
        return "closed"
    if t < dtime(9, 30):
        return "pre"
    if t < dtime(16, 0):
        return "regular"
    if t < dtime(20, 0):
        return "post"
    return "overnight"


def v0535_block_reason(record: dict) -> str | None:
    """Return None if passes, else block reason."""
    ind = (record.get("decision_context") or {}).get("indicators_raw") or {}
    if not ind.get("data_ok"):
        return "data_ok=False"
    sig_ts = pd.to_datetime(record["ts"])
    if _market_session(sig_ts) == "closed":
        return "market closed"
    if ind.get("is_today") is False:
        return "is_today=False"
    rsi = ind.get("rsi_14")
    vol = ind.get("vol_ratio")
    if rsi is not None and vol is not None:
        pair = (round(float(rsi), 1), round(float(vol), 2))
        if pair in FROZEN_VALUE_BLACKLIST:
            return f"blacklist {pair}"
    return None


def collect_candidates():
    out = []
    for p in sorted(REVIEW_DIR.glob("2026-*")):
        if not p.is_dir() or p.name > "2026-05-15":
            continue
        tj = p / "triggers.json"
        if not tj.exists():
            continue
        d = json.load(open(tj, encoding="utf-8"))
        for r in d:
            if r.get("trigger") == "direction_trend" and r.get("ticker") == "US.RKLB":
                out.append((p.name, r))
    return out


def main():
    kl = load_kline(HIST_CSV)
    print(f"K_1m bars: {len(kl)} from {kl.index[0]} to {kl.index[-1]}\n")

    cands = collect_candidates()
    print(f"Candidates: {len(cands)} direction_trend records on RKLB\n")

    rows = []
    for date_str, r in cands:
        block = v0535_block_reason(r)
        v35_push = block is None
        ind = (r.get("decision_context") or {}).get("indicators_raw") or {}
        scores = {}
        for w in (5, 10, 15):
            sc = score_signal(kl, r["ts"], r["direction"], w)
            scores[f"win_{w}"] = sc["win"] if sc else None
            scores[f"mfe_{w}"] = sc["mfe"] if sc else None
            scores[f"mae_{w}"] = sc["mae"] if sc else None
            scores[f"ret_{w}"] = sc["ret"] if sc else None

        rows.append({
            "date": date_str,
            "ts": r["ts"],
            "direction": r["direction"],
            "strength": r.get("strength"),
            "rsi": r.get("data", {}).get("rsi"),
            "vol_ratio": r.get("data", {}).get("vol_ratio"),
            "day_chg": r.get("data", {}).get("day_change_pct"),
            "data_ok": ind.get("data_ok"),
            "is_today": ind.get("is_today"),
            "v35_push": v35_push,
            "v35_block_reason": block or "",
            **scores,
        })

    df = pd.DataFrame(rows)
    out_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / "docs"
    detail_path = output_dir / f"v0531_vs_v0535_detail_{out_suffix}.csv"
    report_path = output_dir / f"v0531_vs_v0535_report_{out_suffix}.txt"
    try:
        df.to_csv(detail_path, index=False)
    except PermissionError as e:
        print(f"[WARN] detail CSV not saved: {e}")
        detail_path = None

    out_lines = []

    def line(s=""):
        out_lines.append(s)
        print(s)

    line("=" * 78)
    line("v0.5.31 vs v0.5.35 方向准确率回测  (RKLB direction_trend, 04-24 ~ 05-15)")
    line("=" * 78)
    line(f"\n样本: {len(df)} 候选信号, 可评分 {df['win_10'].notna().sum()} (其他在 overnight 无 K_1m)")

    # ── 主表: 各窗口 v0.5.31 vs v0.5.35 ──
    line("\n┌─ 准确率主表 ─┐")
    line(f"{'窗口':<6} {'版本':<10} {'推送':>5} {'对':>5} {'准确率':>7} {'avgMFE':>8} {'avgMAE':>8} {'avgRet':>8}")
    line("─" * 70)
    for w in (5, 10, 15):
        col = f"win_{w}"
        scored = df[df[col].notna()]
        for label, sub in [("v0.5.31", scored), ("v0.5.35", scored[scored["v35_push"]])]:
            if len(sub) == 0:
                line(f"{w:>2}min  {label:<10} {0:>5}")
                continue
            wins = sub[sub[col] == True]
            wr = len(wins) / len(sub) * 100
            line(f"{w:>2}min  {label:<10} {len(sub):>5} {len(wins):>5} {wr:>6.1f}% "
                 f"{sub[f'mfe_{w}'].mean():>+7.2f}% {sub[f'mae_{w}'].mean():>+7.2f}% {sub[f'ret_{w}'].mean():>+7.2f}%")
        line("")

    # ── 关键洞察: 干净数据 vs 脏数据 ──
    line("\n┌─ 干净 vs 脏数据分层 (10min 窗口) ─┐")
    scored = df[df["win_10"].notna()]
    clean = scored[scored["data_ok"] == True]
    dirty = scored[scored["data_ok"] == False]
    line(f"data_ok=True  : 样本 {len(clean):>3}, 准确 {(clean['win_10']==True).sum():>3} "
         f"({(clean['win_10']==True).mean()*100:5.1f}%), avgRet {clean['ret_10'].mean():+.2f}%")
    line(f"data_ok=False : 样本 {len(dirty):>3}, 准确 {(dirty['win_10']==True).sum():>3} "
         f"({(dirty['win_10']==True).mean()*100:5.1f}%), avgRet {dirty['ret_10'].mean():+.2f}%")

    # ── 阻断原因分布 ──
    line("\n┌─ v0.5.35 阻断原因 ─┐")
    blocked = df[~df["v35_push"]]
    line(f"总阻断: {len(blocked)} / {len(df)} = {len(blocked)/len(df)*100:.1f}%")
    for reason, cnt in blocked["v35_block_reason"].value_counts().items():
        line(f"  {reason:<35}  {cnt:>3}")

    # ── 按方向×强度 ──
    line("\n┌─ v0.5.31 (全推) 按方向×强度  10min 准确率 ─┐")
    g = df[df["win_10"].notna()].groupby(["direction", "strength"])
    for (d, s), sub in g:
        wr = sub["win_10"].mean() * 100
        avg_ret = sub["ret_10"].mean()
        line(f"  {d:>5} / {s:<6}  n={len(sub):>3}  win={wr:5.1f}%  avgRet={avg_ret:+.2f}%")

    # ── data_ok=True 子集再分层 ──
    line("\n┌─ data_ok=True 子集 (v0.5.31 推 / v0.5.35 也推) 按方向 ─┐")
    if len(clean) > 0:
        for d, sub in clean.groupby("direction"):
            wins = (sub["win_10"] == True).sum()
            line(f"  {d:>5}  n={len(sub):>3}  win={wins:>2} ({wins/len(sub)*100:5.1f}%)  avgRet={sub['ret_10'].mean():+.2f}%")

    try:
        report_path.write_text("\n".join(out_lines), encoding="utf-8")
        print(f"\nReport saved: {report_path}")
    except PermissionError as e:
        print(f"\n[WARN] report not saved: {e}")
    print(f"Detail CSV:   {detail_path or '(not saved)'}")


if __name__ == "__main__":
    main()
