"""CLI entrypoint for the shared Claude/Codex orchestration helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.agent_proxy_core import (
    PHASE_OBJECTIVES,
    PhaseRequirementError,
    PhaseTransitionError,
    RuntimeConflictError,
    auto_repair_attachment,
    build_command,
    create_task,
    create_worktree,
    load_active_state,
    migrate_legacy_task,
    prune_dangling_attachments,
    recover_detached_head,
    remember_task,
    remove_worktree,
    repair_attachment,
    resolve_backend,
    restore_attachment_workspace,
    run_phase,
    run_worktree_bootstrap,
    show_attachment_health,
    show_worktree_branch_check,
    show_worktree_env_check,
    show_worktree_status,
    switch_backend,
    write_handoff,
)
from scripts.agent_proxy_nl import ParsedAction, parse_request

__all__ = [
    "PHASE_OBJECTIVES",
    "PhaseRequirementError",
    "PhaseTransitionError",
    "RuntimeConflictError",
    "build_command",
    "create_task",
    "create_worktree",
    "load_active_state",
    "main",
    "migrate_legacy_task",
    "remember_task",
    "prune_dangling_attachments",
    "recover_detached_head",
    "remove_worktree",
    "repair_attachment",
    "resolve_backend",
    "restore_attachment_workspace",
    "run_phase",
    "run_worktree_bootstrap",
    "show_attachment_health",
    "show_worktree_branch_check",
    "show_worktree_env_check",
    "show_worktree_status",
    "switch_backend",
    "write_handoff",
]


def print_status(root: Path) -> None:
    print(json.dumps(load_active_state(root), indent=2, ensure_ascii=True))


def resolve_task_id(root: Path, task_id: str | None, last_task_id: str | None) -> str:
    resolved = task_id or last_task_id or load_active_state(root).get("task_id")
    if resolved:
        return str(resolved)
    raise ValueError("No task-id provided and no active task is recorded.")


def resolve_action_path(root: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def handle_action(
    root: Path, action: ParsedAction, last_task_id: str | None
) -> tuple[int, str | None]:
    params = dict(action.params)
    if action.name == "status":
        print_status(root)
        return 0, last_task_id
    if action.name == "switch":
        path = switch_backend(root, params["backend"], params["reason"], params.get("task_id"))
        print(f"switch: {path.relative_to(root)}")
        return 0, last_task_id
    if action.name == "new-task":
        backend = resolve_backend(root, params.get("backend"))
        path = create_task(root, params["title"], params["goal"], backend, params.get("task_id"))
        task_id = path.name
        remember_task(root, task_id)
        print(f"new-task: {path.relative_to(root)}")
        return 0, task_id
    if action.name == "run":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        return run_phase(root, params["phase"], task_id, backend, bool(params["dry_run"])), task_id
    if action.name == "handoff":
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        path = write_handoff(root, task_id, params["to"], params["summary"])
        print(f"handoff: {path.relative_to(root)}")
        return 0, task_id
    if action.name == "migrate-legacy-task":
        legacy_path = resolve_action_path(root, params.get("path"))
        if legacy_path is None:
            raise ValueError("Legacy task migration requires a markdown path.")
        payload = migrate_legacy_task(
            root,
            legacy_path,
            backend=params.get("backend"),
            dry_run=bool(params.get("dry_run")),
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        task_id = str(payload["task_id"]) if not params.get("dry_run") else last_task_id
        return 0, task_id
    if action.name == "worktree-create":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        worktree_path, branch = create_worktree(
            root,
            task_id,
            backend,
            branch=params.get("branch"),
            path=resolve_action_path(root, params.get("path")),
            base_ref=params.get("base_ref"),
            dry_run=bool(params.get("dry_run")),
        )
        print(json.dumps({"path": str(worktree_path), "branch": branch}, ensure_ascii=True))
        return 0, task_id
    if action.name == "worktree-remove":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        payload = remove_worktree(
            root,
            task_id,
            backend=backend,
            path=resolve_action_path(root, params.get("path")),
            force=bool(params.get("force")),
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0, task_id
    if action.name == "worktree-recover-head":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        payload = recover_detached_head(
            root,
            task_id,
            backend=backend,
            path=resolve_action_path(root, params.get("path")),
            branch=params.get("branch"),
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0, task_id
    if action.name == "worktree-env-check":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        print(
            show_worktree_env_check(
                root,
                task_id,
                backend=backend,
                path=resolve_action_path(root, params.get("path")),
            )
        )
        return 0, task_id
    if action.name == "worktree-branch-check":
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        print(show_worktree_branch_check(root, task_id, branch=params.get("branch")))
        return 0, task_id
    if action.name == "worktree-bootstrap":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        payload, exit_code = run_worktree_bootstrap(
            root,
            task_id,
            backend=backend,
            path=resolve_action_path(root, params.get("path")),
            dry_run=bool(params.get("dry_run")),
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return exit_code, task_id
    if action.name == "worktree-attachment-check":
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        print(show_attachment_health(root, task_id))
        return 0, task_id
    if action.name == "worktree-attachment-repair":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        path = resolve_action_path(root, params.get("path"))
        if path is None:
            raise ValueError("Attachment repair requires a workspace path.")
        payload = repair_attachment(root, task_id, backend=backend, path=path)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0, task_id
    if action.name == "worktree-attachment-auto-repair":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        payload = auto_repair_attachment(root, task_id, backend=backend)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0, task_id
    if action.name == "worktree-attachment-prune":
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        payload = prune_dangling_attachments(root, task_id)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0, task_id
    if action.name == "worktree-restore":
        backend = resolve_backend(root, params.get("backend"))
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        restored_path = restore_attachment_workspace(root, task_id, backend)
        print(json.dumps({"path": str(restored_path)}, ensure_ascii=True))
        return 0, task_id
    if action.name == "worktree-status":
        task_id = resolve_task_id(root, params.get("task_id"), last_task_id)
        print(show_worktree_status(root, task_id))
        return 0, task_id
    raise ValueError(f"Unsupported action: {action.name}")


def run_request(root: Path, request: str) -> int:
    last_task_id = None
    for action in parse_request(request):
        exit_code, last_task_id = handle_action(root, action, last_task_id)
        if exit_code != 0:
            return exit_code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Switchable Claude/Codex orchestration helper.")
    parser.add_argument("--root", default=".", help="Project root. Defaults to the current directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show the active orchestration control preference.")

    switch_parser = subparsers.add_parser("switch", help="Switch the active driver backend.")
    switch_parser.add_argument("--backend", choices=("claude", "codex"), required=True)
    switch_parser.add_argument("--reason", required=True)
    switch_parser.add_argument("--task-id")

    task_parser = subparsers.add_parser("new-task", help="Create a task contract directory.")
    task_parser.add_argument("--title", required=True)
    task_parser.add_argument("--goal", required=True)
    task_parser.add_argument("--backend")
    task_parser.add_argument("--task-id")

    migrate_parser = subparsers.add_parser(
        "migrate-legacy-task",
        help="Migrate a legacy single-file task markdown into the directory model.",
    )
    migrate_parser.add_argument("--path", required=True)
    migrate_parser.add_argument("--backend")
    migrate_parser.add_argument("--dry-run", action="store_true")

    run_parser = subparsers.add_parser("run", help="Run or preview a workflow phase.")
    run_parser.add_argument("--phase", choices=tuple(PHASE_OBJECTIVES), required=True)
    run_parser.add_argument("--task-id", required=True)
    run_parser.add_argument("--backend")
    run_parser.add_argument("--dry-run", action="store_true")

    handoff_parser = subparsers.add_parser("handoff", help="Write a handoff note.")
    handoff_parser.add_argument("--task-id", required=True)
    handoff_parser.add_argument("--to", choices=("claude", "codex"), required=True)
    handoff_parser.add_argument("--summary", default="")

    worktree_parser = subparsers.add_parser("worktree", help="Create or inspect a task worktree.")
    worktree_subparsers = worktree_parser.add_subparsers(dest="worktree_command", required=True)

    worktree_create = worktree_subparsers.add_parser("create", help="Create a linked worktree for a task.")
    worktree_create.add_argument("--task-id", required=True)
    worktree_create.add_argument("--backend")
    worktree_create.add_argument("--branch")
    worktree_create.add_argument("--path")
    worktree_create.add_argument("--base-ref")
    worktree_create.add_argument("--dry-run", action="store_true")

    worktree_remove = worktree_subparsers.add_parser(
        "remove",
        help="Remove a linked worktree and rebind runtime to the main workspace.",
    )
    worktree_remove.add_argument("--task-id", required=True)
    worktree_remove.add_argument("--backend")
    worktree_remove.add_argument("--path")
    worktree_remove.add_argument("--force", action="store_true")

    worktree_recover = worktree_subparsers.add_parser(
        "recover-head",
        help="Reattach a detached worktree HEAD back to the task branch.",
    )
    worktree_recover.add_argument("--task-id", required=True)
    worktree_recover.add_argument("--backend")
    worktree_recover.add_argument("--path")
    worktree_recover.add_argument("--branch")

    worktree_env = worktree_subparsers.add_parser(
        "env-check",
        help="Validate a task worktree path or recorded attachment.",
    )
    worktree_env.add_argument("--task-id", required=True)
    worktree_env.add_argument("--backend")
    worktree_env.add_argument("--path")

    worktree_branch = worktree_subparsers.add_parser(
        "branch-check",
        help="Inspect whether a branch is already bound to a worktree.",
    )
    worktree_branch.add_argument("--task-id", required=True)
    worktree_branch.add_argument("--branch")

    worktree_bootstrap = worktree_subparsers.add_parser(
        "bootstrap",
        help="Run the configured bootstrap checks inside a task worktree.",
    )
    worktree_bootstrap.add_argument("--task-id", required=True)
    worktree_bootstrap.add_argument("--backend")
    worktree_bootstrap.add_argument("--path")
    worktree_bootstrap.add_argument("--dry-run", action="store_true")

    worktree_attachment = worktree_subparsers.add_parser(
        "attachment-check",
        help="Inspect whether recorded local attachments are still valid.",
    )
    worktree_attachment.add_argument("--task-id", required=True)

    worktree_attachment_repair = worktree_subparsers.add_parser(
        "attachment-repair",
        help="Repair the active attachment to point at a valid workspace path.",
    )
    worktree_attachment_repair.add_argument("--task-id", required=True)
    worktree_attachment_repair.add_argument("--backend")
    worktree_attachment_repair.add_argument("--path", required=True)

    worktree_attachment_auto = worktree_subparsers.add_parser(
        "attachment-auto-repair",
        help="Auto-select a valid workspace and repair the active attachment.",
    )
    worktree_attachment_auto.add_argument("--task-id", required=True)
    worktree_attachment_auto.add_argument("--backend")

    worktree_attachment_prune = worktree_subparsers.add_parser(
        "attachment-prune",
        help="Remove dangling attachments that are not referenced by the active runtime.",
    )
    worktree_attachment_prune.add_argument("--task-id", required=True)

    worktree_restore = worktree_subparsers.add_parser(
        "restore",
        help="Restore runtime workspace binding from the recorded attachment.",
    )
    worktree_restore.add_argument("--task-id", required=True)
    worktree_restore.add_argument("--backend")

    worktree_status = worktree_subparsers.add_parser("status", help="Show current worktree runtime state.")
    worktree_status.add_argument("--task-id", required=True)

    ask_parser = subparsers.add_parser("ask", help="Execute a request described in natural language.")
    ask_parser.add_argument("request", nargs="+", help="Natural-language request text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        root = Path(args.root).resolve()

        if args.command == "status":
            print_status(root)
            return 0
        if args.command == "switch":
            path = switch_backend(root, args.backend, args.reason, args.task_id)
            print(path.relative_to(root))
            return 0
        if args.command == "new-task":
            backend = resolve_backend(root, args.backend)
            path = create_task(root, args.title, args.goal, backend, args.task_id)
            remember_task(root, path.name)
            print(path.relative_to(root))
            return 0
        if args.command == "migrate-legacy-task":
            payload = migrate_legacy_task(
                root,
                Path(args.path),
                backend=args.backend,
                dry_run=args.dry_run,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=True))
            return 0
        if args.command == "run":
            backend = resolve_backend(root, args.backend)
            return run_phase(root, args.phase, args.task_id, backend, args.dry_run)
        if args.command == "handoff":
            print(write_handoff(root, args.task_id, args.to, args.summary).relative_to(root))
            return 0
        if args.command == "worktree":
            if args.worktree_command == "create":
                backend = resolve_backend(root, args.backend)
                worktree_path, branch = create_worktree(
                    root,
                    args.task_id,
                    backend,
                    branch=args.branch,
                    path=Path(args.path).resolve() if args.path else None,
                    base_ref=args.base_ref,
                    dry_run=args.dry_run,
                )
                print(json.dumps({"path": str(worktree_path), "branch": branch}, ensure_ascii=True))
                return 0
            if args.worktree_command == "remove":
                backend = resolve_backend(root, args.backend)
                payload = remove_worktree(
                    root,
                    args.task_id,
                    backend=backend,
                    path=Path(args.path).resolve() if args.path else None,
                    force=bool(args.force),
                )
                print(json.dumps(payload, indent=2, ensure_ascii=True))
                return 0
            if args.worktree_command == "recover-head":
                backend = resolve_backend(root, args.backend)
                payload = recover_detached_head(
                    root,
                    args.task_id,
                    backend=backend,
                    path=Path(args.path).resolve() if args.path else None,
                    branch=args.branch,
                )
                print(json.dumps(payload, indent=2, ensure_ascii=True))
                return 0
            if args.worktree_command == "env-check":
                backend = resolve_backend(root, args.backend)
                print(
                    show_worktree_env_check(
                        root,
                        args.task_id,
                        backend=backend,
                        path=Path(args.path).resolve() if args.path else None,
                    )
                )
                return 0
            if args.worktree_command == "branch-check":
                print(show_worktree_branch_check(root, args.task_id, branch=args.branch))
                return 0
            if args.worktree_command == "bootstrap":
                backend = resolve_backend(root, args.backend)
                payload, exit_code = run_worktree_bootstrap(
                    root,
                    args.task_id,
                    backend=backend,
                    path=Path(args.path).resolve() if args.path else None,
                    dry_run=args.dry_run,
                )
                print(json.dumps(payload, indent=2, ensure_ascii=True))
                return exit_code
            if args.worktree_command == "attachment-check":
                print(show_attachment_health(root, args.task_id))
                return 0
            if args.worktree_command == "attachment-repair":
                backend = resolve_backend(root, args.backend)
                payload = repair_attachment(
                    root,
                    args.task_id,
                    backend=backend,
                    path=Path(args.path).resolve(),
                )
                print(json.dumps(payload, indent=2, ensure_ascii=True))
                return 0
            if args.worktree_command == "attachment-auto-repair":
                backend = resolve_backend(root, args.backend)
                payload = auto_repair_attachment(root, args.task_id, backend=backend)
                print(json.dumps(payload, indent=2, ensure_ascii=True))
                return 0
            if args.worktree_command == "attachment-prune":
                payload = prune_dangling_attachments(root, args.task_id)
                print(json.dumps(payload, indent=2, ensure_ascii=True))
                return 0
            if args.worktree_command == "restore":
                backend = resolve_backend(root, args.backend)
                restored_path = restore_attachment_workspace(root, args.task_id, backend)
                print(json.dumps({"path": str(restored_path)}, ensure_ascii=True))
                return 0
            if args.worktree_command == "status":
                print(show_worktree_status(root, args.task_id))
                return 0
        if args.command == "ask":
            return run_request(root, " ".join(args.request))
        raise ValueError(f"Unsupported command: {args.command}")
    except (
        ValueError,
        RuntimeError,
        FileNotFoundError,
        PhaseTransitionError,
        PhaseRequirementError,
        RuntimeConflictError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
