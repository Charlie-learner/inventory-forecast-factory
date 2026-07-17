from pathlib import Path

from scripts.clean_workspace import clean, collect_targets


def test_clean_workspace_preserves_user_data_examples_and_environment(tmp_path: Path):
    generated = [
        tmp_path / "artifacts" / "runs" / "result.json",
        tmp_path / "inventory_agent" / "module" / "__pycache__" / "module.pyc",
        tmp_path / ".coverage",
    ]
    protected = [
        tmp_path / "data" / "raw" / "user.csv",
        tmp_path / "examples" / "evidence.json",
        tmp_path / ".venv" / "Lib" / "__pycache__" / "dependency.pyc",
    ]
    for path in generated + protected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")

    targets = collect_targets(tmp_path)
    assert tmp_path / "artifacts" in targets
    assert tmp_path / "inventory_agent" / "module" / "__pycache__" in targets
    assert all(path not in targets for path in protected)

    clean(tmp_path, apply=True)
    assert all(not path.exists() for path in generated)
    assert all(path.exists() for path in protected)


def test_clean_workspace_defaults_to_dry_run(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "result.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("test", encoding="utf-8")

    assert clean(tmp_path, apply=False) == [tmp_path / "artifacts"]
    assert artifact.exists()
