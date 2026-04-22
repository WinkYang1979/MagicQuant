"""
════════════════════════════════════════════════════════════════════
  MagicQuant Focus — context.py
  VERSION : v0.5.2
  DATE    : 2026-04-22
  CHANGES :
    - [NEW] cash_available 字段:从 Futu 账户查到的真实可用现金
    - [NEW] cash_fetched_at:可用现金最后更新时间
    - [NEW] last_any_trigger_ts:全局互斥计时,用于避免刷屏
    - [NEW] first_data_ts:首次收到报价的时间戳,用于心跳显示运行时长
  DEPENDS :
    (无)
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

import time
from datetime import datetime
from typing import Optional


class FocusSession:
    def __init__(self, master_ticker: str, followers: list):
        self.master       = master_ticker
        self.followers    = followers
        self.started_at   = datetime.now()
        self.active       = True

        self.prices       = {}
        self.session_high = {}
        self.session_low  = {}

        self.peak_price   = {}
        self.trough_price = {}
        self.peak_time    = {}
        self.trough_time  = {}

        # v0.5 实时快照
        self.quote_snapshot   = {}
        self.first_data_ts    = None   # ← v0.5.2

        # v0.5.2 账户现金
        self.cash_available   = None
        self.cash_power       = None   # 购买力(融资后)
        self.cash_fetched_at  = 0

        # v0.5.2 全局互斥
        self.last_any_trigger_ts = 0

        self.positions_snapshot = {}
        self.positions_fetched_at = 0

        self.last_trigger_time = {}

        self.loop_count    = 0
        self.trigger_count = 0
        self.push_count    = 0
        self.error_count   = 0

    def update_price(self, ticker: str, price: float):
        now = time.time()
        if self.first_data_ts is None:
            self.first_data_ts = now
        if ticker not in self.prices:
            self.prices[ticker] = []
        self.prices[ticker].append((now, price))

        cutoff = now - 1800
        self.prices[ticker] = [(t, p) for t, p in self.prices[ticker] if t >= cutoff]

        if ticker not in self.session_high or price > self.session_high[ticker]:
            self.session_high[ticker] = price
        if ticker not in self.session_low or price < self.session_low[ticker]:
            self.session_low[ticker] = price

        self._update_peak_trough(ticker, price, now)

    def _update_peak_trough(self, ticker: str, price: float, ts: float):
        peak = self.peak_price.get(ticker, price)
        trough = self.trough_price.get(ticker, price)
        if price > peak:
            self.peak_price[ticker] = price
            self.peak_time[ticker]  = ts
        if price < trough:
            self.trough_price[ticker] = price
            self.trough_time[ticker]  = ts

    def reset_peak_trough(self, ticker: str):
        current_price = self.get_last_price(ticker)
        if current_price:
            self.peak_price[ticker]   = current_price
            self.trough_price[ticker] = current_price
            now = time.time()
            self.peak_time[ticker]    = now
            self.trough_time[ticker]  = now

    # ── 实时快照 ─────────────────────────────────
    def update_quote(self, ticker: str, quote: dict):
        if quote:
            self.quote_snapshot[ticker] = quote

    def get_quote(self, ticker: str) -> Optional[dict]:
        return self.quote_snapshot.get(ticker)

    def get_day_change_pct(self, ticker: str) -> Optional[float]:
        q = self.quote_snapshot.get(ticker)
        return q.get("change_pct") if q else None

    def get_prev_close(self, ticker: str) -> Optional[float]:
        q = self.quote_snapshot.get(ticker)
        return q.get("prev_close") if q else None

    def get_quote_update_time(self, ticker: str) -> Optional[str]:
        """行情最后更新时间(来自 Futu update_time)"""
        q = self.quote_snapshot.get(ticker)
        return q.get("update_time") if q else None

    # ── v0.5.2 账户现金 ─────────────────────────
    def update_cash(self, cash: float, power: float = None):
        if cash is not None:
            self.cash_available = float(cash)
        if power is not None:
            self.cash_power = float(power)
        self.cash_fetched_at = time.time()

    def cash_stale(self, max_age_sec: int = 60) -> bool:
        return (time.time() - self.cash_fetched_at) > max_age_sec

    # ── 查询 ────────────────────────────────────
    def get_last_price(self, ticker: str) -> Optional[float]:
        hist = self.prices.get(ticker, [])
        return hist[-1][1] if hist else None

    def get_price_change_pct(self, ticker: str, seconds: int) -> Optional[float]:
        hist = self.prices.get(ticker, [])
        if len(hist) < 2:
            return None
        now = time.time()
        target_ts = now - seconds
        past_price = None
        for ts, p in hist:
            if ts <= target_ts:
                past_price = p
            else:
                break
        if past_price is None or past_price <= 0:
            return None
        current = hist[-1][1]
        return round((current - past_price) / past_price * 100, 2)

    def get_peak_drawdown_pct(self, ticker: str) -> Optional[float]:
        peak = self.peak_price.get(ticker)
        current = self.get_last_price(ticker)
        if peak is None or current is None or peak <= 0:
            return None
        return round((current - peak) / peak * 100, 2)

    def get_trough_rebound_pct(self, ticker: str) -> Optional[float]:
        trough = self.trough_price.get(ticker)
        current = self.get_last_price(ticker)
        if trough is None or current is None or trough <= 0:
            return None
        return round((current - trough) / trough * 100, 2)

    # ── 持仓 ────────────────────────────────────
    def update_positions(self, positions: dict):
        self.positions_snapshot = positions or {}
        self.positions_fetched_at = time.time()

    def get_position(self, ticker: str) -> Optional[dict]:
        return self.positions_snapshot.get(ticker)

    def positions_stale(self, max_age_sec: int = 60) -> bool:
        return (time.time() - self.positions_fetched_at) > max_age_sec

    # ── 触发器冷却 ──────────────────────────────
    def can_trigger(self, trigger_name: str, cooldown_sec: int = 180) -> bool:
        last = self.last_trigger_time.get(trigger_name, 0)
        return (time.time() - last) >= cooldown_sec

    def mark_triggered(self, trigger_name: str):
        self.last_trigger_time[trigger_name] = time.time()
        self.trigger_count += 1

    # ── 状态摘要 ────────────────────────────────
    def summary(self) -> str:
        now = datetime.now()
        dur = now - self.started_at
        mins = int(dur.total_seconds() / 60)
        master_price = self.get_last_price(self.master)
        master_high = self.session_high.get(self.master)
        master_low = self.session_low.get(self.master)
        day_chg = self.get_day_change_pct(self.master)

        lines = [
            f"🎯 盯盘状态 · {self.master}",
            f"启动于: {self.started_at.strftime('%H:%M:%S')} · 运行 {mins} 分钟",
            f"",
            f"主标: {self.master}",
        ]
        if master_price:
            line = f"  现价: ${master_price:.2f}"
            if day_chg is not None:
                line += f"  日内 {day_chg:+.2f}%"
            lines.append(line)
        if master_high and master_low:
            lines.append(f"  今日: ${master_low:.2f} ~ ${master_high:.2f}")

        lines.append(f"")
        lines.append(f"跟随: {', '.join(t.replace('US.','') for t in self.followers)}")
        for t in self.followers:
            pos = self.get_position(t)
            if pos and pos.get("qty", 0) > 0:
                pl = pos.get("pl_val", 0) or 0
                sign = "+" if pl >= 0 else ""
                lines.append(f"  {t.replace('US.','')}: {pos['qty']:.0f} 股  "
                             f"{sign}${pl:.2f} ({sign}{pos.get('pl_pct',0):.2f}%)")
            else:
                lines.append(f"  {t.replace('US.','')}: 无持仓")

        # v0.5.2 显示可用现金
        if self.cash_available is not None:
            lines.append(f"")
            lines.append(f"💵 可用现金: ${self.cash_available:,.2f}")
            if self.cash_power is not None and self.cash_power > self.cash_available:
                lines.append(f"   购买力: ${self.cash_power:,.2f}")

        lines += [
            f"",
            f"循环: {self.loop_count} 次",
            f"触发: {self.trigger_count} 次",
            f"推送: {self.push_count} 次",
        ]
        if self.error_count > 0:
            lines.append(f"错误: {self.error_count} 次")
        return "\n".join(lines)
