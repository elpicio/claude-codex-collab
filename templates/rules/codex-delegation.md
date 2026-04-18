---
description: 代码实现可以通过 Codex 执行，但共享控制面状态不能回退到 Claude 私有目录
globs: ["scripts/**/*.py", "tests/**/*.py"]
---

# Codex 委派规则

这个规则约束的是 `claude_codex` 模式下的实现委托方式，不改变共享控制面的任务模型。

## 核心原则

- Claude 可以负责 driver、phase 路由、审查和交接
- 代码实现优先通过 Codex 完成
- 任务状态只能写进 `.orchestration/tasks/` 和 shared runtime

## 不允许做的事

- 在 `.claude/` 里单独维护第二套 phase 状态
- 绕过 `contract.json`、`verify.json` 和 handoff/checkpoint 机制
- 只靠会话记忆推进任务，不回写共享控制面
