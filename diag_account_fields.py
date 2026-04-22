"""
accinfo_query 字段探测
C:\\MagicQuant\\ 下跑:
    python diag_account_fields.py
"""
try:
    from moomoo import (
        OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm, Currency, RET_OK
    )
except ImportError:
    from futu import (
        OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm, Currency, RET_OK
    )

from config.settings import FUTU_HOST, FUTU_PORT

ctx = OpenSecTradeContext(
    filter_trdmarket=TrdMarket.US,
    security_firm=SecurityFirm.FUTUAU,
    host=FUTU_HOST, port=FUTU_PORT,
)

print("\n" + "="*70)
print("  【1】默认(无 currency 参数):")
print("="*70)
ret, data = ctx.accinfo_query(trd_env=TrdEnv.REAL, refresh_cache=True)
if ret == RET_OK and data is not None and len(data) > 0:
    print(f"  列名: {list(data.columns)}")
    print(f"  行数: {len(data)}")
    for i, row in data.iterrows():
        print(f"\n  第 {i} 行完整数据:")
        for col in data.columns:
            print(f"    {col:30s} = {row[col]}")
else:
    print(f"  失败: {data}")


# 尝试枚举各种 currency
for cur_name in ["USD", "HKD", "AUD", "NONE"]:
    cur_enum = getattr(Currency, cur_name, None)
    if cur_enum is None and cur_name != "NONE":
        print(f"\n  (Currency.{cur_name} 枚举不存在)")
        continue
    print("\n" + "="*70)
    if cur_name == "NONE":
        continue
    print(f"  【2】currency=Currency.{cur_name}:")
    print("="*70)
    try:
        ret, data = ctx.accinfo_query(
            trd_env=TrdEnv.REAL, refresh_cache=True,
            currency=cur_enum,
        )
        if ret == RET_OK and data is not None and len(data) > 0:
            for i, row in data.iterrows():
                key_fields = ["cash", "power", "total_assets", "market_val",
                              "currency", "realized_pl", "unrealized_pl"]
                parts = []
                for k in key_fields:
                    if k in row.index:
                        parts.append(f"{k}={row[k]}")
                print(f"    {' | '.join(parts)}")
        else:
            print(f"  失败: {data}")
    except Exception as e:
        print(f"  异常: {e}")

ctx.close()
