from __future__ import annotations

from pathlib import Path

from scripts.check_documentation_layout import collect_issues


def test_repo_scaffold_passes_documentation_layout() -> None:
    root = Path(__file__).resolve().parents[1]
    assert collect_issues(root) == []
