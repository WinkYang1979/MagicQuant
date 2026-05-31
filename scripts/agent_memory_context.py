"""
MagicQuant agent_memory_context.py
VERSION : v0.1.0
DEPENDS : docs/AGENT_MEMORY.md, docs/PROJECT_MEMORY_INDEX.md, docs/STRATEGY_SCORECARD.md

Compile stable project memory into a single context file for AI agents.
把长期项目记忆编译成单一上下文文件，供 AI 开工前读取。
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BASE_DIR / ".agent_memory_context.md"
SOURCE_FILES = [
    BASE_DIR / "AGENT_MEMORY.md",
    BASE_DIR / "docs" / "AGENT_MEMORY.md",
    BASE_DIR / "docs" / "PROJECT_MEMORY_INDEX.md",
    BASE_DIR / "docs" / "STRATEGY_SCORECARD.md",
]
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*=\s*\S+"),
    re.compile(r"\b\d{9,}:[A-Za-z0-9_-]{20,}\b"),
]


def read_source(path: Path) -> str:
    if not path.exists():
        return f"> Missing: {path}\n"
    text = path.read_text(encoding="utf-8", errors="replace")
    return scrub_secrets(text)


def scrub_secrets(text: str) -> str:
    cleaned = text
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub("[REDACTED_SECRET]", cleaned)
    return cleaned


def build_context(source_files: list[Path]) -> str:
    lines = [
        "# MagicQuant Compiled Agent Memory",
        "",
        f"Generated at UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Use this as startup context only. Verify current code and data before making changes.",
        "",
    ]
    for path in source_files:
        lines += [
            "---",
            "",
            f"## Source: {path.relative_to(BASE_DIR)}",
            "",
            read_source(path).strip(),
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def parse_args():
    parser = argparse.ArgumentParser(description="Compile MagicQuant agent memory context.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output markdown path.")
    parser.add_argument("--print", action="store_true", help="Print compiled context instead of writing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = build_context(SOURCE_FILES)
    if args.print:
        print(context)
        return 0
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = BASE_DIR / out_path
    out_path.write_text(context, encoding="utf-8")
    print(f"[agent-memory] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
