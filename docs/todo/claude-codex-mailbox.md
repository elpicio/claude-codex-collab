# Claude / Codex Mailbox

## 背景

当前的 `claude_codex` 模式已经有共享任务目录、shared runtime、日志和 handoff，但还没有一条明确的 Claude -> Codex -> Claude 结果通道。

现在 Claude 可以通过 `agent_proxy` 触发 `codex exec`，Codex 的结果主要散在这几个位置：

- shared runtime 里的 phase 状态
- shared log 里的 stdout / stderr
- worktree 里的代码改动
- `handoffs/` 里的交接说明

这套方式足够做一次性委托，但不适合结构化回传，也不适合后面继续扩成多轮协作。

## 目标

补一层 mailbox，让 Claude 发给 Codex 的任务和 Codex 回给 Claude 的结果都有固定格式和固定位置。

这层 mailbox 先服务一个最直接的流程：

1. Claude 写一条实现请求
2. Codex 读取请求并执行
3. Codex 写回结果和摘要
4. Claude 读取结果后决定 review、verify 或 handoff

## 范围

第一版只覆盖 `claude_codex` 模式下的单任务消息流，不处理跨任务调度，也不处理多 agent 广播。

第一版至少要解决这些问题：

- 消息放哪里
- 谁负责写入和读取
- 请求和结果的最小字段是什么
- Claude 如何知道 Codex 已完成
- 失败、取消和重试如何表达

## 候选方向

优先考虑 shared runtime 下的结构化消息文件，例如：

- `$(git rev-parse --git-common-dir)/<repo-name>/messages/<task-id>.jsonl`

或者按 run 拆目录：

- `$(git rev-parse --git-common-dir)/<repo-name>/messages/<task-id>/<message-id>.json`

先不要引入 MCP。当前目标是把 Claude 和 Codex 之间的结果回传做清楚。

## 下一步

- 定 mailbox 路径和生命周期
- 定消息格式
- 定 `agent_proxy` 的消息命令
- 定 Claude 发起委托和 Codex 回写结果的最短流程
- 补测试，至少覆盖 send / read / ack / result
