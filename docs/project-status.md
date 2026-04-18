# Project Status

## 当前阶段

这个仓库使用共享控制面。Claude 和 Codex 通过 `.orchestration/`、task 目录和 shared runtime 协作。

## 当前重点

- 保持 `.orchestration/codex/` 真源和 `.codex/` mirror 一致
- 保持 `setup.sh` 生成的安装结果与仓库当前控制面一致
- 让文档、memory、task state 的边界持续清晰

## 恢复入口

- `AGENTS.md`
- `CLAUDE.md`
- `.orchestration/README.md`
- `.orchestration/specs/index.md`
- `memory/current/INDEX.md`
