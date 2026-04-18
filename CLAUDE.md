# Shared Control Plane Project Instruction

## 项目概况

这个仓库提供 Claude / Codex 的共享控制面脚手架。

- 共享控制面在 `.orchestration/`
- 共享工作集在 `memory/current/`
- 当前状态入口在 `docs/project-status.md`
- 可执行入口在 `scripts/`

## 先读哪里

- `memory/current/INDEX.md`
- `docs/project-status.md`
- `.orchestration/README.md`
- `.orchestration/specs/index.md`
- `.orchestration/specs/documentation.md`

如果当前任务已经建立，再读：

- `.orchestration/tasks/<task-id>/contract.json`
- `.orchestration/tasks/<task-id>/task.md`
- `.orchestration/tasks/<task-id>/context/<phase>.jsonl`
- `.orchestration/tasks/<task-id>/verify.json`
- `.orchestration/tasks/<task-id>/checkpoints/`
- `.orchestration/tasks/<task-id>/handoffs/`

## 常用命令

```bash
python -m scripts.agent_proxy status
python -m scripts.check_documentation_layout
python -m pytest -q tests
```

## 操作原则

### 1. Plan First

非 trivial 任务先对齐 plan，再进入 implement。

### 2. Verification Before Done

做完必须有 verify 结果。没验证就明确写没验证。

### 3. Capture Discoveries

会影响后续协作的发现要写进 `docs/`、`memory/` 或 task 目录，不留在会话里。

### 4. Shared State First

任务状态只能写进 `.orchestration/tasks/<task-id>/` 和 shared runtime，不能各自退回 `.claude/` 或 `.codex/` 私有状态。

## 文档与 Memory

- 正式文档放 `docs/`
- 待办放 `docs/todo/`
- 归档材料放 `docs/archive/`
- 当前共享工作集放 `memory/current/`
- 旧摘要放 `memory/history/`
- 本机临时记忆放 `git common dir/<repo-name>/memory/`
- `.claude/` 不再保存项目共享记忆

## 多 Agent 协作

- Claude 和 Codex 共用 `.orchestration/` 控制面
- 任务状态放 `.orchestration/tasks/<task-id>/` 和 shared runtime
- `.claude/` 和 `.codex/` 都是 adapter，不是状态真源
- `.orchestration/codex/` 是 Codex adapter 真源，`.codex/` 是 mirror
- 任务切换、handoff、phase 运行、worktree 管理统一走 `python -m scripts.agent_proxy`
