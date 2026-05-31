"""
诊断: 目标价突破后是否会自动升级到下一档？
读 data/review/2026-05-12/triggers.json，找 RKLB 突破 $120 前后的推送
"""
import json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\MagicQuant\data\review\2026-05-12\triggers.json")
data = json.loads(P.read_text(encoding="utf-8"))
print(f"今日触发总数: {len(data)}")

# trigger 类型分布
from collections import Counter
ct = Counter(d["trigger"] for d in data)
print("\nTrigger 类型分布:")
for k, v in ct.most_common(10):
    print(f"  {k:30s} {v}")

# 找 RKLB 实际价格穿越 $120 的时刻
print("\nRKLB 在 $120 附近的关键时刻:")
prev_px = None
crossed_120_ts = None
for d in data:
    px = d.get("prices", {}).get("RKLB")
    if px is None:
        continue
    if prev_px is not None and prev_px < 120 and px >= 120:
        crossed_120_ts = d["ts"]
        print(f"  {d['ts']}  RKLB 上穿 $120 (从 ${prev_px} → ${px})  trigger={d['trigger']} ticker={d['ticker']}")
        break
    prev_px = px

if crossed_120_ts is None:
    print("  没找到从 <120 跨到 ≥120 的连续事件，看每条触发记录的 RKLB 价格走势:")
    pxs = [(d["ts"], d.get("prices", {}).get("RKLB")) for d in data if d.get("prices", {}).get("RKLB")]
    rklb_pxs = [p for _, p in pxs]
    print(f"  RKLB 价格范围: {min(rklb_pxs):.2f} ~ {max(rklb_pxs):.2f}")
    print(f"  突破 $120 的样本数: {sum(1 for p in rklb_pxs if p >= 120)}")
    if any(p >= 120 for p in rklb_pxs):
        crossed_120_ts = next(ts for ts, p in pxs if p >= 120)
        print(f"  首次 ≥$120 的时间: {crossed_120_ts}")

# 在 cross 前后各取 5 条 RKLB 推送，看 t1/t2 是否变化
print("\nRKLB 相关推送中的 t1/t2 值（首次 ≥$120 前 3 条 + 后 5 条）:")
rklb_hits = [d for d in data if "RKLB" in d.get("ticker", "")]
print(f"  RKLB 触发总数: {len(rklb_hits)}")

# 看有 t1 字段的推送
with_t1 = [d for d in rklb_hits if d.get("data", {}).get("t1") is not None]
print(f"  含 t1 字段的: {len(with_t1)}")
print(f"  含 'target'/'目标' 字眼的 message_text 数: "
      f"{sum(1 for d in rklb_hits if '目标' in d.get('message_text', ''))}")
print(f"  含 '更新'/'升级' 字眼的: "
      f"{sum(1 for d in rklb_hits if '更新' in d.get('message_text', '') or '升级' in d.get('message_text', ''))}")

# 列出含目标价的所有 RKLB 推送（不含 RKLZ/RKLX 推送）
print("\n所有 RKLB（不含 X/Z）含 t1 的推送的 t1/t2/price 序列:")
seen = []
for d in rklb_hits:
    if d.get("ticker") != "US.RKLB":
        continue
    t1 = d.get("data", {}).get("t1")
    t2 = d.get("data", {}).get("t2")
    if t1:
        seen.append({
            "ts": d["ts"],
            "trigger": d["trigger"],
            "price": d.get("prices", {}).get("RKLB"),
            "t1": t1, "t2": t2,
        })
for s in seen[:25]:
    print(f"  {s['ts']}  {s['trigger']:25s} price=${s['price']}  t1=${s['t1']}  t2=${s['t2']}")
print(f"  ... 共 {len(seen)} 条")

# 找消息文本里包含 "目标" 的，验证语言
print("\nmessage_text 含 '目标' 的样例（前 3 条）:")
shown = 0
for d in rklb_hits:
    if shown >= 3:
        break
    txt = d.get("message_text", "")
    if "目标" in txt:
        # 截取目标价附近
        idx = txt.find("目标")
        chunk = txt[max(0, idx-30):idx+200].replace("\n", " | ")
        print(f"  [{d['ts']}] {d['trigger']}: ...{chunk}...")
        shown += 1
