"""
VERSION : v0.1.0
DEPENDS : run_ta_daily.py, root.daily_briefing, .env, TradingAgents reports

Notify Telegram when TradingAgents finishes, and watch background runs for timeout.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


BASE_DIR = Path(__file__).resolve().parent
TA_LOG_BASE = Path.home() / ".tradingagents" / "logs"
PROCESS_FILE = BASE_DIR / "data" / "shared" / "ta_process.json"


def _load_env() -> None:
    for path in (BASE_DIR / ".env", BASE_DIR / "TradingAgents" / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def send_tg(text: str) -> bool:
    _load_env()
    token = os.getenv("TG_BOT_TOKEN")
    chat = os.getenv("TG_CHAT_ID")
    if not token or not chat or requests is None:
        print(text)
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=10,
        )
        return bool(resp.json().get("ok"))
    except Exception as e:
        print(f"  [TA notify] Telegram failed: {e}")
        return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _find_report_dir(ticker: str, trade_date: str | None) -> Path | None:
    ticker_dir = TA_LOG_BASE / ticker
    if trade_date:
        report_dir = ticker_dir / trade_date / "reports"
        return report_dir if report_dir.exists() else None
    if not ticker_dir.exists():
        return None
    date_dirs = sorted(
        [p for p in ticker_dir.iterdir() if p.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", p.name)],
        key=lambda p: p.name,
        reverse=True,
    )
    return date_dirs[0] / "reports" if date_dirs else None


def _decision_from_text(text: str) -> str:
    patterns = [
        r"\*\*Rating\*\*:\s*([A-Za-z_-]+)",
        r"FINAL TRANSACTION PROPOSAL[:\s*]+([A-Za-z_-]+)",
        r"\b(BUY|HOLD|SELL|OVERWEIGHT|UNDERWEIGHT|NEUTRAL)\b",
    ]
    raw = ""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).upper()
            break
    if raw in ("BUY", "OVERWEIGHT", "OUTPERFORM"):
        return "买入"
    if raw in ("SELL", "UNDERWEIGHT", "REDUCE"):
        return "卖出"
    if raw in ("HOLD", "NEUTRAL"):
        return "持有"
    return "持有"


def _signals_from_text(text: str, limit: int = 2) -> list[str]:
    signals: list[str] = []
    for line in text.splitlines():
        clean = line.strip().lstrip("-*• ").strip()
        if not clean or len(clean) < 12:
            continue
        lower = clean.lower()
        if any(word in lower for word in ("rklb", "revenue", "margin", "risk", "launch", "contract", "target", "rating")):
            signals.append(clean[:90])
        if len(signals) >= limit:
            break
    return signals or ["报告已生成，详细内容已写入 TradingAgents reports", "今日简报仍按最新 reports 自动读取"]


def _confidence_from_text(text: str) -> str:
    match = re.search(r"confidence[:\s*]+(\d{1,3})\s*%", text, re.IGNORECASE)
    if match:
        return f"{min(100, int(match.group(1)))}%"
    return "未标注"


def notify_complete(ticker: str, trade_date: str | None) -> None:
    report_dir = _find_report_dir(ticker, trade_date)
    if not report_dir:
        send_tg(f"⚠️ TradingAgents 分析完成但未找到 reports · {ticker}")
        return
    text = _read_text(report_dir / "final_decision.md") or _read_text(report_dir / "market_report.md")
    report_date = report_dir.parent.name
    decision = _decision_from_text(text)
    signals = _signals_from_text(text)
    confidence = _confidence_from_text(text)
    msg = (
        f"🤖 TradingAgents 分析完成 · {ticker} · 今日\n"
        f"结论: {decision}\n"
        "关键信号:\n"
        + "\n".join(f"• {line}" for line in signals)
        + f"\n置信: {confidence}"
    )
    send_tg(msg)
    if PROCESS_FILE.exists():
        try:
            data = json.loads(PROCESS_FILE.read_text(encoding="utf-8"))
            if data.get("ticker") == ticker and data.get("trade_date") == report_date:
                PROCESS_FILE.unlink()
        except Exception:
            pass


def _pid_running(pid: int) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return False
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            return code.value == 259
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def watch_timeout(pid: int, ticker: str, trade_date: str, timeout_sec: int) -> None:
    started = time.time()
    while time.time() - started < timeout_sec:
        if not _pid_running(pid):
            return
        time.sleep(15)
    if not _pid_running(pid):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=15)
    else:
        os.kill(pid, 9)
    send_tg("⚠️ TradingAgents 今日分析超时，使用昨日结论")
    try:
        if PROCESS_FILE.exists():
            PROCESS_FILE.unlink()
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--ticker", default="RKLB")
    parser.add_argument("--date", default="")
    parser.add_argument("--timeout", type=int, default=40 * 60)
    args = parser.parse_args()

    if args.watch:
        watch_timeout(args.pid, args.ticker, args.date, args.timeout)
    else:
        notify_complete(args.ticker, args.date or None)


if __name__ == "__main__":
    main()
