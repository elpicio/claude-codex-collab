from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.agent_proxy_core as agent_proxy_core
from scripts.agent_proxy_core import (
    create_task,
    load_active_state,
    mailbox_ack,
    mailbox_read,
    mailbox_result,
    mailbox_send,
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


def test_mailbox_send_read_ack_result_flow(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Add structured request/result flow",
        backend="claude",
        task_id="task-123",
    )

    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Implement mailbox v1",
        details="Follow docs/todo/claude-codex-mailbox.md",
    )

    codex_inbox = mailbox_read(root, "task-123", to_backend="codex", message_type="request")
    assert len(codex_inbox) == 1
    assert codex_inbox[0]["id"] == request["id"]
    assert codex_inbox[0]["status"] == "pending"

    acked = mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")
    assert acked["status"] == "acked"
    assert acked["ack"]["by"] == "codex"

    result = mailbox_result(
        root,
        "task-123",
        request_id=request["id"],
        from_backend="codex",
        status="succeeded",
        summary="Mailbox implemented with tests",
    )
    assert result["type"] == "result"
    assert result["status"] == "succeeded"
    assert result["reply_to"] == request["id"]
    assert result["to"] == "claude"

    claude_inbox = mailbox_read(root, "task-123", to_backend="claude", message_type="result")
    assert len(claude_inbox) == 1
    assert claude_inbox[0]["id"] == result["id"]

    request_after = mailbox_read(root, "task-123", message_type="request")[0]
    assert request_after["status"] == "resolved"
    assert request_after["resolution"] == "succeeded"
    assert request_after["result_id"] == result["id"]


@pytest.mark.parametrize("status", ["failed", "cancelled", "retry_requested"])
def test_mailbox_result_status_variants(tmp_path: Path, status: str) -> None:
    root = tmp_path / f"demo-repo-{status}"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Track result status variants",
        backend="claude",
        task_id="task-123",
    )
    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Run implementation step",
    )
    mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")

    result = mailbox_result(
        root,
        "task-123",
        request_id=request["id"],
        from_backend="codex",
        status=status,
        summary=f"Run finished with {status}",
    )

    assert result["status"] == status
    request_after = mailbox_read(root, "task-123", message_type="request")[0]
    assert request_after["resolution"] == status


def test_mailbox_ack_rejects_wrong_receiver(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Validate mailbox ack receiver",
        backend="claude",
        task_id="task-123",
    )
    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Implement mailbox",
    )

    with pytest.raises(ValueError, match="not addressed to backend"):
        mailbox_ack(root, "task-123", message_id=request["id"], by_backend="claude")


def test_mailbox_ack_rejects_duplicate_ack(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Reject duplicate mailbox ack",
        backend="claude",
        task_id="task-123",
    )
    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Implement mailbox",
    )
    mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")

    with pytest.raises(ValueError, match="already acknowledged"):
        mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")


def test_mailbox_ack_reports_resolved_before_acknowledged(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Report resolved state explicitly",
        backend="claude",
        task_id="task-123",
    )
    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Implement mailbox",
    )
    mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")
    mailbox_result(
        root,
        "task-123",
        request_id=request["id"],
        from_backend="codex",
        status="succeeded",
        summary="done",
    )

    with pytest.raises(ValueError, match="already resolved"):
        mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")


def test_mailbox_result_requires_ack_before_resolve(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Enforce request ack before result",
        backend="claude",
        task_id="task-123",
    )
    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Implement mailbox",
    )

    with pytest.raises(ValueError, match="must be acknowledged before result"):
        mailbox_result(
            root,
            "task-123",
            request_id=request["id"],
            from_backend="codex",
            status="succeeded",
            summary="done",
        )


def test_mailbox_result_rejects_resolving_request_twice(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Reject duplicate result writes",
        backend="claude",
        task_id="task-123",
    )
    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Implement mailbox",
    )
    mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")
    mailbox_result(
        root,
        "task-123",
        request_id=request["id"],
        from_backend="codex",
        status="succeeded",
        summary="done",
    )

    with pytest.raises(ValueError, match="already resolved"):
        mailbox_result(
            root,
            "task-123",
            request_id=request["id"],
            from_backend="codex",
            status="succeeded",
            summary="done-again",
        )


def test_mailbox_read_limit_is_oldest_first(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Validate limit direction",
        backend="claude",
        task_id="task-123",
    )
    mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="first",
    )
    mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="second",
    )
    mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="third",
    )

    messages = mailbox_read(
        root,
        "task-123",
        to_backend="codex",
        message_type="request",
        limit=2,
    )
    assert [item["payload"]["summary"] for item in messages] == ["first", "second"]


def test_mailbox_read_unacked_requires_request_type(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Keep unacked polling request-only",
        backend="claude",
        task_id="task-123",
    )
    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Implement mailbox",
    )
    mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")
    mailbox_result(
        root,
        "task-123",
        request_id=request["id"],
        from_backend="codex",
        status="succeeded",
        summary="done",
    )

    with pytest.raises(ValueError, match="requires message_type='request'"):
        mailbox_read(root, "task-123", only_unacked=True)

    with pytest.raises(ValueError, match="requires message_type='request'"):
        mailbox_read(root, "task-123", message_type="result", only_unacked=True)


def test_mailbox_read_unacked_returns_only_pending_requests(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Filter only pending requests",
        backend="claude",
        task_id="task-123",
    )
    first = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="first",
    )
    mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="second",
    )
    mailbox_send(
        root,
        "task-123",
        from_backend="codex",
        to_backend="claude",
        summary="third",
    )
    mailbox_ack(root, "task-123", message_id=first["id"], by_backend="codex")

    messages = mailbox_read(
        root,
        "task-123",
        message_type="request",
        only_unacked=True,
    )
    assert len(messages) == 2
    assert [item["payload"]["summary"] for item in messages] == ["second", "third"]
    assert {str(item["to"]) for item in messages} == {"codex", "claude"}
    assert all(item["status"] == "pending" for item in messages)

    codex_messages = mailbox_read(
        root,
        "task-123",
        to_backend="codex",
        message_type="request",
        only_unacked=True,
    )
    assert len(codex_messages) == 1
    assert codex_messages[0]["payload"]["summary"] == "second"


def test_mailbox_read_reports_domain_error_for_missing_task(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)

    with pytest.raises(ValueError, match="task not found: task-missing"):
        mailbox_read(root, "task-missing", message_type="request")


def test_mailbox_read_reports_domain_error_for_unreadable_contract(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    task_root = root / ".orchestration" / "tasks" / "task-bad"
    task_root.mkdir(parents=True)
    (task_root / "contract.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="task contract unreadable: task-bad"):
        mailbox_read(root, "task-bad", message_type="request")


def test_mailbox_read_reports_domain_error_for_permission_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)

    def raise_permission_error(*args: object, **kwargs: object) -> dict[str, object]:
        raise PermissionError("permission denied")

    monkeypatch.setattr(agent_proxy_core, "load_contract", raise_permission_error)
    with pytest.raises(ValueError, match="task contract unreadable: task-denied"):
        mailbox_read(root, "task-denied", message_type="request")


def test_mailbox_ack_rejects_result_message(tmp_path: Path) -> None:
    root = tmp_path / "demo-repo"
    init_repo(root)
    create_task(
        root,
        title="Mailbox v1",
        goal="Keep ack semantics request-only",
        backend="claude",
        task_id="task-123",
    )
    request = mailbox_send(
        root,
        "task-123",
        from_backend="claude",
        to_backend="codex",
        summary="Implement mailbox",
    )
    mailbox_ack(root, "task-123", message_id=request["id"], by_backend="codex")
    result = mailbox_result(
        root,
        "task-123",
        request_id=request["id"],
        from_backend="codex",
        status="succeeded",
        summary="done",
    )

    with pytest.raises(ValueError, match="only supports request"):
        mailbox_ack(root, "task-123", message_id=result["id"], by_backend="claude")
