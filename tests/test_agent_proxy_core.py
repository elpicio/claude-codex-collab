from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.agent_proxy_core import (
    create_task,
    load_active_state,
    load_runtime,
    remember_task,
    shared_runtime_path,
    switch_backend,
)
from scripts.agent_proxy_nl import parse_request


def init_repo(root: Path) -> None:
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, capture_output=True, text=True, check=True)
    (root / "AGENTS.md").write_text("bootstrap\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("bootstrap\n", encoding="utf-8")
    (root / ".orchestration" / "README.md").parent.mkdir(parents=True, exist_ok=True)
    (root / ".orchestration" / "README.md").write_text("control plane\n", encoding="utf-8")


def test_create_task_writes_contract_runtime_and_context(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)

    directory = create_task(
        root,
        title="Upgrade Control Plane",
        goal="Bootstrap shared task state",
        backend="claude",
        task_id="task-123",
    )

    assert directory == root / ".orchestration" / "tasks" / "task-123"
    assert (directory / "contract.json").exists()
    assert (directory / "task.md").exists()
    assert (directory / "verify.json").exists()
    assert (directory / "context" / "plan.jsonl").exists()
    assert (directory / "context" / "implement.jsonl").exists()
    assert (directory / "context" / "review.jsonl").exists()
    assert shared_runtime_path(root, "task-123").exists()

    runtime = load_runtime(root, "task-123")
    assert runtime["task_id"] == "task-123"
    assert runtime["control"]["mode"] == "claude_codex"
    assert runtime["phase"]["name"] == "plan"


def test_parse_request_keeps_action_order() -> None:
    actions = parse_request("切到 codex，然后创建 monitor 任务，目标：实现共享控制面")
    assert [action.name for action in actions] == ["switch", "new-task"]
    assert actions[0].params["backend"] == "codex"
    assert actions[1].params["title"] == "monitor"


def test_switch_backend_preserves_task_id_when_not_provided(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)

    remember_task(root, "task-123")
    switch_backend(root, "codex", "manual switch", None)

    state = load_active_state(root)
    assert state["backend"] == "codex"
    assert state["control_mode"] == "codex_native"
    assert state["task_id"] == "task-123"


def test_session_start_hook_switches_backend_and_keeps_active_task(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)

    remember_task(root, "task-123")
    switch_backend(root, "claude", "seed state", None)

    hook = Path(__file__).resolve().parents[1] / ".orchestration" / "hooks" / "session_start.py"
    result = subprocess.run(
        [
            sys.executable,
            str(hook),
            "--backend",
            "codex",
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    output = json.loads(result.stdout)
    state = load_active_state(root)

    assert state["backend"] == "codex"
    assert state["control_mode"] == "codex_native"
    assert state["task_id"] == "task-123"
    assert state["reason"] == "session_start:codex"
    assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Active task: task-123" in output["hookSpecificOutput"]["additionalContext"]
