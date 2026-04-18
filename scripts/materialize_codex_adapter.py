"""Sync the repo-stored Codex adapter source into a target adapter directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

COMPONENT_CHOICES = ("all", "agents", "hooks", "config")


def source_dir(root: Path) -> Path:
    return root / ".orchestration" / "codex"


def target_dir(root: Path, target: str | None) -> Path:
    return (root / target).resolve() if target else (root / ".codex").resolve()


def matches_component(relative: Path, component: str) -> bool:
    if component == "all":
        return True
    if component == "config":
        return relative.parts == ("config.toml",)
    return bool(relative.parts) and relative.parts[0] == component


def plan_install(root: Path, target: Path, component: str = "all") -> list[tuple[Path, Path]]:
    source = source_dir(root)
    if not source.is_dir():
        raise FileNotFoundError(f"missing Codex adapter source: {source}")

    operations: list[tuple[Path, Path]] = []
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(source)
        if not matches_component(relative, component):
            continue
        operations.append((path, target / relative))
    return operations


def ensure_target_writable(target: Path) -> None:
    if target.exists() and not target.is_dir():
        raise ValueError(f"target exists but is not a directory: {target}")
    target.mkdir(parents=True, exist_ok=True)


def install(
    root: Path,
    target: Path,
    dry_run: bool,
    component: str = "all",
) -> list[tuple[Path, Path]]:
    operations = plan_install(root, target, component=component)
    if dry_run:
        return operations

    ensure_target_writable(target)
    for src, dst in operations:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return operations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync the repo Codex adapter source.")
    parser.add_argument("--root", default=".", help="Project root. Defaults to the current directory.")
    parser.add_argument("--target", help="Target adapter directory. Defaults to <root>/.codex.")
    parser.add_argument(
        "--component",
        choices=COMPONENT_CHOICES,
        default="all",
        help="Only install one top-level adapter component. Defaults to all.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    target = target_dir(root, args.target)
    operations = install(root, target, args.dry_run, component=args.component)
    for src, dst in operations:
        print(f"{src.relative_to(root)} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
