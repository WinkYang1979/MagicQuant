"""
一次性查询今日成交 — 用独立的 OpenSecTradeContext，不打扰正在跑的 bot
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import FUTU_HOST, FUTU_PORT

try:
    from moomoo import OpenSecTradeContext, TrdEnv, TrdMarket, RET_OK
    try:
        from moomoo import SecurityFirm
        sec_firm = SecurityFirm.FUTUAU
    except Exception:
        sec_firm = None
except ImportError:
    from futu import OpenSecTradeContext, TrdEnv, TrdMarket, RET_OK
    try:
        from futu import SecurityFirm
        sec_firm = SecurityFirm.FUTUAU
    except Exception:
        sec_firm = None

print(f"连 OpenD @ {FUTU_HOST}:{FUTU_PORT}")
kwargs = dict(filter_trdmarket=TrdMarket.US, host=FUTU_HOST, port=FUTU_PORT)
if sec_firm is not None:
    kwargs["security_firm"] = sec_firm

ctx = OpenSecTradeContext(**kwargs)

print("\n=== 今日成交 deal_list_query ===")
ret, deals = ctx.deal_list_query(trd_env=TrdEnv.REAL)
if ret != RET_OK:
    print(f"FAIL: {deals}")
else:
    if deals is None or len(deals) == 0:
        print("(空)")
    else:
        print(f"共 {len(deals)} 条:")
        cols = [c for c in ["create_time", "code", "stock_name", "trd_side", "qty",
                            "price", "deal_id", "order_id", "status"] if c in deals.columns]
        print(deals[cols].to_string(index=False))

print("\n=== 今日订单 history_order_list_query ===")
try:
    ret, orders = ctx.history_order_list_query(trd_env=TrdEnv.REAL)
    if ret != RET_OK:
        print(f"FAIL: {orders}")
    elif orders is None or len(orders) == 0:
        print("(空)")
    else:
        print(f"共 {len(orders)} 条:")
        cols = [c for c in ["create_time", "updated_time", "code", "stock_name",
                            "trd_side", "qty", "dealt_qty", "price", "dealt_avg_price",
                            "order_type", "order_status", "order_id"] if c in orders.columns]
        print(orders[cols].to_string(index=False))
except Exception as e:
    print(f"order query error: {e}")

ctx.close()
print("\n[完成]")
