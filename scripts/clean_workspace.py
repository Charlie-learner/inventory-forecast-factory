"""Safely remove reproducible local artifacts without touching source or user data."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT_NAMES = {
    ".coverage",
    ".pytest_cache",
    ".ruff_cache",
    "artifacts",
    "inventory_capability_factory.egg-info",
    "tmp",
}
PROTECTED_TREES = {".git", ".uv-cache", ".venv", "data", "examples"}


def _inside(root: Path, candidate: Path) -> bool:
    """Return whether a resolved candidate is a descendant of the workspace."""

    return candidate == root or root in candidate.parents


def collect_targets(root: Path) -> list[Path]:
    """Collect only known generated paths under a resolved workspace."""

    root = root.resolve()
    targets = [root / name for name in GENERATED_ROOT_NAMES if (root / name).exists()]
    for current, directories, _ in os.walk(root, topdown=True):
        current_path = Path(current)
        if current_path == root:
            directories[:] = [
                name for name in directories if name not in PROTECTED_TREES
            ]
        if "__pycache__" in directories:
            targets.append(current_path / "__pycache__")
            directories.remove("__pycache__")
    resolved_targets = sorted(
        {target.resolve() for target in targets}, key=lambda path: str(path).lower()
    )
    if not all(_inside(root, target) and target != root for target in resolved_targets):
        raise RuntimeError("refusing to clean a path outside the workspace")
    return resolved_targets


def clean(root: Path, *, apply: bool) -> list[Path]:
    """List or remove generated targets; dry-run is the safe default."""

    targets = collect_targets(root)
    if not apply:
        return targets
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="清理缓存、测试临时目录和运行时 artifacts；不会删除 data、examples 或虚拟环境。"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际删除；不传时只预览将被清理的路径。",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    targets = clean(root, apply=args.apply)
    action = "已清理" if args.apply else "将清理"
    for target in targets:
        print(f"{action}: {target.relative_to(root)}")
    if not targets:
        print("工作区已整洁，没有可清理的运行产物。")
    elif not args.apply:
        print("这是预览；确认后追加 --apply。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
