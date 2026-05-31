"""
MagicQuant frozen experiment guard.
VERSION : v1.0.0
DEPENDS : argparse, dataclasses, hashlib, json, pathlib, typing, config.settings

Purpose / 用途:
Detect changes to frozen strategy, scoring, and benchmark inputs during Trial.
Trial 期间检测策略、评分和 benchmark 输入是否变化。
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, List


STRATEGY_FILES = ("core/arena/roster.py", "core/arena/strategy_catalog.py", "core/arena/ensemble.py")
SCORING_FILES = ("core/arena/fitness.py", "core/arena/validation.py")
BENCHMARK_FILES = ("trial/arena_trial_controller.py",)


@dataclass(frozen=True)
class FrozenManifest:
    """Frozen experiment hash manifest. / 冻结实验 hash 清单。"""

    strategy_hash: str
    scoring_hash: str
    benchmark_hash: str


@dataclass(frozen=True)
class GuardResult:
    """Frozen guard check result. / 冻结守卫检查结果。"""

    allowed_for_official_stats: bool
    warnings: tuple[str, ...]
    current_manifest: FrozenManifest


def _base_dir() -> Path:
    from config.settings import BASE_DIR

    return Path(BASE_DIR)


def default_manifest_path() -> Path:
    return _base_dir() / "data" / "experiment" / "frozen_manifest.json"


def default_report_path() -> Path:
    return _base_dir() / "reports" / "trial" / "frozen_guard_report.md"


def _hash_files(paths: Iterable[str]) -> str:
    digest = hashlib.sha256()
    base = _base_dir()
    for rel_path in sorted(paths):
        path = base / rel_path
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes() if path.exists() else b"__MISSING__")
    return digest.hexdigest()


def build_manifest() -> FrozenManifest:
    """Build current frozen hashes. / 构建当前冻结 hash。"""

    return FrozenManifest(
        strategy_hash=_hash_files(STRATEGY_FILES),
        scoring_hash=_hash_files(SCORING_FILES),
        benchmark_hash=_hash_files(BENCHMARK_FILES),
    )


def save_manifest(path: Path | None = None) -> Path:
    """Write frozen manifest. / 写入冻结清单。"""

    out = path or default_manifest_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(build_manifest()), indent=2, sort_keys=True), encoding="utf-8")
    return out


def load_manifest(path: Path | None = None) -> FrozenManifest | None:
    """Load frozen manifest if present. / 读取冻结清单。"""

    src = path or default_manifest_path()
    if not src.exists():
        return None
    return FrozenManifest(**json.loads(src.read_text(encoding="utf-8")))


def check_frozen_guard(path: Path | None = None) -> GuardResult:
    """Compare current hashes with frozen manifest. / 对比当前 hash 与冻结清单。"""

    expected = load_manifest(path)
    current = build_manifest()
    warnings: List[str] = []
    allowed = True
    if expected is None:
        warnings.append("frozen manifest missing; initialize before official Trial stats")
        allowed = False
    else:
        if current.strategy_hash != expected.strategy_hash:
            warnings.append("strategy hash changed during frozen Trial")
            allowed = False
        if current.scoring_hash != expected.scoring_hash:
            warnings.append("scoring rule hash changed during frozen Trial")
            allowed = False
        if current.benchmark_hash != expected.benchmark_hash:
            warnings.append("benchmark config hash changed during frozen Trial")
            allowed = False
    return GuardResult(allowed, tuple(warnings), current)


def render_guard_report(result: GuardResult) -> str:
    """Render frozen guard report. / 生成冻结守卫报告。"""

    lines = [
        "# Frozen Guard Report",
        "",
        f"Allowed For Official Stats: {result.allowed_for_official_stats}",
        "",
        "Current Hashes:",
        f"- Strategy: {result.current_manifest.strategy_hash}",
        f"- Scoring: {result.current_manifest.scoring_hash}",
        f"- Benchmark: {result.current_manifest.benchmark_hash}",
        "",
        "Warnings:",
    ]
    lines.extend(f"- {warning}" for warning in result.warnings) if result.warnings else lines.append("- none")
    return "\n".join(lines) + "\n"


def write_guard_report(result: GuardResult, path: Path | None = None) -> Path:
    """Write reports/trial/frozen_guard_report.md. / 写入冻结守卫报告。"""

    out = path or default_report_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_guard_report(result), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen Experiment Guard")
    parser.add_argument("--init", action="store_true", help="Write current frozen manifest.")
    args = parser.parse_args()
    if args.init:
        path = save_manifest()
        print(f"[frozen_guard] initialized {path}")
        return 0
    result = check_frozen_guard()
    write_guard_report(result)
    print(f"[frozen_guard] allowed={result.allowed_for_official_stats}")
    return 0 if result.allowed_for_official_stats else 2


if __name__ == "__main__":
    raise SystemExit(main())
