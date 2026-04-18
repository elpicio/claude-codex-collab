#!/usr/bin/env python3
"""Shared SessionStart hook for Claude/Codex adapter startup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def repo_root(default_path: Path) -> Path:
    return default_path.resolve().parents[2]


def resolve_root(raw_root: str | None, default_path: Path) -> Path:
    if raw_root:
        return Path(raw_root).resolve()
    return repo_root(default_path)


def bootstrap_import_path(default_path: Path) -> None:
    source_root = str(repo_root(default_path))
    if source_root not in sys.path:
        sys.path.insert(0, source_root)


def build_additional_context(task_id: str | None) -> str:
    lines = ["Read AGENTS.md first."]
    if task_id:
        lines.extend(
            [
                f"Active task: {task_id}",
                (
                    "Only if you are changing task phase or task state, read the task files "
                    f"under .orchestration/tasks/{task_id}/."
                ),
            ]
        )
    else:
        lines.append("Only read task files if you are changing task phase or task state.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync active backend on CLI session start.")
    parser.add_argument("--backend", choices=("claude", "codex"), required=True)
    parser.add_argument("--root", help="Project root. Defaults to the repository containing this hook.")
    args = parser.parse_args(argv)

    hook_path = Path(__file__)
    root = resolve_root(args.root, hook_path)
    bootstrap_import_path(hook_path)

    from scripts.agent_proxy_core import load_active_state, switch_backend

    reason = f"session_start:{args.backend}"
    switch_backend(root, args.backend, reason=reason, task_id=None)
    state = load_active_state(root)
    task_id = state.get("task_id")
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": build_additional_context(str(task_id) if task_id else None),
        }
    }
    json.dump(output, sys.stdout, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
