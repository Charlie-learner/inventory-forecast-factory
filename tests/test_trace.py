import json
from pathlib import Path

from inventory_agent.observability.trace import RunRetentionManager, RunTraceRecorder


def test_trace_recorder_writes_incremental_events_code_snapshot_and_manifest(
    tmp_path: Path,
):
    run_dir = tmp_path / "20260101_000000_000001"
    trace = RunTraceRecorder(run_dir)
    trace.record(
        stage="test",
        component="ExampleAgent",
        component_type="agent",
        action="run",
        inputs={"request": "demo"},
        outputs={"answer": 1},
    )
    snapshot = trace.snapshot_code("def forecast():\n    return 1\n", "initial", "demo")
    paths = trace.finalize("success", {"result": "ok"})

    assert snapshot is not None and snapshot.name == "01_initial_demo.py"
    assert paths is not None
    events = [
        json.loads(line)
        for line in Path(paths["jsonl"]).read_text(encoding="utf-8").splitlines()
    ]
    assert [event["action"] for event in events] == ["run", "run_finished"]
    manifest = json.loads(Path(paths["manifest"]).read_text(encoding="utf-8"))
    assert manifest["event_count"] == 2
    assert str(snapshot) in manifest["artifacts"]
    assert "ExampleAgent.run" in Path(paths["markdown"]).read_text(encoding="utf-8")


def test_retention_deletes_only_old_timestamped_run_directories(tmp_path: Path):
    names = [
        "20260101_000000_000001",
        "20260102_000000_000001",
        "20260103_000000_000001",
    ]
    for name in names:
        directory = tmp_path / name
        directory.mkdir()
        (directory / "detailed_trace.jsonl").write_text("{}\n", encoding="utf-8")
    unrelated = tmp_path / "manual_notes"
    unrelated.mkdir()

    deleted = RunRetentionManager.cleanup(tmp_path, keep_runs=2)

    assert deleted == [str((tmp_path / names[0]).resolve())]
    assert not (tmp_path / names[0]).exists()
    assert (tmp_path / names[1]).exists()
    assert (tmp_path / names[2]).exists()
    assert unrelated.exists()
