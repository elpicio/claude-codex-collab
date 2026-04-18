# Claude Adapter

`.claude/` 只放 Claude 侧 adapter 文件，不放项目共享记忆，也不放第二套任务状态。

## 先读哪里

- `CLAUDE.md`
- `memory/current/INDEX.md`
- `.orchestration/README.md`
- `.orchestration/specs/index.md`
- `.orchestration/specs/adapters.md`

## 当前两种模式

### 1. `claude_codex`

- Claude 是控制面 driver
- phase 路由、handoff、verify 和任务恢复都走 `.orchestration/tasks/` 和 shared runtime
- 代码实现可以按 `.claude/rules/codex-delegation.md` 委托给 Codex
- Claude 负责设计、审查、决策和交接，不在 `.claude/` 里维护第二套状态

### 2. `codex_native`

- Codex 自己既是 driver，也是执行者
- 仍然读同一套 `.orchestration/` 契约和共享 spec
- 不依赖 Claude adapter 才能恢复任务

## 本目录边界

- `.claude/rules/`：Claude 侧约束和委托规则
- `.claude/settings.json`：Claude CLI 的项目级 adapter 配置
- 不再保留 `.claude/memory/`
- 项目共享记忆统一放 `memory/`

## 启动行为

- Claude CLI 在 SessionStart 时会通过 `.claude/settings.json` 自动把本地控制模式切回 `claude_codex`
- 这个切换只更新 `.orchestration/state/active_control.json` 的本地驱动偏好，不改变共享任务契约
