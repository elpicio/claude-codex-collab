#!/usr/bin/env bash
set -euo pipefail

# Claude Code + Codex MCP 协作模块安装脚本
# 用法: bash setup.sh [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[dry-run] 仅展示将执行的操作，不实际修改文件"
    echo
fi

run() {
    if $DRY_RUN; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

echo "=== Claude Code + Codex MCP 协作模块安装 ==="
echo

# ── 0. 前置检查 ──────────────────────────────────

if ! command -v codex &>/dev/null; then
    echo "ERROR: codex CLI 未安装。请先安装: npm install -g @openai/codex"
    exit 1
fi

if ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI 未安装。请先安装 Claude Code。"
    exit 1
fi

PROJECT_ROOT="$(pwd)"
if ! git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree &>/dev/null; then
    echo "⚠ 当前目录不是 git 仓库，git 安全兜底（diff/回滚）将不可用"
fi
echo "项目根目录: $PROJECT_ROOT"
echo

# ── 1. 注册 MCP Server ──────────────────────────

echo "[1/4] 注册 Codex MCP Server..."

if claude mcp list 2>/dev/null | grep -q "codex"; then
    echo "  ✓ Codex MCP 已注册，跳过"
else
    run claude mcp add codex -s user -- codex -c sandbox=workspace-write mcp-server
    echo "  ✓ Codex MCP 注册完成"
fi
echo

# ── 2. 复制委派规则 ──────────────────────────────

echo "[2/4] 安装委派规则..."

run mkdir -p "$PROJECT_ROOT/.claude/rules"

TARGET_RULE="$PROJECT_ROOT/.claude/rules/codex-delegation.md"
if [[ -f "$TARGET_RULE" ]]; then
    echo "  ! $TARGET_RULE 已存在，跳过（不覆盖）"
    echo "    如需更新，请手动对比: $SCRIPT_DIR/templates/rules/codex-delegation.md"
else
    run cp "$SCRIPT_DIR/templates/rules/codex-delegation.md" "$TARGET_RULE"
    echo "  ✓ 委派规则已复制到 .claude/rules/"
fi
echo

# ── 3. CLAUDE.md 协作章节 ─────────────────────────

echo "[3/4] 检查 CLAUDE.md..."

CLAUDE_MD="$PROJECT_ROOT/CLAUDE.md"
SNIPPET="$SCRIPT_DIR/templates/claude-md-snippet.md"
if [[ -f "$CLAUDE_MD" ]]; then
    if grep -q "多 Agent 协作" "$CLAUDE_MD" 2>/dev/null || grep -q "多Agent协作" "$CLAUDE_MD" 2>/dev/null; then
        echo "  ! CLAUDE.md 已包含协作章节，跳过"
    else
        run bash -c "printf '\n\n' >> '$CLAUDE_MD' && cat '$SNIPPET' >> '$CLAUDE_MD'"
        echo "  ✓ 协作章节已追加到 CLAUDE.md"
    fi
else
    run cp "$SNIPPET" "$CLAUDE_MD"
    echo "  ✓ CLAUDE.md 已创建（含协作章节）"
fi
echo

# ── 4. 配额监控脚本 ──────────────────────────────

echo "[4/4] 安装配额监控脚本..."

run mkdir -p "$PROJECT_ROOT/scripts"

TARGET_SCRIPT="$PROJECT_ROOT/scripts/ratelimit_checker.py"
if [[ -f "$TARGET_SCRIPT" ]]; then
    echo "  ! $TARGET_SCRIPT 已存在，跳过"
else
    run cp "$SCRIPT_DIR/scripts/ratelimit_checker.py" "$TARGET_SCRIPT"
    echo "  ✓ 配额监控脚本已复制到 scripts/"
fi
echo

# ── 完成 ─────────────────────────────────────────

echo "=== 安装完成 ==="
echo
echo "后续步骤："
echo "  1. 重启 Claude Code 会话（MCP 需要重启才能加载）"
echo "  2. 在 Claude Code 中测试: 输入任意编码任务，观察是否通过 Codex 派发"
echo "  3.（可选）编辑 .claude/rules/codex-delegation.md 调整委派路径范围"
echo "  4.（可选）将 settings-permissions.json 中的权限合并到 .claude/settings.local.json"
echo
echo "权限参考文件: $SCRIPT_DIR/templates/settings-permissions.json"
echo
if ! $DRY_RUN; then
    echo "⚠ 重要：请立即重启 Claude Code 会话，否则 MCP 工具不可用！"
fi
