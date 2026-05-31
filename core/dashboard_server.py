# v1.0.1 | 2026-05-10 | DEPENDS: threading, http.server, json, re, config.settings
"""
Dashboard server — 实时推送看板后端
启动后访问 http://localhost:8765
"""

import os
import re
import json
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from config.settings import BASE_DIR, DATA_DIR, TICKER_CONFIG

VERSION = "1.0.1"

DATA_FILE    = os.path.join(DATA_DIR, "dashboard_feed.json")
HTML_FILE    = os.path.join(BASE_DIR, "dashboard.html")
MAX_MESSAGES = 300
DEFAULT_PORT = 8765

# 从配置自动构建 ticker 匹配模式（去掉 "US." 前缀）
_TICKER_RE = re.compile(
    r"\b(" + "|".join(k.replace("US.", "") for k in TICKER_CONFIG) + r")\b"
)

# 预编译，避免每次匹配时重新编译
_TRIGGER_PATTERNS = [
    (re.compile(r"浮盈达标"),                              "profit_target_hit"),
    (re.compile(r"高位回撤|回撤"),                          "drawdown_from_peak"),
    (re.compile(r"波段顶"),                                "swing_top"),
    (re.compile(r"波段底"),                                "swing_bottom"),
    (re.compile(r"方向信号"),                              "direction_trend"),
    (re.compile(r"异动"),                                  "rapid_move"),
    (re.compile(r"心跳|系统心跳"),                          "heartbeat"),
    (re.compile(r"AI\s*分析|ai_analysis", re.IGNORECASE), "ai"),
    (re.compile(r"已启动|startup|stopped",  re.IGNORECASE), "system"),
]

_lock           = threading.Lock()
_server_started = False
_feed_cache: dict  = {"updated_at": "", "messages": []}
_html_cache: bytes = b""


def _infer_trigger(text: str) -> str:
    for pattern, trigger in _TRIGGER_PATTERNS:
        if pattern.search(text):
            return trigger
    return "general"

def _infer_ticker(text: str) -> str:
    m = _TICKER_RE.search(text)
    return m.group(1) if m else ""


def _load_feed() -> dict:
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"updated_at": "", "messages": []}

def _save_feed(feed: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)


def push_message(text_html: str, ticker: str = None, trigger: str = None,
                 style: str = "C", buttons=None) -> None:
    now = datetime.now().isoformat()
    msg = {
        "id":        f"msg_{int(time.time() * 1000)}",
        "timestamp": now,
        "ticker":    ticker  or _infer_ticker(text_html),
        "trigger":   trigger or _infer_trigger(text_html),
        "style":     style,
        "text_html": text_html,
        "buttons":   buttons or [],
    }
    with _lock:
        msgs = _feed_cache["messages"]
        msgs.insert(0, msg)
        if len(msgs) > MAX_MESSAGES:
            del msgs[MAX_MESSAGES:]
        _feed_cache["updated_at"] = now
        _save_feed(_feed_cache)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/feed":
            self._serve_json()
        elif self.path in ("/", "/dashboard.html"):
            self._serve_html()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_json(self):
        with _lock:
            body = json.dumps(_feed_cache, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type",  "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self):
        if not _html_cache:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type",  "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(_html_cache)))
        self.end_headers()
        self.wfile.write(_html_cache)

    def log_message(self, fmt, *args):
        pass


def start_server(port: int = DEFAULT_PORT) -> None:
    global _server_started, _html_cache, _feed_cache
    if _server_started:
        return
    _server_started = True

    try:
        with open(HTML_FILE, "rb") as f:
            _html_cache = f.read()
    except FileNotFoundError:
        pass

    _feed_cache = _load_feed()
    os.makedirs(DATA_DIR, exist_ok=True)

    def _run():
        try:
            HTTPServer(("localhost", port), _Handler).serve_forever()
        except Exception as e:
            print(f"  [dashboard] server error: {e}")

    threading.Thread(target=_run, daemon=True, name="dashboard-http").start()
    print(f"  [dashboard] http://localhost:{port}")
