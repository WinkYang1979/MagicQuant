"""Moomoo AU 美股手续费 —— 自包含副本(与 core/agents/portfolio.py 口径一致,但不依赖它)。

买入: $0.99 + $0.30 = $1.29 固定
卖出: $0.99 + $0.30 + SEC(成交额×0.0000278) + FINRA TAF(股数×0.000166, [0.01, 8.30])
"""

PLATFORM_FEE   = 0.99
SETTLEMENT_FEE = 0.30
SEC_FEE_RATE   = 0.0000278
TAF_RATE       = 0.000166
TAF_MIN        = 0.01
TAF_MAX        = 8.30


def calc_fee(side: str, price: float, qty: int) -> float:
    if qty <= 0:
        return 0.0
    if side == "buy":
        return round(PLATFORM_FEE + SETTLEMENT_FEE, 4)
    amount  = price * qty
    sec_fee = round(amount * SEC_FEE_RATE, 2)
    taf     = min(max(round(qty * TAF_RATE, 2), TAF_MIN), TAF_MAX)
    return round(PLATFORM_FEE + SETTLEMENT_FEE + sec_fee + taf, 4)
