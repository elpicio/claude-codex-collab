"""Natural-language parsing for the orchestration helper."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

BACKEND_RE = re.compile(r"\b(?P<backend>claude|codex)\b", re.IGNORECASE)
TASK_ID_HINT_RE = re.compile(
    r"(?:task[-_ ]?id|任务id|任务编号)\s*[:：]?\s*(?P<task_id>[\w-]+)",
    re.IGNORECASE,
)
BARE_TASK_ID_RE = re.compile(r"\b(?P<task_id>task[-_][\w-]+)\b", re.IGNORECASE)
SWITCH_RE = re.compile(
    r"(?:切到|切换到|切回|切换回|改用|改成|换成)\s*(?P<backend>claude|codex)",
    re.IGNORECASE,
)
TASK_RE = re.compile(
    r"(?:创建|新建|建一个|建个|开一个|开个)\s*(?P<title>[^，。；;!?]*?)(?:任务|task)",
    re.IGNORECASE,
)
HANDOFF_RE = re.compile(
    r"(?:交接给|交还给|移交给|交给|还给|handoff to)\s*(?P<backend>claude|codex)",
    re.IGNORECASE,
)
STATUS_RE = re.compile(r"(状态|当前后端|谁在主导|active backend|backend status)", re.IGNORECASE)
RUN_RE = re.compile(
    r"(?:(?:运行|执行|跑|预览|查看|看|进入)\s*(?P<phase1>plan|implement|review|verify|规划|计划|实现|执行|审查|评审|验证)"
    r"|(?P<phase2>plan|implement|review|verify|规划|计划|实现|执行|审查|评审|验证)\s*(?:阶段|phase))",
    re.IGNORECASE,
)
GOAL_RE = re.compile(
    r"(?:目标|goal|用于|为了|目的是|要做的是|要交付的是)\s*[:：]?\s*(?P<goal>[^。！？!?]+)",
    re.IGNORECASE,
)
SUMMARY_RE = re.compile(
    r"(?:总结|说明|summary|备注)\s*[:：]?\s*(?P<summary>[^。！？!?]+)",
    re.IGNORECASE,
)
PREVIEW_RE = re.compile(r"(dry-run|预览|只看|不要执行|先看看|试运行)", re.IGNORECASE)
FORCE_RE = re.compile(r"\bforce\b|强制", re.IGNORECASE)
PATH_HINT_RE = re.compile(
    r"(?:路径|path|目录|workspace)\s*[:：]?\s*(?P<path>(?:\.{1,2}/|/)?[^\s，。；;!?]+)",
    re.IGNORECASE,
)
PATH_TOKEN_RE = re.compile(r"(?P<path>(?:\.{1,2}/|/)[^\s，。；;!?]+)", re.IGNORECASE)
LEGACY_PATH_RE = re.compile(r"(?P<path>(?:\.{1,2}/)?[^\s，。；;!?]+\.md)\b", re.IGNORECASE)
BRANCH_RE = re.compile(r"(?:分支|branch)\s*[:：]?\s*(?P<branch>[\w./-]+)", re.IGNORECASE)
BASE_REF_RE = re.compile(
    r"(?:base[-_ ]?ref|基线|基准分支|起始分支)\s*[:：]?\s*(?P<base_ref>[\w./-]+)",
    re.IGNORECASE,
)
LEGACY_TASK_RE = re.compile(
    r"(?:迁移|导入|转换).{0,20}(?:legacy\s*task|旧任务|单文件任务|markdown任务)",
    re.IGNORECASE,
)
WORKTREE_CREATE_RE = re.compile(
    r"(?:创建|新建|建立|开(?:一个|个)?).{0,20}(?:worktree|工作树)"
    r"|(?:worktree|工作树).{0,20}(?:创建|新建|建立)",
    re.IGNORECASE,
)
WORKTREE_REMOVE_RE = re.compile(
    r"(?:删除|移除|清理).{0,20}(?:worktree|工作树)"
    r"|(?:worktree|工作树).{0,20}(?:删除|移除|清理)",
    re.IGNORECASE,
)
WORKTREE_STATUS_RE = re.compile(
    r"(?:查看|显示|看看|看).{0,20}(?:worktree|工作树).{0,20}(?:状态|信息)"
    r"|(?:worktree|工作树).{0,20}(?:状态|信息)",
    re.IGNORECASE,
)
WORKTREE_ENV_RE = re.compile(
    r"(?:env-check|环境检查|环境校验|本地配置检查|配置可见性检查)"
    r"|(?:检查|校验|查看).{0,20}(?:worktree|工作树).{0,20}(?:环境|env|本地配置|配置可见性)"
    r"|(?:环境|env|本地配置|配置可见性).{0,20}(?:检查|校验).{0,20}(?:worktree|工作树)",
    re.IGNORECASE,
)
WORKTREE_BRANCH_RE = re.compile(
    r"(?:branch-check|分支占用检查|分支绑定检查)"
    r"|(?:检查|查看|校验).{0,20}(?:分支|branch).{0,20}(?:占用|绑定|worktree|工作树)"
    r"|(?:分支|branch).{0,20}(?:占用|绑定).{0,20}(?:检查|查看|校验)",
    re.IGNORECASE,
)
WORKTREE_BOOTSTRAP_RE = re.compile(
    r"(?:bootstrap|初始化worktree|初始化工作树|准备worktree|准备工作树)"
    r"|(?:bootstrap|初始化|准备).{0,20}(?:worktree|工作树)"
    r"|(?:worktree|工作树).{0,20}(?:bootstrap|初始化|准备)",
    re.IGNORECASE,
)
WORKTREE_RESTORE_RE = re.compile(
    r"(?:恢复|还原|restore).{0,20}(?:attachment|绑定|workspace|工作区)"
    r"|(?:attachment|绑定|workspace|工作区).{0,20}(?:恢复|还原|restore)",
    re.IGNORECASE,
)
WORKTREE_RECOVER_HEAD_RE = re.compile(
    r"(?:recover[- ]?head|恢复head|恢复HEAD|修复head|修复HEAD)"
    r"|(?:恢复|修复|接回).{0,12}(?:head|HEAD|detached\s*head|task branch|分支)"
    r"|(?:detached\s*head).{0,12}(?:恢复|修复|接回)",
    re.IGNORECASE,
)
ATTACHMENT_CHECK_RE = re.compile(
    r"(?:attachment-check|查看attachment状态|查看挂载状态|检查attachment|检查挂载|检查绑定)"
    r"|(?:检查|查看|校验).{0,20}(?:attachment|挂载|绑定).{0,20}(?:状态|健康|是否失效)?",
    re.IGNORECASE,
)
ATTACHMENT_AUTO_REPAIR_RE = re.compile(
    r"(?:attachment-auto-repair|auto[- ]?repair).{0,20}(?:attachment|挂载|绑定)"
    r"|(?:自动修复).{0,20}(?:attachment|挂载|绑定)"
    r"|(?:attachment|挂载|绑定).{0,20}(?:自动修复|auto[- ]?repair)",
    re.IGNORECASE,
)
ATTACHMENT_REPAIR_RE = re.compile(
    r"(?:attachment-repair|repair).{0,20}(?:attachment|挂载|绑定)"
    r"|(?:修复).{0,20}(?:attachment|挂载|绑定)"
    r"|(?:attachment|挂载|绑定).{0,20}(?:修复|repair)",
    re.IGNORECASE,
)
ATTACHMENT_PRUNE_RE = re.compile(
    r"(?:attachment-prune|prune).{0,20}(?:attachment|挂载|绑定)"
    r"|(?:清理|删除).{0,20}(?:dangling|悬挂|失效).{0,20}(?:attachment|挂载|绑定)"
    r"|(?:attachment|挂载|绑定).{0,20}(?:prune|清理)",
    re.IGNORECASE,
)
PHASE_MAP = {
    "plan": "plan",
    "规划": "plan",
    "计划": "plan",
    "implement": "implement",
    "实现": "implement",
    "执行": "implement",
    "review": "review",
    "审查": "review",
    "评审": "review",
    "verify": "verify",
    "验证": "verify",
}


@dataclass(frozen=True)
class ParsedAction:
    name: str
    params: dict[str, Any]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_task_id(text: str) -> str | None:
    match = TASK_ID_HINT_RE.search(text)
    return match.group("task_id") if match else None


def extract_goal(text: str, fallback: str) -> str:
    match = GOAL_RE.search(text)
    if not match:
        return fallback
    return match.group("goal").strip(" ，。；;")


def extract_summary(text: str) -> str:
    match = SUMMARY_RE.search(text)
    if match:
        return match.group("summary").strip(" ，。；;")
    return clean_text(text)


def extract_backend(text: str) -> str | None:
    match = BACKEND_RE.search(text)
    return match.group("backend").lower() if match else None


def extract_task_reference(text: str) -> str | None:
    hinted = extract_task_id(text)
    if hinted:
        return hinted
    match = BARE_TASK_ID_RE.search(text)
    return match.group("task_id") if match else None


def extract_branch(text: str) -> str | None:
    match = BRANCH_RE.search(text)
    return match.group("branch") if match else None


def extract_base_ref(text: str) -> str | None:
    match = BASE_REF_RE.search(text)
    return match.group("base_ref") if match else None


def extract_path(text: str, *, markdown_only: bool = False) -> str | None:
    match = PATH_HINT_RE.search(text)
    if match:
        path = match.group("path")
        if not markdown_only or path.endswith(".md"):
            return path
    if markdown_only:
        legacy = LEGACY_PATH_RE.search(text)
        return legacy.group("path") if legacy else None
    token = PATH_TOKEN_RE.search(text)
    return token.group("path") if token else None


def detect_switch(text: str) -> tuple[int, ParsedAction] | None:
    match = SWITCH_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "switch",
        {
            "backend": match.group("backend").lower(),
            "reason": clean_text(text),
            "task_id": extract_task_id(text),
        },
    )


def detect_new_task(text: str) -> tuple[int, ParsedAction] | None:
    match = TASK_RE.search(text)
    if not match:
        return None
    raw_title = match.group("title").strip(" ，。；;")
    title = re.sub(r"^(?:一个|个)\s*", "", raw_title) or "临时任务"
    return match.start(), ParsedAction(
        "new-task",
        {
            "title": title,
            "goal": extract_goal(text, title),
            "backend": extract_backend(text),
            "task_id": extract_task_reference(text),
        },
    )


def detect_run(text: str) -> tuple[int, ParsedAction] | None:
    match = RUN_RE.search(text)
    if not match:
        return None
    raw_phase = (match.group("phase1") or match.group("phase2") or "").lower()
    return match.start(), ParsedAction(
        "run",
        {
            "phase": PHASE_MAP[raw_phase],
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
            "dry_run": bool(PREVIEW_RE.search(text)),
        },
    )


def detect_handoff(text: str) -> tuple[int, ParsedAction] | None:
    match = HANDOFF_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "handoff",
        {
            "to": match.group("backend").lower(),
            "task_id": extract_task_reference(text),
            "summary": extract_summary(text),
        },
    )


def detect_migrate_legacy_task(text: str) -> tuple[int, ParsedAction] | None:
    if not LEGACY_TASK_RE.search(text):
        return None
    return 0, ParsedAction(
        "migrate-legacy-task",
        {
            "path": extract_path(text, markdown_only=True),
            "backend": extract_backend(text),
            "dry_run": bool(PREVIEW_RE.search(text)),
        },
    )


def detect_worktree_create(text: str) -> tuple[int, ParsedAction] | None:
    match = WORKTREE_CREATE_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-create",
        {
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
            "branch": extract_branch(text),
            "path": extract_path(text),
            "base_ref": extract_base_ref(text),
            "dry_run": bool(PREVIEW_RE.search(text)),
        },
    )


def detect_worktree_remove(text: str) -> tuple[int, ParsedAction] | None:
    match = WORKTREE_REMOVE_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-remove",
        {
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
            "path": extract_path(text),
            "force": bool(FORCE_RE.search(text)),
        },
    )


def detect_worktree_recover_head(text: str) -> tuple[int, ParsedAction] | None:
    match = WORKTREE_RECOVER_HEAD_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-recover-head",
        {
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
            "path": extract_path(text),
            "branch": extract_branch(text),
        },
    )


def detect_worktree_env_check(text: str) -> tuple[int, ParsedAction] | None:
    match = WORKTREE_ENV_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-env-check",
        {
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
            "path": extract_path(text),
        },
    )


def detect_worktree_branch_check(text: str) -> tuple[int, ParsedAction] | None:
    match = WORKTREE_BRANCH_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-branch-check",
        {
            "task_id": extract_task_reference(text),
            "branch": extract_branch(text),
        },
    )


def detect_worktree_bootstrap(text: str) -> tuple[int, ParsedAction] | None:
    match = WORKTREE_BOOTSTRAP_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-bootstrap",
        {
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
            "path": extract_path(text),
            "dry_run": bool(PREVIEW_RE.search(text)),
        },
    )


def detect_attachment_check(text: str) -> tuple[int, ParsedAction] | None:
    match = ATTACHMENT_CHECK_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction("worktree-attachment-check", {"task_id": extract_task_reference(text)})


def detect_attachment_auto_repair(text: str) -> tuple[int, ParsedAction] | None:
    match = ATTACHMENT_AUTO_REPAIR_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-attachment-auto-repair",
        {
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
        },
    )


def detect_attachment_repair(text: str) -> tuple[int, ParsedAction] | None:
    if ATTACHMENT_AUTO_REPAIR_RE.search(text):
        return None
    match = ATTACHMENT_REPAIR_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-attachment-repair",
        {
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
            "path": extract_path(text),
        },
    )


def detect_attachment_prune(text: str) -> tuple[int, ParsedAction] | None:
    match = ATTACHMENT_PRUNE_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-attachment-prune",
        {"task_id": extract_task_reference(text)},
    )


def detect_worktree_restore(text: str) -> tuple[int, ParsedAction] | None:
    match = WORKTREE_RESTORE_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction(
        "worktree-restore",
        {
            "task_id": extract_task_reference(text),
            "backend": extract_backend(text),
        },
    )


def detect_worktree_status(text: str) -> tuple[int, ParsedAction] | None:
    match = WORKTREE_STATUS_RE.search(text)
    if not match:
        return None
    return match.start(), ParsedAction("worktree-status", {"task_id": extract_task_reference(text)})


def detect_status(text: str) -> ParsedAction | None:
    if STATUS_RE.search(text):
        return ParsedAction("status", {})
    return None


def parse_request(text: str) -> list[ParsedAction]:
    request = clean_text(text)
    if not request:
        raise ValueError("Natural-language request is empty.")

    indexed_actions = []
    for detector in (
        detect_switch,
        detect_new_task,
        detect_migrate_legacy_task,
        detect_run,
        detect_handoff,
        detect_worktree_create,
        detect_worktree_remove,
        detect_worktree_recover_head,
        detect_worktree_env_check,
        detect_worktree_branch_check,
        detect_worktree_bootstrap,
        detect_attachment_check,
        detect_attachment_auto_repair,
        detect_attachment_repair,
        detect_attachment_prune,
        detect_worktree_restore,
        detect_worktree_status,
    ):
        detected = detector(request)
        if detected:
            indexed_actions.append(detected)

    if indexed_actions:
        indexed_actions.sort(key=lambda item: item[0])
        return [action for _, action in indexed_actions]

    status = detect_status(request)
    if status:
        return [status]

    backend = BACKEND_RE.search(request)
    if backend:
        return [
            ParsedAction(
                "switch",
                {
                    "backend": backend.group("backend").lower(),
                    "reason": request,
                    "task_id": extract_task_id(request),
                },
            )
        ]

    raise ValueError(f"Could not understand request: {request}")
