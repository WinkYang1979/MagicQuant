"""
快速诊断:看 Moomoo position_list_query 返回的所有字段名
放在 C:\\MagicQuant\\,运行:
    python diag_position_fields.py
"""
try:
    from moomoo import OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm, RET_OK
except ImportError:
    from futu import OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm, RET_OK

from config.settings import FUTU_HOST, FUTU_PORT

ctx = OpenSecTradeContext(
    filter_trdmarket=TrdMarket.US,
    security_firm=SecurityFirm.FUTUAU,
    host=FUTU_HOST, port=FUTU_PORT,
)

print("\n=== position_list_query 字段探测 ===")
ret, data = ctx.position_list_query(trd_env=TrdEnv.REAL, refresh_cache=True)
if ret != RET_OK:
    print(f"失败: {data}")
else:
    print(f"共 {len(data)} 条持仓, 全部列名:")
    print(f"  {list(data.columns)}")
    print()
    if len(data) > 0:
        print("第 1 条完整数据:")
        row = data.iloc[0]
        for col in data.columns:
            val = row[col]
            print(f"  {col:28s} = {val}")

ctx.close()
