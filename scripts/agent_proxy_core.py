"""Core helpers for the shared Claude/Codex orchestration workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover - non-posix fallback
    fcntl = None

ORCH_DIR = ".orchestration"
LOCAL_COMMON_DIR = ".local-common-dir"
PHASE_OBJECTIVES = {
    "plan": "Produce an implementation plan with files, tests, and risks.",
    "implement": "Complete the task, update code or docs, and prepare verification.",
    "review": "Review the current changes against the task scope and report findings first.",
    "verify": "Execute the verify profile for the current workspace and record the result.",
}
BOOTSTRAP_PROFILES = {
    "python_default": {
        "runner": "shell",
        "commands": [
            "PYTHONDONTWRITEBYTECODE=1 python -V",
            "PYTHONDONTWRITEBYTECODE=1 python -m pytest --version",
        ],
    }
}
LOCAL_CONFIG_CANDIDATES = [
    ".env",
    ".env.local",
    ".envrc",
    ".python-version",
    ".venv",
    "venv",
]
CONTEXT_NOTES = {
    "plan": "Task background, scope, and expected deliverables.",
    "implement": "Task scope and the intended implementation target.",
    "review": "Task scope and the criteria that review must check.",
}
MAILBOX_BACKENDS = {"claude", "codex"}
MAILBOX_MESSAGE_TYPES = {"request", "result"}
MAILBOX_REQUEST_STATUSES = {"pending", "acked", "resolved"}
MAILBOX_RESULT_STATUSES = {"succeeded", "failed", "cancelled", "retry_requested"}


class RuntimeConflictError(RuntimeError):
    """Raised when runtime compare-and-swap detects a stale generation."""


class PhaseTransitionError(ValueError):
    """Raised when a requested phase transition is not allowed."""


class PhaseRequirementError(ValueError):
    """Raised when a phase transition requirement is not satisfied."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def lease_expiry_iso(minutes: int = 15) -> str:
    return (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat(
        timespec="seconds"
    )


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "task"


def project_slug(root: Path) -> str:
    top_level = git_top_level(root) or root
    raw = re.sub(r"[^a-zA-Z0-9_.-]+", "-", top_level.name).strip("-").lower()
    return raw or "project"


def orchestration_dir(root: Path) -> Path:
    return root / ORCH_DIR


def repo_tasks_dir(root: Path) -> Path:
    return orchestration_dir(root) / "tasks"


def repo_specs_dir(root: Path) -> Path:
    return orchestration_dir(root) / "specs"


def local_state_dir(root: Path) -> Path:
    return orchestration_dir(root) / "state"


def ensure_repo_dirs(root: Path) -> None:
    for path in (repo_tasks_dir(root), repo_specs_dir(root), local_state_dir(root)):
        path.mkdir(parents=True, exist_ok=True)


def active_state_path(root: Path) -> Path:
    return local_state_dir(root) / "active_control.json"


def legacy_active_state_path(root: Path) -> Path:
    return local_state_dir(root) / "active_backend.json"


def task_dir(root: Path, task_id: str) -> Path:
    return repo_tasks_dir(root) / task_id


def contract_path(root: Path, task_id: str) -> Path:
    return task_dir(root, task_id) / "contract.json"


def task_markdown_path(root: Path, task_id: str) -> Path:
    return task_dir(root, task_id) / "task.md"


def journal_path(root: Path, task_id: str) -> Path:
    return task_dir(root, task_id) / "journal.md"


def verify_path(root: Path, task_id: str) -> Path:
    return task_dir(root, task_id) / "verify.json"


def context_dir(root: Path, task_id: str) -> Path:
    return task_dir(root, task_id) / "context"


def context_path(root: Path, task_id: str, phase: str) -> Path:
    return context_dir(root, task_id) / f"{phase}.jsonl"


def handoff_dir(root: Path, task_id: str) -> Path:
    return task_dir(root, task_id) / "handoffs"


def checkpoint_dir(root: Path, task_id: str) -> Path:
    return task_dir(root, task_id) / "checkpoints"


def driver_run_id(backend: str) -> str:
    return f"run-{backend}-driver"


def control_mode_for_backend(backend: str) -> str:
    return "claude_codex" if backend == "claude" else "codex_native"


def adapter_for_backend(backend: str) -> str:
    return "claude_code" if backend == "claude" else "codex_cli"


def default_state() -> dict[str, Any]:
    return {
        "backend": "claude",
        "control_mode": "claude_codex",
        "driver": {"kind": "claude", "adapter": "claude_code"},
        "task_id": None,
        "reason": "default",
        "switched_at": "not-set",
    }


def normalize_state(payload: dict[str, Any]) -> dict[str, Any]:
    if "driver" in payload:
        payload.setdefault("backend", payload["driver"]["kind"])
        payload.setdefault("control_mode", control_mode_for_backend(str(payload["backend"])))
        payload.setdefault("task_id", None)
        payload.setdefault("reason", "default")
        payload.setdefault("switched_at", "not-set")
        return payload

    backend = str(payload.get("backend", "claude"))
    return {
        "backend": backend,
        "control_mode": control_mode_for_backend(backend),
        "driver": {"kind": backend, "adapter": adapter_for_backend(backend)},
        "task_id": payload.get("task_id"),
        "reason": payload.get("reason", "legacy"),
        "switched_at": payload.get("switched_at", "not-set"),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def load_active_state(root: Path) -> dict[str, Any]:
    path = active_state_path(root)
    if path.exists():
        return normalize_state(load_json(path))

    legacy_path = legacy_active_state_path(root)
    if legacy_path.exists():
        state = normalize_state(load_json(legacy_path))
        save_active_state(root, state)
        return state

    return default_state()


def save_active_state(root: Path, state: dict[str, Any]) -> Path:
    ensure_repo_dirs(root)
    path = active_state_path(root)
    legacy_path = legacy_active_state_path(root)
    write_json(path, normalize_state(state))
    if legacy_path.exists():
        legacy_path.unlink()
    return path


def remember_task(root: Path, task_id: str) -> Path:
    state = load_active_state(root)
    state["task_id"] = task_id
    return save_active_state(root, state)


def load_profile(root: Path, backend: str) -> dict[str, Any]:
    return load_json(orchestration_dir(root) / "profiles" / f"{backend}.json")


def next_index(directory: Path, suffix: str) -> int:
    if not directory.exists():
        return 1
    highest = 0
    for path in directory.glob(f"*{suffix}"):
        try:
            highest = max(highest, int(path.stem))
        except ValueError:
            continue
    return highest + 1


def git_command(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=root, capture_output=True, text=True, check=False)


def run_git(root: Path, args: list[str]) -> str:
    result = git_command(root, args)
    output = result.stdout.strip() or result.stderr.strip()
    return output or "(clean)"


def git_common_dir_for_workspace(root: Path) -> Path | None:
    result = git_command(root, ["git", "rev-parse", "--git-common-dir"])
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    return candidate


def git_common_dir(root: Path) -> Path:
    candidate = git_common_dir_for_workspace(root)
    if candidate is not None:
        return candidate
    return (orchestration_dir(root) / LOCAL_COMMON_DIR).resolve()


def git_top_level(root: Path) -> Path | None:
    result = git_command(root, ["git", "rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def shared_runtime_root(root: Path) -> Path:
    return git_common_dir(root) / project_slug(root)


def shared_runtime_path(root: Path, task_id: str) -> Path:
    return shared_runtime_root(root) / "runtime" / f"{task_id}.json"


def mailbox_dir_path(root: Path) -> Path:
    return shared_runtime_root(root) / "messages"


def mailbox_path(root: Path, task_id: str) -> Path:
    return mailbox_dir_path(root) / f"{task_id}.jsonl"


def mailbox_lock_path(root: Path, task_id: str) -> Path:
    return mailbox_dir_path(root) / f"{task_id}.lock"


def shared_log_dir(root: Path, task_id: str) -> Path:
    return shared_runtime_root(root) / "logs" / task_id


def attachment_path(root: Path, task_id: str, run_id: str) -> Path:
    return shared_runtime_root(root) / "attachments" / task_id / f"{run_id}.json"


def attachment_dir_path(root: Path, task_id: str) -> Path:
    return shared_runtime_root(root) / "attachments" / task_id


def relative_or_absolute(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    lines = [json.dumps(entry, ensure_ascii=True) for entry in entries]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def normalize_mailbox_backend(backend: str) -> str:
    normalized = str(backend).strip().lower()
    if normalized not in MAILBOX_BACKENDS:
        raise ValueError(f"unsupported mailbox backend: {backend}")
    return normalized


def normalize_mailbox_type(message_type: str) -> str:
    normalized = str(message_type).strip().lower()
    if normalized not in MAILBOX_MESSAGE_TYPES:
        raise ValueError(f"unsupported mailbox message type: {message_type}")
    return normalized


def normalize_mailbox_result_status(status: str) -> str:
    normalized = str(status).strip().lower()
    if normalized not in MAILBOX_RESULT_STATUSES:
        raise ValueError(f"unsupported mailbox result status: {status}")
    return normalized


def mailbox_message_id() -> str:
    return f"msg-{uuid.uuid4().hex}"


def _require_task(root: Path, task_id: str) -> None:
    try:
        load_contract(root, task_id)
    except FileNotFoundError as exc:
        raise ValueError(f"task not found: {task_id}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"task contract unreadable: {task_id}") from exc
    except OSError as exc:
        raise ValueError(f"task contract unreadable: {task_id}") from exc


def load_mailbox_entries(root: Path, task_id: str) -> list[dict[str, Any]]:
    # This is a raw read helper; mutating callers must hold the mailbox lock.
    path = mailbox_path(root, task_id)
    if not path.exists():
        return []
    return read_jsonl(path)


def save_mailbox_entries(root: Path, task_id: str, entries: list[dict[str, Any]]) -> Path:
    # Callers must hold the per-task mailbox lock before writing.
    path = mailbox_path(root, task_id)
    write_jsonl(path, entries)
    return path


def mutate_mailbox_entries(
    root: Path,
    task_id: str,
    mutator: Callable[[list[dict[str, Any]]], dict[str, Any]],
) -> dict[str, Any]:
    _require_task(root, task_id)
    mailbox_dir_path(root).mkdir(parents=True, exist_ok=True)
    lock_path = mailbox_lock_path(root, task_id)
    with lock_path.open("a", encoding="utf-8") as lock_handle:
        if fcntl is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            entries = load_mailbox_entries(root, task_id)
            result = mutator(entries)
            save_mailbox_entries(root, task_id, entries)
            return result
        finally:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def find_mailbox_message(
    entries: list[dict[str, Any]], message_id: str
) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    for index, message in enumerate(entries):
        if str(message.get("id")) == message_id:
            return index, message
    return None, None


def mailbox_send(
    root: Path,
    task_id: str,
    *,
    from_backend: str,
    to_backend: str,
    summary: str,
    details: str = "",
) -> dict[str, Any]:
    sender = normalize_mailbox_backend(from_backend)
    receiver = normalize_mailbox_backend(to_backend)
    if sender == receiver:
        raise ValueError("mailbox sender and receiver must be different backends")
    summary_text = summary.strip()
    if not summary_text:
        raise ValueError("mailbox request summary cannot be empty")
    details_text = details.strip()

    def apply(entries: list[dict[str, Any]]) -> dict[str, Any]:
        timestamp = now_iso()
        payload: dict[str, Any] = {"summary": summary_text}
        if details_text:
            payload["details"] = details_text
        message = {
            "id": mailbox_message_id(),
            "task_id": task_id,
            "type": "request",
            "status": "pending",
            "from": sender,
            "to": receiver,
            "reply_to": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "ack": None,
            "payload": payload,
        }
        entries.append(message)
        return message

    return mutate_mailbox_entries(root, task_id, apply)


def mailbox_read(
    root: Path,
    task_id: str,
    *,
    to_backend: str | None = None,
    message_type: str | None = None,
    only_unacked: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    # Returns a parsed snapshot for this call; callers should not rely on object identity across reads.
    _require_task(root, task_id)
    # Intentionally allow cross-backend queries when to_backend is omitted.
    receiver = normalize_mailbox_backend(to_backend) if to_backend else None
    normalized_type = normalize_mailbox_type(message_type) if message_type else None
    if only_unacked and normalized_type != "request":
        raise ValueError("mailbox read with --unacked requires message_type='request'")
    if limit is not None and limit <= 0:
        raise ValueError("mailbox read limit must be greater than zero")

    entries = load_mailbox_entries(root, task_id)
    filtered = []
    for message in entries:
        if receiver and str(message.get("to")) != receiver:
            continue
        if normalized_type and str(message.get("type")) != normalized_type:
            continue
        if only_unacked and str(message.get("status")) != "pending":
            continue
        filtered.append(message)
    if limit is not None:
        filtered = filtered[:limit]
    return filtered


def mailbox_ack(
    root: Path,
    task_id: str,
    *,
    message_id: str,
    by_backend: str,
    note: str = "",
) -> dict[str, Any]:
    backend = normalize_mailbox_backend(by_backend)
    note_text = note.strip()

    def apply(entries: list[dict[str, Any]]) -> dict[str, Any]:
        index, message = find_mailbox_message(entries, message_id)
        if index is None or message is None:
            raise ValueError(f"mailbox message not found: {message_id}")
        if str(message.get("to")) != backend:
            raise ValueError(f"mailbox message {message_id} is not addressed to backend: {backend}")
        if str(message.get("type")) != "request":
            raise ValueError("mailbox ack only supports request messages")
        status = str(message.get("status"))
        if status not in MAILBOX_REQUEST_STATUSES:
            raise ValueError(f"mailbox message status is invalid: {message.get('status')}")
        if status == "resolved":
            raise ValueError(f"mailbox request already resolved: {message_id}")
        if message.get("ack") is not None:
            raise ValueError(f"mailbox message already acknowledged: {message_id}")

        timestamp = now_iso()
        ack_payload: dict[str, Any] = {"by": backend, "at": timestamp}
        if note_text:
            ack_payload["note"] = note_text
        message["ack"] = ack_payload
        message["status"] = "acked"
        message["updated_at"] = timestamp
        entries[index] = message
        return message

    return mutate_mailbox_entries(root, task_id, apply)


def mailbox_result(
    root: Path,
    task_id: str,
    *,
    request_id: str,
    from_backend: str,
    status: str,
    summary: str,
    details: str = "",
) -> dict[str, Any]:
    sender = normalize_mailbox_backend(from_backend)
    resolved_status = normalize_mailbox_result_status(status)
    summary_text = summary.strip()
    if not summary_text:
        raise ValueError("mailbox result summary cannot be empty")
    details_text = details.strip()

    def apply(entries: list[dict[str, Any]]) -> dict[str, Any]:
        index, request_message = find_mailbox_message(entries, request_id)
        if index is None or request_message is None:
            raise ValueError(f"mailbox request not found: {request_id}")
        if str(request_message.get("type")) != "request":
            raise ValueError(f"mailbox message is not a request: {request_id}")
        request_status = str(request_message.get("status"))
        if request_status == "resolved":
            raise ValueError(f"mailbox request already resolved: {request_id}")
        if request_status != "acked":
            raise ValueError(
                f"mailbox request must be acknowledged before result: {request_id} ({request_status})"
            )
        if request_message.get("ack") is None:
            raise ValueError(f"mailbox request missing ack metadata: {request_id}")
        if str(request_message.get("to")) != sender:
            raise ValueError(
                f"mailbox request {request_id} is assigned to {request_message.get('to')}, got {sender}"
            )
        receiver = normalize_mailbox_backend(str(request_message.get("from")))

        timestamp = now_iso()
        payload: dict[str, Any] = {"summary": summary_text}
        if details_text:
            payload["details"] = details_text
        result_message = {
            "id": mailbox_message_id(),
            "task_id": task_id,
            "type": "result",
            "status": resolved_status,
            "from": sender,
            "to": receiver,
            "reply_to": request_id,
            "created_at": timestamp,
            "updated_at": timestamp,
            "ack": None,
            "payload": payload,
        }
        entries.append(result_message)

        request_message["status"] = "resolved"
        request_message["resolution"] = resolved_status
        request_message["resolved_at"] = timestamp
        request_message["result_id"] = result_message["id"]
        request_message["updated_at"] = timestamp
        entries[index] = request_message
        return result_message

    return mutate_mailbox_entries(root, task_id, apply)


def current_branch(root: Path) -> tuple[str | None, bool]:
    result = git_command(root, ["git", "symbolic-ref", "--quiet", "--short", "HEAD"])
    if result.returncode == 0:
        return result.stdout.strip(), False
    return None, True


def current_head_rev(root: Path) -> str | None:
    result = git_command(root, ["git", "rev-parse", "HEAD"])
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def git_dir_path(root: Path) -> Path | None:
    result = git_command(root, ["git", "rev-parse", "--git-dir"])
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def fingerprint_paths_from_git(root: Path) -> list[Path] | None:
    result = git_command(
        root,
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
    )
    if result.returncode != 0:
        return None
    return sorted(root / item for item in result.stdout.split("\0") if item)


def fingerprint_paths_from_filesystem(root: Path) -> list[Path]:
    excluded = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
    }
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in excluded for part in rel_parts):
            continue
        if rel_parts[:2] == (ORCH_DIR, "state"):
            continue
        if rel_parts[:2] == (ORCH_DIR, LOCAL_COMMON_DIR):
            continue
        paths.append(path)
    return sorted(paths)


def workspace_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    paths = fingerprint_paths_from_git(root)
    if paths is None:
        paths = fingerprint_paths_from_filesystem(root)

    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def workspace_state(root: Path, base_ref: str) -> dict[str, Any]:
    branch, detached = current_branch(root)
    head_rev = current_head_rev(root)
    status = git_command(root, ["git", "status", "--short"])
    git_dir = git_dir_path(root)
    site_kind = "main"
    worktree_id = "main"
    if git_dir and "worktrees" in git_dir.parts:
        site_kind = "linked"
        worktree_id = git_dir.name

    return {
        "worktree_id": worktree_id,
        "site_kind": site_kind,
        "checkout_mode": "detached" if detached else "branch",
        "branch": branch,
        "head_rev": head_rev,
        "base_ref": base_ref,
        "detached": detached,
        "exists": root.exists(),
        "is_clean": status.returncode == 0 and not status.stdout.strip(),
        "content_fingerprint": workspace_fingerprint(root),
    }


def default_base_ref(root: Path) -> str:
    branch, detached = current_branch(root)
    if branch and not detached:
        return branch
    return "main"


def default_contract(task_id: str, title: str, goal: str, base_ref: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": title,
        "goal": goal,
        "allowed_control_modes": ["claude_codex", "codex_native"],
        "phase_order": ["plan", "implement", "review", "verify", "handoff"],
        "phase_graph": {
            "plan": {"next": ["implement"]},
            "implement": {"next": ["review"], "requires": ["workspace.attached"]},
            "review": {"next": ["verify"]},
            "verify": {
                "next": ["handoff", "done"],
                "requires": ["verify.pass_current_workspace"],
            },
        },
        "phase_inputs": {
            "plan": {
                "context": ["context/plan.jsonl"],
                "specs": [".orchestration/specs/project.md"],
            },
            "implement": {
                "context": ["context/implement.jsonl"],
                "specs": [
                    ".orchestration/specs/project.md",
                    ".orchestration/specs/coding.md",
                ],
            },
            "review": {
                "context": ["context/review.jsonl"],
                "specs": [
                    ".orchestration/specs/review.md",
                    ".orchestration/specs/adapters.md",
                ],
                "verify_profile": "python_default",
            },
            "verify": {
                "context": [],
                "specs": [
                    ".orchestration/specs/review.md",
                    ".orchestration/specs/documentation.md",
                ],
                "verify_profile": "python_default",
            },
        },
        "verify_file": "verify.json",
        "branch_policy": {
            "base_ref": base_ref,
            "implement_allow_detached": True,
            "review_requires_materialized_branch": True,
        },
        "worktree_policy": {
            "required_for_parallel": True,
            "allow_main_checkout": True,
            "bootstrap_profile": "python_default",
            "requires_env_check": True,
        },
    }


def default_verify_profile() -> dict[str, Any]:
    return {
        "profile": "python_default",
        "entry_phase": "verify",
        "commands": [
            "PYTHONDONTWRITEBYTECODE=1 python -m scripts.check_documentation_layout",
            "PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests",
        ],
        "pass_invariant": (
            "workspace.is_clean && "
            "verify.last_successful_fingerprint == workspace.content_fingerprint"
        ),
    }


def task_md_content(task_id: str, title: str, goal: str) -> str:
    return f"""# {title}

- Task ID: `{task_id}`
- Goal: {goal}

## Background

Describe the task background and any project context here.

## Scope

- Define the in-scope files and modules.
- Record the non-goals when they matter.

## Deliverables

- [ ] List the concrete outputs for this task.

## Risks

- None recorded yet.

## Human Constraints

- Keep checkpoints and handoff notes current enough that another controller can resume.
"""


def journal_md_content(task_id: str, title: str) -> str:
    return f"""# Journal: {title}

- Task ID: `{task_id}`

"""


def append_task_journal_entry(root: Path, task_id: str, heading: str, lines: list[str]) -> Path:
    path = journal_path(root, task_id)
    if not path.exists():
        atomic_write_text(path, journal_md_content(task_id, task_id))
    entry_lines = [f"## {heading}", ""]
    entry_lines.extend(lines)
    entry_lines.append("")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(entry_lines))
    return path


def context_entries_for_phase(phase: str) -> list[dict[str, Any]]:
    return [{"path": "task.md", "note": CONTEXT_NOTES[phase]}]


def default_runtime(
    task_id: str,
    active_state: dict[str, Any],
    base_ref: str,
    root: Path,
) -> dict[str, Any]:
    run_id = driver_run_id(str(active_state["backend"]))
    return {
        "task_id": task_id,
        "runtime_meta": {
            "schema_version": 1,
            "generation": 0,
            "writer": run_id,
            "updated_at": now_iso(),
        },
        "lease": {"holder": run_id, "expires_at": lease_expiry_iso()},
        "control": {
            "mode": active_state["control_mode"],
            "driver_ref": run_id,
            "phase_owner_ref": run_id,
            "execution_topology": "single",
        },
        "participants": [
            {
                "run_id": run_id,
                "kind": active_state["backend"],
                "role": "driver",
                "state": "idle",
                "attachment_ref": None,
                "session_ref": None,
            }
        ],
        "phase": {"name": "plan", "status": "pending"},
        "workspace": workspace_state(root, base_ref),
        "verify": {
            "status": "pending",
            "runner_ref": None,
            "started_at": None,
            "finished_at": None,
            "last_run_fingerprint": None,
            "last_successful_fingerprint": None,
        },
        "mutation_policy": {
            "authoritative_writer": "driver_only",
            "verify_updates_via": "driver_rpc",
            "worktree_updates_via": "driver_rpc",
        },
        "resume_from": None,
        "checkpoint_ref": None,
    }


def load_contract(root: Path, task_id: str) -> dict[str, Any]:
    return load_json(contract_path(root, task_id))


def runtime_generation(runtime: dict[str, Any]) -> int:
    return int(runtime["runtime_meta"]["generation"])


def participant_ids(runtime: dict[str, Any]) -> set[str]:
    return {str(item["run_id"]) for item in runtime.get("participants", [])}


def upsert_participant(runtime: dict[str, Any], participant: dict[str, Any]) -> None:
    run_id = str(participant["run_id"])
    for index, existing in enumerate(runtime.get("participants", [])):
        if str(existing["run_id"]) == run_id:
            runtime["participants"][index] = participant
            return
    runtime.setdefault("participants", []).append(participant)


def validate_runtime(runtime: dict[str, Any], writer: str) -> None:
    refs = participant_ids(runtime)
    control = runtime["control"]
    driver_ref = control.get("driver_ref")
    phase_owner_ref = control.get("phase_owner_ref")

    if driver_ref and driver_ref not in refs:
        raise RuntimeConflictError(f"driver_ref does not point to a participant: {driver_ref}")
    if phase_owner_ref and phase_owner_ref not in refs:
        raise RuntimeConflictError(
            f"phase_owner_ref does not point to a participant: {phase_owner_ref}"
        )
    if runtime["mutation_policy"]["authoritative_writer"] == "driver_only" and driver_ref:
        if writer != driver_ref:
            raise RuntimeConflictError(
                f"authoritative runtime writes must come from driver_ref={driver_ref}, got {writer}"
            )


def write_runtime(
    root: Path,
    task_id: str,
    runtime: dict[str, Any],
    writer: str,
    expected_generation: int,
) -> Path:
    path = shared_runtime_path(root, task_id)
    existing_generation = 0
    if path.exists():
        existing_generation = int(load_json(path)["runtime_meta"]["generation"])
    if existing_generation != expected_generation:
        raise RuntimeConflictError(
            f"stale runtime generation for {task_id}: expected {expected_generation}, got {existing_generation}"
        )

    payload = copy.deepcopy(runtime)
    payload["runtime_meta"] = {
        "schema_version": 1,
        "generation": existing_generation + 1,
        "writer": writer,
        "updated_at": now_iso(),
    }
    payload["lease"] = {"holder": writer, "expires_at": lease_expiry_iso()}
    validate_runtime(payload, writer)
    write_json(path, payload)
    return path


def load_runtime(root: Path, task_id: str) -> dict[str, Any]:
    path = shared_runtime_path(root, task_id)
    if path.exists():
        return load_json(path)
    contract = load_contract(root, task_id)
    runtime = default_runtime(
        task_id,
        load_active_state(root),
        str(contract["branch_policy"]["base_ref"]),
        root,
    )
    write_runtime(root, task_id, runtime, str(runtime["control"]["driver_ref"]), 0)
    return load_json(path)


def mutate_runtime(
    root: Path,
    task_id: str,
    writer: str,
    mutator: Callable[[dict[str, Any]], None],
    *,
    expected_generation: int | None = None,
) -> dict[str, Any]:
    current = load_runtime(root, task_id)
    current_generation = runtime_generation(current)
    if expected_generation is not None and current_generation != expected_generation:
        raise RuntimeConflictError(
            f"stale runtime generation for {task_id}: expected {expected_generation}, got {current_generation}"
        )
    updated = copy.deepcopy(current)
    mutator(updated)
    write_runtime(root, task_id, updated, writer, current_generation)
    return load_json(shared_runtime_path(root, task_id))


def save_attachment(
    root: Path,
    task_id: str,
    run_id: str,
    kind: str,
    role: str,
    session_ref: str | None,
    local_worktree_path: Path | None = None,
) -> Path:
    path = attachment_path(root, task_id, run_id)
    existing = load_json(path) if path.exists() else {}
    resolved_worktree_path = local_worktree_path
    if resolved_worktree_path is None:
        existing_worktree_path = existing.get("local_worktree_path")
        resolved_worktree_path = (
            Path(str(existing_worktree_path)) if existing_worktree_path else root
        )
    payload = {
        "run_id": run_id,
        "provider": kind,
        "role": role,
        "thread_ref": session_ref if session_ref is not None else existing.get("thread_ref"),
        "session_id": existing.get("session_id"),
        "local_worktree_path": str(resolved_worktree_path.resolve()),
        "pid": existing.get("pid"),
        "lease_expires_at": lease_expiry_iso(),
    }
    write_json(path, payload)
    return path


def load_attachment(root: Path, task_id: str, run_id: str) -> dict[str, Any]:
    path = attachment_path(root, task_id, run_id)
    if not path.exists():
        raise FileNotFoundError(
            f"attachment not found for {task_id}: {relative_or_absolute(root, path)}"
        )
    return load_json(path)


def list_attachments(root: Path, task_id: str) -> list[Path]:
    directory = attachment_dir_path(root, task_id)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def checkpoint_payload(
    runtime: dict[str, Any],
    active_state: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "created_at": now_iso(),
        "reason": reason,
        "control_mode": active_state["control_mode"],
        "driver": active_state["driver"],
        "phase": runtime["phase"],
        "workspace": {
            "worktree_id": runtime["workspace"]["worktree_id"],
            "site_kind": runtime["workspace"]["site_kind"],
            "branch": runtime["workspace"]["branch"],
            "head_rev": runtime["workspace"]["head_rev"],
            "is_clean": runtime["workspace"]["is_clean"],
            "content_fingerprint": runtime["workspace"]["content_fingerprint"],
        },
        "verify": {
            "status": runtime["verify"]["status"],
            "last_successful_fingerprint": runtime["verify"]["last_successful_fingerprint"],
        },
    }


def phase_graph(contract: dict[str, Any]) -> dict[str, Any]:
    return dict(contract.get("phase_graph", {}))


def phase_requirements(runtime: dict[str, Any], requirement: str) -> bool:
    if requirement == "workspace.attached":
        return bool(runtime["workspace"]["exists"])
    if requirement == "verify.pass_current_workspace":
        return (
            runtime["verify"]["status"] == "passed"
            and runtime["workspace"]["is_clean"]
            and runtime["verify"]["last_successful_fingerprint"]
            == runtime["workspace"]["content_fingerprint"]
        )
    return False


def assert_phase_transition_allowed(root: Path, task_id: str, target_phase: str) -> dict[str, Any]:
    contract = load_contract(root, task_id)
    runtime = load_runtime(root, task_id)
    current_phase = str(runtime["phase"]["name"])
    current_status = str(runtime["phase"]["status"])
    graph = phase_graph(contract)

    if target_phase == current_phase:
        if current_status == "running":
            raise PhaseTransitionError(f"phase already running: {current_phase}")
        return runtime

    if current_status == "running":
        raise PhaseTransitionError(
            f"cannot move from running phase {current_phase} to {target_phase}"
        )
    if current_status == "pending":
        raise PhaseTransitionError(
            f"cannot move from pending phase {current_phase} to {target_phase}"
        )
    if current_status == "failed":
        allowed_on_failure = {
            "review": {"implement", "review"},
            "verify": {"implement", "review", "verify"},
        }
        if target_phase in allowed_on_failure.get(current_phase, set()):
            return runtime
        raise PhaseTransitionError(
            f"failed phase {current_phase} can only retry or move to an allowed recovery phase"
        )

    allowed_next = set(graph.get(current_phase, {}).get("next", []))
    if target_phase not in allowed_next:
        raise PhaseTransitionError(f"invalid phase transition: {current_phase} -> {target_phase}")

    for requirement in graph.get(current_phase, {}).get("requires", []):
        if not phase_requirements(runtime, str(requirement)):
            raise PhaseRequirementError(
                f"phase transition {current_phase} -> {target_phase} is blocked by requirement: {requirement}"
            )
    return runtime


def assert_handoff_allowed(runtime: dict[str, Any]) -> None:
    if str(runtime["phase"]["status"]) == "running":
        raise PhaseTransitionError("cannot write handoff while a phase is still running")


def update_runtime_checkpoint_ref(
    root: Path, task_id: str, checkpoint_ref: str, writer: str
) -> dict[str, Any]:
    return mutate_runtime(
        root,
        task_id,
        writer,
        lambda payload: payload.__setitem__("checkpoint_ref", checkpoint_ref),
    )


def write_checkpoint(
    root: Path, task_id: str, runtime: dict[str, Any], reason: str, writer: str
) -> Path:
    directory = checkpoint_dir(root, task_id)
    index = next_index(directory, ".json")
    path = directory / f"{index:04d}.json"
    payload = checkpoint_payload(runtime, load_active_state(root), reason)
    write_json(path, payload)
    update_runtime_checkpoint_ref(root, task_id, relative_or_absolute(root, path), writer)
    append_task_journal_entry(
        root,
        task_id,
        f"{reason} @ {payload['created_at']}",
        [
            f"- Phase: `{runtime['phase']['name']}` / `{runtime['phase']['status']}`",
            f"- Branch: `{runtime['workspace']['branch'] or 'detached'}`",
            f"- Worktree: `{runtime['workspace']['worktree_id']}` / `{runtime['workspace']['site_kind']}`",
            f"- Verify: `{runtime['verify']['status']}`",
            f"- Checkpoint: `{relative_or_absolute(root, path)}`",
        ],
    )
    return path


def create_task(root: Path, title: str, goal: str, backend: str, task_id: str | None) -> Path:
    ensure_repo_dirs(root)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved_id = task_id or f"{timestamp}-{slugify(title)[:40]}"
    directory = task_dir(root, resolved_id)
    if directory.exists():
        raise FileExistsError(f"task directory already exists: {directory}")
    context_dir(root, resolved_id).mkdir(parents=True, exist_ok=True)
    handoff_dir(root, resolved_id).mkdir(parents=True, exist_ok=True)
    checkpoint_dir(root, resolved_id).mkdir(parents=True, exist_ok=True)

    write_json(
        contract_path(root, resolved_id),
        default_contract(resolved_id, title, goal, default_base_ref(root)),
    )
    write_json(verify_path(root, resolved_id), default_verify_profile())
    atomic_write_text(
        task_markdown_path(root, resolved_id), task_md_content(resolved_id, title, goal)
    )
    atomic_write_text(journal_path(root, resolved_id), journal_md_content(resolved_id, title))
    for phase in ("plan", "implement", "review"):
        write_jsonl(context_path(root, resolved_id, phase), context_entries_for_phase(phase))

    active_state = load_active_state(root)
    active_state["backend"] = backend
    active_state["control_mode"] = control_mode_for_backend(backend)
    active_state["driver"] = {"kind": backend, "adapter": adapter_for_backend(backend)}
    save_active_state(root, active_state)

    contract = load_contract(root, resolved_id)
    runtime = default_runtime(
        resolved_id,
        active_state,
        str(contract["branch_policy"]["base_ref"]),
        root,
    )
    writer = driver_run_id(backend)
    write_runtime(root, resolved_id, runtime, writer, 0)
    runtime = load_runtime(root, resolved_id)
    write_checkpoint(root, resolved_id, runtime, "task_created", writer)
    return directory


def parse_legacy_task_markdown(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    frontmatter: dict[str, str] = {}
    body = raw_text
    if raw_text.startswith("---\n"):
        _, _, remainder = raw_text.partition("---\n")
        frontmatter_block, separator, rest = remainder.partition("\n---\n")
        if separator:
            for line in frontmatter_block.splitlines():
                key, _, value = line.partition(":")
                if key and value:
                    frontmatter[key.strip()] = value.strip()
            body = rest

    sections: dict[str, str] = {}
    current_heading: str | None = None
    buffer: list[str] = []
    for line in body.splitlines():
        if line.startswith("# "):
            if current_heading is not None:
                sections[current_heading] = "\n".join(buffer).strip()
            current_heading = line[2:].strip()
            buffer = []
            continue
        buffer.append(line)
    if current_heading is not None:
        sections[current_heading] = "\n".join(buffer).strip()

    return {
        "task_id": frontmatter.get("task_id") or path.stem,
        "backend": frontmatter.get("owner_backend") or "claude",
        "title": sections.get("Title") or path.stem,
        "goal": sections.get("Goal") or "Migrate legacy task to the directory model.",
        "shared_context": sections.get("Shared Context") or "",
        "deliverables": sections.get("Deliverables") or "",
        "verification": sections.get("Verification") or "",
        "open_questions": sections.get("Open Questions") or "",
    }


def migrated_task_md_content(parsed: dict[str, Any], source_ref: str) -> str:
    shared_context = parsed["shared_context"] or "- None recorded."
    deliverables = parsed["deliverables"] or "- [ ] Define the concrete outputs for this task."
    verification = parsed["verification"] or "- [ ] Define the checks for this task."
    open_questions = parsed["open_questions"] or "- None yet."
    return f"""# {parsed['title']}

- Task ID: `{parsed['task_id']}`
- Goal: {parsed['goal']}

## Background

Migrated from legacy task file: `{source_ref}`.

## Shared Context

{shared_context}

## Scope

- Preserve the legacy task intent while moving to the directory model.

## Deliverables

{deliverables}

## Verification

{verification}

## Open Questions

{open_questions}

## Human Constraints

- Keep checkpoints, handoffs, and journal entries current enough that another controller can resume.
"""


def migrate_legacy_task(
    root: Path,
    legacy_path_input: Path,
    *,
    backend: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    legacy_path = legacy_path_input.resolve()
    if not legacy_path.exists():
        raise FileNotFoundError(f"legacy task file not found: {legacy_path}")
    if legacy_path.suffix != ".md":
        raise RuntimeError(f"legacy task file must be markdown: {legacy_path}")

    parsed = parse_legacy_task_markdown(legacy_path)
    resolved_backend = backend or str(parsed["backend"])
    if resolved_backend not in {"claude", "codex"}:
        resolved_backend = str(load_active_state(root)["backend"])
    target_dir = task_dir(root, str(parsed["task_id"]))
    if target_dir.exists():
        raise RuntimeError(f"target task directory already exists: {target_dir}")

    payload = {
        "task_id": str(parsed["task_id"]),
        "backend": resolved_backend,
        "legacy_path": relative_or_absolute(root, legacy_path),
        "target_dir": relative_or_absolute(root, target_dir),
        "title": str(parsed["title"]),
        "goal": str(parsed["goal"]),
    }
    if dry_run:
        return payload

    directory = create_task(
        root,
        title=str(parsed["title"]),
        goal=str(parsed["goal"]),
        backend=resolved_backend,
        task_id=str(parsed["task_id"]),
    )
    legacy_source_ref = relative_or_absolute(root, legacy_path)
    atomic_write_text(
        task_markdown_path(root, str(parsed["task_id"])),
        migrated_task_md_content(parsed, legacy_source_ref),
    )
    legacy_target = directory / "legacy-task.md"
    legacy_path.replace(legacy_target)
    append_task_journal_entry(
        root,
        str(parsed["task_id"]),
        f"legacy_task_migrated @ {now_iso()}",
        [
            f"- Source: `{legacy_source_ref}`",
            f"- Legacy copy: `{relative_or_absolute(root, legacy_target)}`",
            f"- Backend: `{resolved_backend}`",
        ],
    )
    runtime = load_runtime(root, str(parsed["task_id"]))
    write_checkpoint(
        root,
        str(parsed["task_id"]),
        runtime,
        "legacy_task_migrated",
        driver_run_id(resolved_backend),
    )
    remember_task(root, str(parsed["task_id"]))
    return payload


def switch_backend(root: Path, backend: str, reason: str, task_id: str | None) -> Path:
    current_state = load_active_state(root)
    state = {
        "backend": backend,
        "control_mode": control_mode_for_backend(backend),
        "driver": {"kind": backend, "adapter": adapter_for_backend(backend)},
        "task_id": task_id if task_id is not None else current_state.get("task_id"),
        "reason": reason,
        "switched_at": now_iso(),
    }
    return save_active_state(root, state)


def phase_input_paths(
    root: Path, task_id: str, phase: str
) -> tuple[list[dict[str, Any]], list[str], str | None]:
    contract = load_contract(root, task_id)
    phase_inputs = contract["phase_inputs"][phase]
    contexts: list[dict[str, Any]] = []
    for relative_path in phase_inputs.get("context", []):
        jsonl_path = task_dir(root, task_id) / relative_path
        if jsonl_path.exists():
            contexts.extend(read_jsonl(jsonl_path))
    specs = [str(item) for item in phase_inputs.get("specs", [])]
    return contexts, specs, phase_inputs.get("verify_profile")


def prompt_file_list(root: Path, task_id: str, phase: str) -> list[str]:
    contexts, specs, _ = phase_input_paths(root, task_id, phase)
    files = [
        "AGENTS.md",
        "CLAUDE.md",
        ".orchestration/README.md",
        relative_or_absolute(root, contract_path(root, task_id)),
        relative_or_absolute(root, task_markdown_path(root, task_id)),
    ]
    for entry in contexts:
        files.append(relative_or_absolute(root, task_dir(root, task_id) / entry["path"]))
    files.extend(specs)
    if phase == "verify":
        files.append(relative_or_absolute(root, verify_path(root, task_id)))
    seen: list[str] = []
    for item in files:
        if item not in seen:
            seen.append(item)
    return seen


def render_prompt(root: Path, phase: str, task_id: str, backend: str) -> str:
    active_state = load_active_state(root)
    contract = load_contract(root, task_id)
    contexts, specs, verify_profile = phase_input_paths(root, task_id, phase)
    file_lines = "\n".join(f"- `{item}`" for item in prompt_file_list(root, task_id, phase))
    context_lines = (
        "\n".join(
            f"- `{relative_or_absolute(root, task_dir(root, task_id) / entry['path'])}`: {entry.get('note', '')}"
            for entry in contexts
        )
        or "- None"
    )
    spec_lines = "\n".join(f"- `{spec}`" for spec in specs) or "- None"
    verify_lines = (
        f"- Verify profile: `{verify_profile}`" if verify_profile else "- Verify profile: none"
    )

    return f"""You are running the {phase} phase for {project_slug(root)}.

Acting backend: {backend}
Control mode: {active_state["control_mode"]}
Task id: {contract["id"]}
Task title: {contract["title"]}

Read these files first:
{file_lines}

Phase inputs:
Context files:
{context_lines}

Spec files:
{spec_lines}

Verification:
{verify_lines}

Rules:
- Treat `contract.json` as the source for phase routing.
- Keep `task.md`, `checkpoints/`, and `handoffs/` usable for the next controller.
- Do not invent a second task state file.
- Do not assume hooks will inject missing context for you.

Phase objective:
{PHASE_OBJECTIVES[phase]}
"""


def resolve_backend(root: Path, backend: str | None) -> str:
    return backend or str(load_active_state(root)["backend"])


def build_command(root: Path, phase: str, backend: str) -> list[str]:
    profile = load_profile(root, backend)
    replacements = {"cwd": str(root.resolve())}
    return [part.format(**replacements) for part in profile["commands"][phase]]


def driver_participant(
    root: Path,
    task_id: str,
    backend: str,
    *,
    state: str,
    session_ref: str | None,
    local_worktree_path: Path | None = None,
) -> dict[str, Any]:
    run_id = driver_run_id(backend)
    attachment = save_attachment(
        root,
        task_id,
        run_id,
        backend,
        "driver",
        session_ref,
        local_worktree_path=local_worktree_path,
    )
    return {
        "run_id": run_id,
        "kind": backend,
        "role": "driver",
        "state": state,
        "attachment_ref": relative_or_absolute(root, attachment),
        "session_ref": session_ref,
    }


def mutate_runtime_as_driver(
    root: Path,
    task_id: str,
    backend: str,
    state: str,
    mutator: Callable[[dict[str, Any], str], None],
    *,
    session_ref: str | None = None,
    local_worktree_path: Path | None = None,
) -> dict[str, Any]:
    contract = load_contract(root, task_id)
    participant = driver_participant(
        root,
        task_id,
        backend,
        state=state,
        session_ref=session_ref,
        local_worktree_path=local_worktree_path,
    )
    run_id = str(participant["run_id"])

    def wrapped(payload: dict[str, Any]) -> None:
        payload["control"] = {
            "mode": control_mode_for_backend(backend),
            "driver_ref": run_id,
            "phase_owner_ref": run_id,
            "execution_topology": "single",
        }
        upsert_participant(payload, participant)
        payload["workspace"] = workspace_state(root, str(contract["branch_policy"]["base_ref"]))
        mutator(payload, run_id)

    return mutate_runtime(root, task_id, run_id, wrapped)


def start_phase_runtime(
    root: Path,
    task_id: str,
    phase: str,
    backend: str,
    session_ref: str | None = None,
) -> dict[str, Any]:
    assert_phase_transition_allowed(root, task_id, phase)
    return mutate_runtime_as_driver(
        root,
        task_id,
        backend,
        "active",
        lambda payload, run_id: payload.__setitem__("phase", {"name": phase, "status": "running"}),
        session_ref=session_ref,
    )


def finish_phase_runtime(
    root: Path,
    task_id: str,
    phase: str,
    backend: str,
    *,
    succeeded: bool,
    session_ref: str | None = None,
) -> dict[str, Any]:
    return mutate_runtime_as_driver(
        root,
        task_id,
        backend,
        "finished",
        lambda payload, run_id: payload.__setitem__(
            "phase",
            {"name": phase, "status": "passed" if succeeded else "failed"},
        ),
        session_ref=session_ref,
    )


def start_verify_runtime(root: Path, task_id: str, backend: str) -> dict[str, Any]:
    started_at = now_iso()
    assert_phase_transition_allowed(root, task_id, "verify")
    return mutate_runtime_as_driver(
        root,
        task_id,
        backend,
        "active",
        lambda payload, run_id: (
            payload.__setitem__("phase", {"name": "verify", "status": "running"}),
            payload["verify"].update(
                {
                    "status": "running",
                    "runner_ref": "verify-runner",
                    "started_at": started_at,
                    "finished_at": None,
                    "last_run_fingerprint": None,
                }
            ),
        ),
    )


def finish_verify_runtime(root: Path, task_id: str, backend: str, exit_code: int) -> dict[str, Any]:
    finished_at = now_iso()

    def apply(payload: dict[str, Any], run_id: str) -> None:
        payload["phase"] = {
            "name": "verify",
            "status": "passed" if exit_code == 0 else "failed",
        }
        payload["verify"]["status"] = "passed" if exit_code == 0 else "failed"
        payload["verify"]["runner_ref"] = "verify-runner"
        payload["verify"]["finished_at"] = finished_at
        payload["verify"]["last_run_fingerprint"] = payload["workspace"]["content_fingerprint"]
        if exit_code == 0:
            payload["verify"]["last_successful_fingerprint"] = payload["workspace"][
                "content_fingerprint"
            ]

    return mutate_runtime_as_driver(root, task_id, backend, "finished", apply)


def write_handoff(root: Path, task_id: str, to_backend: str, summary: str) -> Path:
    ensure_repo_dirs(root)
    active = load_active_state(root)
    current_runtime = load_runtime(root, task_id)
    assert_handoff_allowed(current_runtime)
    runtime = mutate_runtime_as_driver(
        root,
        task_id,
        str(active["backend"]),
        "finished",
        lambda payload, run_id: payload.__setitem__("phase", {"name": "handoff", "status": "ready"}),
    )
    checkpoint = write_checkpoint(
        root, task_id, runtime, "handoff", driver_run_id(str(active["backend"]))
    )

    status_text = run_git(root, ["git", "status", "--short"])
    diff_text = run_git(root, ["git", "diff", "--stat"])
    directory = handoff_dir(root, task_id)
    index = next_index(directory, ".md")
    path = directory / f"{index:04d}.md"
    content = f"""# Handoff: {task_id}

- Generated at: {now_iso()}
- To backend: {to_backend}
- Control mode: {active["control_mode"]}
- Driver: `{active["driver"]["kind"]}`
- Phase owner ref: `{runtime["control"]["phase_owner_ref"]}`
- Current phase: `{runtime["phase"]["name"]}` / `{runtime["phase"]["status"]}`
- Branch: `{runtime["workspace"]["branch"] or "detached"}`
- Worktree id: `{runtime["workspace"]["worktree_id"]}`
- Head rev: `{runtime["workspace"]["head_rev"] or "not-set"}`
- Workspace clean: `{runtime["workspace"]["is_clean"]}`
- Workspace fingerprint: `{runtime["workspace"]["content_fingerprint"]}`
- Verify status: `{runtime["verify"]["status"]}`
- Checkpoint: `{relative_or_absolute(root, checkpoint)}`
- Task contract: `{relative_or_absolute(root, contract_path(root, task_id))}`
- Task brief: `{relative_or_absolute(root, task_markdown_path(root, task_id))}`

## Operator Summary
{summary or "Fill in what changed, what is blocked, and what must happen next."}

## Git Status
```text
{status_text}
```

## Diff Stat
```text
{diff_text}
```
"""
    atomic_write_text(path, content)
    return path


def verify_commands(root: Path, task_id: str) -> list[str]:
    return [str(item) for item in load_json(verify_path(root, task_id))["commands"]]


def bootstrap_commands_for_task(root: Path, task_id: str) -> tuple[str, list[str], str]:
    contract = load_contract(root, task_id)
    profile = str(contract["worktree_policy"]["bootstrap_profile"])
    profile_payload = BOOTSTRAP_PROFILES.get(profile)
    if profile_payload is None:
        raise RuntimeError(f"unsupported worktree bootstrap profile: {profile}")
    return profile, [str(item) for item in profile_payload["commands"]], str(profile_payload["runner"])


def worktree_root_for_task(root: Path, task_id: str) -> Path:
    return Path("/tmp") / f"{project_slug(root)}-worktrees" / task_id


def default_worktree_branch(task_id: str) -> str:
    return f"task/{task_id}"


def worktree_exists(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


def list_git_worktrees(root: Path) -> list[dict[str, Any]]:
    result = git_command(root, ["git", "worktree", "list", "--porcelain"])
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git worktree list failed"
        raise RuntimeError(message)

    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["worktree"] = value
        elif key == "HEAD":
            current["head_rev"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "detached":
            current["detached"] = True
        elif key == "locked":
            current["locked"] = value or True
        elif key == "prunable":
            current["prunable"] = value or True
    if current:
        entries.append(current)
    return entries


def local_branch_exists(root: Path, branch: str) -> bool:
    result = git_command(root, ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"])
    return result.returncode == 0


def inspect_branch_occupancy(root: Path, branch: str) -> dict[str, Any]:
    owners = []
    for entry in list_git_worktrees(root):
        if entry.get("branch") != branch:
            continue
        owners.append(
            {
                "path": str(Path(str(entry["worktree"])).resolve()),
                "head_rev": entry.get("head_rev"),
                "detached": bool(entry.get("detached", False)),
                "locked": entry.get("locked"),
                "prunable": entry.get("prunable"),
            }
        )
    return {
        "branch": branch,
        "branch_exists": local_branch_exists(root, branch),
        "occupied": bool(owners),
        "occupied_by": owners,
    }


def inspect_local_config_visibility(root: Path, workspace_root: Path) -> dict[str, Any]:
    root_visible = []
    workspace_visible = []
    missing_in_workspace = []
    for candidate in LOCAL_CONFIG_CANDIDATES:
        root_path = root / candidate
        workspace_path = workspace_root / candidate
        if root_path.exists():
            root_visible.append(candidate)
            if workspace_path.exists():
                workspace_visible.append(candidate)
            else:
                missing_in_workspace.append(candidate)
        elif workspace_path.exists():
            workspace_visible.append(candidate)
    return {
        "candidates": list(LOCAL_CONFIG_CANDIDATES),
        "root_visible": root_visible,
        "workspace_visible": workspace_visible,
        "missing_in_workspace": missing_in_workspace,
    }


def materialize_local_config(root: Path, workspace_root: Path) -> list[dict[str, Any]]:
    actions = []
    if workspace_root.resolve() == root.resolve():
        return actions
    for candidate in LOCAL_CONFIG_CANDIDATES:
        source = root / candidate
        target = workspace_root / candidate
        if not source.exists() or target.exists():
            continue
        relative_target = os.path.relpath(source, start=target.parent)
        target.symlink_to(relative_target, target_is_directory=source.is_dir())
        actions.append({"kind": "symlink", "path": candidate, "target": relative_target})
    return actions


def required_workspace_files(root: Path, task_id: str) -> list[Path]:
    return [
        Path("AGENTS.md"),
        Path("CLAUDE.md"),
        Path(".orchestration/README.md"),
        Path(relative_or_absolute(root, contract_path(root, task_id))),
        Path(relative_or_absolute(root, verify_path(root, task_id))),
    ]


def inspect_worktree_environment(root: Path, task_id: str, workspace_root: Path) -> dict[str, Any]:
    contract = load_contract(root, task_id)
    resolved_path = workspace_root.resolve()
    project_common_dir = git_common_dir(root)
    required_files = required_workspace_files(root, task_id)

    path_exists = resolved_path.exists()
    git_root = git_top_level(resolved_path) if path_exists else None
    workspace_common_dir = git_common_dir_for_workspace(resolved_path) if path_exists else None
    local_config = (
        inspect_local_config_visibility(root.resolve(), resolved_path) if path_exists else None
    )
    missing_files = (
        [rel.as_posix() for rel in required_files if not (resolved_path / rel).exists()]
        if path_exists
        else [rel.as_posix() for rel in required_files]
    )
    workspace = (
        workspace_state(resolved_path, str(contract["branch_policy"]["base_ref"]))
        if path_exists
        else None
    )
    checks = {
        "path_exists": path_exists,
        "git_root_matches_path": git_root == resolved_path,
        "same_clone_family": workspace_common_dir == project_common_dir,
        "required_files_present": not missing_files,
        "detached_head": bool(workspace["detached"]) if workspace is not None else None,
        "local_config_visible": (
            not bool(local_config["missing_in_workspace"]) if local_config is not None else None
        ),
    }
    issues: list[str] = []
    warnings: list[str] = []
    if not checks["path_exists"]:
        issues.append(f"workspace path does not exist: {resolved_path}")
    if path_exists and not checks["git_root_matches_path"]:
        issues.append(f"workspace path is not a git worktree root: {resolved_path}")
    if path_exists and not checks["same_clone_family"]:
        issues.append("workspace path does not belong to the same git common dir")
    if missing_files:
        warnings.append(f"workspace is missing required files: {', '.join(missing_files)}")
    if workspace is not None and workspace["detached"]:
        warnings.append("workspace is in detached HEAD state")
    if local_config is not None and local_config["missing_in_workspace"]:
        warnings.append(
            "workspace is missing local config files or dirs: "
            + ", ".join(local_config["missing_in_workspace"])
        )
    return {
        "task_id": task_id,
        "workspace_path": str(resolved_path),
        "bootstrap_profile": contract["worktree_policy"]["bootstrap_profile"],
        "requires_env_check": bool(contract["worktree_policy"]["requires_env_check"]),
        "checks": checks,
        "local_config": local_config,
        "missing_files": missing_files,
        "issues": issues,
        "warnings": warnings,
        "ok": not issues,
        "workspace": workspace,
    }


def attached_worktree_path(root: Path, task_id: str, backend: str) -> tuple[Path, str]:
    run_id = driver_run_id(backend)
    attachment = load_attachment(root, task_id, run_id)
    local_worktree_raw = attachment.get("local_worktree_path")
    if not local_worktree_raw:
        raise RuntimeError(
            f"attachment for {task_id} does not contain local_worktree_path: {run_id}"
        )
    return Path(str(local_worktree_raw)).expanduser().resolve(), relative_or_absolute(
        root, attachment_path(root, task_id, run_id)
    )


def restore_attachment_workspace(root: Path, task_id: str, backend: str) -> Path:
    run_id = driver_run_id(backend)
    resolved_path, attachment_ref = attached_worktree_path(root, task_id, backend)
    env_status = inspect_worktree_environment(root, task_id, resolved_path)
    if not env_status["ok"]:
        raise RuntimeError("; ".join(str(item) for item in env_status["issues"]))

    contract = load_contract(root, task_id)
    mutate_runtime_as_driver(
        root,
        task_id,
        backend,
        "active",
        lambda payload, driver_ref: (
            payload.__setitem__(
                "workspace",
                workspace_state(resolved_path, str(contract["branch_policy"]["base_ref"])),
            ),
            payload.__setitem__(
                "resume_from",
                {
                    "kind": "attachment",
                    "run_id": run_id,
                    "attachment_ref": attachment_ref,
                    "workspace_path": str(resolved_path),
                    "restored_at": now_iso(),
                },
            ),
        ),
        local_worktree_path=resolved_path,
    )
    runtime = load_runtime(root, task_id)
    write_checkpoint(root, task_id, runtime, "attachment_restored", run_id)
    return resolved_path


def create_worktree(
    root: Path,
    task_id: str,
    backend: str,
    *,
    branch: str | None = None,
    path: Path | None = None,
    base_ref: str | None = None,
    dry_run: bool = False,
) -> tuple[Path, str]:
    contract = load_contract(root, task_id)
    resolved_branch = branch or default_worktree_branch(task_id)
    resolved_base_ref = base_ref or str(contract["branch_policy"]["base_ref"])
    resolved_path = (path or worktree_root_for_task(root, task_id)).resolve()
    branch_status = inspect_branch_occupancy(root, resolved_branch)
    if branch_status["occupied"]:
        owner = branch_status["occupied_by"][0]
        raise RuntimeError(f"branch already occupied: {resolved_branch} -> {owner['path']}")
    command = ["git", "worktree", "add", str(resolved_path)]
    if branch_status["branch_exists"]:
        command.append(resolved_branch)
    else:
        command.extend(["-b", resolved_branch, resolved_base_ref])

    if dry_run:
        print("Command:", json.dumps(command, ensure_ascii=True))
        return resolved_path, resolved_branch

    if worktree_exists(resolved_path):
        raise FileExistsError(f"worktree path already exists and is not empty: {resolved_path}")

    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git worktree add failed"
        raise RuntimeError(message)

    env_status = inspect_worktree_environment(root, task_id, resolved_path)
    if not env_status["ok"]:
        raise RuntimeError("; ".join(str(item) for item in env_status["issues"]))

    mutate_runtime_as_driver(
        root,
        task_id,
        backend,
        "active",
        lambda payload, run_id: payload.__setitem__(
            "workspace", workspace_state(resolved_path, resolved_base_ref)
        ),
        local_worktree_path=resolved_path,
    )
    runtime = load_runtime(root, task_id)
    write_checkpoint(root, task_id, runtime, "worktree_created", driver_run_id(backend))
    return resolved_path, resolved_branch


def show_worktree_status(root: Path, task_id: str) -> str:
    runtime = load_runtime(root, task_id)
    workspace = runtime["workspace"]
    return json.dumps(
        {
            "task_id": task_id,
            "worktree_id": workspace["worktree_id"],
            "site_kind": workspace["site_kind"],
            "branch": workspace["branch"],
            "head_rev": workspace["head_rev"],
            "is_clean": workspace["is_clean"],
            "content_fingerprint": workspace["content_fingerprint"],
            "resume_from": runtime["resume_from"],
        },
        indent=2,
        ensure_ascii=True,
    )


def show_worktree_env_check(
    root: Path,
    task_id: str,
    *,
    backend: str | None = None,
    path: Path | None = None,
) -> str:
    resolved_backend = backend or str(load_active_state(root)["backend"])
    resolved_path = path
    attachment_ref: str | None = None
    if resolved_path is None:
        run_id = driver_run_id(resolved_backend)
        attachment = load_attachment(root, task_id, run_id)
        resolved_path = Path(str(attachment["local_worktree_path"])).expanduser().resolve()
        attachment_ref = relative_or_absolute(root, attachment_path(root, task_id, run_id))

    payload = inspect_worktree_environment(root, task_id, resolved_path)
    payload["backend"] = resolved_backend
    payload["attachment_ref"] = attachment_ref
    return json.dumps(payload, indent=2, ensure_ascii=True)


def show_worktree_branch_check(root: Path, task_id: str, branch: str | None = None) -> str:
    resolved_branch = branch or default_worktree_branch(task_id)
    contract = load_contract(root, task_id)
    payload = inspect_branch_occupancy(root, resolved_branch)
    payload["task_id"] = task_id
    payload["base_ref"] = str(contract["branch_policy"]["base_ref"])
    return json.dumps(payload, indent=2, ensure_ascii=True)


def inspect_attachment_health(root: Path, task_id: str) -> dict[str, Any]:
    entries = []
    ok_count = 0
    dangling_count = 0
    for path in list_attachments(root, task_id):
        payload = load_json(path)
        workspace_path_raw = payload.get("local_worktree_path")
        workspace_path = (
            Path(str(workspace_path_raw)).expanduser().resolve() if workspace_path_raw else None
        )
        if workspace_path is None:
            env_status = None
            issues = ["attachment does not contain local_worktree_path"]
            warnings: list[str] = []
            ok = False
        else:
            env_status = inspect_worktree_environment(root, task_id, workspace_path)
            issues = list(env_status["issues"])
            warnings = list(env_status["warnings"])
            ok = bool(env_status["ok"])
        if ok:
            ok_count += 1
        else:
            dangling_count += 1
        entries.append(
            {
                "run_id": payload.get("run_id"),
                "provider": payload.get("provider"),
                "role": payload.get("role"),
                "attachment_ref": relative_or_absolute(root, path),
                "workspace_path": str(workspace_path) if workspace_path is not None else None,
                "ok": ok,
                "issues": issues,
                "warnings": warnings,
                "env_check": env_status,
            }
        )
    return {
        "task_id": task_id,
        "attachment_count": len(entries),
        "ok_count": ok_count,
        "dangling_count": dangling_count,
        "attachments": entries,
    }


def show_attachment_health(root: Path, task_id: str) -> str:
    return json.dumps(inspect_attachment_health(root, task_id), indent=2, ensure_ascii=True)


def update_runtime_workspace_binding(
    root: Path,
    task_id: str,
    backend: str,
    workspace_path: Path,
    reason: str,
    resume_kind: str,
) -> Path:
    contract = load_contract(root, task_id)
    run_id = driver_run_id(backend)
    attachment_ref = relative_or_absolute(root, attachment_path(root, task_id, run_id))
    resolved_path = workspace_path.resolve()
    mutate_runtime_as_driver(
        root,
        task_id,
        backend,
        "active",
        lambda payload, driver_ref: (
            payload.__setitem__(
                "workspace",
                workspace_state(resolved_path, str(contract["branch_policy"]["base_ref"])),
            ),
            payload.__setitem__(
                "resume_from",
                {
                    "kind": resume_kind,
                    "run_id": run_id,
                    "attachment_ref": attachment_ref,
                    "workspace_path": str(resolved_path),
                    "updated_at": now_iso(),
                },
            ),
        ),
        local_worktree_path=resolved_path,
    )
    runtime = load_runtime(root, task_id)
    write_checkpoint(root, task_id, runtime, reason, run_id)
    return resolved_path


def remove_worktree(
    root: Path,
    task_id: str,
    *,
    backend: str,
    path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    resolved_path = path.resolve() if path is not None else attached_worktree_path(root, task_id, backend)[0]
    if resolved_path == root.resolve():
        raise RuntimeError("refusing to remove the main workspace path")

    env_status = inspect_worktree_environment(root, task_id, resolved_path)
    if not env_status["checks"]["path_exists"]:
        raise RuntimeError(f"workspace path does not exist: {resolved_path}")
    if not env_status["checks"]["git_root_matches_path"]:
        raise RuntimeError(f"workspace path is not a git worktree root: {resolved_path}")
    if env_status["workspace"] is None or env_status["workspace"]["site_kind"] != "linked":
        raise RuntimeError(f"workspace path is not a linked worktree: {resolved_path}")

    removed_branch = env_status["workspace"]["branch"]
    command = ["git", "worktree", "remove"]
    if force:
        command.append("--force")
    command.append(str(resolved_path))

    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git worktree remove failed"
        raise RuntimeError(message)

    prune_result = subprocess.run(
        ["git", "worktree", "prune"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if prune_result.returncode != 0:
        message = prune_result.stderr.strip() or prune_result.stdout.strip() or "git worktree prune failed"
        raise RuntimeError(message)

    new_workspace = update_runtime_workspace_binding(
        root,
        task_id,
        backend,
        root,
        "worktree_removed",
        "worktree_removed",
    )
    return {
        "task_id": task_id,
        "backend": backend,
        "removed_path": str(resolved_path),
        "removed_branch": removed_branch,
        "workspace_path": str(new_workspace),
        "force": force,
    }


def repair_attachment(
    root: Path,
    task_id: str,
    *,
    backend: str,
    path: Path,
) -> dict[str, Any]:
    resolved_path = path.resolve()
    env_status = inspect_worktree_environment(root, task_id, resolved_path)
    if not env_status["ok"]:
        raise RuntimeError("; ".join(str(item) for item in env_status["issues"]))

    updated_path = update_runtime_workspace_binding(
        root,
        task_id,
        backend,
        resolved_path,
        "attachment_repaired",
        "attachment_repaired",
    )
    return {
        "task_id": task_id,
        "backend": backend,
        "workspace_path": str(updated_path),
        "env_check": env_status,
    }


def auto_repair_attachment(root: Path, task_id: str, *, backend: str) -> dict[str, Any]:
    runtime = load_runtime(root, task_id)
    candidate_paths: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add_candidate(reason: str, path: Path) -> None:
        resolved = str(path.resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        candidate_paths.append((reason, path.resolve()))

    runtime_workspace = runtime.get("workspace", {})
    runtime_branch = str(runtime_workspace.get("branch") or default_worktree_branch(task_id))
    if runtime_workspace.get("site_kind") == "main":
        add_candidate("runtime_main_workspace", root)
    else:
        branch_status = inspect_branch_occupancy(root, runtime_branch)
        if len(branch_status["occupied_by"]) == 1:
            add_candidate("runtime_branch_owner", Path(str(branch_status["occupied_by"][0]["path"])))

    default_branch_status = inspect_branch_occupancy(root, default_worktree_branch(task_id))
    if len(default_branch_status["occupied_by"]) == 1:
        add_candidate("default_branch_owner", Path(str(default_branch_status["occupied_by"][0]["path"])))

    add_candidate("main_workspace", root)

    for reason, candidate in candidate_paths:
        env_status = inspect_worktree_environment(root, task_id, candidate)
        if not env_status["ok"]:
            continue
        payload = repair_attachment(root, task_id, backend=backend, path=candidate)
        payload["auto_reason"] = reason
        payload["changed"] = True
        return payload

    raise RuntimeError(f"no valid workspace candidate found for attachment auto repair: {task_id}")


def attachment_ref_set(runtime: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for participant in runtime.get("participants", []):
        attachment_ref = participant.get("attachment_ref")
        if attachment_ref:
            refs.add(str(attachment_ref))
    return refs


def prune_dangling_attachments(root: Path, task_id: str) -> dict[str, Any]:
    prune_result = subprocess.run(
        ["git", "worktree", "prune"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if prune_result.returncode != 0:
        message = prune_result.stderr.strip() or prune_result.stdout.strip() or "git worktree prune failed"
        raise RuntimeError(message)

    runtime = load_runtime(root, task_id)
    referenced_refs = attachment_ref_set(runtime)
    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for path in list_attachments(root, task_id):
        payload = load_json(path)
        workspace_path_raw = payload.get("local_worktree_path")
        workspace_path = (
            Path(str(workspace_path_raw)).expanduser().resolve() if workspace_path_raw else None
        )
        attachment_ref = relative_or_absolute(root, path)
        is_valid = workspace_path is not None and inspect_worktree_environment(
            root, task_id, workspace_path
        )["ok"]
        if is_valid:
            continue
        entry = {
            "run_id": payload.get("run_id"),
            "attachment_ref": attachment_ref,
            "workspace_path": str(workspace_path) if workspace_path is not None else None,
        }
        if attachment_ref in referenced_refs:
            skipped.append(entry)
            continue
        path.unlink()
        removed.append(entry)
    return {
        "task_id": task_id,
        "removed_count": len(removed),
        "skipped_count": len(skipped),
        "removed": removed,
        "skipped": skipped,
    }


def recover_detached_head(
    root: Path,
    task_id: str,
    *,
    backend: str,
    path: Path | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    resolved_path = path.resolve() if path is not None else attached_worktree_path(root, task_id, backend)[0]
    env_status = inspect_worktree_environment(root, task_id, resolved_path)
    if not env_status["ok"]:
        raise RuntimeError("; ".join(str(item) for item in env_status["issues"]))
    workspace = env_status["workspace"]
    if workspace is None:
        raise RuntimeError(f"workspace state is unavailable: {resolved_path}")

    resolved_branch = branch or workspace["branch"] or default_worktree_branch(task_id)
    branch_status = inspect_branch_occupancy(root, resolved_branch)
    if branch_status["occupied"]:
        owner = branch_status["occupied_by"][0]
        if Path(str(owner["path"])).resolve() != resolved_path:
            raise RuntimeError(f"branch already occupied: {resolved_branch} -> {owner['path']}")

    changed = False
    if workspace["detached"]:
        command = ["git", "switch"]
        if branch_status["branch_exists"]:
            command.append(resolved_branch)
        else:
            contract = load_contract(root, task_id)
            command.extend(["-c", resolved_branch, str(contract["branch_policy"]["base_ref"])])
        result = subprocess.run(
            command,
            cwd=resolved_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "git switch failed"
            raise RuntimeError(message)
        changed = True

    rebound_path = update_runtime_workspace_binding(
        root,
        task_id,
        backend,
        resolved_path,
        "detached_head_recovered",
        "detached_head_recovered",
    )
    return {
        "task_id": task_id,
        "backend": backend,
        "workspace_path": str(rebound_path),
        "branch": resolved_branch,
        "changed": changed,
    }


def run_worktree_bootstrap(
    root: Path,
    task_id: str,
    *,
    backend: str,
    path: Path | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], int]:
    profile, commands, resolved_runner = bootstrap_commands_for_task(root, task_id)
    resolved_path = path.resolve() if path is not None else attached_worktree_path(root, task_id, backend)[0]
    env_status = inspect_worktree_environment(root, task_id, resolved_path)
    payload = {
        "task_id": task_id,
        "backend": backend,
        "workspace_path": str(resolved_path),
        "profile": profile,
        "resolved_runner": resolved_runner,
        "commands": commands,
        "env_check": env_status,
        "log_path": None,
    }
    if not env_status["ok"]:
        return payload, 1
    if dry_run:
        return payload, 0

    setup_actions = materialize_local_config(root.resolve(), resolved_path)
    payload["setup_actions"] = setup_actions

    outputs: list[str] = []
    exit_code = 0
    for command in commands:
        result = subprocess.run(
            command,
            cwd=resolved_path,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            check=False,
        )
        outputs.append(f"$ {command}\n{result.stdout}{result.stderr}".strip())
        if result.returncode != 0 and exit_code == 0:
            exit_code = result.returncode

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = shared_log_dir(root, task_id) / f"{timestamp}-{task_id}-bootstrap.log"
    atomic_write_text(log_path, "\n\n".join(outputs) + "\n")
    payload["log_path"] = relative_or_absolute(root, log_path)

    runtime = load_runtime(root, task_id)
    write_checkpoint(
        root,
        task_id,
        runtime,
        "worktree_bootstrap_passed" if exit_code == 0 else "worktree_bootstrap_failed",
        driver_run_id(backend),
    )
    return payload, exit_code


def run_verify_phase(root: Path, task_id: str, dry_run: bool) -> int:
    prompt = render_prompt(root, "verify", task_id, "verify-runner")
    commands = verify_commands(root, task_id)
    if dry_run:
        print("Verify commands:", json.dumps(commands, ensure_ascii=True))
        print()
        print(prompt)
        return 0

    backend = str(load_active_state(root)["backend"])
    start_verify_runtime(root, task_id, backend)
    outputs: list[str] = []
    exit_code = 0
    for command in commands:
        result = subprocess.run(
            command,
            cwd=root,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            check=False,
        )
        outputs.append(f"$ {command}\n{result.stdout}{result.stderr}".strip())
        if result.returncode != 0 and exit_code == 0:
            exit_code = result.returncode

    finish_verify_runtime(root, task_id, backend, exit_code)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = shared_log_dir(root, task_id) / f"{timestamp}-{task_id}-verify.log"
    atomic_write_text(log_path, "\n\n".join(outputs) + "\n")
    print(relative_or_absolute(root, log_path))
    return exit_code


def run_phase(root: Path, phase: str, task_id: str, backend: str, dry_run: bool) -> int:
    if phase == "verify":
        return run_verify_phase(root, task_id, dry_run)

    prompt = render_prompt(root, phase, task_id, backend)
    command = build_command(root, phase, backend)
    if dry_run:
        print("Command:", json.dumps(command, ensure_ascii=True))
        print()
        print(prompt)
        return 0

    start_phase_runtime(root, task_id, phase, backend)
    result = subprocess.run(
        command,
        cwd=root,
        input=prompt,
        capture_output=True,
        text=True,
        check=False,
    )
    finish_phase_runtime(root, task_id, phase, backend, succeeded=result.returncode == 0)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = shared_log_dir(root, task_id) / f"{timestamp}-{task_id}-{phase}-{backend}.log"
    output = result.stdout.strip() or result.stderr.strip()
    atomic_write_text(log_path, (output or "(no output)") + "\n")
    print(relative_or_absolute(root, log_path))
    return result.returncode
