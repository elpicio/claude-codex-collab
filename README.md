# Claude / Codex Shared Control Plane

给 Claude Code 和 Codex CLI 共用的一套任务控制面。

它只做一件事：让同一个任务的状态、phase、handoff 和 verify 有统一位置，不再散在会话里。

这个项目的几个核心点：

- 统一 phase：`plan / implement / review / verify`
- 两种模式：`claude_codex` 和 `codex_native`
- 统一任务目录：`.orchestration/tasks/<task-id>/`
- 统一命令入口：`python -m scripts.agent_proxy`

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

## 先看这些文件

- [AGENTS.md](AGENTS.md)
- [CLAUDE.md](CLAUDE.md)
- [.orchestration/README.md](.orchestration/README.md)
- [docs/shared-control-plane.md](docs/shared-control-plane.md)
