"""
MagicQuant — AI Provider 连通性测试
独立脚本,一键验证所有 AI 是否都能正常响应.

用法:
  cd C:\\MagicQuant
  python test_ai_providers.py

测试内容:
  1. .env 文件是否存在且加载正常
  2. 每个 API Key 是否配置
  3. 每个 AI 是否能正常调用(真实 API 调用, 花钱但很少)
  4. 每个 AI 响应时间 + token 消耗 + 估算成本
  5. 汇总报告
"""

import os
import sys
import time
import json
from pathlib import Path

# 让脚本从项目根目录运行
BASE_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BASE_DIR))

# 加载 .env
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
    print(f"✅ 加载 .env: {ENV_FILE}")
else:
    print(f"❌ 找不到 .env 文件: {ENV_FILE}")
    sys.exit(1)

print()
print("=" * 70)
print("  MagicQuant AI 连通性测试 v1.0")
print("=" * 70)
print()

# 导入 provider
try:
    from core.agents.providers import (
        ClaudeOpusProvider, ClaudeHaikuProvider,
        OpenAIProvider, DeepSeekProvider, KimiProvider,
    )
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print(f"   请确保 core/agents/ 目录下有所有文件")
    sys.exit(1)


# ── 测试配置 ──────────────────────────────────────────
TEST_SYSTEM = "你是一个简洁的助手,用 20 字以内回复."
TEST_USER   = "RKLB 现价$89, RSI=72, 流星线, 该买该卖? 一句话."


# ── Provider 清单 ─────────────────────────────────────
providers_to_test = [
    ("ANTHROPIC_API_KEY", "Claude Opus 4.7",  ClaudeOpusProvider),
    ("ANTHROPIC_API_KEY", "Claude Haiku 4.5", ClaudeHaikuProvider),
    ("OPENAI_API_KEY",    "GPT-5",            OpenAIProvider),
    ("DEEPSEEK_API_KEY",  "DeepSeek V3",      DeepSeekProvider),
    ("MOONSHOT_API_KEY",  "Kimi K2",          KimiProvider),
]


# ── Step 1: 检查 Key ──────────────────────────────────
print("─" * 70)
print("📋 Step 1: 检查 API Key 配置")
print("─" * 70)

configured = []
missing = []
for env_var, name, cls in providers_to_test:
    key = os.environ.get(env_var) or os.environ.get(
        "KIMI_API_KEY" if env_var == "MOONSHOT_API_KEY" else ""
    )
    if key:
        # 显示 key 前 7 位 + **** + 后 4 位
        masked = key[:7] + "*" * 10 + key[-4:] if len(key) > 15 else "***"
        print(f"  ✅ {name:22s} key={masked}")
        configured.append((env_var, name, cls, key))
    else:
        print(f"  ❌ {name:22s} 未配置 (环境变量 {env_var})")
        missing.append(name)

print()
print(f"  已配置: {len(configured)} / {len(providers_to_test)}")
if missing:
    print(f"  未配置: {', '.join(missing)}")

if not configured:
    print()
    print("❌ 没有任何 API Key,无法继续测试")
    sys.exit(1)

print()

# ── Step 2: 逐个测试调用 ──────────────────────────────
print("─" * 70)
print("🧪 Step 2: 发送真实 API 请求 (每个 AI 约 $0.001-$0.02)")
print("─" * 70)
print()
print(f"系统 prompt: {TEST_SYSTEM}")
print(f"用户 prompt: {TEST_USER}")
print()

results = []

for env_var, name, cls, key in configured:
    print(f"  ⏳ 测试 {name} ...", end=" ", flush=True)
    t0 = time.time()
    try:
        provider = cls(key)
        result = provider.call(TEST_SYSTEM, TEST_USER, max_tokens=100, timeout=20)
        elapsed_s = time.time() - t0
        
        if result.get("error"):
            print(f"❌ 错误")
            print(f"     错误: {result['error']}")
            results.append({
                "name": name, "ok": False, 
                "error": result["error"], "time": elapsed_s,
            })
        else:
            tokens = result["input_tokens"] + result["output_tokens"]
            cost = result["cost_usd"]
            text = result["text"].strip()[:60]
            print(f"✅ {elapsed_s:.1f}s  {tokens} tok  ${cost:.4f}")
            print(f"     回复: {text}{'...' if len(result['text']) > 60 else ''}")
            results.append({
                "name": name, "ok": True,
                "time": elapsed_s, "tokens": tokens, "cost": cost,
                "text": result["text"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            })
    except Exception as e:
        elapsed_s = time.time() - t0
        print(f"❌ 异常")
        print(f"     异常: {str(e)[:150]}")
        results.append({"name": name, "ok": False, "error": str(e), "time": elapsed_s})
    print()


# ── Step 3: 汇总 ──────────────────────────────────────
print("─" * 70)
print("📊 Step 3: 总结")
print("─" * 70)
print()

ok_count = sum(1 for r in results if r["ok"])
total_cost = sum(r.get("cost", 0) for r in results if r["ok"])
total_tokens = sum(r.get("tokens", 0) for r in results if r["ok"])

print(f"  通过: {ok_count} / {len(results)}")
print(f"  失败: {len(results) - ok_count}")
print(f"  本次测试总花费: ${total_cost:.4f} ({total_tokens} tokens)")
print()

if ok_count >= 2:
    # 估算晚上赛马成本
    # 假设每轮 2000 input + 500 output tokens
    rounds_per_night = 130   # 6.5 小时 × 20 轮/小时
    avg_cost = total_cost / ok_count if ok_count > 0 else 0
    est_night = avg_cost * rounds_per_night
    print(f"  🌙 预估今晚成本 (180秒/轮,~130轮): ${est_night:.2f} ~ ${est_night * 2:.2f}")
    print()

# 按成功/失败分组
if ok_count > 0:
    print("  ✅ 已接通的 AI:")
    for r in results:
        if r["ok"]:
            print(f"     • {r['name']:22s} {r['time']:.1f}s · {r.get('tokens', 0)} tok · ${r.get('cost', 0):.4f}")
    print()

if any(not r["ok"] for r in results):
    print("  ❌ 未接通的 AI:")
    for r in results:
        if not r["ok"]:
            err = r.get("error", "unknown")[:80]
            print(f"     • {r['name']:22s} {err}")
    print()

# ── Step 4: 综合判断 ──────────────────────────────────
print("─" * 70)
print("🎯 Step 4: 是否可以启动 /race?")
print("─" * 70)
print()

if ok_count >= 2:
    print(f"  ✅ 有 {ok_count} 个 AI 可用,可以启动 AI 大赛!")
    print()
    print(f"  Telegram 输入:")
    print(f"     /race_providers   # 查看可用 AI")
    print(f"     /race             # 启动大赛")
    sys.exit(0)
elif ok_count == 1:
    print(f"  ⚠️  只有 1 个 AI 可用,赛马没意义")
    print(f"     建议检查其他 AI 的 key 或重试")
    sys.exit(1)
else:
    print(f"  ❌ 没有可用 AI,无法启动赛马")
    print(f"     请检查 .env 文件和 API key 是否正确")
    sys.exit(1)
