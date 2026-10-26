from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.integrations.notebook_notion.plan import build_plan, projection
from src.integrations.notebook_notion.remote import SyncError
from src.tools.notebook.models import NotebookEntry


def entry(title="sample", body="body"):
    key = f"research/2026-10-01#{title}"
    properties = {
        "이름": {"title": [{"text": {"content": title}}]},
        "Key": {"rich_text": [{"text": {"content": key}}]},
        "Type": {"select": {"name": "research"}},
        "Date": {"date": {"start": "2026-10-01"}},
        "Source Path": {
            "rich_text": [{"text": {"content": f"notebook/research/2026-10.md#{title}"}}]
        },
        "PDF 원문": {"url": None},
    }
    return SimpleNamespace(
        key=key,
        title=title,
        date="2026-10-01",
        type="research",
        body_markdown=body,
        source_path=f"notebook/research/2026-10.md#{title}",
        action=None,
        properties=lambda: deepcopy(properties),
    )


def snapshot():
    schema = {
        k: {"id": k, "type": t, t: {}}
        for k, t in {
            "이름": "title",
            "Key": "rich_text",
            "Type": "select",
            "Date": "date",
            "종목": "multi_select",
            "테마": "multi_select",
            "액션": "select",
            "출처": "url",
            "Source Path": "rich_text",
            "Content Hash": "rich_text",
            "PDF 원문": "url",
        }.items()
    }
    schema["Type"]["select"]["options"] = [{"name": t} for t in ("research", "trades", "thoughts")]
    schema["액션"]["select"]["options"] = [{"name": t} for t in ("매수", "매도", "관망", "손절")]
    return {"database_id": "db", "data_source_id": "ds", "schema": schema, "pages": []}


def page(item, hash_value=None, id="old"):
    properties = item.properties()
    if hash_value:
        properties["Content Hash"] = {"rich_text": [{"text": {"content": hash_value}}]}
    return {"id": id, "last_edited_time": "2026-10-01T00:00:00Z", "properties": properties}


def test_plan_separates_legacy_orphan_and_new_without_writes():
    old, new, orphan = entry("old"), entry("new"), entry("orphan")
    state = snapshot()
    state["pages"] = [page(old), page(orphan, id="orphan")]
    plan = build_plan([old, new], state)
    assert plan["counts"] == {"LEGACY_UNVERIFIED": 1, "CREATE_CANDIDATE": 1, "ORPHAN_CANDIDATE": 1}
    assert [p["key"] for p in plan["selected"]] == [new.key]
    assert plan["blockers"] == []
    assert "body_markdown" not in str(plan)


def test_remote_plan_stock_groups_include_legacy_and_new_local_documents():
    old = NotebookEntry("research", "2026-10-01", "old", "private text", "old", stocks=["NVDA"])
    new = NotebookEntry(
        "research", "2026-10-01", "new", "private text", "new", stocks=["NVDA", "AMD"]
    )
    state = snapshot()
    state["pages"] = [page(old)]
    plan = build_plan([old, new], state)
    assert plan["stock_groups"] == {"AMD": [new.key], "NVDA": [new.key, old.key]}
    assert plan["counts"] == {"CREATE_CANDIDATE": 1, "LEGACY_UNVERIFIED": 1}
    assert "private text" not in str(plan)


def test_hash_detects_content_change_and_is_stable():
    item = entry()
    hash_value = projection(item, [item])[0]["Content Hash"]["rich_text"][0]["text"]["content"]
    state = snapshot()
    state["pages"] = [page(item, hash_value)]
    assert build_plan([item], state)["counts"] == {"UNCHANGED": 1}
    assert build_plan([entry(body="edited")], state)["counts"] == {"UPDATE_CANDIDATE": 1}
    assert build_plan([entry(body="edited")], state)["selected"] == []


@pytest.mark.parametrize("drift", ["duplicate_remote", "duplicate_local", "schema_type", "staging"])
def test_conflicts_block_entire_apply(drift):
    item = entry()
    state = snapshot()
    entries = [item]
    if drift == "duplicate_remote":
        state["pages"] = [page(item), page(item, id="duplicate")]
    elif drift == "duplicate_local":
        entries.append(item)
    elif drift == "schema_type":
        state["schema"]["Key"] = {"type": "number", "number": {}}
    else:
        staged = page(item)
        staged["properties"]["Key"]["rich_text"][0]["text"]["content"] = "__staging__/run/key"
        state["pages"] = [staged]
    plan = build_plan(entries, state)
    assert plan["blockers"]


def test_missing_schema_is_a_concrete_proposal_not_a_mutation():
    state = snapshot()
    for k in ("Source Path", "Content Hash", "PDF 원문"):
        state["schema"].pop(k)
    state["schema"]["액션"]["select"]["options"] = [{"name": "매수"}, {"name": "매도"}]
    plan = build_plan([entry()], state)
    assert plan["schema_proposal"]["properties"]["Content Hash"] == {"rich_text": {}}
    assert plan["schema_proposal"]["properties"]["PDF 원문"] == {"url": {}}
    assert plan["blockers"] == ["SCHEMA_CHANGE_REQUIRED"]


def test_selected_keys_must_be_eligible_and_manifest_digest_changes():
    item = entry()
    with pytest.raises(SyncError):
        build_plan([item], snapshot(), only_keys=["missing"])
    all_plan = build_plan([item, entry("other")], snapshot())
    one_plan = build_plan([item, entry("other")], snapshot(), only_keys=[item.key])
    assert all_plan["manifest_id"] != one_plan["manifest_id"]


def test_remote_edit_with_unchanged_hash_is_blocked():
    item = entry()
    props, blocks = projection(item, [item])
    state = snapshot()
    state["pages"] = [{"id": "old", "properties": props, "last_edited_time": "now"}]
    plan = build_plan(
        [item],
        state,
        read_blocks=lambda _: [
            {"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "human edit"}}]}}
        ],
    )
    assert plan["counts"] == {"CONFLICT": 1}
    assert plan["blockers"]


def test_new_multiselect_options_require_explicit_schema_review():
    item = entry()
    original = item.properties
    item.properties = lambda: {
        **original(),
        "종목": {"multi_select": [{"name": "NEW"}]},
        "테마": {"multi_select": [{"name": "theme"}]},
    }
    plan = build_plan([item], snapshot())
    assert "SCHEMA_CHANGE_REQUIRED" in plan["blockers"]
    assert plan["schema_proposal"]["properties"]["종목"]["multi_select"]["options"] == [
        {"name": "NEW"}
    ]


@pytest.mark.parametrize("remote_name", ["CAPEX", " CapEx "])
def test_existing_option_case_and_spacing_do_not_require_schema_change(remote_name):
    item = NotebookEntry("research", "2026-10-01", "sample", "body", "sample", themes=["CapEx"])
    state = snapshot()
    state["schema"]["테마"]["multi_select"]["options"] = [{"id": "capex", "name": remote_name}]
    assert build_plan([item], state)["blockers"] == []


def test_notion_normalized_option_readback_remains_unchanged():
    item = NotebookEntry("research", "2026-10-01", "sample", "body", "sample", themes=["CapEx"])
    properties, blocks = projection(item, [item])
    properties["테마"] = {"multi_select": [{"id": "capex", "name": "CAPEX"}]}
    state = snapshot()
    state["schema"]["테마"]["multi_select"]["options"] = [{"id": "capex", "name": "CAPEX"}]
    state["pages"] = [{"id": "page", "properties": properties}]
    plan = build_plan([item], state, read_blocks=lambda _: blocks)
    assert plan["counts"] == {"UNCHANGED": 1}
    assert plan["blockers"] == []
    properties["테마"] = {"multi_select": [{"name": "Different Theme"}]}
    assert build_plan([item], state, read_blocks=lambda _: blocks)["counts"] == {"CONFLICT": 1}


def test_readable_only_projection_uses_v2_content_hash():
    item = entry(body="text [[unresolved]]")
    properties, _ = projection(item, [item])
    assert properties["Content Hash"]["rich_text"][0]["text"]["content"] == (
        "notebook-v2:668168a6813855b0aa02a13a9bcf3775cba160e9f5f77dde371ee935def58c32"
    )
