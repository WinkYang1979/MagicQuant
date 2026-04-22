"""
════════════════════════════════════════════════════════════════════
  MagicQuant 慧投 — realtime_quote.py
  VERSION : v0.5.4
  DATE    : 2026-04-22
  CHANGES :
    v0.5.4 (2026-04-22):
      - [FIX] /account 的 total_assets / market_val 显示错误 bug
              v0.5.3 返回 HKD 聚合值($62,117),但字段含义是 USD
              导致 /account 显示 "总资产 $62,117 美股账户" 误导
              修复:用 usd_assets 作为美股总资产,usd_assets - cash = 市值
              HKD 聚合值移到 raw_hkd_total / raw_hkd_market(诊断用)
    v0.5.3 (2026-04-22):
      - [FIX] HKD 聚合 bug:cash 字段实际是 HKD 聚合值
              修复:优先 us_cash / us_avl_withdrawal_cash 字段
    v0.5.2 (2026-04-22):
      - [FIX] fetch_positions 字段名对齐 Moomoo AU
    v0.5.1 (2026-04-22):
      - [NEW] 夜盘/盘前/盘后时段价识别
      - [FIX] security_firm=FUTUAU
    v0.5.0 (2026-04-22):
      - [NEW] fetch_account / fetch_positions / fetch_cash
  DEPENDS : (无)
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from moomoo import (
        OpenQuoteContext, OpenSecTradeContext,
        RET_OK, TrdMarket, TrdEnv, Currency,
    )
except ImportError:
    from futu import (
        OpenQuoteContext, OpenSecTradeContext,
        RET_OK, TrdMarket, TrdEnv, Currency,
    )

from config.settings import FUTU_HOST, FUTU_PORT


# ══════════════════════════════════════════════════════════════════
#  v0.5.1: 美东时段识别 + 价格字段选择
# ══════════════════════════════════════════════════════════════════
#  美股时段 (美东 ET):
#    夜盘   20:00 - 03:50 (次日)   overnight_price
#    盘前   04:00 - 09:30          pre_price
#    盘中   09:30 - 16:00          last_price
#    盘后   16:00 - 20:00          after_price
#    休市   03:50 - 04:00 (空档)   退回 last_price

from datetime import timezone, timedelta, time as _dtime


def _et_now():
    """返回当前美东时间 (naive datetime)"""
    utc_now = datetime.now(timezone.utc)
    month = utc_now.month
    offset = -4 if 3 <= month <= 11 else -5   # 粗略夏令时
    et = utc_now + timedelta(hours=offset)
    return et.replace(tzinfo=None)


def _detect_session(et_dt=None):
    """RTH/PRE/AFTER/OVERNIGHT/CLOSED"""
    if et_dt is None:
        et_dt = _et_now()
    t = et_dt.time()
    if t >= _dtime(20, 0) or t < _dtime(3, 50):
        return "OVERNIGHT"
    if _dtime(3, 50) <= t < _dtime(4, 0):
        return "CLOSED"
    if _dtime(4, 0) <= t < _dtime(9, 30):
        return "PRE"
    if _dtime(9, 30) <= t < _dtime(16, 0):
        return "RTH"
    if _dtime(16, 0) <= t < _dtime(20, 0):
        return "AFTER"
    return "CLOSED"


def _pick_price(row, session):
    """
    按时段选 snapshot 字段,返回 (price, session_used)

    Fallback:
      OVERNIGHT → overnight_price → after_price → last_price
      AFTER     → after_price → last_price
      PRE       → pre_price → last_price
      RTH       → last_price
    """
    def _safe(field):
        if field not in row.index:
            return None
        v = row[field]
        try:
            vf = float(v)
            if vf != vf or vf == 0:
                return None
            return vf
        except (TypeError, ValueError):
            return None

    last = _safe("last_price")

    if session == "OVERNIGHT":
        p = _safe("overnight_price")
        if p is not None:
            return p, "OVERNIGHT"
        p = _safe("after_price")
        if p is not None:
            return p, "AFTER"
        return last, "RTH"
    if session == "AFTER":
        p = _safe("after_price")
        if p is not None:
            return p, "AFTER"
        return last, "RTH"
    if session == "PRE":
        p = _safe("pre_price")
        if p is not None:
            return p, "PRE"
        return last, "RTH"
    return last, "RTH"


# ══════════════════════════════════════════════════════════════════
#  QuoteClient — 行情 + 账户 + K 线
# ══════════════════════════════════════════════════════════════════

class QuoteClient:
    """常驻 Futu Quote + Trade 双连接，线程安全。"""

    def __init__(self, host=FUTU_HOST, port=FUTU_PORT):
        self.host = host
        self.port = port

        # ── 行情连接 ──────────────────────────────────────────────
        self._ctx         = None
        self._lock        = threading.Lock()
        self._last_err_at = 0
        self._err_cooldown = 30

        # 暴露给 focus_manager._fetch_5m_kline
        self._quote_ctx  = None   # 同 self._ctx 的别名,建连后赋值
        self._quote_lock = threading.Lock()

        # ── 交易连接 ──────────────────────────────────────────────
        self._trd_ctx         = None
        self._trd_lock        = threading.Lock()
        self._trd_last_err_at = 0

        self._connect_quote()
        self._connect_trade()

    # ── 行情连接管理 ──────────────────────────────────────────────
    def _connect_quote(self):
        try:
            if self._ctx is not None:
                try:
                    self._ctx.close()
                except:
                    pass
            ctx = OpenQuoteContext(host=self.host, port=self.port)
            self._ctx         = ctx
            self._quote_ctx   = ctx   # 别名
            self._last_err_at = 0
            print(f"  [Quote v0.5.4] Connected to FutuOpenD {self.host}:{self.port}")
            return True
        except Exception as e:
            self._ctx = self._quote_ctx = None
            self._last_err_at = time.time()
            print(f"  [Quote] Connect failed: {e}")
            return False

    def _ensure(self):
        if self._ctx is not None:
            return True
        if time.time() - self._last_err_at < self._err_cooldown:
            return False
        with self._lock:
            if self._ctx is None:
                return self._connect_quote()
        return True

    # focus_manager._fetch_5m_kline 用这个名字
    def _ensure_quote(self):
        return self._ensure()

    # ── 交易连接管理 ──────────────────────────────────────────────
    def _connect_trade(self):
        """
        v0.5.1: moomoo-api 新版要求必须传 security_firm。
        FUTUAU = Moomoo AU (澳大利亚),即老杨的券商
        如果 SDK 不支持 SecurityFirm 枚举,降级用字符串尝试
        """
        try:
            if self._trd_ctx is not None:
                try:
                    self._trd_ctx.close()
                except:
                    pass

            # 尝试导入 SecurityFirm 枚举
            security_firm = None
            try:
                from moomoo import SecurityFirm
                security_firm = SecurityFirm.FUTUAU
            except (ImportError, AttributeError):
                try:
                    from futu import SecurityFirm
                    security_firm = SecurityFirm.FUTUAU
                except (ImportError, AttributeError):
                    pass

            # 优先带 security_firm,失败再退回不带
            if security_firm is not None:
                try:
                    self._trd_ctx = OpenSecTradeContext(
                        filter_trdmarket=TrdMarket.US,
                        security_firm=security_firm,
                        host=self.host, port=self.port,
                    )
                    self._trd_last_err_at = 0
                    print(f"  [Trade] Connected (US, FUTUAU)")
                    return True
                except Exception as e1:
                    print(f"  [Trade] FUTUAU 连接失败,尝试降级: {e1}")

            # 降级:不带 security_firm(老 SDK 版本)
            self._trd_ctx = OpenSecTradeContext(
                filter_trdmarket=TrdMarket.US,
                host=self.host, port=self.port,
            )
            self._trd_last_err_at = 0
            print(f"  [Trade] Connected (US, no security_firm)")
            return True
        except Exception as e:
            self._trd_ctx = None
            self._trd_last_err_at = time.time()
            print(f"  [Trade] Connect failed: {e}")
            return False

    def _ensure_trade(self):
        if self._trd_ctx is not None:
            return True
        if time.time() - self._trd_last_err_at < self._err_cooldown:
            return False
        with self._trd_lock:
            if self._trd_ctx is None:
                return self._connect_trade()
        return True

    def close(self):
        with self._lock:
            if self._ctx is not None:
                try:
                    self._ctx.close()
                except:
                    pass
                self._ctx = self._quote_ctx = None
                print("  [Quote] Closed")
        with self._trd_lock:
            if self._trd_ctx is not None:
                try:
                    self._trd_ctx.close()
                except:
                    pass
                self._trd_ctx = None
                print("  [Trade] Closed")

    # ══════════════════════════════════════════════════════════════
    #  行情查询
    # ══════════════════════════════════════════════════════════════

    def fetch_one(self, ticker: str, timeout: float = 3.0) -> dict | None:
        """
        单票实时快照。失败返回 None。

        v0.5.1: 根据美东时段自动选价格字段(夜盘用 overnight_price 等)

        返回:
            ticker / price / prev_close / change / change_pct
            volume / update_time / age_sec / fetched_at
            session          # "RTH"/"PRE"/"AFTER"/"OVERNIGHT"/"CLOSED"
            session_used     # 实际取到价的时段 (fallback 后)
            rth_close        # RTH 收盘价,夜盘时用于对比
        """
        if not self._ensure():
            return None
        try:
            with self._lock:
                ret, snap = self._ctx.get_market_snapshot([ticker])
            if ret != RET_OK or snap is None or len(snap) == 0:
                return None

            row   = snap.iloc[0]
            prev  = float(row["prev_close_price"])
            update_time = str(row["update_time"])
            rth_close = float(row["last_price"])   # 保留作参考

            # v0.5.1: 按时段选价
            session = _detect_session()
            price, session_used = _pick_price(row, session)
            if price is None:
                return None

            age_sec = -1
            try:
                dt_q    = datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
                age_sec = max(0, int((_et_now() - dt_q).total_seconds()))
            except:
                pass

            return {
                "ticker":       ticker,
                "price":        round(price, 4),
                "prev_close":   round(prev, 4),
                "change":       round(price - prev, 4),
                "change_pct":   round((price - prev) / prev * 100, 2) if prev else 0.0,
                "volume":       int(row["volume"]),
                "update_time":  update_time,
                "age_sec":      age_sec,
                "fetched_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "session":      session,
                "session_used": session_used,
                "rth_close":    round(rth_close, 4),
            }
        except Exception as e:
            print(f"  [Quote] fetch_one({ticker}) error: {e}")
            with self._lock:
                self._ctx = self._quote_ctx = None
                self._last_err_at = time.time()
            return None

    def fetch_many(self, tickers: list, max_workers: int = 4) -> dict:
        """批量并发拉取。返回 {ticker: quote_dict or None}"""
        result = {tk: None for tk in tickers}
        if not tickers or not self._ensure():
            return result
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {pool.submit(self.fetch_one, tk): tk for tk in tickers}
            for fut in as_completed(futs, timeout=10):
                tk = futs[fut]
                try:
                    result[tk] = fut.result()
                except Exception as e:
                    print(f"  [Quote] batch error on {tk}: {e}")
        return result

    # ══════════════════════════════════════════════════════════════
    #  账户查询 (v0.5.0 新增)
    # ══════════════════════════════════════════════════════════════

    def fetch_account(self) -> dict | None:
        """
        查账户资金(美元计价)。返回包含 cash / power / total_assets 的 dict。
        失败返回 None。

        v0.5.3 修复 HKD 聚合问题:
          Moomoo AU 多币种账户,默认 accinfo_query 返回 HKD 聚合值,
          字段里的 "USD" 其实是 HKD。修复策略:
            1) 优先用 us_cash / us_avl_withdrawal_cash / usd_assets 独立美元字段
            2) 兜底:再发一次带 currency=Currency.USD 的查询

        返回结构(一律美元):
            {
                "cash":            3537.93,   # 美元可用现金
                "power":           3537.93,   # 美元购买力(现金账户 = cash)
                "total_assets":    62086.50,  # 全账户总资产(USD 折算)
                "market_val":      34439.98,  # 总市值(USD 折算)
                "usd_cash":        3537.93,   # 纯美元现金(冗余字段)
                "usd_assets":      7933.52,   # 纯美元资产
                "usd_buying_power":3537.93,   # 美元购买力
                "raw_hkd_cash":    27704.29,  # 原 HKD 聚合值(诊断用)
                "currency":        "USD",
                "fetched_at":      "2026-04-22 14:30:00"
            }
        """
        if not self._ensure_trade():
            return None
        try:
            # 第 1 次查询:默认(返回 HKD 聚合),但里面有 us_cash 等美元字段
            with self._trd_lock:
                ret, data = self._trd_ctx.accinfo_query(
                    trd_env=TrdEnv.REAL,
                    refresh_cache=True,
                )
            if ret != RET_OK or data is None or len(data) == 0:
                return None

            row = data.iloc[0]

            def _f(*cols, default=0.0):
                """从多个候选字段里找第一个有效数值"""
                for col in cols:
                    if col in row.index:
                        v = row[col]
                        if v is None:
                            continue
                        try:
                            # 过滤 'N/A' / 'nan' 字符串
                            if isinstance(v, str) and v.strip().upper() in ("N/A", "NAN", ""):
                                continue
                            fv = float(v)
                            if fv != fv:   # NaN
                                continue
                            return fv
                        except (TypeError, ValueError):
                            continue
                return default

            # 优先美元字段(Moomoo AU accinfo 内置)
            usd_cash          = _f("us_cash", "usd_cash")
            usd_avl_withdraw  = _f("us_avl_withdrawal_cash", "usd_avl_withdrawal_cash")
            usd_buy_power     = _f("usd_net_cash_power")
            usd_assets_val    = _f("usd_assets")

            # 原 HKD 聚合值(保留用于诊断)
            hkd_cash          = _f("cash")
            hkd_total         = _f("total_assets")
            hkd_market        = _f("market_val")

            # 策略 1: 如果内置美元字段齐全,直接用
            if usd_cash > 0 or usd_avl_withdraw > 0:
                cash = usd_avl_withdraw or usd_cash
                power = usd_buy_power or cash

                # v0.5.4: total_assets 和 market_val 统一用美股账户真实美元值
                # 不再返回 HKD 聚合(那个会误导 /account 显示)
                # usd_assets = 美股账户总资产 (USD 计价)
                # usd_market = usd_assets - usd_cash = 美股持仓市值
                usd_market_val = max(0, usd_assets_val - cash)

                return {
                    "cash":             round(cash, 2),
                    "power":            round(power, 2),
                    "total_assets":     round(usd_assets_val, 2),    # 美股账户 USD 总资产
                    "market_val":       round(usd_market_val, 2),    # 美股持仓市值 USD
                    "usd_cash":         round(usd_cash, 2),
                    "usd_buying_power": round(usd_buy_power or cash, 2),
                    "usd_assets":       round(usd_assets_val, 2),
                    # 诊断字段:HKD 聚合原值(跨币种综合账户总览)
                    "raw_hkd_cash":     round(hkd_cash, 2),
                    "raw_hkd_total":    round(hkd_total, 2),
                    "raw_hkd_market":   round(hkd_market, 2),
                    "currency":         "USD",
                    "fetched_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

            # 策略 2 (fallback): 内置美元字段缺失,重新查询 Currency.USD
            print("  [Trade] us_cash 字段缺失,fallback 到 Currency.USD 查询")
            with self._trd_lock:
                ret2, data2 = self._trd_ctx.accinfo_query(
                    trd_env=TrdEnv.REAL,
                    refresh_cache=True,
                    currency=Currency.USD,
                )
            if ret2 != RET_OK or data2 is None or len(data2) == 0:
                return None
            row2 = data2.iloc[0]

            def _f2(*cols, default=0.0):
                for col in cols:
                    if col in row2.index:
                        v = row2[col]
                        if v is None:
                            continue
                        try:
                            if isinstance(v, str) and v.strip().upper() in ("N/A", "NAN", ""):
                                continue
                            fv = float(v)
                            if fv != fv:
                                continue
                            return fv
                        except (TypeError, ValueError):
                            continue
                return default

            cash2       = _f2("cash", "avl_withdrawal_cash")
            power2      = _f2("power", "max_power_short") or cash2
            total2      = _f2("total_assets")
            market2     = _f2("market_val")

            return {
                "cash":             round(cash2, 2),
                "power":            round(power2, 2),
                "total_assets":     round(total2, 2),
                "market_val":       round(market2, 2),
                "usd_cash":         round(cash2, 2),
                "usd_buying_power": round(power2, 2),
                "usd_assets":       round(total2, 2),
                "raw_hkd_cash":     round(hkd_cash, 2),
                "currency":         "USD",
                "fetched_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            print(f"  [Trade] fetch_account error: {e}")
            with self._trd_lock:
                self._trd_ctx = None
                self._trd_last_err_at = time.time()
            return None

    def fetch_cash(self) -> float | None:
        """fetch_account 的简化版，只返回可用现金。失败返回 None。"""
        acc = self.fetch_account()
        return acc["cash"] if acc else None

    def fetch_positions(self) -> dict | None:
        """
        查实时持仓。返回 {ticker: position_dict}。
        失败返回 None(调用方判断 None 则保留缓存)。

        v0.5.2: 字段名对齐 Moomoo AU position_list_query 返回结构
                新增 can_sell_qty / today_pl_val / position_side / unrealized_pl

        position_dict 结构:
            {
                "ticker":        "US.RKLZ",
                "qty":           100,
                "can_sell_qty":  100,        # T+1 可卖数量
                "cost_price":    11.43,      # 成本价
                "current_price": 11.33,      # 最新价 (来自 nominal_price)
                "market_val":    1133.0,     # 市值
                "pl_val":        -10.0,      # 浮动盈亏(美金)
                "pl_pct":        -0.87,      # 浮动盈亏百分比
                "today_pl_val":  47.69,      # 今日盈亏
                "position_side": "LONG",     # LONG/SHORT
                "unrealized_pl": -2366.06,   # 未实现盈亏
            }
        """
        if not self._ensure_trade():
            return None
        try:
            with self._trd_lock:
                ret, data = self._trd_ctx.position_list_query(
                    trd_env=TrdEnv.REAL,
                    refresh_cache=True,
                )
            if ret != RET_OK or data is None:
                return None

            positions = {}
            for _, row in data.iterrows():
                ticker = str(row.get("code", ""))
                if not ticker:
                    continue
                if not ticker.startswith("US."):
                    ticker = "US." + ticker

                def _f(*cols, default=0.0):
                    """从多个候选字段名里找第一个有效值"""
                    for col in cols:
                        if col in row.index:
                            v = row[col]
                            if v is None:
                                continue
                            try:
                                fv = float(v)
                                if fv != fv:   # NaN
                                    continue
                                return fv
                            except (TypeError, ValueError):
                                continue
                    return default

                def _s(*cols, default=""):
                    """字符串字段"""
                    for col in cols:
                        if col in row.index:
                            v = row[col]
                            if v is not None and str(v).strip():
                                return str(v)
                    return default

                # v0.5.2: 按 Moomoo AU 实际字段名,同时兼容老版 alias
                qty           = int(_f("qty", "position_qty", default=0))
                can_sell_qty  = int(_f("can_sell_qty", "sellable_qty", default=qty))
                cost_price    = _f("cost_price", "average_cost", "diluted_cost", "avg_cost")
                current_price = _f("nominal_price", "current_price", "last_price")
                market_val    = _f("market_val", "position_val")
                pl_val        = _f("pl_val", "profit_val")
                pl_pct        = _f("pl_ratio", "pl_ratio_val", "pl_pct")
                today_pl_val  = _f("today_pl_val", default=0.0)
                unrealized_pl = _f("unrealized_pl", default=pl_val)
                realized_pl   = _f("realized_pl", default=0.0)
                position_side = _s("position_side", default="LONG")

                # Moomoo AU 的 pl_ratio 直接是百分比(如 -41.37)
                # 但老版可能用小数(-0.0087 = -0.87%),兜底转换
                if 0 < abs(pl_pct) < 1:
                    pl_pct = round(pl_pct * 100, 2)

                # 兜底:如果没 pl_val 但有 current/cost,自算
                if pl_val == 0 and current_price > 0 and cost_price > 0:
                    pl_val = round((current_price - cost_price) * qty, 2)
                if pl_pct == 0 and current_price > 0 and cost_price > 0:
                    pl_pct = round((current_price - cost_price) / cost_price * 100, 2)

                if qty > 0:
                    positions[ticker] = {
                        "ticker":         ticker,
                        "qty":            qty,
                        "can_sell_qty":   can_sell_qty,
                        "cost_price":     round(cost_price, 4),
                        "current_price":  round(current_price, 4),
                        "market_val":     round(market_val, 2),
                        "pl_val":         round(pl_val, 2),
                        "pl_pct":         round(pl_pct, 2),
                        "today_pl_val":   round(today_pl_val, 2),
                        "unrealized_pl":  round(unrealized_pl, 2),
                        "realized_pl":    round(realized_pl, 2),
                        "position_side":  position_side,
                    }
            return positions

        except Exception as e:
            print(f"  [Trade] fetch_positions error: {e}")
            with self._trd_lock:
                self._trd_ctx = None
                self._trd_last_err_at = time.time()
            return None


# ══════════════════════════════════════════════════════════════════
#  单例入口
# ══════════════════════════════════════════════════════════════════

_client_singleton: QuoteClient | None = None
_singleton_lock = threading.Lock()


def get_client() -> QuoteClient:
    global _client_singleton
    if _client_singleton is None:
        with _singleton_lock:
            if _client_singleton is None:
                _client_singleton = QuoteClient()
    return _client_singleton


def close_client():
    global _client_singleton
    if _client_singleton is not None:
        _client_singleton.close()
        _client_singleton = None


# ══════════════════════════════════════════════════════════════════
#  辅助：把实时 quote 合并到 signal dict
# ══════════════════════════════════════════════════════════════════

def merge_realtime_into_signal(signal: dict, quote: dict | None) -> dict:
    if not quote:
        signal["price_is_live"] = False
        signal.setdefault("price_at", signal.get("update_time", ""))
        return signal

    signal["price"]         = quote["price"]
    signal["prev_close"]    = quote["prev_close"]
    signal["change"]        = quote["change"]
    signal["change_pct"]    = quote["change_pct"]
    signal["volume"]        = quote["volume"]
    signal["price_at"]      = quote["update_time"]
    signal["quote_age_sec"] = quote["age_sec"]
    signal["price_is_live"] = True
    # v0.5.1 新增透传
    signal["session"]       = quote.get("session", "RTH")
    signal["session_used"]  = quote.get("session_used", "RTH")
    signal["rth_close"]     = quote.get("rth_close")
    return signal


def merge_positions_into_signals(signals: dict, positions: dict | None) -> dict:
    """
    v0.5.1: 把持仓合并到 signals dict。
    watchlist 外但有持仓的票会自动补简版 signal。

    signals 形如 {ticker: signal_dict}
    positions 形如 {ticker: pos_dict}
    """
    if signals is None:
        signals = {}
    if not positions:
        return signals

    # 1) 对已有 signal 叠加 position
    for tk, sig in list(signals.items()):
        pos = positions.get(tk)
        if pos:
            sig["position"] = pos
            sig["has_position"] = True

    # 2) watchlist 外但有持仓的票,补简版 signal
    for tk, pos in positions.items():
        if tk not in signals:
            signals[tk] = {
                "ticker":        tk,
                "position":      pos,
                "has_position":  True,
                "position_only": True,
                "price":         pos.get("current_price", 0),
                "prev_close":    0,
                "change":        0,
                "change_pct":    0,
            }
    return signals


# ══════════════════════════════════════════════════════════════════
#  本地测试
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    client = get_client()

    # v0.5.2: 支持子命令
    #   python -m core.realtime_quote            → 全套测试
    #   python -m core.realtime_quote quote      → 只测行情
    #   python -m core.realtime_quote account    → 只测账户
    #   python -m core.realtime_quote positions  → 只测持仓
    #   python -m core.realtime_quote US.RKLB ...→ 测指定 ticker
    SPECIAL = {"quote", "account", "positions", "all"}
    args = sys.argv[1:]
    mode = None
    if len(args) == 1 and args[0] in SPECIAL:
        mode = args[0]
        args = []

    # 决定要不要跑 quotes / account / positions
    run_quotes    = mode in (None, "quote", "all") or args
    run_account   = mode in (None, "account", "all")
    run_positions = mode in (None, "positions", "all")

    if run_quotes:
        test_tickers = args if args else ["US.RKLB", "US.RKLX", "US.RKLZ"]
        print(f"\n  Testing quotes: {test_tickers}")
        t0     = time.time()
        quotes = client.fetch_many(test_tickers)
        elapsed = time.time() - t0
        for tk, q in quotes.items():
            if q:
                tag = q.get("session_used", "?")
                print(f"  {tk}: ${q['price']}  {q['change']:+.2f} ({q['change_pct']:+.2f}%)  "
                      f"[{tag}]  age={q['age_sec']}s  @ {q['update_time']}")
            else:
                print(f"  {tk}: 获取失败")
        print(f"  Quotes elapsed: {elapsed:.2f}s")

    if run_account:
        print("\n  Testing account...")
        acc = client.fetch_account()
        if acc:
            print(f"  💵 USD Cash:         ${acc['cash']:,.2f}")
            print(f"  💪 USD Buying Power: ${acc['power']:,.2f}")
            print(f"  🏦 USD Total Assets: ${acc['total_assets']:,.2f}  (美股账户)")
            print(f"  📈 USD Market Val:   ${acc['market_val']:,.2f}  (美股持仓市值)")
            print()
            print(f"  — 跨币种综合账户参考(HKD 聚合):")
            print(f"    raw HKD cash:   {acc.get('raw_hkd_cash', 0):,.2f}")
            print(f"    raw HKD total:  {acc.get('raw_hkd_total', 0):,.2f}")
            print(f"    raw HKD market: {acc.get('raw_hkd_market', 0):,.2f}")
        else:
            print("  Account: 获取失败")

    if run_positions:
        print("\n  Testing positions...")
        pos = client.fetch_positions()
        if pos:
            for tk, p in pos.items():
                today = p.get('today_pl_val', 0)
                today_sign = "+" if today >= 0 else ""
                print(f"  {tk}: {p['qty']}股 @${p['cost_price']}  "
                      f"现价 ${p['current_price']}  "
                      f"浮盈 ${p['pl_val']:+.2f} ({p['pl_pct']:+.2f}%)  "
                      f"今日 {today_sign}${today:.2f}  "
                      f"可卖 {p.get('can_sell_qty', p['qty'])}")
        else:
            print("  Positions: 无持仓或获取失败")

    close_client()
