"""
futu_data_collector.py - 全量数据采集器
一次性拉取所有有用的 Futu/Moomoo 数据，保存到 account_data.json
包含：账户信息、持仓、今日订单、历史订单、成交记录、资金流水、行情快照

Run: python futu_data_collector.py
"""

import json, os
from datetime import datetime, timedelta

try:
    from moomoo import (
        OpenQuoteContext, OpenSecTradeContext,
        SubType, KLType, RET_OK, AuType,
        TrdMarket, TrdEnv, TrdSide, OrderStatus,
        Market, SecurityType, SecurityFirm
    )
except ImportError:
    from futu import (
        OpenQuoteContext, OpenSecTradeContext,
        SubType, KLType, RET_OK, AuType,
        TrdMarket, TrdEnv, TrdSide, OrderStatus,
        Market, SecurityType, SecurityFirm
    )

HOST     = "127.0.0.1"
PORT     = 11111
import sys
sys.path.insert(0, r"C:\MagicQuant")
from config.settings import ACCOUNT_FILE as OUT_FILE, FUTU_HOST as HOST, FUTU_PORT as PORT, DEFAULT_WATCHLIST as TICKERS
TICKERS  = ["US.TSLA", "US.SOXL", "US.RKLB", "US.RKLX"]


def safe(fn, label=""):
    try:
        return fn()
    except Exception as e:
        print(f"  [{label}] Error: {e}")
        return None


def collect_account(trd_ctx):
    """账户资产信息
    Moomoo AU 默认 accinfo_query 返回 HKD 聚合值。
    us_cash / usd_assets 是内置的 USD 独立字段，覆盖写入 cash/total_assets/market_val
    供 bot_controller JSON fallback 正确读取 USD 值。
    """
    ret, data = trd_ctx.accinfo_query(trd_env=TrdEnv.REAL, refresh_cache=True)
    if ret != RET_OK or len(data) == 0:
        return {}
    row = data.iloc[0]

    # 存全部原始字段
    result = {}
    for col in data.columns:
        try:
            val = row[col]
            result[col] = float(val) if hasattr(val, '__float__') else str(val)
        except:
            result[col] = str(row[col])

    def _fv(*keys, default=0.0):
        for k in keys:
            v = result.get(k)
            if v is not None:
                try:
                    fv = float(v)
                    if fv == fv and fv != 0.0:   # 非 NaN、非 0
                        return fv
                except (TypeError, ValueError):
                    pass
        return default

    # us_cash = Moomoo UI 显示的 USD 现金总额
    # usd_assets = 美股账户 USD 总资产
    usd_cash   = _fv("us_cash", "usd_cash")
    usd_assets = _fv("usd_assets")
    usd_avl    = _fv("us_avl_withdrawal_cash")

    if usd_cash > 0 or usd_assets > 0:
        # 用 HKD 原始字段做诊断保留，USD 字段覆盖主键
        result["raw_hkd_cash"]        = result.get("cash", 0)
        result["raw_hkd_total_assets"]= result.get("total_assets", 0)
        result["raw_hkd_market_val"]  = result.get("market_val", 0)

        result["cash"]         = usd_cash
        result["total_assets"] = usd_assets
        result["market_val"]   = round(max(0.0, usd_assets - usd_cash), 2)
        result["avl_withdrawal_cash"] = usd_avl
        result["currency"]     = "USD"

    print(f"  账户总资产 (USD): ${result.get('total_assets', 0):,.2f}")
    print(f"  可用现金   (USD): ${result.get('cash', 0):,.2f}")
    print(f"  持仓市值   (USD): ${result.get('market_val', 0):,.2f}")
    return result


def collect_positions(trd_ctx):
    """当前持仓"""
    ret, data = trd_ctx.position_list_query(trd_env=TrdEnv.REAL)
    if ret != RET_OK or len(data) == 0:
        return []
    positions = []
    for _, row in data.iterrows():
        pos = {}
        for col in data.columns:
            try:
                val = row[col]
                pos[col] = float(val) if hasattr(val, '__float__') else str(val)
            except:
                pos[col] = str(row[col])
        positions.append(pos)
        print(f"  持仓: {pos.get('code','')} {pos.get('qty',0)}股 "
              f"成本${pos.get('cost_price',0):.2f} "
              f"盈亏${pos.get('pl_val',0):.2f}")
    return positions


def collect_today_orders(trd_ctx):
    """今日订单"""
    ret, data = trd_ctx.order_list_query(trd_env=TrdEnv.REAL)
    if ret != RET_OK or len(data) == 0:
        return []
    orders = []
    for _, row in data.iterrows():
        order = {}
        for col in data.columns:
            try:
                val = row[col]
                order[col] = float(val) if hasattr(val, '__float__') else str(val)
            except:
                order[col] = str(row[col])
        orders.append(order)
    print(f"  今日订单: {len(orders)} 条")
    return orders


def collect_history_orders(trd_ctx, days=30):
    """历史订单（近N天）"""
    end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    ret, data = trd_ctx.history_order_list_query(
        trd_env=TrdEnv.REAL,
        start=start,
        end=end
    )
    if ret != RET_OK or len(data) == 0:
        return []
    orders = []
    for _, row in data.iterrows():
        order = {}
        for col in data.columns:
            try:
                val = row[col]
                order[col] = float(val) if hasattr(val, '__float__') else str(val)
            except:
                order[col] = str(row[col])
        orders.append(order)
    print(f"  历史订单（近{days}天）: {len(orders)} 条")
    return orders


def collect_today_deals(trd_ctx):
    """今日成交"""
    ret, data = trd_ctx.deal_list_query(trd_env=TrdEnv.REAL)
    if ret != RET_OK or len(data) == 0:
        return []
    deals = []
    for _, row in data.iterrows():
        deal = {}
        for col in data.columns:
            try:
                val = row[col]
                deal[col] = float(val) if hasattr(val, '__float__') else str(val)
            except:
                deal[col] = str(row[col])
        deals.append(deal)
    print(f"  今日成交: {len(deals)} 条")
    return deals


def collect_history_deals(trd_ctx, days=30):
    """历史成交"""
    end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    ret, data = trd_ctx.history_deal_list_query(
        trd_env=TrdEnv.REAL,
        start=start,
        end=end
    )
    if ret != RET_OK or len(data) == 0:
        return []
    deals = []
    for _, row in data.iterrows():
        deal = {}
        for col in data.columns:
            try:
                val = row[col]
                deal[col] = float(val) if hasattr(val, '__float__') else str(val)
            except:
                deal[col] = str(row[col])
        deals.append(deal)
    print(f"  历史成交（近{days}天）: {len(deals)} 条")
    return deals


def collect_cash_flow(trd_ctx, days=30):
    """资金流水（入金出金记录）"""
    end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        ret, data = trd_ctx.acccash_flow_query(
            trd_env=TrdEnv.REAL,
            start=start,
            end=end
        )
        if ret != RET_OK or len(data) == 0:
            return []
        flows = []
        for _, row in data.iterrows():
            flow = {}
            for col in data.columns:
                try:
                    val = row[col]
                    flow[col] = float(val) if hasattr(val, '__float__') else str(val)
                except:
                    flow[col] = str(row[col])
            flows.append(flow)
        print(f"  资金流水（近{days}天）: {len(flows)} 条")
        return flows
    except Exception as e:
        print(f"  资金流水查询不支持: {e}")
        return []


def collect_market_snapshot(quote_ctx, tickers):
    """行情快照"""
    ret, data = quote_ctx.get_market_snapshot(tickers)
    if ret != RET_OK:
        return {}
    snapshots = {}
    for _, row in data.iterrows():
        code = str(row.get("code", ""))
        snap = {}
        for col in data.columns:
            try:
                val = row[col]
                snap[col] = float(val) if hasattr(val, '__float__') else str(val)
            except:
                snap[col] = str(row[col])
        snapshots[code] = snap
        print(f"  快照: {code} ${snap.get('last_price',0):.2f} "
              f"52周高${snap.get('highest_52weeks_price',0):.2f} "
              f"52周低${snap.get('lowest_52weeks_price',0):.2f}")
    return snapshots


def collect_stock_basicinfo(quote_ctx, tickers):
    """股票基本信息"""
    codes = [t.replace("US.", "") for t in tickers]
    ret, data = quote_ctx.get_stock_basicinfo(
        Market.US, SecurityType.ETF
    )
    basicinfo = {}
    if ret == RET_OK:
        for _, row in data.iterrows():
            code = "US." + str(row.get("code", ""))
            if code in tickers:
                info = {}
                for col in data.columns:
                    try:
                        val = row[col]
                        info[col] = float(val) if hasattr(val, '__float__') else str(val)
                    except:
                        info[col] = str(row[col])
                basicinfo[code] = info

    # Also try STOCK type
    ret2, data2 = quote_ctx.get_stock_basicinfo(
        Market.US, SecurityType.STOCK
    )
    if ret2 == RET_OK:
        for _, row in data2.iterrows():
            code = "US." + str(row.get("code", ""))
            if code in tickers:
                info = {}
                for col in data2.columns:
                    try:
                        val = row[col]
                        info[col] = float(val) if hasattr(val, '__float__') else str(val)
                    except:
                        info[col] = str(row[col])
                basicinfo[code] = info

    print(f"  基本信息: {len(basicinfo)} 只")
    return basicinfo


def collect_order_book(quote_ctx, tickers):
    """买卖盘口（五档）"""
    order_books = {}
    for ticker in tickers:
        try:
            ret_sub, _ = quote_ctx.subscribe([ticker], [SubType.ORDER_BOOK], subscribe_push=False)
            if ret_sub == RET_OK:
                ret, data = quote_ctx.get_order_book(ticker, num=5)
                if ret == RET_OK:
                    order_books[ticker] = {
                        "bid": [(float(p), int(v)) for p, v, *_ in data.get("Bid", [])],
                        "ask": [(float(p), int(v)) for p, v, *_ in data.get("Ask", [])],
                    }
        except Exception as e:
            print(f"  盘口 {ticker}: {e}")
    print(f"  盘口数据: {len(order_books)} 只")
    return order_books


def calc_pnl_summary(history_deals):
    """从成交记录计算盈亏统计"""
    if not history_deals:
        return {}

    total_buy  = sum(float(d.get("deal_val", 0)) for d in history_deals if str(d.get("trd_side","")).upper() in ("BUY","LONG"))
    total_sell = sum(float(d.get("deal_val", 0)) for d in history_deals if str(d.get("trd_side","")).upper() in ("SELL","SHORT"))
    total_fee  = sum(float(d.get("fee", 0)) for d in history_deals)
    trade_count = len(history_deals)

    # Group by ticker
    by_ticker = {}
    for d in history_deals:
        code = d.get("code", "")
        if code not in by_ticker:
            by_ticker[code] = {"buy_val": 0, "sell_val": 0, "count": 0, "fee": 0}
        side = str(d.get("trd_side","")).upper()
        val  = float(d.get("deal_val", 0))
        fee  = float(d.get("fee", 0))
        if side in ("BUY","LONG"):
            by_ticker[code]["buy_val"] += val
        else:
            by_ticker[code]["sell_val"] += val
        by_ticker[code]["count"] += 1
        by_ticker[code]["fee"] += fee

    return {
        "total_buy":    round(total_buy, 2),
        "total_sell":   round(total_sell, 2),
        "total_fee":    round(total_fee, 2),
        "trade_count":  trade_count,
        "by_ticker":    {k: {kk: round(vv, 4) if isinstance(vv, float) else vv
                             for kk, vv in v.items()}
                         for k, v in by_ticker.items()},
    }


def main():
    print(f"\n{'='*55}")
    print(f"  MagicQuant Data Collector")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}\n")

    result = {"collected_at": datetime.now().isoformat()}

    # ── 行情连接 ──────────────────────────────────────────
    print("[ 行情数据 ]")
    quote_ctx = OpenQuoteContext(host=HOST, port=PORT)

    result["market_snapshot"] = safe(
        lambda: collect_market_snapshot(quote_ctx, TICKERS), "行情快照")
    result["stock_basicinfo"] = safe(
        lambda: collect_stock_basicinfo(quote_ctx, TICKERS), "基本信息")
    result["order_book"] = safe(
        lambda: collect_order_book(quote_ctx, TICKERS), "盘口")

    quote_ctx.close()

    # ── 交易连接 ──────────────────────────────────────────
    print("\n[ 账户数据 ]")
    trd_ctx = OpenSecTradeContext(host=HOST, port=PORT, filter_trdmarket=TrdMarket.US, security_firm=SecurityFirm.FUTUAU)

    result["account"]          = safe(lambda: collect_account(trd_ctx),          "账户")
    result["positions"]        = safe(lambda: collect_positions(trd_ctx),         "持仓")
    result["today_orders"]     = safe(lambda: collect_today_orders(trd_ctx),      "今日订单")
    result["today_deals"]      = safe(lambda: collect_today_deals(trd_ctx),       "今日成交")
    result["history_orders"]   = safe(lambda: collect_history_orders(trd_ctx),    "历史订单")
    result["history_deals"]    = safe(lambda: collect_history_deals(trd_ctx),     "历史成交")
    result["cash_flow"]        = safe(lambda: collect_cash_flow(trd_ctx),         "资金流水")

    trd_ctx.close()

    # ── 统计计算 ──────────────────────────────────────────
    print("\n[ 统计分析 ]")
    deals = result.get("history_deals") or []
    result["pnl_summary"] = calc_pnl_summary(deals)
    if result["pnl_summary"]:
        s = result["pnl_summary"]
        print(f"  近30天交易: {s.get('trade_count',0)} 笔")
        print(f"  总手续费:   ${s.get('total_fee',0):.2f}")

    # ── 保存 ─────────────────────────────────────────────
    print(f"\n[ 保存数据 ]")
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"  已保存至 {OUT_FILE}")

    # 统计
    sections = {k: v for k, v in result.items() if k != "collected_at"}
    print(f"\n{'='*55}")
    print(f"  采集完成！共 {len(sections)} 个数据模块")
    for k, v in sections.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} 条")
        elif isinstance(v, dict):
            print(f"  {k}: {len(v)} 项")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
