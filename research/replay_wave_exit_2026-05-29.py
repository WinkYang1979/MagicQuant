# -*- coding: utf-8 -*-
"""
回放: "shadow_targeted_* → 低频波段提醒" 出口方案
─────────────────────────────────────────────
目的: 用真实录制数据(data/review/{date}/)验证 Codex 提的
      "把已检测到的 shadow 信号开一个低频 Telegram 出口" 方案,
      到底会推几条 / 节奏如何 / 方向是否命中 / 能否覆盖用户箭头点。

数据源:
  - shadow_signals.json  (已检测的波段拐点候选, 当前 shadow_only=True 不推)
  - kline_5m_RKLB.json   (当天真实 5m K 线, 用于前向打分)

不改任何 core/focus 代码; 纯纸面回放。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "data" / "review"
DATES = ["2026-05-28", "2026-05-29"]
# 用户在 05-29 截图上标的箭头点 (ET, 近似)
ARROWS_0529 = ["00:34", "02:42", "03:03", "03:33", "04:16"]
FWD_WINDOWS = (15, 30)  # 前向打分窗口(分钟)
COOLDOWN_MIN = 30       # 每方向冷却


def load_json(p):
    return json.load(open(p, encoding="utf-8"))


def load_kline(date):
    # 优先用 Futu 全时段补足数据(含隔夜, 无快照截断); 缺失才回退 review 录制快照
    full = ROOT / "data" / "historical" / "RKLB_5m_2026-05-28_2026-05-29_full.json"
    rows = load_json(full) if full.exists() else load_json(REVIEW / date / "kline_5m_RKLB.json")
    out = []
    for r in rows:
        out.append((datetime.strptime(r["time_key"], "%Y-%m-%d %H:%M:%S"),
                    float(r["high"]), float(r["low"]), float(r["close"])))
    out.sort(key=lambda x: x[0])
    return out


def fwd_score(kl, ts, entry, direction, win_min):
    """前向窗口内 MFE/MAE/收盘收益(%). 数据不足返回 None."""
    end = ts + timedelta(minutes=win_min)
    fut = [(t, h, l, c) for (t, h, l, c) in kl if ts < t <= end]
    if len(fut) < 2:
        return None
    hi = max(h for _, h, _, _ in fut)
    lo = min(l for _, _, l, _ in fut)
    close = fut[-1][3]
    if direction == "long":
        return dict(mfe=(hi - entry) / entry * 100,
                    mae=(entry - lo) / entry * 100,
                    ret=(close - entry) / entry * 100,
                    bars=len(fut))
    else:  # short
        return dict(mfe=(entry - lo) / entry * 100,
                    mae=(hi - entry) / entry * 100,
                    ret=(entry - close) / entry * 100,
                    bars=len(fut))


def apply_gate(sigs, gate):
    """套通知闸门 + 每方向 30min 冷却, 返回会真正推送的信号列表."""
    out = []
    last_push = {}  # direction -> ts
    for s in sigs:
        ts = datetime.strptime(s["ts"], "%Y-%m-%d %H:%M:%S")
        if not gate(s):
            continue
        d = s["direction"]
        if d in last_push and (ts - last_push[d]).total_seconds() < COOLDOWN_MIN * 60:
            continue  # 冷却内, 压掉
        last_push[d] = ts
        out.append(s)
    return out


# 三个候选闸门
GATES = {
    "A_raw(无闸门)":            lambda s: True,
    "B_+量比0.8确认":           lambda s: (s.get("vol_ratio") or 0) >= 0.8,
    "C_+量比0.8且动量确认":      lambda s: (s.get("vol_ratio") or 0) >= 0.8 and (
        (s["direction"] == "long" and (s.get("move5_pct") or 0) > 0) or
        (s["direction"] == "short" and (s.get("move5_pct") or 0) < 0)),
}


def main():
    for date in DATES:
        sd_path = REVIEW / date / "shadow_signals.json"
        if not sd_path.exists():
            continue
        sigs = sorted(load_json(sd_path), key=lambda s: s["ts"])
        kl = load_kline(date)
        kl_end = kl[-1][0] if kl else None

        print("=" * 70)
        print(f"  {date}   shadow 候选 {len(sigs)} 条   5m K线覆盖到 {kl_end}")
        print("=" * 70)

        # 逐条: 闸门通过情况 + 前向打分
        print(f"{'时间ET':<9}{'trigger':<26}{'方向':<6}{'RSI':>5}{'量比':>6}"
              f"{'  fwd15(ret/mfe/mae)':<24}{'fwd30(ret/mfe/mae)':<22}{'命中':>5}")
        for s in sigs:
            ts = datetime.strptime(s["ts"], "%Y-%m-%d %H:%M:%S")
            entry = float(s["current"])
            sc = {w: fwd_score(kl, ts, entry, s["direction"], w) for w in FWD_WINDOWS}
            def fmt(x):
                if x is None:
                    return "数据不足".ljust(18)
                return f"{x['ret']:+.2f}/{x['mfe']:.2f}/{x['mae']:.2f}".ljust(20)
            # 命中判定: 用 15min 收益方向(long要涨/short要跌)
            s15 = sc[15]
            hit = "" if s15 is None else ("✓" if s15["ret"] > 0 else "✗")
            tn = ts.strftime("%H:%M")
            print(f"{tn:<9}{s['trigger']:<26}{s['direction']:<6}{s.get('rsi',0):>5.1f}"
                  f"{s.get('vol_ratio',0):>6.2f}  {fmt(sc[15])}{fmt(sc[30])}{hit:>5}")

        # 三闸门: 推送量 / 节奏 / 命中率 / 覆盖
        print(f"\n  --- 闸门对比 (含每方向 {COOLDOWN_MIN}min 冷却) ---")
        for name, gate in GATES.items():
            pushed = apply_gate(sigs, gate)
            # 节奏: 相邻推送最小间隔
            tss = [datetime.strptime(p["ts"], "%Y-%m-%d %H:%M:%S") for p in pushed]
            gaps = [(tss[i] - tss[i-1]).total_seconds() / 60 for i in range(1, len(tss))]
            min_gap = f"{min(gaps):.0f}min" if gaps else "-"
            # 方向命中率(15min)
            hits = tot = 0
            for p in pushed:
                ts = datetime.strptime(p["ts"], "%Y-%m-%d %H:%M:%S")
                sc = fwd_score(kl, ts, float(p["current"]), p["direction"], 15)
                if sc is not None:
                    tot += 1
                    hits += 1 if sc["ret"] > 0 else 0
            hr = f"{hits}/{tot}" if tot else "n/a"
            # 覆盖箭头(仅 05-29)
            cov = ""
            if date == "2026-05-29":
                ph = {datetime.strptime(p["ts"], "%Y-%m-%d %H:%M:%S").strftime("%H:%M") for p in pushed}
                covered = [a for a in ARROWS_0529 if any(abs((datetime.strptime(date+" "+a, "%Y-%m-%d %H:%M")
                            - datetime.strptime(date+" "+x, "%Y-%m-%d %H:%M")).total_seconds()) <= 300 for x in ph)]
                cov = f"  覆盖箭头 {len(covered)}/{len(ARROWS_0529)}: {covered}"
            print(f"  {name:<22} 推送 {len(pushed)} 条 | 最小间隔 {min_gap} | "
                  f"方向命中(15m) {hr}{cov}")
        print()


if __name__ == "__main__":
    main()
