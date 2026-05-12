"""
════════════════════════════════════════════════════════════════════
  MagicQuant — 每日开盘简报
  VERSION : v0.5.1
  DATE    : 2026-05-13
  CHANGES :
    v0.5.1 (2026-05-13):
      - [BUG] 当日盈亏算成 (卖出收入 - 当日买入成本) — 忽略昨日遗留
              持仓的真实成本,导致继承持仓被低估或高估。
      - [FIX] 改 FIFO 真实盈亏:
              · _load_initial_positions:从前一交易日 session_summary.json
                的 positions_final 读取继承持仓 (qty + cost),作为初始 lots
              · _compute_fifo_pl:回放 deals,SELL 按 FIFO 消费最早 lot,
                每个 match 算 (sell-buy)×qty,扣 $0.02/股双边手续费
              · 输出 trade.matched_lots / gross_pl / fee / net_pl
              · 总计 pnl_realized_gross / pnl_fees / pnl_realized_net
              | switch to FIFO realized P&L; inherit prior-day positions
      - [FIX] 信号方向匹配改前向:gap = (d_ts - t_ts).total_seconds()
              要求 ≥0,即信号必须在操作之前才算"跟随"
              | forward-only window: signal must precede the trade
      - [FIX] 错过的强信号判定:
              · 信号触发时已有同方向持仓 → 不算错过
              · 信号后 30min 内有同向操作 → 不算错过
              | "missed" filters out (a) same-direction position already
                held at signal time, (b) signal acted on within 30min
      - [CHG] SELL 信号匹配池加 stop_loss_warning / drawdown_from_peak
              配合 swing_detector v0.5.27 新增的卖出方向触发器
      - [UI] 文本 / HTML 输出加初始持仓 / FIFO 匹配明细 / 持仓变化
      - [API] review 新增字段:initial_positions / position_changes /
              pnl_realized_gross / pnl_realized_net / pnl_fees /
              fifo_warnings;pnl_rough 保留兼容(值改为 net)
    v0.5.0 (2026-05-12):
      - [FIX] load_trading_agents 优先读 final_decision.md (而不是 market_report.md
              里的预判)，提取 Rating / Price Target / Time Horizon / Entry Zone / Stop
              过去会拿到分析师层的"BUY"，实际 final synthesis 是"Underweight"
      - [NEW] 热点事件板块: AI 操作建议六字段 (方向/介入/止盈/止损/周期/风险)
      - [REDESIGN] 压力位/支撑位带编号 (压力位1 最近 / 压力位3 最远)
      - [NEW] 期权信号 "信号解读" 三句话 + "→ 综合结论" 一句话
              (按 CLAUDE.md 推送规范: 参数+解读+结论)
      - [REDESIGN] 今日策略改子表式: 信心/仓位 进度条 + 买入明细 + 账户分配 + 目标位
              目标位带 RKLX 杠杆预期 (RKLB+3.2% → RKLX+6.4%)
      - [NEW] 昨日操作复盘: Futu history_deal_list_query + 信号匹配 + 行为评分
              三星: 执行力 / 止盈纪律 / 追高克制
    v0.4.0 (2026-05-12):
      - [FIX] 期权 OI/vol 走 get_market_snapshot（chain 不带）
              字段名修正: option_type / strike_price / option_open_interest
      - [REDESIGN] 热点事件改中文一句话（≤20 字），不再贴 TA 英文原文
      - [REDESIGN] 技术面去掉 ✅❌ 勾选条，留关键数字
      - [NEW] 今日策略读实盘账户 + RKLB/RKLX 报价，输出具体仓位/目标/止损
              激进型: 仓位=confidence×1.0 上限95%, bullish 推 RKLX 2x
      - [REDESIGN] 期权数据取不到时显示"期权数据略"，不再报错文案
    v0.3.0 (2026-05-12):
      - [NEW] 期权信号模块: Futu OpenAPI get_option_chain
              Max Pain 价位 / Put-Call Ratio / 异常大单
      - [REDESIGN] 四板块排版: 热点事件 / 技术面 / 期权信号 / 今日策略
    v0.2.0 (2026-04-27):
      - 两层信号对比: daily_briefing 快速评分 vs TradingAgents AI
      - 关键技术位 / 昨日复盘简况
  DEPENDS :
    config/settings.py (FUTU_HOST / FUTU_PORT)
    moomoo / futu SDK (期权数据)
    requests (Polygon 日线)
  OWNER   : laoyang
════════════════════════════════════════════════════════════════════
"""

import os, sys, re, json, requests
from pathlib import Path
from datetime import datetime, timedelta

# Windows 控制台默认 GBK，强制 UTF-8 避免 emoji 编码崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).parent
# 加入项目根，供 core / config 模块导入
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parent))

# ══════════════════════════════════════════════════════════════════
#  配置
# ══════════════════════════════════════════════════════════════════
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR.parent / ".env")
except ImportError:
    pass

TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT  = os.getenv("TG_CHAT_ID")
POLY_KEY = os.getenv("POLYGON_API_KEY", "ipIkF6FsAk9JFNFA27BgpeWa3hpDTzD4")
TICKER   = "RKLB"

try:
    from config.settings import FUTU_HOST, FUTU_PORT
except Exception:
    FUTU_HOST = os.getenv("FUTU_HOST", "127.0.0.1")
    FUTU_PORT  = int(os.getenv("FUTU_PORT", "11111"))

TA_LOG_BASE = Path.home() / ".tradingagents" / "logs"


# ══════════════════════════════════════════════════════════════════
#  数据获取 — Polygon 日线（技术面兜底）
# ══════════════════════════════════════════════════════════════════
def fetch_daily_bars(ticker: str, days: int = 30) -> list:
    end   = datetime.now()
    start = end - timedelta(days=days + 10)
    url   = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day"
        f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
        f"?adjusted=true&sort=asc&limit=50&apiKey={POLY_KEY}"
    )
    try:
        r = requests.get(url, timeout=15)
        bars = r.json().get("results", [])
        print(f"  [Polygon] 获取成功: {len(bars)} 根日线，最新收盘 ${bars[-1]['c'] if bars else 'N/A'}")
        return bars
    except Exception as e:
        msg = f"⚠️ Polygon 日线获取失败: {e}"
        print(msg)
        send_tg(msg)
        return []


# ══════════════════════════════════════════════════════════════════
#  数据获取 — Futu OpenAPI 期权链
# ══════════════════════════════════════════════════════════════════
def fetch_option_data(ticker: str) -> dict:
    """
    Futu/Moomoo OpenAPI 期权链 + market_snapshot 拿 OI/volume
    get_option_chain 只返回静态合约信息（option_type/strike_price），
    OI 和 volume 需 get_market_snapshot 单独查（每批最多 200 条）

    返回:
        ok / max_pain / expiry / pc_ratio / pc_label / call_oi / put_oi /
        anomalies / error
    """
    empty = {
        "ok": False, "max_pain": None, "expiry": None,
        "pc_ratio": None, "pc_label": "—",
        "call_oi": 0, "put_oi": 0,
        "anomalies": [], "error": "",
    }

    try:
        try:
            from moomoo import OpenQuoteContext, RET_OK
        except ImportError:
            from futu import OpenQuoteContext, RET_OK

        futu_code = f"US.{ticker}"
        ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
        print(f"  [Futu 期权] 已连接 {FUTU_HOST}:{FUTU_PORT}")

        oi_map, vol_map = {}, {}
        try:
            # ── 1. 最近到期日 ─────────────────────────────────────
            ret, expiry_df = ctx.get_option_expiration_date(code=futu_code)
            if ret != RET_OK or expiry_df is None or expiry_df.empty:
                empty["error"] = f"get_option_expiration_date failed: {expiry_df}"
                print(f"  [Futu 期权] {empty['error']}")
                return empty

            col = "strike_time" if "strike_time" in expiry_df.columns else expiry_df.columns[0]
            expiry_dates = sorted(expiry_df[col].dropna().astype(str).unique())
            nearest = expiry_dates[0]
            if len(nearest) > 10:
                nearest = nearest[:10]
            print(f"  [Futu 期权] 最近到期日: {nearest}，共 {len(expiry_dates)} 个到期日")

            # ── 2. 期权链（静态合约信息）─────────────────────────
            ret, chain_df = ctx.get_option_chain(
                code=futu_code, start=nearest, end=nearest,
            )
            if ret != RET_OK or chain_df is None or chain_df.empty:
                empty["error"] = f"get_option_chain failed: {chain_df}"
                print(f"  [Futu 期权] {empty['error']}")
                return empty

            print(f"  [Futu 期权] chain 获取成功: {len(chain_df)} 条合约")

            # ── 3. snapshot 拿 OI / volume ──────────────────────
            codes = chain_df["code"].astype(str).tolist() if "code" in chain_df.columns else []
            if not codes:
                empty["error"] = "chain 无 code 列"
                print(f"  [Futu 期权] {empty['error']}")
                return empty

            for i in range(0, len(codes), 200):
                batch = codes[i:i+200]
                ret_s, snap_df = ctx.get_market_snapshot(batch)
                if ret_s != RET_OK or snap_df is None or snap_df.empty:
                    print(f"  [Futu 期权] snapshot 批 {i}-{i+len(batch)} 失败: {snap_df}")
                    continue
                for _, row in snap_df.iterrows():
                    c = str(row.get("code", ""))
                    if not c:
                        continue
                    oi = row.get("option_open_interest", 0)
                    vl = row.get("volume", 0)
                    try:
                        oi_v = float(oi) if oi == oi and oi is not None else 0.0
                    except Exception:
                        oi_v = 0.0
                    try:
                        vl_v = float(vl) if vl == vl and vl is not None else 0.0
                    except Exception:
                        vl_v = 0.0
                    oi_map[c] = oi_v
                    vol_map[c] = vl_v

            total_oi = sum(oi_map.values())
            print(f"  [Futu 期权] snapshot 覆盖 {len(oi_map)}/{len(codes)} 合约, 总 OI={int(total_oi):,}")
            if total_oi <= 0:
                empty["error"] = "snapshot OI 全为 0"
                return empty

        finally:
            ctx.close()

    except Exception as e:
        empty["error"] = f"Futu 期权 SDK 异常: {e}"
        print(f"  [Futu 期权] {empty['error']}")
        return empty

    # ── 4. 解析字段（chain_df + snapshot map）──────────────────
    try:
        cp_col  = next((c for c in ["option_type", "call_put", "callput"] if c in chain_df.columns), None)
        str_col = next((c for c in ["strike_price", "strike"] if c in chain_df.columns), None)
        if not (cp_col and str_col):
            empty["error"] = f"chain 字段缺失 cp={cp_col} strike={str_col}"
            print(f"  [Futu 期权] {empty['error']}")
            return empty

        chain_df["_cp"]     = chain_df[cp_col].astype(str).str.upper()
        chain_df["_strike"] = chain_df[str_col].astype(float)
        chain_df["_oi"]     = chain_df["code"].astype(str).map(oi_map).fillna(0).astype(float)
        chain_df["_vol"]    = chain_df["code"].astype(str).map(vol_map).fillna(0).astype(float)

        calls = chain_df[chain_df["_cp"].str.contains("CALL")]
        puts  = chain_df[chain_df["_cp"].str.contains("PUT")]

        call_oi = int(calls["_oi"].sum())
        put_oi  = int(puts["_oi"].sum())

        # ── Put/Call Ratio ────────────────────────────────────────
        if call_oi > 0:
            pc_ratio = round(put_oi / call_oi, 2)
            if pc_ratio >= 1.2:
                pc_label = "偏空"
            elif pc_ratio <= 0.8:
                pc_label = "偏多"
            else:
                pc_label = "中性"
        else:
            pc_ratio, pc_label = None, "—"

        # ── Max Pain 计算 ─────────────────────────────────────────
        all_strikes = sorted(chain_df["_strike"].unique())
        call_map = {row["_strike"]: row["_oi"] for _, row in calls.iterrows()}
        put_map  = {row["_strike"]: row["_oi"] for _, row in puts.iterrows()}

        min_pain = float("inf")
        max_pain = None
        for s in all_strikes:
            # ITM calls: strike < s  → value (s - strike) × OI
            c_pain = sum(
                (s - k) * oi for k, oi in call_map.items() if k < s and oi > 0
            )
            # ITM puts: strike > s  → value (strike - s) × OI
            p_pain = sum(
                (k - s) * oi for k, oi in put_map.items() if k > s and oi > 0
            )
            total = c_pain + p_pain
            if total < min_pain:
                min_pain = total
                max_pain = s

        print(f"  [Futu 期权] Max Pain: ${max_pain}  PCR: {pc_ratio} ({pc_label})")
        print(f"  [Futu 期权] Call OI: {call_oi:,}  Put OI: {put_oi:,}")

        # ── 异常大单检测 ──────────────────────────────────────────
        # 条件: 成交量 > OI × 3，且成交量 > 500（过滤低流动性噪音）
        anomalies = []
        for _, row in chain_df.iterrows():
            vol = row["_vol"]
            oi  = row["_oi"]
            if vol > 500 and oi > 0 and vol > oi * 3:
                anomalies.append({
                    "strike": row["_strike"],
                    "type":   "Call" if "CALL" in row["_cp"] else "Put",
                    "volume": int(vol),
                    "oi":     int(oi),
                })

        anomalies.sort(key=lambda x: -x["volume"])
        anomalies = anomalies[:3]
        if anomalies:
            print(f"  [Futu 期权] 异常大单 {len(anomalies)} 条: "
                  + "  ".join(f"${a['strike']} {a['type']} vol{a['volume']:,}/oi{a['oi']:,}"
                               for a in anomalies))
        else:
            print("  [Futu 期权] 无异常大单")

        return {
            "ok": True,
            "max_pain": round(max_pain, 2) if max_pain is not None else None,
            "expiry":   nearest,
            "pc_ratio": pc_ratio,
            "pc_label": pc_label,
            "call_oi":  call_oi,
            "put_oi":   put_oi,
            "anomalies": anomalies,
            "error": "",
        }

    except Exception as e:
        msg = f"⚠️ 期权数据解析异常: {e}"
        print(msg)
        send_tg(msg)
        empty["error"] = str(e)
        return empty


# ══════════════════════════════════════════════════════════════════
#  技术指标计算（基于日线）
# ══════════════════════════════════════════════════════════════════
def calc_daily_indicators(bars: list) -> dict:
    if len(bars) < 20:
        return {}

    closes  = [b["c"] for b in bars]
    highs   = [b["h"] for b in bars]
    lows    = [b["l"] for b in bars]
    volumes = [b["v"] for b in bars]

    ma5  = sum(closes[-5:])  / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20

    def rsi(prices, period=14):
        gains = losses = 0.0
        for i in range(1, period + 1):
            d = prices[-i] - prices[-i - 1]
            if d > 0: gains  += d
            else:     losses -= d
        if losses == 0: return 100
        rs = (gains / period) / (losses / period)
        return round(100 - 100 / (1 + rs), 1)

    rsi_val = rsi(closes)

    atrs = []
    for i in range(-14, 0):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i]  - closes[i - 1]))
        atrs.append(tr)
    atr = sum(atrs) / len(atrs)

    vol_3     = sum(volumes[-3:])  / 3
    vol_10    = sum(volumes[-10:]) / 10
    vol_ratio = round(vol_3 / vol_10, 2) if vol_10 > 0 else 1.0

    recent_high = max(highs[-10:])
    recent_low  = min(lows[-10:])
    prev_close  = closes[-1]
    prev_high   = highs[-1]
    prev_low    = lows[-1]

    momentum_3d = (closes[-1] - closes[-4]) / closes[-4] * 100 if len(closes) >= 4 else 0

    return {
        "close":       round(prev_close, 2),
        "prev_high":   round(prev_high, 2),
        "prev_low":    round(prev_low, 2),
        "ma5":         round(ma5, 2),
        "ma10":        round(ma10, 2),
        "ma20":        round(ma20, 2),
        "rsi":         rsi_val,
        "atr":         round(atr, 2),
        "vol_ratio":   vol_ratio,
        "recent_high": round(recent_high, 2),
        "recent_low":  round(recent_low, 2),
        "momentum_3d": round(momentum_3d, 2),
    }


# ══════════════════════════════════════════════════════════════════
#  市场偏向评分
# ══════════════════════════════════════════════════════════════════
def calc_bias_score(ind: dict) -> dict:
    if not ind:
        return {"score": 6, "bias": "neutral", "label": "中性观望",
                "emoji": "➡️", "confidence": 30, "details": []}

    score   = 0
    details = []

    close = ind["close"]
    ma5   = ind["ma5"]
    ma10  = ind["ma10"]
    ma20  = ind["ma20"]
    rsi   = ind["rsi"]
    vr    = ind["vol_ratio"]
    mom   = ind["momentum_3d"]

    if ma5 > ma20 * 1.005:
        score += 2
        details.append(("✅", "均线", f"MA5 ${ma5:.2f} 强于 MA20 ${ma20:.2f}，多头排列"))
    elif ma5 > ma20:
        score += 1
        details.append(("⚠️", "均线", f"MA5 ${ma5:.2f} 小幅高于 MA20，趋势偏多但不强"))
    else:
        details.append(("❌", "均线", f"MA5 ${ma5:.2f} 低于 MA20 ${ma20:.2f}，空头排列"))

    if close > ma10 * 1.01:
        score += 2
        details.append(("✅", "位置", f"收盘 ${close} 明显高于 MA10 ${ma10:.2f}"))
    elif close > ma10:
        score += 1
        details.append(("⚠️", "位置", f"收盘 ${close} 略高于 MA10 ${ma10:.2f}"))
    else:
        details.append(("❌", "位置", f"收盘 ${close} 低于 MA10 ${ma10:.2f}"))

    if 50 <= rsi <= 65:
        score += 2
        details.append(("✅", "RSI", f"RSI {rsi} 多头健康区（50-65）"))
    elif 65 < rsi <= 75:
        score += 1
        details.append(("⚠️", "RSI", f"RSI {rsi} 偏高，注意超买"))
    elif rsi < 50:
        details.append(("❌", "RSI", f"RSI {rsi} 低于 50，空头占优"))
    else:
        score -= 1
        details.append(("🚨", "RSI", f"RSI {rsi} 严重超买"))

    if vr >= 1.3:
        score += 2
        details.append(("✅", "量能", f"量比 {vr}x，近期放量"))
    elif vr >= 1.0:
        score += 1
        details.append(("⚠️", "量能", f"量比 {vr}x，量能正常"))
    else:
        details.append(("❌", "量能", f"量比 {vr}x，量能萎缩"))

    if mom >= 3.0:
        score += 2
        details.append(("✅", "动量", f"3日涨幅 {mom:+.1f}%，动能强"))
    elif mom >= 0:
        score += 1
        details.append(("⚠️", "动量", f"3日涨幅 {mom:+.1f}%，动能偏正"))
    else:
        details.append(("❌", "动量", f"3日跌幅 {mom:+.1f}%，空头动能"))

    ph  = ind["prev_high"]
    pl  = ind["prev_low"]
    rng = ph - pl
    if rng > 0:
        pos = (close - pl) / rng
        if pos >= 0.7:
            score += 2
            details.append(("✅", "收盘位", f"收于日内高位 {pos*100:.0f}%"))
        elif pos >= 0.4:
            score += 1
            details.append(("⚠️", "收盘位", f"收于日内中位 {pos*100:.0f}%"))
        else:
            details.append(("❌", "收盘位", f"收于日内低位 {pos*100:.0f}%"))

    score = max(0, min(12, score))
    if score >= 8 and rsi <= 72:
        bias, emoji, label = "bullish_strong", "🟢🟢", "强烈看多"
    elif score == 7:
        bias, emoji, label = "bullish_weak",   "🟢",   "偏多"
    elif score <= 2 and rsi >= 35:
        bias, emoji, label = "bearish_strong", "🔴🔴", "强烈看空"
    else:
        bias, emoji, label = "neutral",        "➡️",   "中性观望"

    confidence = int(abs(score - 5) / 7 * 100 + 30)

    return {
        "score":      score,
        "bias":       bias,
        "label":      label,
        "emoji":      emoji,
        "confidence": min(confidence, 95),
        "details":    details,
    }


# ══════════════════════════════════════════════════════════════════
#  关键价位计算
# ══════════════════════════════════════════════════════════════════
def calc_key_levels(ind: dict) -> dict:
    if not ind:
        return {}

    close = ind["close"]
    atr   = ind["atr"]
    ph    = ind["prev_high"]
    pl    = ind["prev_low"]
    rh    = ind["recent_high"]
    rl    = ind["recent_low"]
    ma5   = ind["ma5"]
    ma20  = ind["ma20"]

    resistance_levels = sorted(set([
        round(ph, 2),
        round(rh, 2),
        round(close + atr * 1.0, 2),
        round(close + atr * 1.5, 2),
    ]))
    resistance = [r for r in resistance_levels if r > close][:3]

    support_levels = sorted(set([
        round(pl, 2),
        round(rl, 2),
        round(ma5, 2),
        round(ma20, 2),
        round(close - atr * 1.0, 2),
        round(close - atr * 1.5, 2),
    ]), reverse=True)
    support = [s for s in support_levels if s < close][:3]

    return {"resistance": resistance, "support": support, "atr": atr}


# ══════════════════════════════════════════════════════════════════
#  TradingAgents 报告读取
# ══════════════════════════════════════════════════════════════════
def load_trading_agents(ticker: str) -> dict:
    """v0.5: 优先 final_decision.md 拿结构化字段 (Rating / Price Target / Time Horizon
    / Entry Zone / Stop)，fallback market_report.md 的 FINAL TRANSACTION PROPOSAL"""
    ta_dir = TA_LOG_BASE / ticker
    if not ta_dir.exists():
        return {"found": False}

    date_dirs = sorted(
        [d for d in ta_dir.iterdir()
         if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)],
        key=lambda d: d.name, reverse=True,
    )
    if not date_dirs:
        return {"found": False}

    report_date = date_dirs[0].name
    final_path  = date_dirs[0] / "reports" / "final_decision.md"
    market_path = date_dirs[0] / "reports" / "market_report.md"

    out = {
        "found":          True,
        "date":           report_date,
        "decision":       "UNKNOWN",
        "decision_label": "—",
        "decision_emoji": "❓",
        "rating_raw":     None,
        "price_target":   None,
        "time_horizon":   None,
        "horizon_class":  "—",
        "entry_zone":     None,   # (low, high) USD
        "stop_level":     None,   # USD
        "risk_level":     "中",
        "summary_text":   "",
    }

    # ── 优先从 final_decision.md 拿结构化字段 ──
    fd_text = ""
    if final_path.exists():
        try:
            fd_text = final_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            fd_text = ""

    if fd_text:
        m = re.search(r"\*\*Rating\*\*:\s*([\w\-]+)", fd_text, re.IGNORECASE)
        if m: out["rating_raw"] = m.group(1).strip()

        m = re.search(r"\*\*Price Target\*\*:\s*\$?([\d.]+)", fd_text)
        if m:
            try: out["price_target"] = float(m.group(1))
            except Exception: pass

        m = re.search(r"\*\*Time Horizon\*\*:\s*([^\n]+)", fd_text)
        if m: out["time_horizon"] = m.group(1).strip()

        m = re.search(r"\*\*Executive Summary\*\*:\s*(.+?)(?=\n\n\*\*[A-Z]|\Z)",
                      fd_text, re.DOTALL)
        if m:
            out["summary_text"] = m.group(1).strip()
            # 入场区间 "$XX-$XX" / "$XX-XX"
            for em in re.finditer(
                    r"\$(\d+(?:\.\d+)?)\s*[-–]\s*\$?(\d+(?:\.\d+)?)",
                    out["summary_text"]):
                lo, hi = float(em.group(1)), float(em.group(2))
                if 1 < lo < hi < 10000:
                    out["entry_zone"] = (round(lo, 2), round(hi, 2))
                    break
            # 止损 "stop ... $XX"
            sm = re.search(r"stop[^.\n]{0,80}?\$(\d+(?:\.\d+)?)",
                           out["summary_text"], re.IGNORECASE)
            if sm:
                try: out["stop_level"] = float(sm.group(1))
                except Exception: pass

    # ── fallback: market_report.md FINAL TRANSACTION PROPOSAL ──
    if not out["rating_raw"] and market_path.exists():
        try:
            mr_text = market_path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"FINAL TRANSACTION PROPOSAL[:\s]+\**(\w+)\**",
                          mr_text, re.IGNORECASE)
            if m: out["rating_raw"] = m.group(1).upper()
        except Exception:
            pass

    # ── 映射 rating → 中文 + 标准化 decision ──
    rating_norm = (out["rating_raw"] or "").upper().replace("-", "").replace("_", "")
    rating_map = {
        "BUY":         ("BUY",  "买入", "🟢"),
        "OVERWEIGHT":  ("BUY",  "加仓", "🟢"),
        "SELL":        ("SELL", "卖出", "🔴"),
        "UNDERWEIGHT": ("SELL", "减仓", "🔴"),
        "HOLD":        ("HOLD", "持有", "➡️"),
        "EQUALWEIGHT": ("HOLD", "持有", "➡️"),
        "NEUTRAL":     ("HOLD", "观望", "⚪"),
    }
    if rating_norm in rating_map:
        dec, lb, em = rating_map[rating_norm]
        out["decision"]       = dec
        out["decision_label"] = lb
        out["decision_emoji"] = em

    # ── 持有周期分类 ──
    if out["time_horizon"]:
        th = out["time_horizon"].lower()
        if "month" in th:
            months = [int(x) for x in re.findall(r"(\d+)", out["time_horizon"])]
            if months:
                avg = sum(months) / len(months)
                if avg <= 2:   out["horizon_class"] = "短线"
                elif avg <= 6: out["horizon_class"] = "中线"
                else:          out["horizon_class"] = "长线"
        elif "week" in th or "day" in th:
            out["horizon_class"] = "短线"
        elif "year" in th:
            out["horizon_class"] = "长线"

    # ── 风险等级（简化推断）──
    if out["decision"] == "SELL":
        out["risk_level"] = "高"
    elif out["decision"] == "BUY":
        out["risk_level"] = "中"
    else:
        out["risk_level"] = "中"

    return out


# ══════════════════════════════════════════════════════════════════
#  两层共识
# ══════════════════════════════════════════════════════════════════
def calc_consensus(bias: dict, ta: dict) -> dict:
    db_side = ("bullish" if "bullish" in bias["bias"] else
               "bearish" if "bearish" in bias["bias"] else "neutral")
    ta_decision = ta.get("decision", "UNKNOWN")
    ta_side = ("bullish" if ta_decision == "BUY" else
               "bearish" if ta_decision == "SELL" else "neutral")

    if db_side == ta_side == "bullish":
        return {"emoji": "🤝", "text": "两层共振看多，信号较强"}
    if db_side == ta_side == "bearish":
        return {"emoji": "🤝", "text": "两层共振看空，建议规避"}
    if db_side == ta_side == "neutral":
        return {"emoji": "🤝", "text": "两层一致观望，等待方向"}
    if db_side == "bullish" and ta_side == "neutral":
        return {"emoji": "⚡", "text": "短线偏多 / AI 观望，轻仓试探"}
    if db_side == "neutral" and ta_side == "bullish":
        return {"emoji": "⚡", "text": "短线中性 / AI 看多，等日线确认"}
    if db_side == "bearish" and ta_side == "neutral":
        return {"emoji": "⚡", "text": "短线偏空 / AI 观望，保守为主"}
    if db_side == "neutral" and ta_side == "bearish":
        return {"emoji": "⚡", "text": "短线中性 / AI 看空，减少暴露"}
    return {"emoji": "⚠️", "text": "两层分歧，建议空仓观望"}


# ══════════════════════════════════════════════════════════════════
#  昨日复盘
# ══════════════════════════════════════════════════════════════════
def load_yesterday_summary() -> dict:
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    paths = [
        BASE_DIR / "data" / "review" / yesterday / "triggers.json",
        BASE_DIR / "data" / "review" / yesterday / "session_summary.json",
    ]

    triggers_count = push_count = 0
    cash = None

    if paths[0].exists():
        try:
            triggers_count = len(json.load(open(paths[0])))
        except Exception:
            pass

    if paths[1].exists():
        try:
            summary    = json.load(open(paths[1]))
            push_count = summary.get("push_count", 0)
            cash       = summary.get("cash_available_final")
        except Exception:
            pass

    return {"date": yesterday, "triggers_count": triggers_count,
            "push_count": push_count, "cash": cash}


# ══════════════════════════════════════════════════════════════════
#  中文技术信号（替代 TA 英文 snippet）
# ══════════════════════════════════════════════════════════════════
def _chinese_signals(ind: dict, bias: dict) -> list:
    """从本地指标生成 ≤20 字的中文一句话信号"""
    if not ind:
        return []
    out = []

    rsi = ind.get("rsi", 50)
    if rsi >= 75:
        out.append(f"RSI {rsi}，严重超买区")
    elif rsi >= 65:
        out.append(f"RSI {rsi}，偏高警惕回调")
    elif rsi >= 50:
        out.append(f"RSI {rsi}，多头健康区")
    elif rsi >= 35:
        out.append(f"RSI {rsi}，弱势整理")
    else:
        out.append(f"RSI {rsi}，严重超卖区")

    ma5, ma20 = ind.get("ma5"), ind.get("ma20")
    if ma5 and ma20:
        if ma5 > ma20 * 1.005:
            out.append("均线多头排列（MA5>MA20）")
        elif ma5 < ma20 * 0.995:
            out.append("均线空头排列（MA5<MA20）")

    vr = ind.get("vol_ratio", 1.0)
    if vr >= 1.5:
        out.append(f"量比 {vr}x，明显放量")
    elif vr < 0.8:
        out.append(f"量比 {vr}x，量能萎缩")

    mom = ind.get("momentum_3d", 0)
    if mom >= 5:
        out.append(f"3日涨 {mom:+.1f}%，动能强")
    elif mom <= -5:
        out.append(f"3日跌 {mom:+.1f}%，空头施压")

    atr = ind.get("atr", 0)
    close = ind.get("close", 0)
    if atr > 0 and close > 0:
        out.append(f"ATR ${atr}，日波动±{atr/close*100:.1f}%")

    return out


# ══════════════════════════════════════════════════════════════════
#  实盘上下文（账户 + 持仓 + RKLB/RKLX 价）
# ══════════════════════════════════════════════════════════════════
def _fetch_live_context(ticker: str = "RKLB") -> dict:
    """读取实时账户 + RKLB/RKLX 报价。失败 ok=False，调用方降级"""
    ctx = {
        "ok": False, "cash": None,
        "rklb_position": None, "rklx_position": None,
        "rklb_price": None,    "rklx_price": None,
    }
    try:
        sys.path.insert(0, str(BASE_DIR.parent))
        from core.realtime_quote import get_client as _gc
        qc = _gc()

        acc = qc.fetch_account()
        if acc:
            ctx["cash"] = float(acc.get("cash") or acc.get("usd_cash") or 0)

        pos = qc.fetch_positions()
        if isinstance(pos, list):
            pos = {p["ticker"]: p for p in pos if isinstance(p, dict) and "ticker" in p}
        if isinstance(pos, dict):
            for code, p in pos.items():
                short = str(code).replace("US.", "")
                if short == "RKLB":
                    ctx["rklb_position"] = p
                elif short == "RKLX":
                    ctx["rklx_position"] = p

        for tk, key in [("RKLB", "rklb_price"), ("RKLX", "rklx_price")]:
            q = qc.fetch_one(f"US.{tk}")
            if q and q.get("price"):
                ctx[key] = float(q["price"])

        ctx["ok"] = True
        print(f"  [strategy] cash=${ctx['cash']} RKLB=${ctx['rklb_price']} RKLX=${ctx['rklx_price']}")
    except Exception as e:
        print(f"  [strategy] 实盘上下文获取失败: {e}")
    return ctx


# ══════════════════════════════════════════════════════════════════
#  策略构造（具体可执行建议）— 激进型
# ══════════════════════════════════════════════════════════════════
def _build_strategy(bias: dict, ind: dict, levels: dict,
                    live: dict, ticker: str = "RKLB") -> dict:
    """
    激进型策略:
      仓位 = confidence × 1.0 上限 95%
      bullish_strong/weak → 推 RKLX (2x)，量按 RKLX 价算
      neutral/bearish → 不推介入
      止损贴 support[-1]，入场 close - ATR
    """
    b = bias["bias"]
    conf = bias.get("confidence", 0)
    atr = levels.get("atr") or ind.get("atr", 0)
    close = ind.get("close", 0)
    rklb_price = live.get("rklb_price") or close
    rklx_price = live.get("rklx_price")
    cash = live.get("cash") or 0

    # ── 是否推入场 ──
    bullish = b in ("bullish_strong", "bullish_weak")
    if not bullish or rklb_price <= 0:
        return {"action": "wait", "ticker": ticker, "bias": b}

    # ── 关键价位（用 live 价过滤，避免昨日收盘的过期压力/支撑）──
    raw_resists  = levels.get("resistance", []) or []
    raw_supports = levels.get("support", []) or []
    resists  = sorted([r for r in raw_resists if r > rklb_price])
    supports = sorted([s for s in raw_supports if s < rklb_price], reverse=True)

    # fallback: 若 live 价已突破所有静态压力/支撑，按 ATR 推算
    if not resists:
        resists = [round(rklb_price + atr, 2), round(rklb_price + atr * 2, 2)]
    elif len(resists) < 2:
        resists.append(round(rklb_price + atr * 2, 2))
    if not supports:
        supports = [round(rklb_price - atr, 2), round(rklb_price - atr * 1.5, 2)]

    # 入场区: live-ATR 到 live-ATR/2 之间（激进型 pullback）
    entry_low  = round(rklb_price - atr, 2)
    entry_high = round(rklb_price - atr * 0.5, 2)
    entry_mid  = round((entry_low + entry_high) / 2, 2)

    t1 = round(resists[0], 2)
    t2 = round(resists[1], 2)
    stop = round(supports[-1], 2)  # 深止损（最远支撑）

    # ── 仓位（激进型：cap 95%）──
    pos_pct = min(0.95, conf / 100.0)
    dollars = round(cash * pos_pct, 2) if cash else 0

    # ── 工具选择 ──
    tool = "RKLX"
    tool_price = rklx_price if rklx_price else rklb_price
    tool_label = "做多 RKLX（2x 多头）"
    if not rklx_price or rklx_price <= 0:
        tool = "RKLB"
        tool_price = rklb_price
        tool_label = "做多 RKLB"

    qty = int(dollars / tool_price) if (dollars and tool_price) else 0
    actual_cost = round(qty * tool_price, 2)

    risk_per_share = round(entry_mid - stop, 2)
    t1_pct = round((t1 - rklb_price) / rklb_price * 100, 1) if rklb_price else 0
    t2_pct = round((t2 - rklb_price) / rklb_price * 100, 1) if rklb_price else 0

    return {
        "action":         "enter_long",
        "ticker":         ticker,
        "bias":           b,
        "current_price":  round(rklb_price, 2),
        "entry_low":      entry_low,
        "entry_high":     entry_high,
        "entry_mid":      entry_mid,
        "tool":           tool,
        "tool_label":     tool_label,
        "tool_price":     round(tool_price, 2),
        "qty":            qty,
        "dollars":        actual_cost,
        "pos_pct":        round(pos_pct * 100, 0),
        "cash":           round(cash, 2) if cash else None,
        "t1":             t1,
        "t1_pct":         t1_pct,
        "t2":             t2,
        "t2_pct":         t2_pct,
        "stop":           stop,
        "risk_per_share": risk_per_share,
    }


# ══════════════════════════════════════════════════════════════════
#  v0.5: 期权信号大白话解读（CLAUDE.md 推送规范）
# ══════════════════════════════════════════════════════════════════
def _option_interpretation(opt: dict, live_price: float) -> list:
    """生成期权信号的中文解读 + 综合结论。每行 ≤30 字"""
    if not opt.get("ok"):
        return []
    lines = []
    mp = opt.get("max_pain")
    pc = opt.get("pc_ratio")

    if mp is not None and live_price > 0:
        gap_pct = (live_price - mp) / mp * 100
        if abs(gap_pct) < 3:
            lines.append(f"Max Pain ${mp} 离现价近，到期前可能震荡这附近")
        elif gap_pct > 10:
            lines.append(f"现价比 Max Pain ${mp} 高 {gap_pct:.0f}%，到期前庄家有压价动机")
        elif gap_pct < -10:
            lines.append(f"现价比 Max Pain ${mp} 低 {abs(gap_pct):.0f}%，到期前可能反弹")
        else:
            lines.append(f"Max Pain ${mp}，短期庄家压制目标")

    if pc is not None:
        if pc >= 1.2:
            lines.append(f"Put/Call {pc:.2f} 偏空，看跌期权多于看涨")
        elif pc <= 0.8:
            lines.append(f"Put/Call {pc:.2f} 偏多，资金更看涨")
        else:
            lines.append(f"Put/Call {pc:.2f} 中性，多空均衡")

    anomalies = opt.get("anomalies", []) or []
    if anomalies:
        big = anomalies[0]
        if big.get("type", "").upper() == "CALL":
            lines.append(f"异动 ${big['strike']:.0f} Call 大量买入，资金赌涨到 ${big['strike']:.0f} 以上")
        else:
            lines.append(f"异动 ${big['strike']:.0f} Put 大量买入，资金对冲下跌")

    # ── 综合结论 ──
    bull, bear = 0, 0
    if pc is not None:
        if pc <= 0.8: bull += 1
        elif pc >= 1.2: bear += 1
    if anomalies:
        t = anomalies[0].get("type", "").upper()
        if t == "CALL": bull += 1
        elif t == "PUT": bear += 1
    if mp and live_price > 0:
        if live_price > mp * 1.10: bear += 1
        elif live_price < mp * 0.90: bull += 1

    if bull > bear:
        verdict = "短期震荡、中期偏多"
    elif bear > bull:
        verdict = "短期或有回调，中期偏空"
    else:
        verdict = "多空胶着，等更明确信号"
    lines.append(f"→ 综合: {verdict}")
    return lines


# ══════════════════════════════════════════════════════════════════
#  v0.5: 进度条 (用于 信心 / 仓位 可视化)
# ══════════════════════════════════════════════════════════════════
def _bar(pct: float, width: int = 10) -> str:
    if pct is None: pct = 0
    pct = max(0, min(100, pct))
    n = round(pct / 100 * width)
    return "█" * n + "░" * (width - n)


# ══════════════════════════════════════════════════════════════════
#  v0.5: 昨日操作复盘
# ══════════════════════════════════════════════════════════════════
def _melbourne_yesterday_str() -> str:
    try:
        from zoneinfo import ZoneInfo
        return (datetime.now(ZoneInfo("Australia/Melbourne")) - timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _fetch_history_deals(date_str: str) -> list:
    """从 Futu 拉指定日期的成交记录（Melbourne 时区）"""
    try:
        try:
            from moomoo import OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm, RET_OK
        except ImportError:
            from futu import OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm, RET_OK

        try:
            trd = OpenSecTradeContext(
                filter_trdmarket=TrdMarket.US,
                host=FUTU_HOST, port=FUTU_PORT,
                security_firm=SecurityFirm.FUTUAU,
            )
        except TypeError:
            trd = OpenSecTradeContext(
                filter_trdmarket=TrdMarket.US,
                host=FUTU_HOST, port=FUTU_PORT,
            )

        try:
            ret, data = trd.history_deal_list_query(
                trd_env=TrdEnv.REAL,
                start=f"{date_str} 00:00:00",
                end=f"{date_str} 23:59:59",
            )
            if ret != RET_OK or data is None or len(data) == 0:
                print(f"  [复盘] {date_str} 无成交记录")
                return []
            deals = []
            for _, row in data.iterrows():
                deals.append({
                    "code":  str(row.get("code", "")),
                    "price": float(row.get("price", 0)),
                    "qty":   float(row.get("qty", 0)),
                    "side":  str(row.get("trd_side", "")).upper(),
                    "create_time": str(row.get("create_time", "")),
                })
            print(f"  [复盘] {date_str} 成交 {len(deals)} 条")
            return deals
        finally:
            trd.close()
    except Exception as e:
        print(f"  [复盘] 拉取成交异常: {e}")
        return []


def _load_yesterday_triggers(date_str: str) -> list:
    path = BASE_DIR.parent / "data" / "review" / date_str / "triggers.json"
    if not path.exists():
        print(f"  [复盘] 未找到 {path}")
        return []
    try:
        triggers = json.loads(path.read_text(encoding="utf-8"))
        print(f"  [复盘] 加载触发记录 {len(triggers)} 条")
        return triggers
    except Exception as e:
        print(f"  [复盘] 解析 triggers 失败: {e}")
        return []


# ══════════════════════════════════════════════════════════════════
#  v0.5.1 — FIFO 真实盈亏计算
#  | FIFO-based realized P&L for yesterday's review
#  关键改动:
#    1) 继承前一交易日 positions_final 作为初始 lots (而不是当作 0)
#    2) 每笔 SELL FIFO 消费最早 lot,逐 match 计算 (sell-buy)×qty
#    3) 扣除每股双边手续费估算 (与 swing_detector 一致 $0.02/股)
# ══════════════════════════════════════════════════════════════════
_FIFO_FEE_PER_SHARE_ROUNDTRIP = 0.02   # 与 swing_detector profit_fee_per_share 一致


def _load_initial_positions(date_str: str, max_lookback_days: int = 7) -> dict:
    """
    找 date_str 之前最近一个有 session_summary.json 的交易日,
    返回 {full_ticker: {"qty": int, "cost": float}}。
    跨周末/节假日时往前回溯,最多 max_lookback_days 天。
    | locate the prior trading day's session_summary and return positions_final
    """
    try:
        base_dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {}

    for back in range(1, max_lookback_days + 1):
        prev = (base_dt - timedelta(days=back)).strftime("%Y-%m-%d")
        path = BASE_DIR.parent / "data" / "review" / prev / "session_summary.json"
        if not path.exists():
            continue
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
            raw = summary.get("positions_final") or {}
            result = {}
            for tk, info in raw.items():
                qty = int(info.get("qty") or 0)
                cost = float(info.get("cost") or 0)
                if qty > 0 and cost > 0:
                    # 统一加 US. 前缀;positions_final 里 key 是短名 (RKLX)
                    full = tk if tk.startswith("US.") else f"US.{tk}"
                    result[full] = {"qty": qty, "cost": cost}
            print(f"  [复盘] 继承前一交易日 {prev} positions_final: "
                  f"{len(result)} 个 ticker")
            return result
        except Exception as e:
            print(f"  [复盘] 解析 {prev} session_summary 失败: {e}")
            continue

    print(f"  [复盘] 未找到 {date_str} 之前 {max_lookback_days} 天内的 session_summary")
    return {}


def _parse_deal_ts(s):
    """解析 deal create_time → datetime;失败返回 None"""
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _compute_fifo_pl(deals: list, initial_positions: dict,
                     fee_per_share_roundtrip: float = _FIFO_FEE_PER_SHARE_ROUNDTRIP) -> dict:
    """
    用 FIFO 算法回放当日 deals,返回:
      {
        "trades":          [{...}]   # 每笔 deal 的明细 + match 结果
        "totals": {
          "realized_gross": float,    # 不扣费的实现盈亏
          "fees":           float,    # 总手续费估算
          "realized_net":   float,    # 扣费后实现盈亏
        },
        "position_changes": {ticker_short: (initial_qty, final_qty)},
        "warnings":         [str, ...]
      }
    | replay deals as FIFO; emit per-trade match detail and totals.
    """
    # lot queue: {full_ticker: list of {qty, price, source, time}}
    lots = {}
    for tk, info in initial_positions.items():
        lots[tk] = [{
            "qty":    info["qty"],
            "price":  info["cost"],
            "source": "继承",       # 显示用
            "time":   None,         # 继承 lot 无时间
        }]

    initial_qty = {tk: sum(l["qty"] for l in lots[tk]) for tk in lots}

    trades_out = []
    realized_gross = 0.0
    fees_total = 0.0
    warnings = []

    fee_per_side = fee_per_share_roundtrip / 2   # 单边

    for d in sorted(deals, key=lambda x: x.get("create_time", "")):
        full_tk = d["code"]
        if not full_tk.startswith("US."):
            full_tk = f"US.{full_tk}"

        side = d["side"]
        qty  = int(round(float(d["qty"])))
        price = float(d["price"])
        ts_str = d["create_time"]

        time_short = ts_str[11:19] if len(ts_str) >= 19 else ts_str

        record = {
            "time":         time_short,
            "ts_full":      ts_str,
            "side":         "买入" if "BUY" in side else "卖出" if "SELL" in side else side,
            "ticker":       full_tk.replace("US.", ""),
            "ticker_full":  full_tk,
            "qty":          qty,
            "price":        round(price, 4),
            "amount":       round(qty * price, 2),
            "matched_lots": [],
            "gross_pl":     0.0,
            "fee":          0.0,
            "net_pl":       0.0,
            "unmatched_qty": 0,
        }

        if "BUY" in side:
            lots.setdefault(full_tk, []).append({
                "qty":    qty,
                "price":  price,
                "source": time_short,
                "time":   ts_str,
            })
        elif "SELL" in side:
            remaining = qty
            queue = lots.setdefault(full_tk, [])
            gross = 0.0
            while remaining > 0 and queue:
                head = queue[0]
                take = min(remaining, head["qty"])
                gross += (price - head["price"]) * take
                record["matched_lots"].append({
                    "qty":       take,
                    "buy_price": round(head["price"], 4),
                    "source":    head["source"],
                })
                head["qty"] -= take
                remaining   -= take
                if head["qty"] <= 0:
                    queue.pop(0)

            if remaining > 0:
                # 异常:卖出数量超过持仓 (空仓?数据缺失?)
                record["unmatched_qty"] = remaining
                warnings.append(
                    f"{time_short} {record['ticker']} 卖出 {qty} 股,"
                    f"但 lot 队列只够 {qty - remaining} 股 — 缺失 {remaining} 股的 buy 记录"
                )
                # 缺失部分按 buy_price=0 计 (不合理但避免崩溃,会被 warnings 提示)

            fee = qty * fee_per_side * 2   # 双边 (buy+sell)
            record["gross_pl"] = round(gross, 2)
            record["fee"]      = round(fee, 2)
            record["net_pl"]   = round(gross - fee, 2)
            realized_gross += gross
            fees_total     += fee

        trades_out.append(record)

    # 持仓变化:initial vs final
    all_tickers = set(initial_qty.keys()) | set(lots.keys())
    position_changes = {}
    for tk in sorted(all_tickers):
        init = initial_qty.get(tk, 0)
        final = sum(l["qty"] for l in lots.get(tk, []))
        if init != final or init > 0 or final > 0:
            position_changes[tk.replace("US.", "")] = (init, final)

    return {
        "trades": trades_out,
        "totals": {
            "realized_gross": round(realized_gross, 2),
            "fees":           round(fees_total, 2),
            "realized_net":   round(realized_gross - fees_total, 2),
        },
        "position_changes": position_changes,
        "warnings": warnings,
        "initial_positions_display": {
            tk.replace("US.", ""): {"qty": v["qty"], "cost": v["cost"]}
            for tk, v in initial_positions.items()
        },
    }


def _build_yesterday_review(date_str: str, deals: list, triggers: list) -> dict:
    """
    匹配实际成交与系统信号,给出行为评分(粗略:1-5 星)+ 真实盈亏。
    v0.5.1 (2026-05-13):
      - [FIX] pnl 改为 FIFO 真实盈亏 (继承前一交易日 positions_final 为初始 lots)
      - [FIX] 信号匹配:gap = (d_ts - t_ts).total_seconds(),要求 ≥0
              即信号必须在操作之前才算"跟随" (操作前 30 分钟窗口)
      - [FIX] "已有同方向持仓时"的强入场信号不算错过
    | switch to FIFO realized P&L; signal match is forward-only
      (signal must precede the trade); strong-entry not flagged as
      missed if same-direction position already exists at signal time.
    """
    review = {
        "date": date_str, "trades": [], "missed": [],
        "scores": {"execution": 5, "profit_discipline": 5, "chase_restraint": 5},
        "pnl_rough": 0.0,           # 保留字段名兼容,值改为 FIFO 真实净盈亏
        "pnl_realized_gross": 0.0,
        "pnl_realized_net":   0.0,
        "pnl_fees":           0.0,
        "initial_positions":  {},
        "position_changes":   {},
        "fifo_warnings":      [],
        "tips": [],
        "triggers_total": len(triggers),
    }

    # ── 1) FIFO 真实盈亏(继承前一交易日 positions_final) ──
    initial_positions = _load_initial_positions(date_str)
    fifo = _compute_fifo_pl(deals, initial_positions)

    review["initial_positions"]   = fifo["initial_positions_display"]
    review["position_changes"]    = fifo["position_changes"]
    review["pnl_realized_gross"]  = fifo["totals"]["realized_gross"]
    review["pnl_fees"]            = fifo["totals"]["fees"]
    review["pnl_realized_net"]    = fifo["totals"]["realized_net"]
    review["pnl_rough"]           = fifo["totals"]["realized_net"]  # 兼容老字段
    review["fifo_warnings"]       = fifo["warnings"]

    # ── 2) 信号匹配 (前向 30 min:信号必须在操作之前) ──
    # | forward-only match: signal must precede the trade by ≤ 30min
    trigger_ts = [(t, _parse_deal_ts(t.get("ts", ""))) for t in triggers]
    trigger_ts = [(t, ts) for t, ts in trigger_ts if ts is not None]

    fifo_trades = fifo["trades"]   # 已含 time/side/ticker/qty/price/match...
    for ft in fifo_trades:
        d_ts = _parse_deal_ts(ft["ts_full"])
        nearby = None
        if d_ts:
            best, best_gap = None, 999999
            for t, t_ts in trigger_ts:
                gap = (d_ts - t_ts).total_seconds()
                # 必须 t_ts <= d_ts (信号在前),且窗口 30 分钟内
                if gap < 0 or gap > 1800:
                    continue
                if gap >= best_gap:
                    continue
                if ft["ticker_full"] != t.get("ticker", ""):
                    continue
                trg = t.get("trigger", "")
                side_buy  = (ft["side"] == "买入")
                side_sell = (ft["side"] == "卖出")
                if side_buy and t.get("direction") == "long":
                    best, best_gap = t, gap
                elif side_sell and t.get("direction") == "short":
                    best, best_gap = t, gap
                elif side_sell and trg in ("profit_target_hit", "stop_loss_warning",
                                            "near_resistance", "overbought_surge",
                                            "large_day_gain", "drawdown_from_peak"):
                    # v0.5.1: 新增 stop_loss_warning / drawdown_from_peak 进卖出匹配池
                    best, best_gap = t, gap
            nearby = (best, best_gap) if best else None

        ft["trigger"]  = nearby[0].get("trigger") if nearby else None
        ft["strength"] = nearby[0].get("strength") if nearby else None
        ft["gap_min"]  = round(nearby[1] / 60, 1) if nearby else None
        # 显式语义:有 trigger 就是跟随信号,无就是自主操作
        ft["follow_signal"] = bool(nearby)

    review["trades"] = fifo_trades

    # ── 3) 评分基础 ──
    strong_entries = [t for t in triggers
                      if t.get("strength") == "STRONG"
                      and t.get("trigger") in ("direction_trend", "swing_top", "swing_bottom")
                      and t.get("direction") in ("long", "short")]

    # 评分: 执行力 = STRONG 入场信号 30min 内有成交比例
    executed = 0
    for t in strong_entries:
        t_ts = _parse_deal_ts(t.get("ts", ""))
        if not t_ts: continue
        for d in deals:
            d_ts = _parse_deal_ts(d["create_time"])
            if not d_ts: continue
            if 0 <= (d_ts - t_ts).total_seconds() <= 1800:
                executed += 1
                break
    exec_ratio = executed / len(strong_entries) if strong_entries else 1.0
    review["scores"]["execution"] = max(0, min(5, round(exec_ratio * 5)))

    # 评分: 止盈纪律 = profit_target_hit 30min 内有 SELL 比例
    pt_signals = [t for t in triggers if t.get("trigger") == "profit_target_hit"]
    sold = 0
    for t in pt_signals:
        t_ts = _parse_deal_ts(t.get("ts", ""))
        if not t_ts: continue
        for d in deals:
            if "SELL" not in d["side"]: continue
            d_ts = _parse_deal_ts(d["create_time"])
            if not d_ts: continue
            if 0 <= (d_ts - t_ts).total_seconds() <= 1800:
                sold += 1
                break
    pt_ratio = sold / len(pt_signals) if pt_signals else 1.0
    review["scores"]["profit_discipline"] = max(0, min(5, round(pt_ratio * 5)))

    # 评分: 追高克制 = 阻力/超买/大涨预警后 10min 内 没 BUY 比例
    chase_signals = [t for t in triggers
                     if t.get("trigger") in ("near_resistance", "overbought_surge", "large_day_gain")]
    avoided = 0
    for t in chase_signals:
        t_ts = _parse_deal_ts(t.get("ts", ""))
        if not t_ts: continue
        bought_after = False
        for d in deals:
            if "BUY" not in d["side"]: continue
            d_ts = _parse_deal_ts(d["create_time"])
            if not d_ts: continue
            if 0 <= (d_ts - t_ts).total_seconds() <= 600:
                bought_after = True
                break
        if not bought_after:
            avoided += 1
    chase_ratio = avoided / len(chase_signals) if chase_signals else 1.0
    review["scores"]["chase_restraint"] = max(0, min(5, round(chase_ratio * 5)))

    # ── 4) 错过的强信号(剔除"已有同方向持仓"+"30min 内有同向操作") ──
    # | "missed" excludes signals where same-direction position already exists,
    #   or where user already acted within 30min after the signal
    def _position_qty_at(ticker_full: str, ts: datetime) -> int:
        """回放到 ts 之前的所有 deals,返回该 ticker 在 ts 时的净持仓股数"""
        qty = initial_positions.get(ticker_full, {}).get("qty", 0)
        for d in sorted(deals, key=lambda x: x.get("create_time", "")):
            d_ts = _parse_deal_ts(d["create_time"])
            if not d_ts or d_ts >= ts:
                break
            full = d["code"] if d["code"].startswith("US.") else f"US.{d['code']}"
            if full != ticker_full:
                continue
            if "BUY" in d["side"]:
                qty += int(round(float(d["qty"])))
            elif "SELL" in d["side"]:
                qty -= int(round(float(d["qty"])))
        return qty

    for t in strong_entries:
        t_ts = _parse_deal_ts(t.get("ts", ""))
        if not t_ts: continue
        ticker = t.get("ticker", "")
        direction = t.get("direction")

        # 跳过:同方向已有持仓
        # | skip if same-direction position already held
        qty_at_signal = _position_qty_at(ticker, t_ts)
        if direction == "long" and qty_at_signal > 0:
            continue

        # 跳过:信号后 30min 内有同向操作
        # | skip if user acted in same direction within 30min after signal
        acted = False
        for d in deals:
            d_ts = _parse_deal_ts(d["create_time"])
            if not d_ts: continue
            if not (0 <= (d_ts - t_ts).total_seconds() <= 1800):
                continue
            full = d["code"] if d["code"].startswith("US.") else f"US.{d['code']}"
            if full != ticker:
                continue
            if direction == "long" and "BUY" in d["side"]:
                acted = True; break
            if direction == "short" and "SELL" in d["side"]:
                acted = True; break
        if acted:
            continue

        review["missed"].append(t)

    # ── 5) tips ──
    s = review["scores"]
    if s["execution"] < 3:
        review["tips"].append("强信号出现时减少犹豫，按建议时间窗口内执行")
    if s["chase_restraint"] < 3:
        review["tips"].append("阻力位/超买预警出现就停止加仓，等回调")
    if s["profit_discipline"] < 3:
        review["tips"].append("浮盈达标信号要重视，分批止盈锁定利润")
    if not review["tips"]:
        review["tips"].append("继续保持现有纪律")

    return review


# ══════════════════════════════════════════════════════════════════
#  格式化 — 期权信号板块
# ══════════════════════════════════════════════════════════════════
def _fmt_option_section(opt: dict) -> list:
    lines = ["━━ 期权信号 ━━"]

    if not opt.get("ok"):
        lines.append("  期权数据略")
        return lines

    # Max Pain
    expiry = opt.get("expiry", "")
    expiry_fmt = ""
    if expiry:
        try:
            m, d = int(expiry[5:7]), int(expiry[8:10])
            expiry_fmt = f"{m}/{d}"
        except Exception:
            expiry_fmt = expiry[5:]

    if opt.get("max_pain") is not None:
        lines.append(f"Max Pain: <b>${opt['max_pain']}</b>（到期 {expiry_fmt}）")

    pc  = opt.get("pc_ratio")
    lbl = opt.get("pc_label", "—")
    if pc is not None:
        lines.append(f"Put/Call: <b>{pc:.2f}</b>（{lbl}）"
                     f"  Call OI {opt['call_oi']:,}  Put OI {opt['put_oi']:,}")

    anomalies = opt.get("anomalies", [])
    if anomalies:
        for a in anomalies[:2]:
            lines.append(f"  异动 ${a['strike']:.0f} {a['type']}  "
                         f"量{a['volume']:,}/仓{a['oi']:,}（{a['volume']/a['oi']:.1f}x）")

    return lines


# ══════════════════════════════════════════════════════════════════
#  格式化 Telegram 消息 — 五板块排版（v0.5）
# ══════════════════════════════════════════════════════════════════
def format_briefing(ticker: str, ind: dict, bias: dict, levels: dict,
                    yesterday: dict, ta: dict, opt: dict,
                    live: dict, strat: dict, review: dict = None) -> str:
    now   = datetime.now().strftime("%Y-%m-%d")
    close = ind.get("close", 0)
    atr   = levels.get("atr", 0)
    live_px = (live.get("rklb_price") if live else None) or close

    lines = [
        f"📊 <b>开盘简报 · {ticker} · {now}</b>",
        f"",
    ]

    # ══ 板块一：热点事件 + AI 操作结论 ═════════════════════════════
    lines.append("🔥 <b>热点事件</b>")
    if ta.get("found"):
        lines.append(f"AI 判定 ({ta['date']}): "
                     f"{ta['decision_emoji']} <b>{ta['decision_label']}</b>")
        if ta.get("entry_zone"):
            lo, hi = ta["entry_zone"]
            lines.append(f"  介入区间: ${lo}-${hi}")
        if ta.get("price_target"):
            lines.append(f"  止盈目标: ${ta['price_target']}")
        if ta.get("stop_level"):
            lines.append(f"  止损位: ${ta['stop_level']}")
        if ta.get("horizon_class") != "—":
            th = ta.get("time_horizon") or ""
            lines.append(f"  持有周期: {ta['horizon_class']}（{th[:40]}）" if th else f"  持有周期: {ta['horizon_class']}")
        lines.append(f"  风险等级: {ta['risk_level']}")
    else:
        lines.append("AI 判定: 未运行")
    lines.append("")
    lines.append("技术信号:")
    for s in _chinese_signals(ind, bias):
        lines.append(f"• {s}")
    lines.append("")

    # ══ 板块二：技术面（带编号的压力/支撑）═════════════════════════
    lines.append("📈 <b>技术面</b>")
    lines.append(f"昨收 <b>${close}</b>   RSI {ind.get('rsi','—')}   "
                 f"量比 {ind.get('vol_ratio','—')}x   "
                 f"3日 {ind.get('momentum_3d',0):+.1f}%")
    lines.append(f"MA5/10/20: ${ind.get('ma5','—')} / ${ind.get('ma10','—')} / ${ind.get('ma20','—')}   "
                 f"ATR ${atr:.2f}")
    resists = levels.get("resistance", []) or []
    supports = levels.get("support", []) or []
    for i, r in enumerate(resists, 1):
        suffix = "（最近）" if i == 1 else ("（最远）" if i == len(resists) else "")
        lines.append(f"压力位{i}: ${r}{suffix}")
    for i, s in enumerate(supports, 1):
        suffix = "（最近）" if i == 1 else ("（最远）" if i == len(supports) else "")
        lines.append(f"支撑位{i}: ${s}{suffix}")
    lines.append(f"评分: <b>{bias['label']}</b>  {bias['score']}/12  置信 {bias['confidence']}%")
    lines.append("")

    # ══ 板块三：期权信号（数据 + 大白话解读 + 综合结论）════════════
    lines.append("🎯 <b>期权信号</b>")
    if opt.get("ok"):
        opt_lines = _fmt_option_section(opt)
        lines += [l for l in opt_lines if not l.startswith("━━")]
        lines.append("")
        lines.append("信号解读:")
        for s in _option_interpretation(opt, live_px):
            lines.append(f"  {s}")
    else:
        lines.append("期权数据略")
    lines.append("")

    # ══ 板块四：今日策略（结构化）═════════════════════════════════
    lines.append("🧭 <b>今日策略</b>")
    consensus = calc_consensus(bias, ta)
    lines.append(f"{consensus['emoji']} 两层共识: {consensus['text']}")

    if strat.get("action") == "enter_long":
        conf = bias.get("confidence", 0)
        pos_pct = strat.get("pos_pct", 0)
        lines.append("")
        lines.append(f"建议操作: <b>{strat['tool_label']}</b>")
        lines.append(f"信心 {_bar(conf)} {conf}%")
        lines.append(f"仓位 {_bar(pos_pct)} {pos_pct:.0f}%")
        lines.append("")
        lines.append("买入明细:")
        lines.append(f"  品种: {strat['tool']}")
        lines.append(f"  价格: ${strat['tool_price']}（现价）")
        lines.append(f"  数量: <b>{strat['qty']} 股</b>")
        lines.append(f"  总金额: <b>${strat['dollars']:,.0f}</b>")
        if strat.get("cash"):
            invest_pct = (strat["dollars"] / strat["cash"] * 100) if strat["cash"] else 0
            lines.append("")
            lines.append("账户分配:")
            lines.append(f"  可用现金: ${strat['cash']:,.0f}")
            lines.append(f"  本次投入: ${strat['dollars']:,.0f}（{invest_pct:.0f}%）")
            lines.append(f"  剩余现金: ${strat['cash'] - strat['dollars']:,.0f}")
        # 目标位（带 RKLX 2x 预期）
        leverage = 2.0 if strat["tool"] == "RKLX" else 1.0
        lev_note = "RKLX 预期" if strat["tool"] == "RKLX" else "预期"
        lines.append("")
        lines.append(f"目标位（标的: {ticker}）:")
        lines.append(f"  第一目标: ${strat['t1']}（{strat['t1_pct']:+.1f}%）→ {lev_note} {strat['t1_pct']*leverage:+.1f}%")
        lines.append(f"  第二目标: ${strat['t2']}（{strat['t2_pct']:+.1f}%）→ {lev_note} {strat['t2_pct']*leverage:+.1f}%")
        stop_pct = (strat['stop'] - strat['current_price']) / strat['current_price'] * 100 if strat['current_price'] else 0
        lines.append(f"  止损位: ${strat['stop']}（{stop_pct:+.1f}%）→ {lev_note} {stop_pct*leverage:+.1f}%")
        lines.append(f"单笔风险: 约 ${strat['risk_per_share']:.2f}/股 RKLB")
    elif "bearish" in bias["bias"]:
        lines.append("🔴 偏空，空仓或减仓观望")
    else:
        lines.append("➡️ 方向不明，观望为主")
    lines.append("")

    # ══ 板块五：昨日操作复盘 ══════════════════════════════════════
    # v0.5.1: FIFO 真实盈亏 + 信号方向匹配
    lines.append("📋 <b>昨日操作复盘</b>")
    if review:
        # 初始持仓 (继承前一交易日)
        init_pos = review.get("initial_positions", {}) or {}
        if init_pos:
            init_parts = [f"{tk} {v['qty']}股 @${v['cost']:.2f}"
                          for tk, v in init_pos.items()]
            lines.append(f"初始持仓: {' / '.join(init_parts)}")

        if review.get("trades"):
            lines.append("你的操作:")
            for t in review["trades"]:
                sig = (f"（{t['trigger']} 跟随 {t['gap_min']}min ✓）"
                       if t.get("trigger") else "（自主操作 · 无对应信号）")
                lines.append(
                    f"  {t['time']}  {t['side']} {t['ticker']} "
                    f"{t['qty']}股 @${t['price']:.2f} {sig}"
                )
                # 卖出附加 FIFO 匹配明细
                if t["side"] == "卖出" and t.get("matched_lots"):
                    match_parts = [f"{m['qty']}股×${m['buy_price']:.2f}({m['source']})"
                                   for m in t["matched_lots"]]
                    net_sign   = "+" if t["net_pl"]   >= 0 else "-"
                    gross_sign = "+" if t["gross_pl"] >= 0 else "-"
                    lines.append(
                        f"    └ FIFO: {' + '.join(match_parts)}"
                        f" = 实现 {net_sign}${abs(t['net_pl']):.2f}"
                        f"（毛 {gross_sign}${abs(t['gross_pl']):.2f} - 费 ${t['fee']:.2f}）"
                    )
                    if t.get("unmatched_qty"):
                        lines.append(
                            f"    ⚠️ 缺失 {t['unmatched_qty']} 股 buy 记录"
                        )

            # 持仓变化
            pc = review.get("position_changes", {}) or {}
            if pc:
                pc_parts = [f"{tk} {init}→{final}" for tk, (init, final) in pc.items()]
                lines.append(f"持仓变化: {' / '.join(pc_parts)}")

            pnl_net   = review.get("pnl_realized_net",   0.0)
            pnl_gross = review.get("pnl_realized_gross", 0.0)
            pnl_fees  = review.get("pnl_fees",           0.0)
            pnl_word = "盈" if pnl_net > 0 else ("亏" if pnl_net < 0 else "持平")
            lines.append(
                f"当日真实盈亏: <b>${pnl_net:+,.2f}</b>（{pnl_word}, "
                f"毛 ${pnl_gross:+,.2f} - 费 ${pnl_fees:.2f}）"
            )
            for w in (review.get("fifo_warnings") or [])[:3]:
                lines.append(f"  ⚠️ {w}")
        else:
            lines.append("昨日无成交")
        if review.get("missed"):
            lines.append("")
            lines.append("错过的强信号:")
            for m in review["missed"][:3]:
                ts = m.get("ts", "")[11:19]
                short = m.get("ticker", "").replace("US.", "")
                lines.append(f"  {ts}  {short}  {m.get('trigger')}")
        s = review["scores"]
        lines.append("")
        lines.append("行为评分:")
        lines.append(f"  执行力 {'★' * s['execution']}{'☆' * (5 - s['execution'])}")
        lines.append(f"  止盈纪律 {'★' * s['profit_discipline']}{'☆' * (5 - s['profit_discipline'])}")
        lines.append(f"  追高克制 {'★' * s['chase_restraint']}{'☆' * (5 - s['chase_restraint'])}")
        if review.get("tips"):
            lines.append("")
            lines.append("下次改进:")
            for tip in review["tips"]:
                lines.append(f"  • {tip}")
    else:
        lines.append("昨日无操作")

    lines += [
        f"",
        f"<i>/detail {ticker}  /ask {ticker} 你的问题</i>",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  Telegram 推送
# ══════════════════════════════════════════════════════════════════
def send_tg(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        print("  ⚠️ TG_BOT_TOKEN 或 TG_CHAT_ID 未配置")
        print(text)
        return False
    try:
        url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id":    TG_CHAT,
            "text":       text,
            "parse_mode": "HTML",
        }, timeout=10)
        ok = resp.json().get("ok", False)
        if ok:
            print("  ✅ Telegram 推送成功")
        else:
            print(f"  ❌ Telegram 推送失败: {resp.text[:120]}")
        return ok
    except Exception as e:
        print(f"  ❌ Telegram 推送异常: {e}")
        return False


# ══════════════════════════════════════════════════════════════════
#  HTML 简报输出
# ══════════════════════════════════════════════════════════════════
_HTML_CSS = (
    ":root{--g:#16a34a;--r:#dc2626;--gr:#6b7280;--bd:#e5e7eb;--bg:#f9fafb;--cd:#fff;--tx:#111827;--hd:#374151}"
    "*{box-sizing:border-box;margin:0;padding:0}"
    "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
    "background:var(--bg);color:var(--tx);padding:16px;line-height:1.6;font-size:15px}"
    ".wrap{max-width:820px;margin:0 auto}"
    "h1{font-size:1.35em;margin-bottom:4px}"
    "h2{font-size:1.05em;font-weight:700;color:var(--hd);margin:0 0 10px}"
    ".meta{color:var(--gr);font-size:.85em;margin-bottom:16px}"
    ".card{background:var(--cd);border:1px solid var(--bd);border-radius:8px;padding:14px 16px;margin-bottom:12px}"
    ".tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:.8em;font-weight:600}"
    ".bull{color:var(--g)}.bear{color:var(--r)}.neut{color:var(--gr)}"
    ".bull-bg{background:#dcfce7;color:var(--g)}.bear-bg{background:#fee2e2;color:var(--r)}"
    ".neut-bg{background:#f3f4f6;color:var(--gr)}"
    "table{width:100%;border-collapse:collapse;font-size:.9em;margin:8px 0}"
    "th{background:#f3f4f6;padding:7px 10px;border:1px solid var(--bd);color:var(--hd);font-weight:600;text-align:left}"
    "td{padding:6px 10px;border:1px solid var(--bd);vertical-align:top}"
    "tr:nth-child(even) td{background:#fafafa}"
    ".num{text-align:right}.ctr{text-align:center}"
    ".ok{color:var(--g);font-weight:600}.fail{color:var(--r);font-weight:600}.warn{color:#d97706}"
    "ul{margin:6px 0 0 20px}li{margin:3px 0}"
    "hr{border:none;border-top:1px solid var(--bd);margin:10px 0}"
    "@media(max-width:500px){body{padding:10px;font-size:14px}th,td{padding:5px 7px}"
    ".card{padding:10px 12px}}"
)


def _html_page(title: str, body: str) -> str:
    return (
        f'<!DOCTYPE html><html lang="zh"><head>'
        f'<meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}</title>'
        f'<style>{_HTML_CSS}</style>'
        f'</head><body><div class="wrap">{body}</div></body></html>'
    )


def _html_option_section(opt: dict) -> str:
    if not opt.get("ok"):
        return "<p class='neut'>期权数据略</p>"

    expiry = opt.get("expiry", "")
    expiry_fmt = ""
    if expiry:
        try:
            m, d = int(expiry[5:7]), int(expiry[8:10])
            expiry_fmt = f"{m}/{d}"
        except Exception:
            expiry_fmt = expiry[5:]

    rows = ""
    mp = opt.get("max_pain")
    if mp is not None:
        rows += (
            f"<tr><td>Max Pain</td>"
            f"<td class='num'><strong>${mp}</strong></td>"
            f"<td>到期日 {expiry_fmt}</td></tr>"
        )

    pc = opt.get("pc_ratio")
    lbl = opt.get("pc_label", "—")
    if pc is not None:
        pc_cls = "bear" if pc >= 1.2 else ("bull" if pc <= 0.8 else "neut")
        rows += (
            f"<tr><td>Put/Call Ratio</td>"
            f"<td class='num {pc_cls}'><strong>{pc:.2f}</strong></td>"
            f"<td>{lbl} &nbsp; Call OI {opt.get('call_oi',0):,} &nbsp; Put OI {opt.get('put_oi',0):,}</td></tr>"
        )

    anomalies = opt.get("anomalies", [])
    if anomalies:
        for a in anomalies:
            ratio = a['volume'] / a['oi'] if a['oi'] else 0
            type_cls = "bull" if a['type'].upper() == "CALL" else "bear"
            rows += (
                f"<tr><td>⚡ 异动</td>"
                f"<td class='num {type_cls}'>${a['strike']:.0f} {a['type']}</td>"
                f"<td>量 {a['volume']:,} / 仓 {a['oi']:,}  ({ratio:.1f}x)</td></tr>"
            )
    else:
        rows += "<tr><td>异动大单</td><td class='neut'>—</td><td>无明显异常</td></tr>"

    return (
        f"<table><tr><th>指标</th><th class='num'>数值</th><th>备注</th></tr>"
        f"{rows}</table>"
    )


def format_briefing_html(ticker: str, ind: dict, bias: dict, levels: dict,
                         yesterday: dict, ta: dict, opt: dict,
                         live: dict, strat: dict, review: dict = None) -> str:
    now   = datetime.now().strftime("%Y-%m-%d")
    close = ind.get("close", 0)
    atr   = levels.get("atr", 0)
    score = bias["score"]
    live_px = (live.get("rklb_price") if live else None) or close

    b = bias["bias"]
    bias_cls = "bull-bg" if "bullish" in b else ("bear-bg" if "bearish" in b else "neut-bg")

    # ══ 板块 1: 热点事件 + AI 详细操作建议 ═════════════════
    if ta.get("found"):
        ta_dec = ta.get("decision", "UNKNOWN")
        dec_cls = "bull" if ta_dec == "BUY" else ("bear" if ta_dec == "SELL" else "neut")
        rows = (
            f"<tr><td>建议方向</td>"
            f"<td class='num'><span class='{dec_cls}'><strong>{ta.get('decision_label','—')}</strong></span></td>"
            f"<td>AI 综合判定 ({ta['date']})</td></tr>"
        )
        if ta.get("entry_zone"):
            lo, hi = ta["entry_zone"]
            rows += f"<tr><td>介入区间</td><td class='num bull'>${lo}–${hi}</td><td>AI 给出的回调买入区间</td></tr>"
        if ta.get("price_target"):
            pt_pct = ((ta['price_target'] - live_px) / live_px * 100) if live_px > 0 else 0
            pt_cls = "bull" if pt_pct > 0 else "bear"
            rows += f"<tr><td>止盈目标</td><td class='num {pt_cls}'>${ta['price_target']}</td><td>距现价 {pt_pct:+.1f}%</td></tr>"
        if ta.get("stop_level"):
            sl_pct = ((ta['stop_level'] - live_px) / live_px * 100) if live_px > 0 else 0
            rows += f"<tr><td>止损位</td><td class='num bear'>${ta['stop_level']}</td><td>跌破触发减仓 ({sl_pct:+.1f}%)</td></tr>"
        if ta.get("horizon_class") != "—":
            th = ta.get("time_horizon") or ""
            rows += f"<tr><td>持有周期</td><td class='num'>{ta['horizon_class']}</td><td>{th}</td></tr>"
        risk_cls = "fail" if ta["risk_level"] == "高" else ("warn" if ta["risk_level"] == "中" else "ok")
        rows += f"<tr><td>风险等级</td><td class='num {risk_cls}'><strong>{ta['risk_level']}</strong></td><td></td></tr>"
        events_html = (
            f"<table>"
            f"<tr><th>项目</th><th class='num'>数值</th><th>说明</th></tr>"
            f"{rows}</table>"
        )
    else:
        events_html = "<p class='neut'>AI 判定: 未运行</p>"

    signals = _chinese_signals(ind, bias)
    if signals:
        events_html += "<p style='margin-top:8px'><strong>本地技术信号:</strong></p><ul>"
        events_html += "".join(f"<li>{s}</li>" for s in signals)
        events_html += "</ul>"

    # ══ 板块 2: 技术面（带编号的压力/支撑）═════════════════
    mom_3d = ind.get("momentum_3d", 0)
    mom_cls = "bull" if mom_3d > 0 else ("bear" if mom_3d < 0 else "neut")
    resists = levels.get("resistance", []) or []
    supports = levels.get("support", []) or []

    tech_rows = (
        f"<tr><td>昨收</td><td class='num'><strong>${close}</strong></td>"
        f"<td>RSI {ind.get('rsi','—')} &nbsp; 量比 {ind.get('vol_ratio','—')}x &nbsp; "
        f"<span class='{mom_cls}'>3日 {mom_3d:+.1f}%</span></td></tr>"
        f"<tr><td>均线</td><td class='num'>—</td>"
        f"<td>MA5 ${ind.get('ma5','—')} / MA10 ${ind.get('ma10','—')} / "
        f"MA20 ${ind.get('ma20','—')} &nbsp; ATR ${atr:.2f}</td></tr>"
    )
    for i, r in enumerate(resists, 1):
        suffix = "（最近）" if i == 1 else ("（最远）" if i == len(resists) else "")
        tech_rows += f"<tr><td>压力位{i}</td><td class='num bear'>${r}</td><td>{suffix}</td></tr>"
    for i, s in enumerate(supports, 1):
        suffix = "（最近）" if i == 1 else ("（最远）" if i == len(supports) else "")
        tech_rows += f"<tr><td>支撑位{i}</td><td class='num bull'>${s}</td><td>{suffix}</td></tr>"
    tech_rows += (
        f"<tr><td>评分</td>"
        f"<td class='num'><span class='tag {bias_cls}'>{bias['label']} {score}/12</span></td>"
        f"<td>置信 {bias['confidence']}%</td></tr>"
    )
    tech_html = (
        f"<table><tr><th>指标</th><th class='num'>数值</th><th>说明</th></tr>"
        f"{tech_rows}</table>"
    )

    # ══ 板块 3: 期权（数据 + 解读 + 结论）══════════════════
    opt_data_html = _html_option_section(opt)
    opt_interp_html = ""
    if opt.get("ok"):
        interp_lines = _option_interpretation(opt, live_px)
        if interp_lines:
            opt_interp_html = (
                "<p style='margin-top:10px'><strong>信号解读:</strong></p>"
                "<ul>" + "".join(f"<li>{l}</li>" for l in interp_lines) + "</ul>"
            )

    # ══ 板块 4: 今日策略（结构化 + 进度条 + 子表）══════════
    consensus = calc_consensus(bias, ta)
    consensus_html = (
        f"<p><strong>{consensus['emoji']} 两层共识:</strong> {consensus['text']}</p>"
    )

    if strat.get("action") == "enter_long":
        conf = bias.get("confidence", 0)
        pos_pct = strat.get("pos_pct", 0)
        bars_html = (
            f"<p><strong>建议操作:</strong> {strat['tool_label']}</p>"
            f"<p style='font-family:monospace'>信心 {_bar(conf)} {conf}%</p>"
            f"<p style='font-family:monospace'>仓位 {_bar(pos_pct)} {pos_pct:.0f}%</p>"
        )

        buy_rows = (
            f"<tr><td>品种</td><td class='num'><strong>{strat['tool']}</strong></td><td>{strat['tool_label']}</td></tr>"
            f"<tr><td>价格</td><td class='num'>${strat['tool_price']}</td><td>现价</td></tr>"
            f"<tr><td>数量</td><td class='num'><strong>{strat['qty']} 股</strong></td><td></td></tr>"
            f"<tr><td>总金额</td><td class='num'><strong>${strat['dollars']:,.0f}</strong></td><td></td></tr>"
        )
        buy_html = (
            "<p style='margin-top:10px'><strong>买入明细:</strong></p>"
            f"<table>{buy_rows}</table>"
        )

        alloc_html = ""
        if strat.get("cash"):
            invest_pct = strat["dollars"] / strat["cash"] * 100
            alloc_rows = (
                f"<tr><td>可用现金</td><td class='num'>${strat['cash']:,.0f}</td><td></td></tr>"
                f"<tr><td>本次投入</td><td class='num bull'>${strat['dollars']:,.0f}</td><td>{invest_pct:.0f}%</td></tr>"
                f"<tr><td>剩余现金</td><td class='num'>${strat['cash'] - strat['dollars']:,.0f}</td><td></td></tr>"
            )
            alloc_html = (
                "<p style='margin-top:10px'><strong>账户分配:</strong></p>"
                f"<table>{alloc_rows}</table>"
            )

        # 目标位（带 RKLX 杠杆预期）
        leverage = 2.0 if strat["tool"] == "RKLX" else 1.0
        lev_note = "RKLX 预期" if strat["tool"] == "RKLX" else "预期"
        stop_pct = (strat['stop'] - strat['current_price']) / strat['current_price'] * 100 if strat['current_price'] else 0
        target_rows = (
            f"<tr><td>第一目标</td><td class='num bull'><strong>${strat['t1']}</strong></td>"
            f"<td>{strat['t1_pct']:+.1f}% → {lev_note} {strat['t1_pct']*leverage:+.1f}%</td></tr>"
            f"<tr><td>第二目标</td><td class='num bull'>${strat['t2']}</td>"
            f"<td>{strat['t2_pct']:+.1f}% → {lev_note} {strat['t2_pct']*leverage:+.1f}%</td></tr>"
            f"<tr><td>止损位</td><td class='num bear'><strong>${strat['stop']}</strong></td>"
            f"<td>{stop_pct:+.1f}% → {lev_note} {stop_pct*leverage:+.1f}%</td></tr>"
            f"<tr><td>单笔风险</td><td class='num'>${strat['risk_per_share']:.2f}/股</td>"
            f"<td>RKLB 单股最大损失</td></tr>"
        )
        target_html = (
            f"<p style='margin-top:10px'><strong>目标位（标的: {ticker}）:</strong></p>"
            f"<table>{target_rows}</table>"
        )

        strat_html = bars_html + buy_html + alloc_html + target_html
    elif "bearish" in b:
        strat_html = "<p class='fail'>🔴 偏空，空仓或减仓观望</p>"
    else:
        strat_html = "<p class='neut'>➡️ 方向不明，观望为主</p>"

    # ══ 板块 5: 昨日操作复盘 ══════════════════════════════
    # v0.5.1: FIFO 真实盈亏 + 继承持仓 + 持仓变化
    review_html = ""
    if review:
        # 初始持仓 (继承前一交易日 positions_final)
        init_pos = review.get("initial_positions", {}) or {}
        if init_pos:
            init_parts = [f"{tk} {v['qty']}股 @${v['cost']:.2f}"
                          for tk, v in init_pos.items()]
            review_html += (
                "<p><strong>初始持仓（继承前一交易日）:</strong> "
                + " / ".join(init_parts) + "</p>"
            )

        # 成交表
        if review.get("trades"):
            rows = ""
            for t in review["trades"]:
                side_cls = "bull" if t["side"] == "买入" else "bear"
                sig_txt = (f"<span class='neut'>{t['trigger']} ({t['strength'] or '—'}) 跟随 {t['gap_min']}min ✓</span>"
                           if t.get("trigger") else "<span class='neut'>自主操作（无对应信号）</span>")
                rows += (
                    f"<tr><td>{t['time']}</td>"
                    f"<td><span class='{side_cls}'><strong>{t['side']}</strong></span></td>"
                    f"<td>{t['ticker']}</td>"
                    f"<td class='num'>{t['qty']}</td>"
                    f"<td class='num'>${t['price']:.2f}</td>"
                    f"<td class='num'>${t['amount']:,.0f}</td>"
                    f"<td>{sig_txt}</td></tr>"
                )
                # FIFO 匹配明细行 (仅卖出)
                if t["side"] == "卖出" and t.get("matched_lots"):
                    match_parts = [f"{m['qty']}×${m['buy_price']:.2f}({m['source']})"
                                   for m in t["matched_lots"]]
                    pl_cls     = "bull" if t["net_pl"]   >= 0 else "bear"
                    net_sign   = "+"    if t["net_pl"]   >= 0 else "-"
                    gross_sign = "+"    if t["gross_pl"] >= 0 else "-"
                    rows += (
                        f"<tr><td colspan='7' style='padding-left:24px;font-size:12px;color:#666'>"
                        f"└ FIFO: {' + '.join(match_parts)} → "
                        f"实现 <span class='{pl_cls}'><strong>{net_sign}${abs(t['net_pl']):.2f}</strong></span>"
                        f"（毛 {gross_sign}${abs(t['gross_pl']):.2f} − 费 ${t['fee']:.2f}）"
                        f"</td></tr>"
                    )
                    if t.get("unmatched_qty"):
                        rows += (
                            f"<tr><td colspan='7' style='padding-left:24px;color:#c00'>"
                            f"⚠️ 缺失 {t['unmatched_qty']} 股 buy 记录</td></tr>"
                        )
            trades_table = (
                "<table>"
                "<tr><th>时间</th><th>动作</th><th>品种</th>"
                "<th class='num'>数量</th><th class='num'>价格</th>"
                "<th class='num'>金额</th><th>对应信号</th></tr>"
                f"{rows}</table>"
            )

            pnl_net   = review.get("pnl_realized_net",   0.0)
            pnl_gross = review.get("pnl_realized_gross", 0.0)
            pnl_fees  = review.get("pnl_fees",           0.0)
            pnl_cls = "bull" if pnl_net > 0 else ("bear" if pnl_net < 0 else "neut")
            pnl_word = "盈" if pnl_net > 0 else ("亏" if pnl_net < 0 else "持平")

            # 持仓变化
            pc = review.get("position_changes", {}) or {}
            pc_html = ""
            if pc:
                pc_parts = [f"{tk} {init}→{final}" for tk, (init, final) in pc.items()]
                pc_html = f"<p>持仓变化: {' / '.join(pc_parts)}</p>"

            review_html += (
                "<p><strong>你的操作:</strong></p>"
                + trades_table
                + pc_html
                + f"<p>当日真实盈亏（FIFO,已扣手续费）: "
                  f"<span class='{pnl_cls}'><strong>${pnl_net:+,.2f}</strong></span>"
                  f"（{pnl_word},毛 ${pnl_gross:+,.2f} − 费 ${pnl_fees:.2f}）</p>"
            )
            for w in (review.get("fifo_warnings") or [])[:3]:
                review_html += f"<p class='bear' style='font-size:12px'>⚠️ {w}</p>"
        else:
            review_html += "<p class='neut'>昨日无成交</p>"

        # 错过的强信号
        if review.get("missed"):
            miss_rows = ""
            for m in review["missed"][:5]:
                ts = m.get("ts", "")[11:19]
                short = m.get("ticker", "").replace("US.", "")
                miss_rows += f"<li>{ts}  {short}  {m.get('trigger')} ({m.get('strength')})</li>"
            review_html += f"<p style='margin-top:8px'><strong>错过的强信号:</strong></p><ul>{miss_rows}</ul>"

        # 评分
        s = review["scores"]
        def _stars(n):
            return "★" * n + "☆" * (5 - n)
        review_html += (
            "<p style='margin-top:8px'><strong>行为评分:</strong></p>"
            "<table>"
            f"<tr><td>执行力</td><td>{_stars(s['execution'])}</td></tr>"
            f"<tr><td>止盈纪律</td><td>{_stars(s['profit_discipline'])}</td></tr>"
            f"<tr><td>追高克制</td><td>{_stars(s['chase_restraint'])}</td></tr>"
            "</table>"
        )

        if review.get("tips"):
            review_html += "<p style='margin-top:8px'><strong>下次改进:</strong></p><ul>"
            for tip in review["tips"]:
                review_html += f"<li>{tip}</li>"
            review_html += "</ul>"
    else:
        review_html = "<p class='neut'>昨日无操作</p>"

    # ══ 组装 ══════════════════════════════════════════════
    body = (
        f"<h1>开盘简报 · {ticker} · {now}</h1>"
        f"<div class='meta'>daily_briefing v0.5 &nbsp;·&nbsp; "
        f"评分 {score}/12 &nbsp;·&nbsp; 置信 {bias['confidence']}%</div>"

        f"<div class='card'><h2>🔥 热点事件</h2>{events_html}</div>"

        f"<div class='card'><h2>📈 技术面</h2>{tech_html}</div>"

        f"<div class='card'><h2>🎯 期权信号</h2>{opt_data_html}{opt_interp_html}</div>"

        f"<div class='card'><h2>🧭 今日策略</h2>"
        f"{consensus_html}<hr>{strat_html}</div>"

        f"<div class='card'><h2>📋 昨日操作复盘</h2>{review_html}</div>"

        f"<div class='meta' style='text-align:center;margin-top:16px'>"
        f"/detail {ticker} &nbsp; /ask {ticker} 你的问题</div>"
    )
    return _html_page(f"开盘简报 · {ticker} · {now}", body)


# ══════════════════════════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print(f"  MagicQuant 开盘简报  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # ── 1. 日线技术面 ─────────────────────────────────────────────
    print(f"\n  [1/4] 拉取 {TICKER} 日线数据（Polygon）...")
    bars = fetch_daily_bars(TICKER, days=30)
    if not bars:
        print("  ❌ 无法获取数据，终止")
        return

    ind = calc_daily_indicators(bars)
    if not ind:
        print("  ❌ 数据不足（需要 ≥20 根日线）")
        return

    print(f"  收盘 ${ind['close']}  RSI {ind['rsi']}  量比 {ind['vol_ratio']}x")

    bias   = calc_bias_score(ind)
    levels = calc_key_levels(ind)
    print(f"  偏向: {bias['label']} ({bias['score']}/12)  "
          f"压力 {levels.get('resistance',[])}  支撑 {levels.get('support',[])}")

    # ── 2. TradingAgents AI ───────────────────────────────────────
    print(f"\n  [2/4] 读取 TradingAgents 报告...")
    ta = load_trading_agents(TICKER)
    if ta.get("found"):
        print(f"  {ta['date']} → {ta['decision']} ({ta['decision_label']})")
    else:
        print("  未找到报告，跳过")

    # ── 3. 期权数据（Futu OpenAPI）────────────────────────────────
    print(f"\n  [3/6] 拉取 {TICKER} 期权数据（Futu OpenAPI）...")
    opt = fetch_option_data(TICKER)

    # ── 4. 实盘上下文 + 策略构造 ──────────────────────────────────
    print(f"\n  [4/6] 读取实盘账户 + 构造策略...")
    live  = _fetch_live_context(TICKER)
    strat = _build_strategy(bias, ind, levels, live, TICKER)

    # ── 5. 昨日操作复盘（墨尔本昨日成交 + 信号匹配）───────────────
    print(f"\n  [5/6] 拉取昨日操作复盘...")
    y_date_str = _melbourne_yesterday_str()
    y_deals    = _fetch_history_deals(y_date_str)
    y_triggers = _load_yesterday_triggers(y_date_str)
    review     = _build_yesterday_review(y_date_str, y_deals, y_triggers) \
                 if (y_deals or y_triggers) else None

    # 旧字段兼容（其他代码可能引用）
    yesterday = load_yesterday_summary()

    # ── 格式化 + 推送 ─────────────────────────────────────────────
    print(f"\n  [6/6] 格式化简报...")
    msg = format_briefing(TICKER, ind, bias, levels, yesterday, ta, opt,
                           live, strat, review)

    print(f"\n{'=' * 60}")
    print(msg)
    print(f"{'=' * 60}")

    # 保存 HTML 简报
    briefing_dir = BASE_DIR.parent / "data" / "briefing"
    briefing_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    html_path = briefing_dir / f"daily_{date_str}.html"
    html_content = format_briefing_html(TICKER, ind, bias, levels, yesterday,
                                          ta, opt, live, strat, review)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\n  💾 HTML 简报: {html_path}")

    print("\n  推送到 Telegram...")
    send_tg(msg)


if __name__ == "__main__":
    main()
