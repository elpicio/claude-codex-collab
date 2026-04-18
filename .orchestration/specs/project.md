# Project Spec

这个仓库采用共享 Claude / Codex 控制面。

控制面约束：

- 任务契约放在 `.orchestration/tasks/<task-id>/`
- 共享运行态不放 repo 工作树文件里，而是放 `git common dir/<repo-name>/`
- `task.md` 给人看，`contract.json`、`verify.json`、`checkpoints/` 给脚本和恢复流程用
- Claude 和 Codex 都必须遵守同一套任务模型，不能各自维护一份 phase 状态

工作方式：

- 非 trivial 任务先有 plan 再进入 implement
- 做完不能只靠自然语言宣称完成，必须有 verify 结果
- 发现会影响后续协作的坑，要写进文档、memory 或 task 目录
