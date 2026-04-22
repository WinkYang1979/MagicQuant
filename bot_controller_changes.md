# bot_controller.py v0.3.6 改动说明

> 如果你不想用 `apply_patch.py` 自动打补丁,可以手动在 `bot/bot_controller.py` 里做以下 3 处修改。

---

## 改动 1:import 区(约第 93 行)

**找到这段:**

```python
try:
    from core.focus import (
        start_focus as focus_start,
        stop_focus  as focus_stop,
        get_focus_status,
        is_focused,
        set_ai_advise,
        is_ai_advise_enabled,
        HAS_AI_ADVISOR,
    )
    HAS_FOCUS = True
```

**在 `)` 后面追加:**

```python
    # v0.3.6: 手动召集智囊团
    try:
        from core.focus import manual_consult, HAS_MANUAL_CONSULT
    except ImportError:
        HAS_MANUAL_CONSULT = False
```

---

## 改动 2:指令路由(约第 2320 行)

**找到这段(ai_advise_status 指令结束的地方):**

```python
    if cmd == "ai_advise_status":
        if not HAS_AI_ADVISOR:
            return "❌ AI 智囊团模块未加载"
        enabled = is_ai_advise_enabled()
        return (
            f"🤖 AI 智囊团状态: {'✅ 开启' if enabled else '⏸️ 关闭'}\n"
            ...
            f"每次花费约 $0.04,一晚 20 次触发 ≈ $0.80"
        )
```

**在它后面(紧接 `)`)追加:**

```python
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
                "⚠️ 当前没有运行中的 Focus 盯盘\n"
                "请先 /focus 启动盯盘,再用 /ai_test 召集智囊团.\n\n"
                "💡 /ai_test 不受触发器限制,随时可用"
            )

        reason = " ".join(args) if args else "主动询问 AI 意见"
        send_tg("🤖 正在召集 AI 智囊团...约 20 秒\n三位顾问 + Opus Leader 并行思考中")

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
            return f"❌ 召集失败: {str(e)[:150]}"
```

---

## 改动 3:help 文本(约第 1380 行)

**找到 cmd_help() 函数里这段:**

```python
        "🤖 AI 智囊团(Focus 触发时咨询)\n"
        "/ai_advise_on      开启智囊团(默认开)\n"
        "/ai_advise_off     关闭智囊团\n"
        "/ai_advise_status  查看状态\n\n"
```

**改为:**

```python
        "🤖 AI 智囊团(Focus 触发时咨询)\n"
        "/ai_advise_on      开启智囊团(默认开)\n"
        "/ai_advise_off     关闭智囊团\n"
        "/ai_advise_status  查看状态\n"
        "/ai_test [原因]    🆕 手动召集(不等触发)\n\n"
```

---

## 改完后

1. 保存文件
2. 关掉 bot 窗口,重启 `MagicYang.bat`
3. Telegram 发 `/ai_test` 测试

---

**强烈建议用 `apply_patch.py` 自动打补丁**,不用手动改 3 处,减少出错。
