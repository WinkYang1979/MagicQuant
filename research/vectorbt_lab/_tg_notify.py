"""
MagicQuant _tg_notify.py
VERSION : v0.1.0
DEPENDS : config.settings, requests

Independent Telegram helper for vectorbt research scheduler.
独立研究调度器 Telegram 辅助函数，不导入实盘 bot/core 模块。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_token_chat(chat_id_env: str = "TG_CHAT_ID", fallback_chat_id_env: str | None = None) -> tuple[str, str]:
    token = os.environ.get("TG_BOT_TOKEN", "")
    chat_id = os.environ.get(chat_id_env, "")
    fallback_chat_id = os.environ.get(fallback_chat_id_env or "", "") if fallback_chat_id_env else ""
    if token and chat_id:
        return token, chat_id
    try:
        from config import settings

        loaded_token = token or getattr(settings, "TG_BOT_TOKEN", "")
        # settings import loads .env into os.environ; reread env-specific chat after import.
        # settings 导入会把 .env 写入 os.environ；这里必须重新读取复盘专用 chat id。
        env_chat_after_settings = os.environ.get(chat_id_env, "")
        env_fallback_after_settings = os.environ.get(fallback_chat_id_env or "", "") if fallback_chat_id_env else ""
        loaded_chat = chat_id or env_chat_after_settings or getattr(settings, chat_id_env, "") or fallback_chat_id or env_fallback_after_settings
        if not loaded_chat and fallback_chat_id_env:
            loaded_chat = getattr(settings, fallback_chat_id_env, "")
        return loaded_token, loaded_chat
    except Exception:
        return token, chat_id or fallback_chat_id


def send(text: str, chat_id_env: str = "TG_CHAT_ID", fallback_chat_id_env: str | None = None) -> bool:
    """Best-effort Telegram send. / 尽力发送，失败不影响调度器。"""
    token, chat_id = _load_token_chat(chat_id_env=chat_id_env, fallback_chat_id_env=fallback_chat_id_env)
    if not token or not chat_id:
        print("[tg] skipped: missing TG_BOT_TOKEN/TG_CHAT_ID")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if resp.status_code >= 400:
            print(f"[tg] failed: {resp.status_code} {resp.text[:200]}")
            return False
        return True
    except Exception as exc:
        print(f"[tg] exception: {exc}")
        return False


def send_review(text: str) -> bool:
    """Send daily review to personal review chat first. / Send to TG_REVIEW_CHAT_ID first."""
    return send(text, chat_id_env="TG_REVIEW_CHAT_ID", fallback_chat_id_env="TG_CHAT_ID")
