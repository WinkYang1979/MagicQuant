"""
swing_bottom / swing_top edge 回测
─────────────────────────────────
候选集: data/review/{date}/triggers.json (04-24~05-15) US.RKLB
价格源: data/historical/RKLB_1m.csv (Futu 干净数据)
评分窗口: 5/10/15/30 min
评分方法: MFE > MAE 算"对"
分层分析: 按 strength (WEAK/STRONG) / 时段 / RSI / 占位指标
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
REVIEW_DIR = ROOT / "data" / "review"
HIST_CSV = ROOT / "data" / "historical" / "RKLB_1m.csv"

TARGET_TRIGGERS = {"swing_bottom", "swing_top"}
WINDOWS = (5, 10, 15, 30)


def load_kline() -> pd.DataFrame:
    df = pd.read_csv(HIST_CSV)
    df["dt"] = pd.to_datetime(df["time_key"])
    return df.set_index("dt").sort_index()


def score(kl: pd.DataFrame, sig_ts: str, direction: str, window_min: int):
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
            if r.get("trigger") not in TARGET_TRIGGERS:
                continue
            if r.get("ticker") != "US.RKLB":
                continue
            out.append((p.name, r))
    return out


def is_placeholder_indicator(record):
    """RSI=50.0 + vol_ratio=1.0 is the calc_all_micro fallback default."""
    data = record.get("data", {})
    rsi = data.get("rsi")
    vol = data.get("vol_ratio")
    return rsi == 50.0 and vol == 1.0


def main():
    kl = load_kline()
    print(f"K_1m bars: {len(kl)} from {kl.index[0]} to {kl.index[-1]}\n")

    cands = collect_candidates()
    print(f"Candidates: {len(cands)} swing_bottom + swing_top records (US.RKLB)\n")

    rows = []
    for date_str, r in cands:
        row = {
            "date": date_str,
            "ts": r["ts"],
            "trigger": r["trigger"],
            "direction": r["direction"],
            "strength": r.get("strength"),
            "rsi": r.get("data", {}).get("rsi"),
            "vol_ratio": r.get("data", {}).get("vol_ratio"),
            "day_chg": r.get("data", {}).get("day_change_pct"),
            "placeholder": is_placeholder_indicator(r),
        }
        ts = pd.to_datetime(r["ts"])
        row["hour"] = ts.hour
        for w in WINDOWS:
            sc = score(kl, r["ts"], r["direction"], w)
            row[f"win_{w}"] = sc["win"] if sc else None
            row[f"mfe_{w}"] = sc["mfe"] if sc else None
            row[f"mae_{w}"] = sc["mae"] if sc else None
            row[f"ret_{w}"] = sc["ret"] if sc else None
        rows.append(row)

    df = pd.DataFrame(rows)
    detail_path = ROOT / "data" / "backtest" / "swing_signals_detail.csv"
    df.to_csv(detail_path, index=False)

    out_lines = []

    def line(s=""):
        out_lines.append(s)
        print(s)

    # ── 全样本汇总 ──
    line("=" * 84)
    line(f"swing_bottom / swing_top 回测  (RKLB, 04-24~05-15, n={len(df)})")
    line("=" * 84)
    scored = df[df["win_10"].notna()]
    line(f"\n样本 {len(df)} 候选, 可评分 {len(scored)} (overnight 时段 Futu 无 K_1m)")
    if len(scored) > 0:
        line(f"占位指标 (rsi=50,vol=1) 比例: {scored['placeholder'].sum()}/{len(scored)} "
             f"({scored['placeholder'].mean()*100:.1f}%)")

    # ── 主表: 按 trigger × strength × window ──
    line("\n┌─ 主表: trigger × strength × 窗口 ─┐")
    line(f"{'trigger':<14} {'strength':<8} {'window':<7} {'n':>4} "
         f"{'win%':>6} {'avgMFE':>8} {'avgMAE':>8} {'avgRet':>8}")
    line("─" * 75)
    for trig in ("swing_bottom", "swing_top"):
        for stren in ("WEAK", "STRONG"):
            for w in WINDOWS:
                sub = df[
                    (df["trigger"] == trig)
                    & (df["strength"] == stren)
                    & (df[f"win_{w}"].notna())
                ]
                if len(sub) == 0:
                    continue
                wins = (sub[f"win_{w}"] == True).sum()
                wr = wins / len(sub) * 100
                line(f"{trig:<14} {stren:<8} {w:>2}min   {len(sub):>4} "
                     f"{wr:>5.1f}% {sub[f'mfe_{w}'].mean():>+7.2f}% "
                     f"{sub[f'mae_{w}'].mean():>+7.2f}% {sub[f'ret_{w}'].mean():>+7.2f}%")
        line("")

    # ── 占位指标 vs 真实指标 (10min) ──
    line("┌─ 占位指标 vs 真实指标 (10min 窗口) ─┐")
    line(f"{'trigger':<14} {'placeholder?':<14} {'n':>4} {'win%':>6} {'avgRet10':>10}")
    for trig in ("swing_bottom", "swing_top"):
        for ph_flag, label in [(True, "占位指标"), (False, "真实指标")]:
            sub = df[
                (df["trigger"] == trig)
                & (df["placeholder"] == ph_flag)
                & (df["win_10"].notna())
            ]
            if len(sub) == 0:
                continue
            wr = (sub["win_10"] == True).mean() * 100
            line(f"{trig:<14} {label:<14} {len(sub):>4} {wr:>5.1f}% "
                 f"{sub['ret_10'].mean():>+9.3f}%")
    line("")

    # ── 按 RSI 区间 (仅真实指标, 10min) ──
    line("┌─ 按 RSI 区间 (剔除占位, 10min) ─┐")
    line(f"{'trigger':<14} {'RSI bin':<10} {'n':>4} {'win%':>6} {'avgRet10':>10}")
    for trig in ("swing_bottom", "swing_top"):
        real = df[
            (df["trigger"] == trig)
            & (~df["placeholder"])
            & (df["win_10"].notna())
        ]
        if len(real) == 0:
            line(f"{trig:<14} (no real-indicator samples)")
            continue
        bins = [(0, 25), (25, 35), (35, 45), (45, 55), (55, 65), (65, 75), (75, 100)]
        for lo, hi in bins:
            sub = real[(real["rsi"] >= lo) & (real["rsi"] < hi)]
            if len(sub) == 0:
                continue
            wr = (sub["win_10"] == True).mean() * 100
            line(f"{trig:<14} {lo:>3}-{hi:<6}   {len(sub):>4} {wr:>5.1f}% "
                 f"{sub['ret_10'].mean():>+9.3f}%")
    line("")

    # ── 按时段 (仅真实指标, 10min) ──
    line("┌─ 按 ET hour (剔除占位, 10min) ─┐")
    line(f"{'trigger':<14} {'hour':<6} {'n':>4} {'win%':>6} {'avgRet10':>10}")
    for trig in ("swing_bottom", "swing_top"):
        real = df[(df["trigger"] == trig) & (~df["placeholder"]) & (df["win_10"].notna())]
        if len(real) == 0:
            continue
        for h, sub in real.groupby("hour"):
            wr = (sub["win_10"] == True).mean() * 100
            line(f"{trig:<14} {h:<6} {len(sub):>4} {wr:>5.1f}% "
                 f"{sub['ret_10'].mean():>+9.3f}%")
    line("")

    # ── 综合结论 ──
    line("=" * 84)
    line("综合结论:")
    line("=" * 84)
    for trig in ("swing_bottom", "swing_top"):
        sub = df[(df["trigger"] == trig) & (df["win_10"].notna())]
        real = sub[~sub["placeholder"]]
        line(f"\n{trig}:")
        line(f"  全部 n={len(sub):>3}  win10={(sub['win_10']==True).mean()*100 if len(sub)>0 else 0:.1f}%  "
             f"avgRet10={sub['ret_10'].mean() if len(sub)>0 else 0:+.3f}%")
        line(f"  真实 n={len(real):>3}  win10={(real['win_10']==True).mean()*100 if len(real)>0 else 0:.1f}%  "
             f"avgRet10={real['ret_10'].mean() if len(real)>0 else 0:+.3f}%")
        if len(real) >= 10:
            # 5min 最准的 strength
            for stren in ("WEAK", "STRONG"):
                sx = real[real["strength"] == stren]
                if len(sx) >= 5:
                    line(f"  {stren:<6} n={len(sx):>3}  win10={(sx['win_10']==True).mean()*100:.1f}%  "
                         f"avgRet10={sx['ret_10'].mean():+.3f}%")

    out_path = ROOT / "data" / "backtest" / "swing_signals_eda.txt"
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\nReport: {out_path}")
    print(f"Detail: {detail_path}")


if __name__ == "__main__":
    main()
