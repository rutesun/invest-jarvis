import json
from dataclasses import asdict
from datetime import UTC, datetime

from typer.testing import CliRunner

from src.cli.notebook import notebook_app
from src.providers.stock_search import SearchResult, StockIdentity


def notebook(tmp_path):
    root = tmp_path / "notebook"
    (root / "research").mkdir(parents=True)
    (root / "research" / "2026-10.md").write_text("## 2026-10-01\n### test\nbody\n")
    return root


def test_offline_outputs_no_apply_manifest_and_no_body(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    output = tmp_path / "plan.json"
    result = CliRunner().invoke(
        notebook_app,
        ["sync", "--offline", "--notebook-dir", str(notebook(tmp_path)), "--manifest", str(output)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text())
    assert data["mode"] == "OFFLINE"
    assert "body" not in output.read_text()
    assert "실제 쓰기: 0" in result.output


def test_cannot_write_artifact_into_original_notebook(tmp_path):
    root = notebook(tmp_path)
    result = CliRunner().invoke(
        notebook_app,
        ["sync", "--offline", "--notebook-dir", str(root), "--manifest", str(root / "bad.json")],
    )
    assert result.exit_code != 0
    assert not (root / "bad.json").exists()


def test_apply_requires_journal_and_rejects_offline(tmp_path):
    root = notebook(tmp_path)
    runner = CliRunner()
    for args in (
        ["--apply", str(tmp_path / "missing.json")],
        [
            "--offline",
            "--apply",
            str(tmp_path / "missing.json"),
            "--journal",
            str(tmp_path / "j.json"),
        ],
        ["--resume"],
    ):
        result = runner.invoke(notebook_app, ["sync", "--notebook-dir", str(root), *args])
        assert result.exit_code != 0


def test_offline_manifest_groups_multiple_documents_by_stock_without_body(tmp_path):
    root = notebook(tmp_path)
    (root / "research" / "2026-10.md").write_text(
        "## 2026-10-01\n### first\n- **종목**: #NVDA #AMD\nprivate text\n"
        "### second\n- **종목**: #NVDA\nother private text\n"
    )
    output = tmp_path / "groups.json"
    cache = tmp_path / "search.json"
    cache.write_text(
        json.dumps(
            {
                "version": 2,
                "provider": "naver-stock-search",
                "queries": {
                    q: {
                        "checked_at": datetime.now(UTC).isoformat(),
                        "result": asdict(
                            SearchResult("resolved", StockIdentity(q, q, "NASDAQ", "USA"))
                        ),
                    }
                    for q in ("NVDA", "AMD")
                },
            }
        )
    )
    result = CliRunner().invoke(
        notebook_app,
        [
            "sync",
            "--offline",
            "--notebook-dir",
            str(root),
            "--stock-cache",
            str(cache),
            "--manifest",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text())
    assert data["stock_groups"] == {
        "AMD": ["research/2026-10-01#first"],
        "NVDA": ["research/2026-10-01#first", "research/2026-10-01#second"],
    }
    assert "private text" not in output.read_text()


def test_offline_uncached_stock_is_incomplete_without_network(tmp_path, monkeypatch):
    root = notebook(tmp_path)
    (root / "research" / "2026-10.md").write_text(
        "## 2026-10-01\n### first\n- **태그**: #삼성전자\n"
    )
    output = tmp_path / "missing.json"
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    result = CliRunner().invoke(
        notebook_app,
        [
            "sync",
            "--offline",
            "--notebook-dir",
            str(root),
            "--stock-cache",
            str(tmp_path / "no-cache.json"),
            "--manifest",
            str(output),
        ],
    )
    assert result.exit_code == 2, result.output
    plan = json.loads(output.read_text())
    assert plan["stock_groups"] == {}
    assert "STOCK_SEARCH_INCOMPLETE" in plan["blockers"]
    assert plan["stock_resolution"]["issues"][0]["query"] == "삼성전자"


def test_search_cache_cannot_be_saved_inside_source(tmp_path):
    root = notebook(tmp_path)
    result = CliRunner().invoke(
        notebook_app,
        [
            "sync",
            "--offline",
            "--notebook-dir",
            str(root),
            "--stock-cache",
            str(root / "cache.json"),
        ],
    )
    assert result.exit_code != 0
    assert not (root / "cache.json").exists()
