"""2026-10-14 read-only Notion captures, anonymized before entering Git."""

import json
from pathlib import Path

import httpx

from src.integrations.notebook_notion.plan import build_plan
from src.integrations.notebook_notion.remote import Remote, canonical_blocks
from src.tools.notebook.parser import parse_notebook_dir


FIXTURES = Path(__file__).parents[1] / "fixtures" / "notebook_notion"


def test_captured_schema_and_query_to_review_plan(tmp_path):
    folder = tmp_path / "research"
    folder.mkdir()
    (folder / "2026-08.md").write_text("## 2026-08-28\n### anonymous\nbody\n### new\nbody\n")
    schema = json.loads((FIXTURES / "schema-2026-10-14.json").read_text())
    query = json.loads((FIXTURES / "legacy-query-2026-10-14.json").read_text())

    def handle(request):
        if request.url.path == "/v1/databases/db":
            return httpx.Response(200, json={"data_sources": [{"id": "source-fixture"}]})
        if request.url.path == "/v1/data_sources/source-fixture":
            return httpx.Response(200, json=schema)
        assert (
            request.method == "POST" and request.url.path == "/v1/data_sources/source-fixture/query"
        )
        return httpx.Response(200, json=query)

    with Remote("fixture-only", transport=httpx.MockTransport(handle)) as remote:
        plan = build_plan(parse_notebook_dir(tmp_path), remote.snapshot("db"))
    assert plan["counts"] == {"LEGACY_UNVERIFIED": 1, "CREATE_CANDIDATE": 1}
    assert [r["key"] for r in plan["selected"]] == ["research/2026-08-28#new"]
    assert plan["blockers"] == ["SCHEMA_CHANGE_REQUIRED"]
    assert set(plan["schema_proposal"]["properties"]) == {"Source Path", "Content Hash", "PDF 원문"}


def test_captured_legacy_blocks_keep_type_text_and_annotations():
    captured = json.loads((FIXTURES / "legacy-blocks-2026-10-14.json").read_text())
    normalized = canonical_blocks(captured["blocks"])
    assert [b["type"] for b in normalized] == [
        "paragraph",
        "callout",
        "callout",
        "callout",
        "callout",
        "paragraph",
    ]
    first = normalized[0]["paragraph"]["rich_text"]
    assert "".join(t["text"]["content"] for t in first) == "anonymous" * 7
    assert first[1]["annotations"] == {"bold": True}
    assert normalized[2]["callout"]["rich_text"][0]["text"]["link"] is None
