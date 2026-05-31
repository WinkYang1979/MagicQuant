"""
MagicQuant pre-open health check.
VERSION : v0.5.35
DEPENDS : config.settings, Futu/Moomoo OpenAPI, core.focus.micro_indicators

开盘前健康检查：K_5M 订阅、K线新鲜度、指标有效性、历史冻结值黑名单。
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from config.settings import FUTU_HOST, FUTU_PORT, TG_BOT_TOKEN, TG_CHAT_ID

try:
    from moomoo import OpenQuoteContext, RET_OK, KLType, AuType, SubType, Session
except Exception:
    from futu import OpenQuoteContext, RET_OK, KLType, AuType, SubType, Session


ROOT = Path(__file__).resolve().parent.parent
TICKER = os.getenv("PRE_OPEN_TICKER", "US.RKLB")
MAX_KLINE_AGE_SEC = int(os.getenv("PRE_OPEN_MAX_KLINE_AGE_SEC", "60"))
FROZEN_BLACKLIST = {
    (43.1, 4.94),
    (43.1, 5.82),
    (57.9, 6.58),
}


def _load_calc_all_micro():
    path = ROOT / "core" / "focus" / "micro_indicators.py"
    spec = importlib.util.spec_from_file_location("mq_micro_indicators_preopen", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.calc_all_micro


def _send_tg(text: str) -> None:
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text},
            timeout=8,
        )
    except Exception:
        pass


def _parse_dt(text) -> datetime | None:
    if text is None:
        return None
    raw = str(text)[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    return None


def main() -> int:
    checks = []
    failures = []
    ctx = None
    try:
        ctx = OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
        ret, msg = ctx.subscribe(
            [TICKER], [SubType.K_5M], subscribe_push=True,
            extended_time=True, session=Session.ALL,
        )
        ok_sub = ret == RET_OK or ret == 0
        checks.append({"name": "K_5M subscribe", "ok": ok_sub, "detail": str(msg)[:120]})
        if not ok_sub:
            failures.append(f"K_5M 订阅失败: {msg}")

        ret, kl = ctx.get_cur_kline(TICKER, 200, KLType.K_5M, AuType.QFQ)
        if ret != RET_OK and ret != 0:
            failures.append(f"K_5M 获取失败: {kl}")
            checks.append({"name": "K_5M fetch", "ok": False, "detail": str(kl)[:120]})
        elif not hasattr(kl, "iloc") or len(kl) == 0:
            failures.append("K_5M 返回为空或非 DataFrame")
            checks.append({"name": "K_5M fetch", "ok": False, "detail": type(kl).__name__})
        else:
            checks.append({"name": "K_5M fetch", "ok": True, "detail": f"bars={len(kl)}"})
            last_time = _parse_dt(kl["time_key"].iloc[-1] if "time_key" in kl.columns else None)
            now_et = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)
            age = (now_et - last_time).total_seconds() if last_time else None
            ok_age = age is not None and 0 <= age <= MAX_KLINE_AGE_SEC
            checks.append({
                "name": "K_5M freshness",
                "ok": ok_age,
                "detail": f"last={last_time} age={age:.0f}s max={MAX_KLINE_AGE_SEC}s" if age is not None else "missing time_key",
            })
            if not ok_age:
                failures.append(checks[-1]["detail"])

            calc_all_micro = _load_calc_all_micro()
            current = float(kl["close"].iloc[-1])
            kl.attrs["et_today"] = now_et.strftime("%Y-%m-%d")
            if "time_key" in kl.columns:
                kl.attrs["has_today_data"] = bool(kl["time_key"].astype(str).str.startswith(kl.attrs["et_today"]).any())
            indicators = calc_all_micro(kl, current)
            rsi = indicators.get("rsi_5m")
            vol = indicators.get("vol_ratio")
            has_indicators = bool(indicators.get("data_ok") and indicators.get("is_today"))
            ok_ind = has_indicators and rsi is not None and round(float(rsi), 1) != 50.0
            checks.append({"name": "indicators", "ok": ok_ind, "detail": f"rsi={rsi} vol={vol} is_today={indicators.get('is_today')}"})
            if not ok_ind:
                failures.append(f"指标不可用或 RSI 默认值: rsi={rsi} is_today={indicators.get('is_today')}")
            pair = (round(float(rsi), 1), round(float(vol), 2)) if rsi is not None and vol is not None else None
            ok_blacklist = pair not in FROZEN_BLACKLIST
            checks.append({"name": "frozen blacklist", "ok": ok_blacklist, "detail": str(pair)})
            if not ok_blacklist:
                failures.append(f"命中历史冻结值黑名单: {pair}")

    except Exception as e:
        failures.append(f"pre_open_check 异常: {e}")
    finally:
        try:
            if ctx:
                ctx.close()
        except Exception:
            pass

    ok = not failures
    out = {
        "ts": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": TICKER,
        "ok": ok,
        "checks": checks,
        "failures": failures,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not ok:
        _send_tg("⚠️ 开盘前健康检查失败\n" + "\n".join(failures[:5]))
        return 1
    _send_tg("✅ 开盘前健康检查通过\nK_5M / 指标 / 冻结黑名单均正常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
