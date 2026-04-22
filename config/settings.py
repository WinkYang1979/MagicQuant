"""
MagicQuant 慧投 — 全局配置
Dare to dream. Data to win.

说明：所有配置集中在此文件，修改后重启相关服务生效。
v0.2.1: 凭证迁移到 .env，不再明文硬编码
"""
import os
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
#  加载 .env 凭证（不依赖 python-dotenv，手写避免增加依赖）
# ══════════════════════════════════════════════════════════════════
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
print(f"🔍 .env 路径: {_ENV_FILE}  存在: {_ENV_FILE.exists()}")
if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def _load_env(name: str, default: str = "", required: bool = False) -> str:
    """从环境变量读取，缺失时友好提示"""
    v = os.environ.get(name, default)
    if required and not v:
        print(f"⚠️  缺失凭证: {name}（请检查 .env 文件）")
    return v

# ── Futu / Moomoo OpenD ──────────────────────────────────────────
FUTU_HOST = "127.0.0.1"
FUTU_PORT = 11111

# ── 账户配置 ─────────────────────────────────────────────────────
ACCOUNT_SIZE  = 20000   # 账户规模（用于仓位计算），请根据实际更新
MAX_RISK_PCT  = 0.05    # 每笔最大风险比例 5%
PDT_LIMIT     = 3       # PDT 限制次数（账户 < $25k 为 3）

# ── 语言设置 / Language ──────────────────────────────────────────
# "zh" = 中文（默认）  |  "en" = English
LANGUAGE = "zh"

# ══════════════════════════════════════════════════════════════════
#  凭证（从 .env 加载，不再明文）
# ══════════════════════════════════════════════════════════════════

# ── Telegram ─────────────────────────────────────────────────────
TG_BOT_TOKEN = _load_env("TG_BOT_TOKEN", required=True)
TG_CHAT_ID   = _load_env("TG_CHAT_ID",   required=True)

# ── Claude API（用于 /detail AI 分析） ────────────────────────────
CLAUDE_API_KEY   = _load_env("CLAUDE_API_KEY")
CLAUDE_MODEL     = "claude-sonnet-4-6"
CLAUDE_PRICE_IN  = 3.00  / 1_000_000
CLAUDE_PRICE_OUT = 15.00 / 1_000_000

# ── OpenAI API（用于 /detail 对比分析） ──────────────────────────
OPENAI_API_KEY   = _load_env("OPENAI_API_KEY")
OPENAI_MODEL     = "gpt-4o"
OPENAI_PRICE_IN  = 0.15 / 1_000_000
OPENAI_PRICE_OUT = 0.60 / 1_000_000

# ══════════════════════════════════════════════════════════════════
#  非敏感配置（保留在代码中）
# ══════════════════════════════════════════════════════════════════

# ── 默认跟踪股票 ─────────────────────────────────────────────────
DEFAULT_WATCHLIST = [
    "US.RKLB",
    "US.RKLX",
    "US.TSLA",
    "US.SOXL",
]

# ── 股票交易风格配置 ──────────────────────────────────────────────
TICKER_CONFIG = {
    "US.TSLA": {"name": "Tesla",         "style": "swing"},
    "US.SOXL": {"name": "SOXL 3x Semi",  "style": "daytrader"},
    "US.RKLB": {"name": "Rocket Lab",     "style": "daytrader"},
    "US.RKLX": {"name": "RocketLab CFD",  "style": "daytrader"},
}

# ── 定时推送时间（本地时间 HH:MM）─────────────────────────────────
PUSH_TIMES = ["09:00", "21:30", "22:30", "23:30", "01:00"]

# ── 技术指标参数 ─────────────────────────────────────────────────
RSI_PERIOD  = 14
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9
BB_PERIOD   = 20
BB_STD      = 2
KL_NUM      = 90

# ── 路径配置 ─────────────────────────────────────────────────────
BASE_DIR      = r"C:\MagicQuant"
DATA_DIR      = os.path.join(BASE_DIR, "data")
CONFIG_DIR    = os.path.join(BASE_DIR, "config")
LOG_DIR       = os.path.join(BASE_DIR, "logs")

SIGNALS_FILE    = os.path.join(DATA_DIR, "signals_latest.json")
ACCOUNT_FILE    = os.path.join(DATA_DIR, "account_data.json")
WATCHLIST_FILE  = os.path.join(CONFIG_DIR, "watchlist.json")
STATEMENTS_DIR  = os.path.join(DATA_DIR, "statements")   # 对账单存储目录
LOG_FILE        = os.path.join(LOG_DIR, "magicquant.log")

# ── 服务端口 ─────────────────────────────────────────────────────
DASHBOARD_PORT = 5000
