"""
MagicQuant — AI Provider 统一接口
支持 Claude / OpenAI / DeepSeek / Kimi
"""

import os
import json
import time
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from typing import Optional


class AIProvider(ABC):
    """AI 统一接口基类"""
    
    name = "base"           # AI 名称
    display_name = "Base"   # 显示名
    
    # 价格(USD per 1M tokens),子类覆盖
    price_input_per_m  = 0.0
    price_output_per_m = 0.0
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.total_calls = 0
        self.total_cost = 0.0
        self.total_tokens = 0
    
    @abstractmethod
    def call(self, system_prompt: str, user_prompt: str,
             max_tokens: int = 500, timeout: int = 30) -> dict:
        """
        调用 AI,返回:
        {
          "text": "AI 回复文本",
          "input_tokens": int,
          "output_tokens": int,
          "cost_usd": float,
          "duration_ms": int,
          "error": str or None
        }
        """
        pass
    
    def calc_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens  / 1_000_000 * self.price_input_per_m +
            output_tokens / 1_000_000 * self.price_output_per_m
        )
    
    def record(self, result: dict):
        """统计"""
        self.total_calls += 1
        self.total_cost += result.get("cost_usd", 0)
        self.total_tokens += (result.get("input_tokens", 0) + result.get("output_tokens", 0))


# ══════════════════════════════════════════════════════════════════
#  Claude (Anthropic)
# ══════════════════════════════════════════════════════════════════

class ClaudeOpusProvider(AIProvider):
    name = "claude_opus"
    display_name = "Claude Opus 4.7"
    price_input_per_m  = 5.0
    price_output_per_m = 25.0
    
    def call(self, system_prompt: str, user_prompt: str,
             max_tokens: int = 500, timeout: int = 30) -> dict:
        t0 = time.time()
        try:
            payload = json.dumps({
                "model": "claude-opus-4-7",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            
            text = data["content"][0]["text"]
            usage = data.get("usage", {})
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            cost = self.calc_cost(in_tok, out_tok)
            result = {
                "text": text,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": cost,
                "duration_ms": int((time.time() - t0) * 1000),
                "error": None,
            }
            self.record(result)
            return result
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"  [{self.display_name}] {err_msg}")
            return {
                "text": "",
                "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0,
                "duration_ms": int((time.time() - t0) * 1000),
                "error": err_msg[:200],
            }


class ClaudeHaikuProvider(ClaudeOpusProvider):
    name = "claude_haiku"
    display_name = "Claude Haiku 4.5"
    price_input_per_m  = 1.0
    price_output_per_m = 5.0
    
    def call(self, system_prompt: str, user_prompt: str,
             max_tokens: int = 500, timeout: int = 30) -> dict:
        t0 = time.time()
        try:
            payload = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            text = data["content"][0]["text"]
            usage = data.get("usage", {})
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            cost = self.calc_cost(in_tok, out_tok)
            result = {
                "text": text, "input_tokens": in_tok, "output_tokens": out_tok,
                "cost_usd": cost,
                "duration_ms": int((time.time() - t0) * 1000),
                "error": None,
            }
            self.record(result)
            return result
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"  [{self.display_name}] {err_msg}")
            return {"text": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0, "duration_ms": int((time.time() - t0) * 1000),
                    "error": err_msg[:200]}


# ══════════════════════════════════════════════════════════════════
#  OpenAI GPT-5
# ══════════════════════════════════════════════════════════════════

class OpenAIProvider(AIProvider):
    name = "gpt_5"
    display_name = "GPT-5.4"
    price_input_per_m  = 2.5
    price_output_per_m = 15.0
    
    def call(self, system_prompt: str, user_prompt: str,
             max_tokens: int = 500, timeout: int = 30) -> dict:
        t0 = time.time()
        try:
            # v0.4 修复:
            # 1) 模型从 gpt-5 升到 gpt-5.4-mini(当前主流,便宜快)
            # 2) max_tokens 在 GPT-5 系列不支持,必须用 max_completion_tokens
            # 3) GPT-5 是 reasoning model,留足预算给 reasoning tokens
            payload = json.dumps({
                "model": "gpt-5.4-mini",
                "max_completion_tokens": max(max_tokens * 4, 2000),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            }).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            in_tok = usage.get("prompt_tokens", 0)
            out_tok = usage.get("completion_tokens", 0)
            cost = self.calc_cost(in_tok, out_tok)
            result = {
                "text": text, "input_tokens": in_tok, "output_tokens": out_tok,
                "cost_usd": cost,
                "duration_ms": int((time.time() - t0) * 1000),
                "error": None,
            }
            self.record(result)
            return result
        except urllib.error.HTTPError as e:
            # HTTP 错误(400/401/429/500 等)读取响应体,打印完整错误
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except:
                pass
            err_msg = f"HTTP {e.code}: {err_body}"
            print(f"  [OpenAI] {err_msg}")
            return {"text": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0, "duration_ms": int((time.time() - t0) * 1000),
                    "error": err_msg[:200]}
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"  [OpenAI] {err_msg}")
            return {"text": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0, "duration_ms": int((time.time() - t0) * 1000),
                    "error": err_msg[:200]}


# ══════════════════════════════════════════════════════════════════
#  DeepSeek V3
# ══════════════════════════════════════════════════════════════════

class DeepSeekProvider(AIProvider):
    name = "deepseek"
    display_name = "DeepSeek V3"
    price_input_per_m  = 0.27
    price_output_per_m = 1.10
    
    def call(self, system_prompt: str, user_prompt: str,
             max_tokens: int = 500, timeout: int = 30) -> dict:
        t0 = time.time()
        try:
            payload = json.dumps({
                "model": "deepseek-chat",
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            }).encode()
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            in_tok = usage.get("prompt_tokens", 0)
            out_tok = usage.get("completion_tokens", 0)
            cost = self.calc_cost(in_tok, out_tok)
            result = {
                "text": text, "input_tokens": in_tok, "output_tokens": out_tok,
                "cost_usd": cost,
                "duration_ms": int((time.time() - t0) * 1000),
                "error": None,
            }
            self.record(result)
            return result
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"  [{self.display_name}] {err_msg}")
            return {"text": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0, "duration_ms": int((time.time() - t0) * 1000),
                    "error": err_msg[:200]}


# ══════════════════════════════════════════════════════════════════
#  Moonshot Kimi K2
# ══════════════════════════════════════════════════════════════════

class KimiProvider(AIProvider):
    name = "kimi"
    display_name = "Kimi K2.5"
    price_input_per_m  = 0.30
    price_output_per_m = 2.00
    
    # 两个可选端点,根据 key 来源选择
    # 老杨人在墨尔本但 key 来自 platform.moonshot.cn,优先 .cn
    # moonshot 官方 FAQ: .cn 和 .ai 账号独立, key 不通用
    # 官方承认从境外访问 .cn 可能超时,因此 timeout 加大
    API_ENDPOINTS = [
        "https://api.moonshot.cn/v1/chat/completions",   # 中国大陆(人民币充值)
        "https://api.moonshot.ai/v1/chat/completions",   # 国际(美元)
    ]
    
    def call(self, system_prompt: str, user_prompt: str,
             max_tokens: int = 500, timeout: int = 60) -> dict:
        # Kimi 从境外访问 .cn 经常超时,即使调用方传了 20s,这里强制至少 45s
        timeout = max(timeout, 45)
        t0 = time.time()
        last_error = None
        
        # v0.4.1: 依次尝试两个端点(首个失败就切换)
        for endpoint in self.API_ENDPOINTS:
            try:
                payload = json.dumps({
                    "model": "kimi-k2.5",
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    # 关闭 thinking 模式:走 HTTP 直接放顶层(extra_body 只在 SDK 里才展开)
                    "thinking": {"type": "disabled"},
                }).encode()
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read())
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                in_tok = usage.get("prompt_tokens", 0)
                out_tok = usage.get("completion_tokens", 0)
                cost = self.calc_cost(in_tok, out_tok)
                result = {
                    "text": text, "input_tokens": in_tok, "output_tokens": out_tok,
                    "cost_usd": cost,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": None,
                }
                self.record(result)
                return result
            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8", errors="replace")[:200]
                except:
                    pass
                last_error = f"HTTP {e.code} @ {endpoint.split('/')[2]}: {err_body}"
                print(f"  [Kimi K2.5] {last_error}")
                # 注意: 401 不能提前 break!
                # Moonshot 的 .ai 和 .cn 是独立账号系统,key 只在其中一个有效
                # .ai 返回 401 可能意味着 key 其实是 .cn 的,要继续试
            except Exception as e:
                last_error = f"{type(e).__name__} @ {endpoint.split('/')[2]}: {str(e)[:150]}"
                print(f"  [Kimi K2.5] {last_error}")
        
        # 所有端点都失败
        return {"text": "", "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0, "duration_ms": int((time.time() - t0) * 1000),
                "error": (last_error or "all endpoints failed")[:200]}


# ══════════════════════════════════════════════════════════════════
#  Factory
# ══════════════════════════════════════════════════════════════════

def _clean_key(raw: Optional[str]) -> Optional[str]:
    """清理环境变量里的 key,过滤空值/注释/占位符"""
    if not raw:
        return None
    # 去掉行内注释
    if "#" in raw:
        raw = raw.split("#", 1)[0]
    # 去掉首尾空白和引号
    key = raw.strip().strip('"').strip("'").strip()
    # 过滤掉太短或明显是占位符的
    if len(key) < 10:
        return None
    if key.lower() in ("your_key_here", "xxx", "none", "null", "todo"):
        return None
    return key


def build_all_providers() -> dict:
    """根据环境变量里有的 API Key,构建可用的 provider.
    
    环境变量兼容性:
      Claude: ANTHROPIC_API_KEY 或 CLAUDE_API_KEY
      Kimi:   MOONSHOT_API_KEY 或 KIMI_API_KEY
    """
    providers = {}
    
    # Claude (支持两种变量名)
    anthropic_key = _clean_key(os.getenv("ANTHROPIC_API_KEY")) or _clean_key(os.getenv("CLAUDE_API_KEY"))
    if anthropic_key:
        providers["claude_opus"]  = ClaudeOpusProvider(anthropic_key)
        providers["claude_haiku"] = ClaudeHaikuProvider(anthropic_key)
    
    openai_key = _clean_key(os.getenv("OPENAI_API_KEY"))
    if openai_key:
        providers["gpt_5"] = OpenAIProvider(openai_key)
    
    deepseek_key = _clean_key(os.getenv("DEEPSEEK_API_KEY"))
    if deepseek_key:
        providers["deepseek"] = DeepSeekProvider(deepseek_key)
    
    kimi_key = _clean_key(os.getenv("MOONSHOT_API_KEY")) or _clean_key(os.getenv("KIMI_API_KEY"))
    if kimi_key:
        providers["kimi"] = KimiProvider(kimi_key)
    
    return providers
