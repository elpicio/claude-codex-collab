# Adapter Contract

这份文档定义 `.claude/` 和 `.codex/` 作为 adapter 时必须遵守的边界。

## 必须遵守

- 所有共享规则都从 `.orchestration/specs/index.md` 进入
- 文档、todo、archive、repo 内 `memory/` 和本机 local memory 的边界从 `.orchestration/specs/documentation.md` 进入
- 当前任务必须从 `.orchestration/tasks/<task-id>/` 读取
- phase 路由只能以 `contract.json` 的 `phase_inputs` 为准
- verify 只能以 `verify.json` 和 runtime 指纹判断为准
- authoritative runtime 只能通过 `scripts.agent_proxy` / `scripts.agent_proxy_core` 回写

## 不允许做的事

- 在 `.claude/` 或 `.codex/` 里单独维护第二套任务状态文件
- 把待办、运行记录或协作记忆继续堆回 `.claude/`
- 跳过 `contract.json` 自己决定 phase 顺序
- 跳过 `verify.json` 自己定义完成条件
- 直接改 shared runtime JSON，绕过 driver 写接口

## Claude Adapter

- 负责把任务契约、phase 输入和 spec 文件装配给 Claude Code
- 在 `claude_codex` 模式下，Claude 是控制面 driver，不是另一套任务状态机
- `.claude/rules/codex-delegation.md` 约束的是 Claude 主控时的实现委托，不改变共享任务契约

## Codex Adapter

- 负责把同一套任务契约装配给 Codex CLI
- `.orchestration/codex/` 是 repo 内可审查的 adapter 真源
- `.codex/` 是 materialized mirror，不是 source of truth
- 当前 runtime 兼容入口保留 `.codex/`

## 控制模式差异

- `claude_codex`
  - Claude 负责 phase 路由、审查、handoff 和 driver 决策
- `codex_native`
  - Codex 自己负责 driver、实现和 review
  - 但任务契约、verify、shared runtime 和文档边界都不变
