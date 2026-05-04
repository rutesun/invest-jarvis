from pathlib import Path

from src.pipelines.daily_report.artifacts import StageArtifactStore


def test_artifact_store_writes_json_and_markdown(tmp_path: Path):
    store = StageArtifactStore(tmp_path / "artifacts" / "daily_report" / "2026-05-05" / "run-1")
    json_path = store.write_json("select", {"selected_clusters": 3})
    md_path = store.write_markdown("main_report", "# main")
    assert json_path.read_text(encoding="utf-8").startswith("{")
    assert md_path.read_text(encoding="utf-8") == "# main"
