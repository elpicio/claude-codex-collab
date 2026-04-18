# Documentation And Memory Spec

这份文档定义 repo 内文档、项目 memory、任务状态和本地 memory 的边界。

## 五层结构

- `.orchestration/specs/`
  - 共享规范真源。
- `.orchestration/tasks/<task-id>/`
  - 单个任务的契约、checkpoint、handoff、verify 和恢复材料。
- `memory/`
  - 进 Git 的项目共享 memory。
  - `memory/current/` 放当前有效的共享工作集。
  - `memory/history/` 放退出当前工作集的旧摘要。
- `.claude/`
  - Claude 侧 adapter 目录。
  - 这里只保留 adapter 规则，不再保存项目共享记忆。
- `docs/`
  - 给人看的项目文档。
  - `docs/` 根目录放当前有效的正式文档。
  - `docs/todo/` 放待办和 WIP。
  - `docs/archive/` 放归档材料。
- `$(git rev-parse --git-common-dir)/<repo-name>/memory/`
  - 当前 clone family 内共享的本机操作记忆。

## Memory 边界

- 需要跨 clone 复用的共享工作集，放 `memory/current/`
- 退出当前工作集但仍需短期追溯的旧摘要，放 `memory/history/`
- `memory/` 只放摘要和导航，不复制 `docs/` 里的完整正文
- 面向读者的正式说明和稳定规范，放 `docs/` 或 `.orchestration/specs/`
- 只在当前 clone family 内有效的运行提示，放 `git common dir/<repo-name>/memory/`
- 任务状态不能写进 memory，任务状态必须留在 `contract.json`、`verify.json`、`checkpoints/`、`handoffs/` 和 shared runtime
- `.claude/` 不再承载项目共享记忆

## 更新规则

- 新增或迁移文档后必须同步 `docs/INDEX.md`
- 新增或迁移当前项目 memory 后必须同步 `memory/INDEX.md` 和 `memory/current/INDEX.md`
- `docs/` 不记录逐轮运行日志；逐轮状态由任务目录和 shared runtime 承担
- `memory/` 不记录 live task state
- 当前机械检查入口是 `python -m scripts.check_documentation_layout`
