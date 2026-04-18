# Shared Control Plane

## 目标

把 Claude 和 Codex 都纳入同一套共享控制面，而不是让某个会话充当唯一真源。

当前实现边界：

- repo 内保存低频任务契约、checkpoint 和 handoff
- shared runtime 保存在同一个 `git common dir/<repo-name>/`
- local attachment 保存 run 级别的本地路径和 session 绑定

shared runtime 只在同一个 clone family 内 authoritative，不是跨机器的全局真源。

## 目录

```text
.orchestration/
├── README.md
├── profiles/
│   ├── claude.json
│   └── codex.json
├── specs/
│   ├── index.md
│   ├── project.md
│   ├── documentation.md
│   ├── coding.md
│   ├── review.md
│   └── adapters.md
├── codex/
│   ├── config.toml
│   ├── hooks.json
│   ├── hooks/
│   └── agents/
└── tasks/
    └── <task-id>/
        ├── contract.json
        ├── task.md
        ├── journal.md
        ├── context/
        │   ├── plan.jsonl
        │   ├── implement.jsonl
        │   └── review.jsonl
        ├── verify.json
        ├── checkpoints/
        └── handoffs/
```

shared runtime 和 attachments 不放 repo 工作树里，位置通过 `git rev-parse --git-common-dir` 解析：

- `.../<repo-name>/runtime/<task-id>.json`
- `.../<repo-name>/attachments/<task-id>/<run-id>.json`
- `.../<repo-name>/logs/<task-id>/...`

## 设计原则

- `contract.json` 保存 phase graph、phase inputs、worktree policy、verify 引用
- `task.md` 给人看，不承担状态机职责
- `verify.json` 只定义 verify phase 的命令和通过条件
- `checkpoints/` 记录低频机器可读快照
- `handoffs/` 只在明确切换时写
- `state/active_control.json` 只是本地驱动偏好，不是共享真源

## 控制模式

- `claude_codex`
  - Claude 是控制面 driver
  - 代码实现可以委托给 Codex
  - 共享任务状态仍然落在 `.orchestration/tasks/` 和 shared runtime
- `codex_native`
  - Codex 自己同时负责 driver 和实现
  - 仍然读同一套 contract、verify 和 shared spec

当前默认行为：

- 打开 Claude CLI 时，SessionStart hook 会把 `state/active_control.json` 同步成 `claude_codex`
- 打开 Codex CLI 时，SessionStart hook 会把 `state/active_control.json` 同步成 `codex_native`
- `python -m scripts.agent_proxy switch ...` 仍然保留，用于显式 handoff、脚本化切换和无 hook 环境

## 当前协作主链路

当前的 Claude / Codex 协作不是靠 MCP 驱动。

- Claude 和 Codex 各自运行官方 CLI
- SessionStart hook 只同步本地 backend 偏好，不写任务真源
- `scripts.agent_proxy` / `scripts.agent_proxy_core` 负责 phase、handoff、worktree、verify 和 runtime 回写
- `.orchestration/tasks/<task-id>/` 和 shared runtime 承担共享状态
- MCP 如果接入，只用于 GitHub、文档、监控或内部服务这类外部能力

## 开发环境

`setup.sh` 只安装控制面骨架，不自动安装 Python 开发依赖。

如果你要在本地跑测试或 verify，先安装项目根目录的 `requirements-dev.txt`。

`conda`:

```bash
conda create -n shared-control-plane python=3.11 -y
conda activate shared-control-plane
python -m pip install -r requirements-dev.txt
```

`uv`:

```bash
uv venv --python 3.11
. .venv/bin/activate
uv pip install -r requirements-dev.txt
```

默认 verify 会执行 `pytest`。`ruff` 目前不是 verify 的必需项，只是放在开发依赖里备用。

## 日常使用

平时直接用自然语言让当前 agent 执行控制动作就行，例如：

```text
切到 codex，然后新建一个 upgrade-control-plane 任务
执行 plan 阶段，task-id task-upgrade-control-plane
把这个任务交接给 claude，说明里写 review next
```

结构化 CLI 还保留着，但主要给脚本化、调试和需要精确控制的场景。

## CLI

```bash
python -m scripts.agent_proxy status
python -m scripts.agent_proxy switch --backend codex --reason "take over implementation"
python -m scripts.agent_proxy new-task --title "upgrade control plane" --goal "bootstrap runtime"
python -m scripts.agent_proxy run --phase plan --task-id <task-id> --dry-run
python -m scripts.agent_proxy run --phase implement --task-id <task-id>
python -m scripts.agent_proxy run --phase review --task-id <task-id>
python -m scripts.agent_proxy run --phase verify --task-id <task-id>
python -m scripts.agent_proxy handoff --task-id <task-id> --to claude --summary "review next"
python -m scripts.agent_proxy worktree create --task-id <task-id>
python -m scripts.agent_proxy worktree bootstrap --task-id <task-id>
python -m scripts.agent_proxy worktree status --task-id <task-id>
python -m scripts.agent_proxy ask "切到 codex，然后新建一个 upgrade-control-plane 任务"
```
