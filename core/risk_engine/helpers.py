"""
MagicQuant Risk Engine — Helper 函数
Dare to dream. Data to win.

基于 Moomoo AU 2026-04 交割单实测校准的费率公式.

包含:
  - estimate_fees         估算单边 + 往返费用
  - estimate_expected_net_profit  预期净利润(扣费后)
  - compute_rr_ratio      风险收益比(扣费后)
  - min_profitable_qty    最小有意义仓位
"""


# ══════════════════════════════════════════════════════════════════
#  Moomoo AU 费率常量(2026-04 交割单校准)
# ══════════════════════════════════════════════════════════════════

MOOMOO_PLATFORM_FEE   = 0.99      # 平台费(固定)
MOOMOO_SETTLEMENT_FEE = 0.30      # 结算费(固定)
SEC_FEE_RATE          = 0.0000278 # SEC 费率(按成交额)
TAF_PER_SHARE         = 0.000166  # TAF(按股数)
TAF_MIN               = 0.01
TAF_MAX               = 8.30


# ══════════════════════════════════════════════════════════════════
#  核心 helper
# ══════════════════════════════════════════════════════════════════

def estimate_fees(qty: int, price: float) -> dict:
    """
    估算交易费用.
    
    买入: 固定 $1.29 (Platform $0.99 + Settlement $0.30)
    卖出: $0.99 + $0.30 + SEC(成交额 × 0.0000278) + TAF(股数 × 0.000166, $0.01~$8.30)
    
    返回:
        {
          "buy_fee":    float,
          "sell_fee":   float,
          "roundtrip":  float,
          "breakdown":  {platform, settlement, sec_fee, taf}
        }
    """
    if qty <= 0 or price <= 0:
        return {
            "buy_fee": 0.0, "sell_fee": 0.0, "roundtrip": 0.0,
            "breakdown": {"platform": 0, "settlement": 0, "sec_fee": 0, "taf": 0},
        }
    
    buy_fee = MOOMOO_PLATFORM_FEE + MOOMOO_SETTLEMENT_FEE
    
    # 卖出动态部分
    amount = qty * price
    sec_fee = amount * SEC_FEE_RATE
    taf = min(max(qty * TAF_PER_SHARE, TAF_MIN), TAF_MAX)
    sell_fee = MOOMOO_PLATFORM_FEE + MOOMOO_SETTLEMENT_FEE + sec_fee + taf
    
    return {
        "buy_fee":   round(buy_fee, 4),
        "sell_fee":  round(sell_fee, 4),
        "roundtrip": round(buy_fee + sell_fee, 4),
        "breakdown": {
            "platform":   MOOMOO_PLATFORM_FEE,
            "settlement": MOOMOO_SETTLEMENT_FEE,
            "sec_fee":    round(sec_fee, 4),
            "taf":        round(taf, 4),
        },
    }


def estimate_expected_net_profit(entry: float, target: float,
                                  qty: int, direction: str = "long") -> float:
    """
    预期净利润 = 毛利润 - 往返费用
    
    direction: "long" | "short"
    """
    if qty <= 0 or entry <= 0 or target <= 0:
        return 0.0
    
    fees = estimate_fees(qty, entry)["roundtrip"]
    
    if direction == "long":
        gross = (target - entry) * qty
    elif direction == "short":
        gross = (entry - target) * qty
    else:
        gross = 0
    
    return round(gross - fees, 2)


def estimate_net_loss(entry: float, stop: float,
                      qty: int, direction: str = "long") -> float:
    """
    打到止损时的最大亏损(正数, 含费用).
    """
    if qty <= 0 or entry <= 0 or stop <= 0:
        return 0.0
    
    fees = estimate_fees(qty, entry)["roundtrip"]
    
    if direction == "long":
        gross = (entry - stop) * qty
    elif direction == "short":
        gross = (stop - entry) * qty
    else:
        gross = 0
    
    return round(gross + fees, 2)


def compute_rr_ratio(entry: float, target: float, stop: float,
                     qty: int, direction: str = "long") -> float:
    """
    风险收益比 = 净利润 / 净亏损
    
    >= 2.0  优秀
    >= 1.5  合格(v0.4 默认阈值)
    < 1.5   警告
    """
    net_profit = estimate_expected_net_profit(entry, target, qty, direction)
    net_loss = estimate_net_loss(entry, stop, qty, direction)
    
    if net_loss <= 0:
        return 0.0
    return round(net_profit / net_loss, 2)


def min_profitable_qty(entry: float, target: float,
                       min_net_profit: float = 5.0,
                       direction: str = "long") -> int:
    """
    达到最小净利润的最少股数.
    
    用途: 当 qty 太小时, 建议"要不别做, 要不做大点".
    
    近似公式 (忽略 SEC/TAF 的细小影响):
      qty * |target - entry| - 2.58 >= min_net_profit
      qty >= (min_net_profit + 2.58) / |target - entry|
    """
    gross_per_share = abs(target - entry)
    if gross_per_share <= 0:
        return 999999
    
    # 2.58 = buy_fee (1.29) + sell_fee 基础 (1.29)
    # 忽略 SEC/TAF 因其与 qty 弱相关
    approx_qty = int((min_net_profit + 2.58) / gross_per_share) + 1
    return max(1, approx_qty)


def compute_position_concentration_pct(position_value: float,
                                        total_portfolio_value: float) -> float:
    """
    单票市值占总资产百分比.
    总资产包括 cash + 所有持仓市值.
    """
    if total_portfolio_value <= 0:
        return 0.0
    return round(position_value / total_portfolio_value * 100, 2)


def compute_effective_leverage(positions: dict, cash: float) -> float:
    """
    计算有效杠杆(含 2x ETF 放大).
    
    RKLX / RKLZ 本身 2x 杠杆 → 放大系数 2
    持有 $5000 RKLX = 实际风险敞口 $10000
    
    有效杠杆 = Σ(position_value × leverage_factor) / 总资产
    """
    if not positions:
        return 0.0
    
    # 2x 杠杆 ETF 列表
    LEVERAGED_2X = {"RKLX", "RKLZ", "TSLL", "TSLQ", "SOXL", "SOXS"}
    
    total_exposure = 0.0
    total_position_value = 0.0
    
    for tk, pos in positions.items():
        ticker_short = tk.replace("US.", "") if isinstance(tk, str) else str(tk)
        qty = pos.get("qty", 0) or pos.get("qty_held", 0)
        price = pos.get("current_price") or pos.get("cost_price", 0)
        
        if qty <= 0 or price <= 0:
            continue
        
        pos_value = qty * price
        total_position_value += pos_value
        
        factor = 2.0 if ticker_short in LEVERAGED_2X else 1.0
        total_exposure += pos_value * factor
    
    total_assets = total_position_value + cash
    if total_assets <= 0:
        return 0.0
    
    return round(total_exposure / total_assets, 2)
