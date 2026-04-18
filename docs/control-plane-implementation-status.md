# Control Plane Implementation Status

## 已落地

- `.orchestration/` 目录结构
- 共享 spec 入口
- `scripts.agent_proxy`、`agent_proxy_core`、`agent_proxy_nl`
- task 目录模型
- shared runtime、attachment、worktree 管理
- `.orchestration/codex/` 真源和 `.codex/` mirror
- `memory/`、`docs/`、`.claude/` 边界
- `setup.sh` 安装共享控制面骨架

## 还要持续检查

- 安装到已有项目时的冲突处理仍然偏保守，默认跳过已有文件
- 如果目标项目不是 Python 项目，`verify.json` 和 bootstrap profile 需要手调
