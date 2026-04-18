"""Configure repo-local defaults such as Git hooksPath."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def configure_hooks(root: Path) -> list[str]:
    hooks_dir = root / ".githooks"
    if not hooks_dir.exists():
        raise FileNotFoundError(f"missing hooks directory: {hooks_dir}")
    hook_path = hooks_dir / "pre-commit"
    if hook_path.exists():
        hook_path.chmod(hook_path.stat().st_mode | 0o111)
    subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=root,
        check=True,
    )
    return ["core.hooksPath=.githooks"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure repo-local shared control-plane defaults.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes only.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    hooks_dir = root / ".githooks"
    if not hooks_dir.exists():
        raise FileNotFoundError(f"missing hooks directory: {hooks_dir}")
    if args.dry_run:
        print("core.hooksPath=.githooks")
        return 0
    for item in configure_hooks(root):
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
