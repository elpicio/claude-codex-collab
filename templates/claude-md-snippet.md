# ── 以下内容插入你项目的 CLAUDE.md ──

## 多 Agent 协作

### 编排架构：MCP + workspace-write + git 安全网

采用 Claude Code 为控制方、Codex 为 MCP Server 的编排模式。

**核心思路**：Claude 做设计和审查，Codex 做代码实现。Codex 直接写文件，代码不经过 Claude 上下文窗口，节省 token。

**三阶段工作流**：
1. **Plan**：Claude 分析需求，生成结构化实施计划
2. **Implement**：通过 MCP 协议将实施任务派发给 Codex，Codex 直接写文件
3. **Review**：Claude 通过 `git diff --stat` 查看变更摘要，按需查看具体 diff

### 角色分工

| Agent | 职责 | 调用方式 |
|-------|------|---------|
| Claude Code | 需求分析、架构设计、代码审查、决策推理 | 交互式 或 `claude -p` |
| Codex | 代码生成、测试编写、工具脚本、重复性实施任务 | MCP Server（`codex mcp-server`） |

### 安全模型

1. **workspace-write sandbox**：Codex 只能修改工作目录内文件，不能操作系统级资源
2. **git 状态检查**：Claude review 阶段跑 `git diff --stat` 看摘要，只对高风险文件查看具体 diff
3. **一键回滚**：不满意随时 `git checkout .` 撤销全部变更
4. **API Key 隔离**：密钥通过环境变量管理，不硬编码在配置文件中

### MCP 调用设计原则

短回合、弱状态依赖。每轮给 Codex 明确输入，做完即结束。不依赖长期 MCP session 续接。

### Token 成本策略

- Codex 直接写文件，代码不经过 Claude 上下文（核心省 token 机制）
- Claude 端只看变更摘要和关键文件，不需要接收完整 diff
- 避免全自动多阶段流程（token 放大效应显著），保持人在回路

### 依赖与前提

- Codex CLI 已安装
- MCP server 已注册（workspace-write sandbox）
- 工作目录为 git 仓库

MCP 注册命令：
```bash
claude mcp add codex -s user -- codex -c sandbox=workspace-write mcp-server
```
