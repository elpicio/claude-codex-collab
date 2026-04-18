# Shared Control Plane

这个项目采用 Claude / Codex 共享控制面。

## 先读入口

- `AGENTS.md`
- `memory/current/INDEX.md`
- `.orchestration/README.md`
- `.orchestration/specs/index.md`
- `.orchestration/specs/documentation.md`

## 协作方式

- 任务契约放 `.orchestration/tasks/<task-id>/`
- 高频运行态放 `git common dir/<repo-name>/`
- `.claude/` 和 `.codex/` 都只是 adapter
- `claude_codex` 和 `codex_native` 两种模式共享同一套任务状态

## 常用命令

```bash
python -m scripts.agent_proxy status
python -m scripts.agent_proxy new-task --title "..." --goal "..."
python -m scripts.agent_proxy run --phase plan --task-id <task-id>
python -m scripts.agent_proxy run --phase implement --task-id <task-id>
python -m scripts.agent_proxy run --phase review --task-id <task-id>
python -m scripts.agent_proxy run --phase verify --task-id <task-id>
```
