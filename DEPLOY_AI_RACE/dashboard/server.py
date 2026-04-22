"""
MagicQuant 慧投 — Dashboard Server v0.3.5
Serves the web dashboard and signal data API.
Run: python dashboard/server.py
Then open: http://localhost:5000

v0.3.5:
  - 新增 /ai_advisor/history API (AI 智囊团历史)
  - 新增 /ai_advisor/cost API (今日累计成本)
  - 新增 /ai_advisor/latest API (最新一次建议)

v0.3.2:
  - 新增 /focus/state API (实时盯盘状态)
  - 新增 /focus.html 丈人版界面
  - 支持 LAN 访问(绑定 0.0.0.0)
"""
import json, os, sys, subprocess, threading, time, webbrowser, socket
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, r"C:\MagicQuant")
from config.settings import SIGNALS_FILE, DASHBOARD_PORT, BASE_DIR

HTML_FILE           = os.path.join(BASE_DIR, "dashboard", "index.html")
FOCUS_HTML_FILE     = os.path.join(BASE_DIR, "dashboard", "focus.html")
AI_ANALYSIS_FILE    = os.path.join(BASE_DIR, "data", "ai_analysis.json")
FOCUS_STATE_FILE    = os.path.join(BASE_DIR, "data", "focus_state.json")
AI_ADVISOR_HISTORY  = os.path.join(BASE_DIR, "data", "ai_advisor_history.json")
AI_ADVISOR_COST     = os.path.join(BASE_DIR, "data", "ai_advisor_cost.json")


def read_file_safe(path: str):
    try:
        if os.path.exists(path):
            return open(path, encoding="utf-8").read()
    except:
        pass
    return None


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/", "/dashboard", "/index.html"):
            content = read_file_safe(HTML_FILE) or "<h1>index.html not found</h1>"
            self._serve(200, "text/html; charset=utf-8", content.encode())
        elif path in ("/focus", "/focus.html", "/laoyang"):
            content = read_file_safe(FOCUS_HTML_FILE)
            if content is None:
                self._serve(404, "text/plain; charset=utf-8",
                           "focus.html not found".encode())
            else:
                self._serve(200, "text/html; charset=utf-8", content.encode())
        elif path == "/signals":
            data = read_file_safe(SIGNALS_FILE)
            if data:
                self._serve(200, "application/json; charset=utf-8", data.encode(),
                            extra_headers={"Access-Control-Allow-Origin": "*"})
            else:
                self._serve(404, "application/json", b'{"error":"signals_latest.json not found"}',
                            extra_headers={"Access-Control-Allow-Origin": "*"})
        elif path == "/ai_analysis":
            data = read_file_safe(AI_ANALYSIS_FILE)
            if data:
                self._serve(200, "application/json; charset=utf-8", data.encode(),
                            extra_headers={"Access-Control-Allow-Origin": "*"})
            else:
                self._serve(200, "application/json", b'{}',
                            extra_headers={"Access-Control-Allow-Origin": "*"})
        elif path == "/focus/state":
            data = read_file_safe(FOCUS_STATE_FILE)
            if data:
                self._serve(200, "application/json; charset=utf-8", data.encode(),
                            extra_headers={"Access-Control-Allow-Origin": "*",
                                          "Cache-Control": "no-cache"})
            else:
                default = json.dumps({
                    "active": False,
                    "message": "盯盘未启动",
                    "updated_at": datetime.now().strftime("%H:%M:%S"),
                })
                self._serve(200, "application/json; charset=utf-8", default.encode(),
                            extra_headers={"Access-Control-Allow-Origin": "*",
                                          "Cache-Control": "no-cache"})
        elif path == "/ai_advisor/history":
            # AI 智囊团完整历史
            data = read_file_safe(AI_ADVISOR_HISTORY)
            if data:
                self._serve(200, "application/json; charset=utf-8", data.encode(),
                            extra_headers={"Access-Control-Allow-Origin": "*",
                                          "Cache-Control": "no-cache"})
            else:
                self._serve(200, "application/json", b'[]',
                            extra_headers={"Access-Control-Allow-Origin": "*"})
        elif path == "/ai_advisor/latest":
            # 只返回最近一条
            data_str = read_file_safe(AI_ADVISOR_HISTORY)
            try:
                history = json.loads(data_str) if data_str else []
                latest = history[-1] if history else None
            except:
                latest = None
            body = json.dumps(latest, ensure_ascii=False) if latest else "null"
            self._serve(200, "application/json; charset=utf-8", body.encode(),
                        extra_headers={"Access-Control-Allow-Origin": "*",
                                      "Cache-Control": "no-cache"})
        elif path == "/ai_advisor/cost":
            data = read_file_safe(AI_ADVISOR_COST)
            if data:
                self._serve(200, "application/json; charset=utf-8", data.encode(),
                            extra_headers={"Access-Control-Allow-Origin": "*"})
            else:
                default = json.dumps({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "cost": 0, "calls": 0, "tokens": 0,
                })
                self._serve(200, "application/json; charset=utf-8", default.encode(),
                            extra_headers={"Access-Control-Allow-Origin": "*"})
        elif path == "/health":
            self._serve(200, "application/json",
                        json.dumps({"status": "ok", "time": datetime.now().isoformat()}).encode())
        else:
            self._serve(404, "text/plain", b"Not found")

    def _serve(self, code, content_type, body, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        msg = args[0] if args else ""
        if "/focus/state" in msg or "/ai_advisor/" in msg:
            return
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")


def auto_refresh():
    fetcher = os.path.join(BASE_DIR, "core", "signal_engine.py")
    while True:
        time.sleep(300)
        try:
            subprocess.run([sys.executable, fetcher, "--once"], timeout=90, cwd=BASE_DIR)
            print(f"  [Auto Refresh] {datetime.now().strftime('%H:%M:%S')} done")
        except Exception as e:
            print(f"  [Auto Refresh] failed: {e}")


def main():
    lan_ip = get_lan_ip()
    print(f"""
  MagicQuant 慧投 Dashboard v0.3.5
  
  本机访问:
    主面板:  http://localhost:{DASHBOARD_PORT}
    丈人版:  http://localhost:{DASHBOARD_PORT}/focus
  
  局域网访问(丈人 iPad/电脑):
    主面板:  http://{lan_ip}:{DASHBOARD_PORT}
    丈人版:  http://{lan_ip}:{DASHBOARD_PORT}/focus
  
  API:
    GET /focus/state          - 实时盯盘状态
    GET /ai_advisor/latest    - 最新 AI 建议
    GET /ai_advisor/history   - 历史记录
    GET /ai_advisor/cost      - 今日成本
  
  Ctrl+C to stop
    """)
    threading.Thread(target=auto_refresh, daemon=True).start()
    server = HTTPServer(("0.0.0.0", DASHBOARD_PORT), Handler)
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{DASHBOARD_PORT}/focus")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard server stopped.")


if __name__ == "__main__":
    main()
