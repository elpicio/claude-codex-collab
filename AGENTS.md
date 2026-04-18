# Shared Control Plane Bootstrap

这个仓库的共享控制面不放在 `.claude/`，也不放在 `.codex/`。

先读这些文件：

- `CLAUDE.md`
- `memory/current/INDEX.md`
- `.orchestration/README.md`
- `.orchestration/specs/index.md`
- `.orchestration/specs/documentation.md`

当前任务如果已经建立，再读：

- `.orchestration/tasks/<task-id>/contract.json`
- `.orchestration/tasks/<task-id>/task.md`
- `.orchestration/tasks/<task-id>/context/<phase>.jsonl`
- `.orchestration/tasks/<task-id>/verify.json`
- `.orchestration/tasks/<task-id>/checkpoints/`
- `.orchestration/tasks/<task-id>/handoffs/`

工作规则：

- phase 路由以 `contract.json` 的 `phase_inputs` 为准
- repo 内只保存低频 contract、checkpoint 和 handoff
- shared runtime 不在 repo 工作树里，而在同一个 `git common dir` 下
- 正式文档、todo、archive、`memory/current/`、`memory/history/`、任务状态和本机 local memory 的边界以 `.orchestration/specs/documentation.md` 为准
- 新增待办文档放 `docs/todo/`，正式文档放 `docs/` 根目录，归档材料放 `docs/archive/`
- 新增项目共享记忆放 `memory/current/`，并同步 `memory/INDEX.md` 和 `memory/current/INDEX.md`
- 失去当前性的旧摘要移到 `memory/history/`
- `git common dir/<repo-name>/memory/` 只放本机临时记忆
- `.claude/` 不再保存项目共享记忆
- `verify` 是正式 phase，不是 review 后面的隐式附属步骤
- 如果 workspace 指纹变了，旧 verify 结果不能直接复用

当前仓库里保留两份 Codex adapter：

- `.orchestration/codex/`：真源
- `.codex/`：提交进仓库的默认镜像副本和当前 runtime 兼容入口

当前约束下：

- 改 Codex adapter 时，先改 `.orchestration/codex/`
- 再按需要同步到 `.codex/`
- `python -m scripts.materialize_codex_adapter --target .codex` 负责生成 mirror

这里的控制模式差异要分清：

- `claude_codex`：Claude 负责 driver、审查和交接，代码实现可委托给 Codex
- `codex_native`：Codex 自己负责 driver 和实现

不要自己再发明第二套任务状态文件。
