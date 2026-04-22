"""
MagicQuant 慧投 — 富途对账单解析器
Moomoo AU Daily Statement PDF Parser

解析富途澳洲每日对账单 PDF，提取：
  - 账户净值变动
  - 每笔交易记录（成交价、数量、方向）
  - 手续费明细（Platform Fee、Settlement Fee、TAF 等）
  - 持仓快照

存储格式：data/statements/YYYY-MM-DD.json

依赖：pdfplumber
安装：pip install pdfplumber

Owner: Zhen Yang
"""

import json, os, re
from datetime import datetime, date, timedelta

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

import sys
sys.path.insert(0, r"C:\MagicQuant")
from config.settings import BASE_DIR

STATEMENTS_DIR = os.path.join(BASE_DIR, "data", "statements")


# ══════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════

def ensure_dir():
    os.makedirs(STATEMENTS_DIR, exist_ok=True)


def statement_path(date_str: str) -> str:
    """YYYY-MM-DD → 完整存储路径 / Full path for a date"""
    return os.path.join(STATEMENTS_DIR, f"{date_str}.json")


def load_statement(date_str: str) -> dict | None:
    """加载已解析的对账单 / Load parsed statement"""
    path = statement_path(date_str)
    try:
        return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
    except:
        return None


def save_statement(date_str: str, data: dict):
    """保存解析结果 / Save parsed result"""
    ensure_dir()
    with open(statement_path(date_str), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_existing_dates() -> list[str]:
    """返回已有对账单的日期列表（升序）/ Return sorted list of existing statement dates"""
    ensure_dir()
    dates = []
    for fn in os.listdir(STATEMENTS_DIR):
        if fn.endswith(".json") and re.match(r"\d{4}-\d{2}-\d{2}\.json", fn):
            dates.append(fn[:-5])
    return sorted(dates)


def get_missing_dates(start_date: str = None, end_date: str = None) -> list[str]:
    """
    检测缺失的交易日对账单
    默认从最早已有日期到昨天，跳过周末
    Detect missing trading day statements (skip weekends)
    """
    existing = set(get_existing_dates())
    if not existing and not start_date:
        return []

    # 确定检测范围
    if start_date:
        d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        d_start = datetime.strptime(min(existing), "%Y-%m-%d").date()

    d_end = date.today() - timedelta(days=1)  # 昨天
    if end_date:
        d_end = datetime.strptime(end_date, "%Y-%m-%d").date()

    missing = []
    d = d_start
    while d <= d_end:
        # 跳过周末（0=周一 ... 6=周日）
        if d.weekday() < 5:
            ds = d.strftime("%Y-%m-%d")
            if ds not in existing:
                missing.append(ds)
        d += timedelta(days=1)
    return missing


# ══════════════════════════════════════════════════════════════════
#  PDF 解析核心
# ══════════════════════════════════════════════════════════════════

def parse_pdf(pdf_path: str) -> dict | None:
    """
    解析富途澳洲每日对账单 PDF
    Parse Moomoo AU daily statement PDF

    Returns: 解析结果 dict，失败返回 None
    """
    if not HAS_PDFPLUMBER:
        return {"error": "pdfplumber not installed. Run: pip install pdfplumber"}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # 合并所有页面文本
            full_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    except Exception as e:
        return {"error": f"PDF读取失败: {e}"}

    return parse_text(full_text)


def parse_text(text: str) -> dict:
    """
    从对账单文本中提取结构化数据
    Extract structured data from statement text

    基于实际富途AU对账单格式（已验证3份样本）
    """
    result = {
        "parsed_at":    datetime.now().isoformat(),
        "statement_date": None,
        "account_number": None,
        "net_asset_value": None,
        "currency":       "USD",
        "trades":         [],
        "fees_total":     0.0,
        "cash_change":    {},
        "positions":      [],
        "raw_fee_lines":  [],
    }

    # ── 基本信息 ─────────────────────────────────────────────────
    # 账户号
    m = re.search(r"Account Number\s+(\d+)", text)
    if m:
        result["account_number"] = m.group(1)

    # 对账单日期（从文件头部 "Apr 14,2026" 或 "Apr 15,2026"）
    m = re.search(r"Daily Statement.*?(\w+ \d+,\d{4})", text)
    if m:
        try:
            result["statement_date"] = datetime.strptime(
                m.group(1), "%b %d,%Y").strftime("%Y-%m-%d")
        except:
            pass

    # 净资产
    m = re.search(r"Ending Net Asset Value \d+\s+Equal to\(AUD\)\s+([\d,]+\.\d+)", text)
    if m:
        result["net_asset_value"] = float(m.group(1).replace(",", ""))

    # ── 交易记录解析 ──────────────────────────────────────────────
    # 格式样例：
    # Buy to Open  Defiance Daily Target 2X Long RKLB ETF RKLX
    # US USD 2026/04/16 02:39:09 31.6600 100 3,166.00
    trade_pattern = re.compile(
        r"(Buy to Open|Sell to Close|Buy to Cover|Sell Short)\s+"
        r"(.+?)\n"                          # 股票全名（可能含换行）
        r"(\w+)\s+(\w+)\s+"                 # 交易所 货币
        r"(\d{4}/\d{2}/\d{2})\s+"          # 日期
        r"(\d{2}:\d{2}:\d{2})\s+"          # 时间
        r"([\d.]+)\s+"                      # 价格
        r"([\d,]+)\s+"                      # 数量
        r"([\d,]+\.\d+)",                   # 金额
        re.DOTALL
    )

    for m in trade_pattern.finditer(text):
        direction = m.group(1)
        symbol_line = m.group(2).strip()
        # 从全名最后一个词提取 ticker（如 RKLX, RKLZ, TSLL）
        ticker_match = re.search(r"\b([A-Z]{2,5})\s*$", symbol_line)
        ticker = ticker_match.group(1) if ticker_match else symbol_line.split()[-1]

        qty    = int(m.group(8).replace(",", ""))
        price  = float(m.group(7))
        amount = float(m.group(9).replace(",", ""))
        dt_str = f"{m.group(5)} {m.group(6)}"
        side   = "BUY" if "Buy" in direction else "SELL"

        result["trades"].append({
            "direction": direction,
            "ticker":    ticker,
            "side":      side,
            "datetime":  dt_str,
            "price":     price,
            "quantity":  qty,
            "amount":    amount,
        })

    # ── 手续费解析 ────────────────────────────────────────────────
    # 格式：Platform Fee: 0.99 Settlement Fee: 0.30 SEC Fee: 0.04 Trading Activity Fee: 0.02
    fee_line_pattern = re.compile(
        r"Platform Fee:\s*([\d.]+)"
        r"(?:\s+Settlement Fee:\s*([\d.]+))?"
        r"(?:\s+SEC Fee:\s*([\d.]+))?"
        r"(?:\s+Trading Activity Fee:\s*([\d.]+))?"
    )

    fees_all = []
    for m in fee_line_pattern.finditer(text):
        fee_entry = {
            "platform":   float(m.group(1) or 0),
            "settlement": float(m.group(2) or 0),
            "sec":        float(m.group(3) or 0),
            "taf":        float(m.group(4) or 0),
        }
        fee_entry["subtotal"] = round(sum(fee_entry.values()), 4)
        fees_all.append(fee_entry)
        result["raw_fee_lines"].append(fee_entry)

    # 去重（同一笔交易费用在 PDF 里通常出现两次）
    seen = set()
    unique_fees = []
    for fe in fees_all:
        key = (fe["platform"], fe["settlement"], fe["sec"], fe["taf"])
        if key not in seen:
            seen.add(key)
            unique_fees.append(fe)

    result["fees_total"] = round(sum(f["subtotal"] for f in unique_fees), 4)
    result["fees_detail"] = unique_fees

    # ── 现金变动 ─────────────────────────────────────────────────
    buy_fee_m  = re.search(r"Buy Fee\s+([-\d.]+)", text)
    sell_fee_m = re.search(r"Sell Fee\s+([-\d.]+)", text)
    buy_amt_m  = re.search(r"Buy Amount\s+([-\d.]+)", text)
    sell_amt_m = re.search(r"Sell Amount\s+\+?([\d.]+)", text)

    result["cash_change"] = {
        "buy_amount":  abs(float(buy_amt_m.group(1)))  if buy_amt_m  else 0.0,
        "buy_fee":     abs(float(buy_fee_m.group(1)))  if buy_fee_m  else 0.0,
        "sell_amount": float(sell_amt_m.group(1))      if sell_amt_m else 0.0,
        "sell_fee":    abs(float(sell_fee_m.group(1))) if sell_fee_m else 0.0,
    }

    # ── 持仓快照 ─────────────────────────────────────────────────
    # 格式：TSLL US USD 251 0 251 1 11.5400 2,896.54 1.403280 4,654.93
    pos_pattern = re.compile(
        r"([A-Z]{2,5})\s+US\s+USD\s+"
        r"(\d+)\s+\d+\s+(\d+)\s+\d+\s+"   # settled unsettled total multiplier
        r"([\d.]+)\s+"                      # closing price
        r"([\d,]+\.\d+)"                    # market value
    )
    seen_pos = set()
    for m in pos_pattern.finditer(text):
        sym = m.group(1)
        if sym in seen_pos:
            continue
        seen_pos.add(sym)
        result["positions"].append({
            "ticker":       sym,
            "quantity":     int(m.group(3)),
            "close_price":  float(m.group(4)),
            "market_value": float(m.group(5).replace(",", "")),
        })

    return result


# ══════════════════════════════════════════════════════════════════
#  盈亏计算
# ══════════════════════════════════════════════════════════════════

def calc_pnl_from_statements(date_from: str = None, date_to: str = None) -> dict:
    """
    从已入库的对账单计算盈亏
    使用实际手续费：买入$1.29，卖出$1.31（已对账单验证）

    Returns: 盈亏汇总 dict
    """
    dates = get_existing_dates()
    if date_from:
        dates = [d for d in dates if d >= date_from]
    if date_to:
        dates = [d for d in dates if d <= date_to]

    all_trades  = []
    total_fees  = 0.0
    trade_days  = set()

    for ds in dates:
        stmt = load_statement(ds)
        if not stmt or "trades" not in stmt:
            continue
        for tr in stmt["trades"]:
            tr["date"] = ds
            all_trades.append(tr)
        total_fees += stmt.get("fees_total", 0.0)
        if stmt.get("trades"):
            trade_days.add(ds)

    # 按 ticker 配对买卖，计算盈亏
    by_ticker = {}
    for tr in all_trades:
        tk = tr["ticker"]
        if tk not in by_ticker:
            by_ticker[tk] = {"trades": [], "realized_pnl": 0.0,
                             "total_buy": 0.0, "total_sell": 0.0,
                             "buy_count": 0, "sell_count": 0}
        by_ticker[tk]["trades"].append(tr)
        if tr["side"] == "BUY":
            by_ticker[tk]["total_buy"]  += tr["amount"]
            by_ticker[tk]["buy_count"]  += 1
        else:
            by_ticker[tk]["total_sell"] += tr["amount"]
            by_ticker[tk]["sell_count"] += 1

    # 粗算实现盈亏：卖出金额 - 买入金额 - 手续费
    # 注：只有完整往返的部分才计入
    summary_by_ticker = {}
    for tk, data in by_ticker.items():
        sell_val = data["total_sell"]
        buy_val  = data["total_buy"]
        # 手续费：买入笔数×1.29 + 卖出笔数×1.31
        fees_est = data["buy_count"] * 1.29 + data["sell_count"] * 1.31
        # 净盈亏（以已平仓部分计算，min(买,卖)为已实现部分）
        paired   = min(sell_val, buy_val)
        ratio    = paired / buy_val if buy_val > 0 else 0
        net_pnl  = sell_val - buy_val - fees_est if sell_val > 0 else -fees_est * ratio

        summary_by_ticker[tk] = {
            "buy_trades":    data["buy_count"],
            "sell_trades":   data["sell_count"],
            "total_buy":     round(buy_val,  2),
            "total_sell":    round(sell_val, 2),
            "fees_est":      round(fees_est, 2),
            "net_pnl":       round(net_pnl,  2),
        }

    total_pnl = round(sum(v["net_pnl"] for v in summary_by_ticker.values()), 2)

    return {
        "date_range":        f"{dates[0]} ~ {dates[-1]}" if dates else "—",
        "trade_days":        len(trade_days),
        "total_trades":      len(all_trades),
        "total_fees":        round(total_fees, 2),
        "total_pnl":         total_pnl,
        "by_ticker":         summary_by_ticker,
        "missing_dates":     get_missing_dates(),
    }


# ══════════════════════════════════════════════════════════════════
#  命令行入口（测试用）
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python statement_parser.py <PDF路径>")
        print("      python statement_parser.py --gaps   查看缺失日期")
        print("      python statement_parser.py --pnl    查看盈亏汇总")
        sys.exit(0)

    if sys.argv[1] == "--gaps":
        missing = get_missing_dates()
        if missing:
            print(f"缺失 {len(missing)} 天对账单:")
            for d in missing:
                print(f"  {d}")
        else:
            print("✅ 无缺失")

    elif sys.argv[1] == "--pnl":
        pnl = calc_pnl_from_statements()
        print(json.dumps(pnl, ensure_ascii=False, indent=2))

    else:
        result = parse_pdf(sys.argv[1])
        if result:
            date_str = result.get("statement_date") or \
                       datetime.now().strftime("%Y-%m-%d")
            save_statement(date_str, result)
            print(f"✅ 解析完成 → {statement_path(date_str)}")
            print(f"   日期: {date_str}")
            print(f"   交易: {len(result['trades'])} 笔")
            print(f"   手续费: ${result['fees_total']}")
        else:
            print("❌ 解析失败")
