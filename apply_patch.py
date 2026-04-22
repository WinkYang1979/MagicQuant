"""
v0.3.6 patch 应用器 — 自动给 bot_controller.py 打补丁

做 3 件事:
  1. 在 focus import 区增加 HAS_MANUAL_CONSULT / manual_consult
  2. 在 ai_advise_status 指令后面插入 /ai_test 指令
  3. 在 help 文本里增加 /ai_test 一行

策略:
  - 幂等(重复跑不会重复插入)
  - 自动备份原文件到 .bak
  - 失败回滚
"""

import os
import sys
import shutil
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BOT_CONTROLLER = BASE_DIR / "bot" / "bot_controller.py"


# ── 要插入的三段代码 ─────────────────────────────────────────

# Patch 1: focus 模块 import 增加 manual_consult
IMPORT_ANCHOR = """        set_ai_advise,
        is_ai_advise_enabled,
        HAS_AI_ADVISOR,
    )"""

IMPORT_REPLACEMENT = """        set_ai_advise,
        is_ai_advise_enabled,
        HAS_AI_ADVISOR,
    )
    # v0.3.6: 手动召集智囊团
    try:
        from core.focus import manual_consult, HAS_MANUAL_CONSULT
    except ImportError:
        HAS_MANUAL_CONSULT = False"""


# Patch 2: 在 ai_advise_status 后面插入 /ai_test 指令
CMD_ANCHOR = '''    if cmd == "ai_advise_status":
        if not HAS_AI_ADVISOR:
            return "❌ AI 智囊团模块未加载"
        enabled = is_ai_advise_enabled()
        return (
            f"🤖 AI 智囊团状态: {'✅ 开启' if enabled else '⏸️ 关闭'}\\n"
            f"\\n"
            f"当开启时,Focus 每次触发会:\\n"
            f"  1. 并行调用 Haiku/DeepSeek/GPT-5 顾问\\n"
            f"  2. Opus Leader 汇总决策\\n"
            f"  3. 推送最终建议到 TG\\n"
            f"\\n"
            f"每次花费约 $0.04,一晚 20 次触发 ≈ $0.80"
        )'''

CMD_INSERT = '''

    # ── v0.3.6: 手动召集智囊团 ──────────────────────────
    if cmd == "ai_test":
        if not HAS_MANUAL_CONSULT:
            return "❌ 手动召集模块未加载 (core/focus/manual_consult.py)"
        if not HAS_FOCUS:
            return "❌ Focus 模块未加载"
        try:
            from core.focus.focus_manager import (
                _current_session, _indicators_cache_global,
            )
        except ImportError:
            return "❌ 无法读取 Focus session 状态"

        if _current_session is None or not _current_session.active:
            return (
                "⚠️ 当前没有运行中的 Focus 盯盘\\n"
                "请先 /focus 启动盯盘,再用 /ai_test 召集智囊团.\\n\\n"
                "💡 /ai_test 不受触发器限制,随时可用"
            )

        reason = " ".join(args) if args else "主动询问 AI 意见"
        send_tg("🤖 正在召集 AI 智囊团...约 20 秒\\n三位顾问 + Opus Leader 并行思考中")

        try:
            result = manual_consult(
                session=_current_session,
                indicators_cache=_indicators_cache_global,
                reason=reason,
                send_tg_fn=send_tg,
            )
            if result.get("error"):
                return f"❌ {result['error']}"
            return None   # 已经由 manual_consult 内部推送
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"❌ 召集失败: {str(e)[:150]}"'''


# Patch 3: help 文本里增加 /ai_test 说明
HELP_ANCHOR = '''        "🤖 AI 智囊团(Focus 触发时咨询)\\n"
        "/ai_advise_on      开启智囊团(默认开)\\n"
        "/ai_advise_off     关闭智囊团\\n"
        "/ai_advise_status  查看状态\\n\\n"'''

HELP_REPLACEMENT = '''        "🤖 AI 智囊团(Focus 触发时咨询)\\n"
        "/ai_advise_on      开启智囊团(默认开)\\n"
        "/ai_advise_off     关闭智囊团\\n"
        "/ai_advise_status  查看状态\\n"
        "/ai_test [原因]    🆕 手动召集(不等触发)\\n\\n"'''


# ── 应用 patch ──────────────────────────────────────────────

def apply_patch():
    if not BOT_CONTROLLER.exists():
        print(f"❌ 找不到 {BOT_CONTROLLER}")
        print("   请确认 patch 包解压到 C:\\MagicQuant\\ 根目录")
        return False

    # 读原文
    original = BOT_CONTROLLER.read_text(encoding="utf-8")
    modified = original

    # 备份
    backup = BOT_CONTROLLER.with_suffix(".py.v035.bak")
    if not backup.exists():
        shutil.copy(BOT_CONTROLLER, backup)
        print(f"✅ 已备份: {backup.name}")
    else:
        print(f"ℹ️  备份已存在(保留): {backup.name}")

    # Patch 1: import
    if "HAS_MANUAL_CONSULT" in modified:
        print("ℹ️  Patch 1 (import) 已应用,跳过")
    else:
        if IMPORT_ANCHOR not in modified:
            print("⚠️  Patch 1 锚点未找到,可能 bot_controller.py 版本不对")
            print("    跳过 Patch 1")
        else:
            modified = modified.replace(IMPORT_ANCHOR, IMPORT_REPLACEMENT, 1)
            print("✅ Patch 1: import 完成")

    # Patch 2: 指令
    if 'cmd == "ai_test"' in modified:
        print("ℹ️  Patch 2 (/ai_test 指令) 已应用,跳过")
    else:
        if CMD_ANCHOR not in modified:
            print("⚠️  Patch 2 锚点未找到")
            print("    你的 ai_advise_status 指令可能已被修改,跳过")
        else:
            modified = modified.replace(CMD_ANCHOR, CMD_ANCHOR + CMD_INSERT, 1)
            print("✅ Patch 2: /ai_test 指令完成")

    # Patch 3: help
    if "/ai_test [原因]" in modified:
        print("ℹ️  Patch 3 (help) 已应用,跳过")
    else:
        if HELP_ANCHOR not in modified:
            print("⚠️  Patch 3 锚点未找到,help 文本可能被修改过,跳过")
        else:
            modified = modified.replace(HELP_ANCHOR, HELP_REPLACEMENT, 1)
            print("✅ Patch 3: help 完成")

    # 写回
    if modified != original:
        BOT_CONTROLLER.write_text(modified, encoding="utf-8")
        print(f"\n✅ bot_controller.py 已更新 ({len(modified) - len(original):+d} 字符)")
    else:
        print("\nℹ️  无需修改(全部已应用)")

    return True


def rollback():
    backup = BOT_CONTROLLER.with_suffix(".py.v035.bak")
    if not backup.exists():
        print(f"❌ 没有备份文件 {backup}")
        return False
    shutil.copy(backup, BOT_CONTROLLER)
    print(f"✅ 已回滚 bot_controller.py 到 v0.3.5 状态")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        ok = apply_patch()
        sys.exit(0 if ok else 1)
