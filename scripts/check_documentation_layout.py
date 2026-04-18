"""Validate repo documentation, project memory layout, and retired Claude memory placement."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SPEC_INDEX_PATHS = (("", "index.md"),)


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    _, _, rest = text.partition("---\n")
    body, marker, _ = rest.partition("\n---\n")
    if not marker:
        return {}
    payload: dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        payload[key.strip()] = value.strip()
    return payload


def path_is_listed(index_text: str, relative_path: str) -> bool:
    return relative_path in index_text


def count_listed(index_text: str, relative_path: str) -> int:
    return index_text.count(relative_path)


def count_markdown_target(index_text: str, relative_path: str) -> int:
    return index_text.count(f"({relative_path})")


def check_docs_root(index_text: str, docs_root: Path) -> list[str]:
    issues: list[str] = []
    todo_name_pattern = re.compile(r"(?:^|[-_])(todo|wip)(?:[-_.]|$)", re.IGNORECASE)
    for path in sorted(docs_root.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        frontmatter = parse_frontmatter(path)
        if frontmatter.get("status", "").lower() in {"todo", "wip"}:
            issues.append(f"{path} has status={frontmatter['status']} but is stored in docs/ root")
        if todo_name_pattern.search(path.stem):
            issues.append(f"{path} looks like a todo/wip file and should live under docs/todo/")
        if not path_is_listed(index_text, path.name):
            issues.append(f"{path} is not listed in docs/INDEX.md")
        elif count_markdown_target(index_text, path.name) > 1:
            issues.append(f"{path} is listed multiple times in docs/INDEX.md")
    return issues


def check_todo_docs(index_text: str, docs_todo: Path) -> list[str]:
    issues: list[str] = []
    for path in sorted(docs_todo.glob("*.md")):
        relative_path = f"todo/{path.name}"
        if not path_is_listed(index_text, relative_path):
            issues.append(f"{path} is not listed in docs/INDEX.md")
        elif count_markdown_target(index_text, relative_path) > 1:
            issues.append(f"{path} is listed multiple times in docs/INDEX.md")
    return issues


def check_spec_indexes(root: Path) -> list[str]:
    specs_root = root / ".orchestration" / "specs"
    issues: list[str] = []
    index_texts: dict[str, str] = {}

    for _, relative_index in SPEC_INDEX_PATHS:
        index_path = specs_root / relative_index
        if not index_path.exists():
            issues.append(f"missing spec index: {index_path}")
            index_texts[relative_index] = ""
            continue
        index_texts[relative_index] = index_path.read_text(encoding="utf-8")

    for subdir, relative_index in SPEC_INDEX_PATHS:
        directory = specs_root / subdir if subdir else specs_root
        for path in sorted(directory.glob("*.md")):
            if path.name == "index.md":
                continue
            index_path = specs_root / relative_index
            index_text = index_texts[relative_index]
            if not path_is_listed(index_text, path.name):
                issues.append(f"{path} is not listed in {index_path}")
            elif count_listed(index_text, path.name) > 1:
                issues.append(f"{path} is listed multiple times in {index_path}")
    return issues


def check_project_memory(
    memory_dir: Path,
    memory_index_text: str,
    current_index_text: str,
) -> list[str]:
    issues: list[str] = []
    for path in sorted(memory_dir.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        issues.append(f"{path} should live under memory/current/ or memory/history/")
    if not path_is_listed(memory_index_text, "current/INDEX.md"):
        issues.append(f"{memory_dir / 'INDEX.md'} is missing current/INDEX.md")
    if not path_is_listed(memory_index_text, "history/README.md"):
        issues.append(f"{memory_dir / 'INDEX.md'} is missing history/README.md")
    current_dir = memory_dir / "current"
    for path in sorted(current_dir.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        if not path_is_listed(current_index_text, path.name):
            issues.append(f"{path} is not listed in memory/current/INDEX.md")
    return issues


def check_required_memory_paths(memory_dir: Path) -> list[str]:
    issues: list[str] = []
    current_dir = memory_dir / "current"
    history_dir = memory_dir / "history"
    current_index = current_dir / "INDEX.md"
    history_readme = history_dir / "README.md"
    if not current_dir.exists():
        issues.append(f"missing current memory directory: {current_dir}")
    if not history_dir.exists():
        issues.append(f"missing memory history directory: {history_dir}")
    if current_dir.exists() and not current_index.exists():
        issues.append(f"missing current memory index: {current_index}")
    if history_dir.exists() and not history_readme.exists():
        issues.append(f"missing memory history readme: {history_readme}")
    return issues


def check_retired_claude_memory(root: Path) -> list[str]:
    issues: list[str] = []
    memory_dir = root / ".claude" / "memory"
    for path in sorted(memory_dir.glob("*.md")):
        issues.append(f"{path} should be removed; project memory now lives under memory/")
    return issues


def collect_issues(root: Path) -> list[str]:
    docs_root = root / "docs"
    docs_index = docs_root / "INDEX.md"
    docs_todo = docs_root / "todo"
    project_memory = root / "memory"
    project_memory_index = project_memory / "INDEX.md"
    spec_path = root / ".orchestration" / "specs" / "documentation.md"

    issues: list[str] = []
    if not spec_path.exists():
        issues.append(f"missing documentation spec: {spec_path}")
    if not docs_index.exists():
        issues.append(f"missing docs index: {docs_index}")
    else:
        index_text = docs_index.read_text(encoding="utf-8")
        issues.extend(check_docs_root(index_text, docs_root))
        if not docs_todo.exists():
            issues.append(f"missing todo docs directory: {docs_todo}")
        else:
            issues.extend(check_todo_docs(index_text, docs_todo))

    if not project_memory.exists():
        issues.append(f"missing project memory directory: {project_memory}")
    elif not project_memory_index.exists():
        issues.append(f"missing project memory index: {project_memory_index}")
    else:
        issues.extend(check_required_memory_paths(project_memory))
        memory_index_text = project_memory_index.read_text(encoding="utf-8")
        current_index = project_memory / "current" / "INDEX.md"
        current_index_text = current_index.read_text(encoding="utf-8") if current_index.exists() else ""
        issues.extend(check_project_memory(project_memory, memory_index_text, current_index_text))

    issues.extend(check_spec_indexes(root))
    issues.extend(check_retired_claude_memory(root))
    return issues


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check documentation and memory placement rules.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    issues = collect_issues(root)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        return 1
    print("documentation-layout-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
