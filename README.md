# Claude / Codex Shared Control Plane

如果在同一个项目里同时用 Claude Code 和 Codex CLI，真正麻烦的通常不是谁来写代码，而是任务做到哪一步、交给了谁、验证结果是不是还有效，这些信息很容易散在会话里。

本项目给 Claude 和 Codex 创建了一套共用的任务结构，在一个地方查看任务说明、阶段状态、交接记录和验证结果。

它适合这种场景：

- Claude 负责规划、审查和交接，Codex 负责实现
- 任务会在 Claude 和 Codex 之间来回切换
- 希望 phase、handoff 和 verify 有固定位置，换会话也能接着做
- 不想在 `.claude/` 和 `.codex/` 里各维护一套状态

本仓库当前提供的是：

- 一套统一的任务阶段：`plan / implement / review / verify`
- 两种使用模式：`claude_codex` 和 `codex_native`
- 一个共享任务目录：`.orchestration/tasks/<task-id>/`
- 一个统一入口：`python -m scripts.agent_proxy`

## 快速开始

```bash
cd /path/to/your-project
bash /path/to/claude-codex-collab/setup.sh
```

安装后，直接用 Claude Code 或 Codex CLI 打开项目。

- 打开 Claude CLI，会切到 `claude_codex`
- 打开 Codex CLI，会切到 `codex_native`

## 开发环境

`setup.sh` 不会自动安装 Python 开发依赖。

如果你要在本地跑测试或 verify，先安装根目录的 `requirements-dev.txt`。

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

当前默认 verify 会用到 `pytest`。`ruff` 放在开发依赖里，方便本地检查，但现在不是 verify 的必需项。

## 快速了解项目设计的相关文件

- [AGENTS.md](AGENTS.md)
- [CLAUDE.md](CLAUDE.md)
- [.orchestration/README.md](.orchestration/README.md)
- [docs/shared-control-plane.md](docs/shared-control-plane.md)

## Acknowledgments

本项目的设计思路受到以下开源项目的启发：

- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow)：Claude Code 与其他模型协作时的工作流设计和安全约束
- [mindfold-ai/Trellis](https://github.com/mindfold-ai/Trellis)：围绕 Claude Code 的工程化组织方式和工具整合思路
