from __future__ import annotations

from pathlib import Path

from scripts.materialize_codex_adapter import install


def write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_install_can_limit_to_config_component(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    write_file(root / ".orchestration" / "codex" / "config.toml", "sandbox_mode = 'workspace-write'\n")
    write_file(root / ".orchestration" / "codex" / "hooks.json", "{}\n")
    write_file(root / ".orchestration" / "codex" / "agents" / "planner.toml", "name = 'planner'\n")

    target = root / ".codex"
    operations = install(root, target, dry_run=False, component="config")

    assert operations == [
        (root / ".orchestration" / "codex" / "config.toml", target / "config.toml")
    ]
    assert (target / "config.toml").exists()
    assert not (target / "hooks.json").exists()
    assert not (target / "agents" / "planner.toml").exists()
