#!/usr/bin/env bash
set -euo pipefail

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

copy_if_missing() {
    local source_path="$1"
    local target_path="$2"

    if [[ -e "$target_path" ]]; then
        echo "  ! ${target_path} 已存在，跳过"
        return
    fi

    run mkdir -p "$(dirname "$target_path")"
    run cp "$source_path" "$target_path"
    echo "  ✓ 已写入 ${target_path}"
}

echo "=== Shared Claude / Codex Control Plane 安装 ==="
echo

if ! command -v codex &>/dev/null; then
    echo "ERROR: codex CLI 未安装。请先安装: npm install -g @openai/codex"
    exit 1
fi

if ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI 未安装。请先安装 Claude Code。"
    exit 1
fi

PROJECT_ROOT="$(pwd)"
HAS_GIT=true
if ! git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree &>/dev/null; then
    HAS_GIT=false
    echo "⚠ 当前目录不是 git 仓库，worktree、shared runtime 和 hooksPath 相关能力不会完整生效"
fi

echo "项目根目录: $PROJECT_ROOT"
echo

echo "[1/4] 注册 Codex MCP Server..."

if timeout 5 claude mcp list 2>/dev/null | grep -q "codex"; then
    echo "  ✓ Codex MCP 已注册，跳过"
else
    echo "  ! 未能确认 Codex MCP 是否已注册，继续执行注册命令"
    run claude mcp add codex -s user -- codex -c sandbox=workspace-write mcp-server
    echo "  ✓ Codex MCP 注册完成"
fi
echo

echo "[2/4] 安装共享控制面骨架..."

FILES_TO_COPY=(
    "AGENTS.md"
    "requirements-dev.txt"
    ".claude/README.md"
    ".claude/rules/codex-delegation.md"
    ".orchestration/README.md"
    ".orchestration/specs/index.md"
    ".orchestration/specs/project.md"
    ".orchestration/specs/documentation.md"
    ".orchestration/specs/coding.md"
    ".orchestration/specs/review.md"
    ".orchestration/specs/adapters.md"
    ".orchestration/profiles/claude.json"
    ".orchestration/profiles/codex.json"
    ".orchestration/codex/config.toml"
    ".orchestration/codex/hooks.json"
    ".orchestration/hooks/session_start.py"
    ".orchestration/codex/agents/planner.toml"
    ".orchestration/codex/agents/implementer.toml"
    ".orchestration/codex/agents/reviewer.toml"
    ".githooks/pre-commit"
    "memory/INDEX.md"
    "memory/current/INDEX.md"
    "memory/current/project_overview.md"
    "memory/current/progress.md"
    "memory/current/docs_structure.md"
    "memory/history/README.md"
    "docs/INDEX.md"
    "docs/project-status.md"
    "docs/control-plane-implementation-status.md"
    "docs/todo/README.md"
    "docs/archive/README.md"
    "scripts/__init__.py"
    "scripts/agent_proxy.py"
    "scripts/agent_proxy_core.py"
    "scripts/agent_proxy_nl.py"
    "scripts/materialize_codex_adapter.py"
    "scripts/check_documentation_layout.py"
    "scripts/bootstrap_repo.py"
    "scripts/ratelimit_checker.py"
)

for relative_path in "${FILES_TO_COPY[@]}"; do
    copy_if_missing "$SCRIPT_DIR/$relative_path" "$PROJECT_ROOT/$relative_path"
done
if [[ -f "$PROJECT_ROOT/.githooks/pre-commit" ]]; then
    run chmod +x "$PROJECT_ROOT/.githooks/pre-commit"
fi
echo

echo "[3/4] 写入 CLAUDE.md 入口..."

CLAUDE_MD="$PROJECT_ROOT/CLAUDE.md"
SNIPPET="$SCRIPT_DIR/templates/claude-md-snippet.md"
if [[ -f "$CLAUDE_MD" ]]; then
    if grep -q "Shared Control Plane" "$CLAUDE_MD" 2>/dev/null; then
        echo "  ! CLAUDE.md 已包含共享控制面入口，跳过"
    else
        if $DRY_RUN; then
            echo "[dry-run] append snippet to $CLAUDE_MD"
        else
            printf '\n\n' >> "$CLAUDE_MD"
            cat "$SNIPPET" >> "$CLAUDE_MD"
        fi
        echo "  ✓ 已追加共享控制面入口到 CLAUDE.md"
    fi
else
    copy_if_missing "$SNIPPET" "$CLAUDE_MD"
fi
echo

echo "[4/4] 生成 .codex mirror 并配置 hooks..."

if [[ -f "$PROJECT_ROOT/scripts/materialize_codex_adapter.py" ]]; then
    run python "$PROJECT_ROOT/scripts/materialize_codex_adapter.py" --root "$PROJECT_ROOT" --target .codex
    echo "  ✓ .codex mirror 已生成"
fi

if $HAS_GIT; then
    run python "$PROJECT_ROOT/scripts/bootstrap_repo.py" --root "$PROJECT_ROOT"
    echo "  ✓ git hooksPath 已配置"
else
    echo "  ! 非 git 仓库，跳过 hooksPath 配置"
fi
echo

echo "=== 安装完成 ==="
echo
echo "后续步骤："
echo "  1. 重启 Claude Code 会话（MCP 需要重启才能加载）"
echo "  2. 查看 AGENTS.md、CLAUDE.md、.orchestration/README.md"
echo "  3. 用 python -m scripts.agent_proxy status 检查控制面状态"
echo "  4. 如需本地验证，先安装 requirements-dev.txt 里的开发依赖"
echo "     conda: conda create -n shared-control-plane python=3.11 -y"
echo "            conda activate shared-control-plane"
echo "            python -m pip install -r requirements-dev.txt"
echo "     uv:    uv venv --python 3.11"
echo "            . .venv/bin/activate"
echo "            uv pip install -r requirements-dev.txt"
echo "  5. 再运行 python -m scripts.check_documentation_layout 和 python -m pytest -q tests"
echo
echo "权限参考文件: $SCRIPT_DIR/templates/settings-permissions.json"
