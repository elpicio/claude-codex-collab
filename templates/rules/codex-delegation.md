---
description: 代码实现必须通过 Codex MCP 派发，Claude 不直接写实现代码
globs: ["src/**/*.py", "tests/**/*.py"]
---

# Codex 委派规则

## 核心原则

**Claude 不直接编写实现代码。**

代码实现必须通过 Codex MCP（`mcp__codex__codex`）派发。Claude 的职责是设计、审查、决策，不是写代码。

## 允许 Claude 直接做的事

- 读取代码（Read / Grep / Glob）
- 审查 `git diff`
- 编写设计文档（`docs/`）
- 编写 rules / skills / memory / 配置文件
- 修复极小的 typo（单行级别，需说明原因）

## 禁止 Claude 直接做的事

- 使用 Write / Edit 工具创建或修改匹配 globs 的代码文件
- 使用 Agent tool（general-purpose）并行生成代码文件
- 绕过 Codex MCP 直接实现功能模块

## 正确的工作流

```
1. Claude 写设计文档/实施规范（接口、测试用例、约束）
2. Claude 通过 mcp__codex__codex 将任务派发给 Codex
3. Codex 在 workspace-write sandbox 中实现代码
4. Claude 用 git diff --stat 审查变更摘要
5. Claude 按需查看具体 diff，确认质量
6. 不满意则 git checkout . 回滚，重新派发
```

## 为什么

Claude 直接写代码会：
- 绕过 MCP 协议的调用边界和安全模型
- 失去 git diff 审查点（Agent 并行写多文件时用户无法逐文件审批）
- 违反"Codex 执行 / Claude 判断"的核心分工
- 浪费 Claude 的上下文窗口在代码生成上（Codex 直接写文件不经过 Claude 上下文）

## 定制说明

如需调整委派范围，修改顶部 `globs` 字段。例如：
- TypeScript 项目：`["src/**/*.ts", "src/**/*.tsx", "tests/**/*.ts"]`
- Go 项目：`["**/*.go"]`
- 多语言项目：`["src/**/*", "tests/**/*", "!**/*.md"]`
