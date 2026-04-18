# Claude / Codex Mailbox

## 状态

mailbox v1 已实现，代码入口：

- `scripts/agent_proxy_core.py`
- `scripts/agent_proxy.py`
- `tests/test_agent_proxy_core.py`

## v1 范围

只覆盖 `claude_codex` 模式下的单任务消息流，不处理跨任务调度和多 agent 广播。

## 存储位置

消息统一写在 shared runtime 下：

- `$(git rev-parse --git-common-dir)/<repo-name>/messages/<task-id>.jsonl`

每行一条 JSON 消息，追加写入，便于审计和回放。

写入实现使用 `flock` 文件锁，避免 Claude/Codex 并发写同一 task mailbox 时互相覆盖。

## 消息模型

统一字段：

- `id`
- `task_id`
- `type` (`request` / `result`)
- `status`
- `from`
- `to`
- `reply_to`
- `created_at`
- `updated_at`
- `ack`
- `payload`

`request` 状态：

- `pending`
- `acked`
- `resolved`

`result` 状态（用于表达执行结果）：

- `succeeded`
- `failed`
- `cancelled`
- `retry_requested`

当写入 `result` 时，会同步把对应 `request` 标记为 `resolved`，并记录 `resolution` 与 `result_id`。

协议约束：

- `ack` 只允许对 `request` 消息执行一次，不允许覆盖已有 ack。
- `result` 只能回写到已 `acked` 的 `request`。

## 命令

`agent_proxy` 新增 `mailbox` 子命令：

- `mailbox send`
- `mailbox read`
- `mailbox ack`
- `mailbox result`

`mailbox read --limit N` 返回过滤后的前 N 条消息（按 append 顺序，即最旧优先）。

`mailbox read --unacked` 只支持 `--type request`，用于轮询未 ack 的请求消息。

`mailbox read` 在不提供 `--to` 时会跨 backend 查询，便于查看同一 task 的全量请求或结果。

示例：

```bash
python -m scripts.agent_proxy mailbox send --task-id task-123 --to codex --summary "实现 mailbox v1"
python -m scripts.agent_proxy mailbox read --task-id task-123 --to codex --type request
python -m scripts.agent_proxy mailbox ack --task-id task-123 --message-id <request-id> --by codex
python -m scripts.agent_proxy mailbox result --task-id task-123 --request-id <request-id> --from codex --status succeeded --summary "实现完成并补测试"
python -m scripts.agent_proxy mailbox read --task-id task-123 --to claude --type result
```

## 最短流程

1. Claude `send` 请求给 Codex
2. Codex `read` 请求
3. Codex `ack` 请求
4. Codex `result` 回写结果（成功/失败/取消/重试）
5. Claude `read` 结果并决定进入 review / verify / handoff

Claude 判断 Codex 完成的标准是：收到 `type=result` 且 `to=claude` 的消息。

## 测试覆盖

当前测试至少覆盖：

- `send -> read -> ack -> result` 主流程
- `failed / cancelled / retry_requested` 状态表达
- `ack` 收件人校验
