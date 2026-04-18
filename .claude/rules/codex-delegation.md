---
description: 代码实现可以通过 Codex 执行，但共享控制面状态不能回退到 Claude 私有目录
globs: ["scripts/**/*.py", "tests/**/*.py"]
---

# Codex 委派规则

## 核心原则

这个规则约束的是 `claude_codex` 模式下的实现委托方式，不改变共享控制面的任务模型。

Claude 可以负责 driver、phase 路由、审查和交接，但代码实现优先通过 Codex 完成。无论谁主导，任务状态都只能写进 `.orchestration/tasks/` 和 shared runtime。

## 允许 Claude 直接做的事

- 读取代码
- 审查 `git diff`
- 编写设计文档、memory、spec 和配置
- 修改控制面文档和 adapter 文件
- 修复极小的 typo

## 禁止 Claude 直接做的事

- 在匹配 `globs` 的实现文件里绕过共享控制面另开一套状态记录
- 只在 `.claude/` 里记 phase 结论，不写回 task 目录
- 用私有会话上下文代替 `contract.json`、`verify.json`、`handoffs/` 和 `checkpoints/`

## 正确工作流

1. Claude 先读 `contract.json`、`task.md` 和 phase 输入。
2. 需要委托实现时，Claude 通过 Codex 派发实现任务。
3. 代码和文档变更完成后，review 和 verify 仍然回到共享控制面。
4. handoff、checkpoint、verify 结果继续写进 `.orchestration/tasks/` 和 shared runtime。
