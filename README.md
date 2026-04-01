# Claude Code + Codex MCP 协作模块

即插即用的 Claude Code / Codex CLI 多 Agent 协作框架。

将 Claude Code 定位为**设计者/审查者**，Codex 定位为**执行者**，通过 MCP 协议连接，用 git 做安全兜底。

## 架构概览

```
用户需求
  │
  ▼
Claude Code（设计 & 审查）
  │  1. 分析需求，写设计规范
  │  2. 通过 MCP 派发任务
  │  3. git diff --stat 审查产出
  │
  ├──── mcp__codex__codex ────►  Codex CLI（执行）
  │                                 │  workspace-write sandbox
  │                                 │  直接写文件，不经 Claude 上下文
  │                                 ▼
  │                              文件变更（git tracked）
  │
  ▼
Claude Code（审查 & 决策）
  ├─ 满意 → git add & commit
  └─ 不满意 → git checkout . 回滚，重新派发
```

## 核心优势

| 特性 | 说明 |
|------|------|
| Token 节省 | Codex 直接写文件，代码不经过 Claude 上下文窗口 |
| 安全兜底 | workspace-write sandbox + git 状态检查 + 一键回滚 |
| 职责清晰 | Claude 做判断，Codex 做执行，互不越权 |
| 审查可控 | `git diff --stat` 看摘要，按需查具体文件 |

## 快速安装

```bash
# 1. 确保 Codex CLI 已安装
codex --version

# 2. 在你的项目目录下运行安装脚本
cd /path/to/your-project
bash /path/to/claude-codex-collab/setup.sh

# 3. 重启 Claude Code 会话（新 MCP 需要重启才能加载）
```

安装脚本会：
- 注册 Codex MCP Server（user scope）
- 复制委派规则到 `.claude/rules/`
- 在 CLAUDE.md 中插入协作章节（如果存在的话）
- 复制配额监控脚本到 `scripts/`

## 手动安装

如果你更喜欢手动配置：

### 1. 注册 MCP Server

```bash
claude mcp add codex -s user -- codex -c sandbox=workspace-write mcp-server
```

### 2. 复制规则文件

```bash
mkdir -p .claude/rules
cp templates/rules/codex-delegation.md .claude/rules/
```

### 3. 编辑 CLAUDE.md

将 `templates/claude-md-snippet.md` 的内容追加到你项目的 CLAUDE.md 中。

### 4.（可选）配额监控

```bash
mkdir -p scripts
cp scripts/ratelimit_checker.py scripts/
```

## 文件说明

```
claude-codex-collab/
├── README.md                          # 本文件
├── setup.sh                           # 一键安装脚本
├── templates/
│   ├── claude-md-snippet.md           # CLAUDE.md 协作章节模板
│   ├── rules/
│   │   └── codex-delegation.md        # 委派规则（可配置路径）
│   └── settings-permissions.json      # 推荐的权限白名单
└── scripts/
    └── ratelimit_checker.py           # Codex 配额监控脚本
```

## 使用方式

安装完成后，在 Claude Code 中正常工作即可。当你要求 Claude 实现代码时，它会：

1. 先写设计文档或实施规范
2. 通过 `mcp__codex__codex` 将任务派发给 Codex
3. Codex 在 sandbox 中直接写文件
4. Claude 用 `git diff --stat` 审查变更
5. 你确认后 commit，不满意则回滚

### MCP 工具参数

```
mcp__codex__codex（启动新任务）
  - prompt（必填）：任务描述
  - sandbox：workspace-write（默认）
  - cwd：工作目录

mcp__codex__codex-reply（继续对话）
  - threadId（必填）：上次调用返回的 ID
  - prompt：后续指令
```

## 注意事项

- **重启生效**：注册 MCP 后必须重启 Claude Code 会话，新工具才会加载
- **sandbox 边界**：`workspace-write` 也允许写 `/tmp`，比预期宽松，安全兜底靠 git
- **短回合设计**：每次 MCP 调用应是独立任务，不依赖长期 session 状态
- **配额管理**：Codex 有 5 小时/周的使用限制，用 ratelimit_checker.py 监控

## 定制指南

### 修改委派范围

默认规则限制 `src/**/*.py` 和 `tests/**/*.py`。如果你的项目结构不同，编辑 `.claude/rules/codex-delegation.md` 中的 `globs` 字段：

```yaml
globs: ["src/**/*.py", "tests/**/*.py"]  # 改成你的路径
```

### 添加领域规则

在 `templates/rules/` 下创建新规则文件，安装时会一并复制。例如为前端项目添加：

```yaml
globs: ["src/**/*.ts", "src/**/*.tsx"]
```

## Acknowledgments

本项目的设计思路受到以下开源项目的启发，感谢这些项目的贡献：

- [ching-kuo/claude-codex](https://github.com/ching-kuo/claude-codex) — MCP 集成方案与三阶段工作流设计
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) — Claude Code + Codex 协作模式与安全模型
- [xiangz19/codex-ratelimit](https://github.com/xiangz19/codex-ratelimit) — Codex 配额监控脚本
