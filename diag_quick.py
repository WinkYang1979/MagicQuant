"""
快速验证 — 看 MagicQuant 的 QuoteClient 实际拿到什么价
放 C:\MagicQuant\,运行:
    python diag_quick.py
"""
from core.realtime_quote import get_client
from datetime import datetime

client = get_client()
for tk in ["US.RKLB", "US.RKLX", "US.RKLZ"]:
    q = client.fetch_one(tk)
    if q:
        print(f"{tk}: ${q['price']}  ({q['change_pct']:+.2f}%)  "
              f"update_time={q['update_time']}  age={q['age_sec']}s")
    else:
        print(f"{tk}: ❌ None")

print(f"\n本地时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
