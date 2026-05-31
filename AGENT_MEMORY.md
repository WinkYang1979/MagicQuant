# MagicQuant Agent Memory Entry

VERSION: v0.1.0  
DEPENDS: docs/AGENT_MEMORY.md, docs/PROJECT_MEMORY_INDEX.md

Before making MagicQuant code or strategy changes, read:

1. `docs/AGENT_MEMORY.md`
2. `docs/PROJECT_MEMORY_INDEX.md`
3. `docs/STRATEGY_SCORECARD.md` when the change touches strategy behavior

This root file exists so future AI agents can quickly find the project memory system.

Core reminder:

- Fix confirmed bugs directly.
- Discuss strategy changes first unless explicitly approved.
- Replay prior logs before accepting strategy changes.
- Keep research code isolated from live trading code unless the user explicitly asks to promote it.
- Never store secrets in memory files.
