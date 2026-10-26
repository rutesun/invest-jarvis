import copy
import json

import pytest

from src.integrations.notebook_notion.apply import apply_plan
from src.integrations.notebook_notion.plan import build_plan, projection
from src.integrations.notebook_notion.remote import SyncError, rich_value
from tests.integrations.test_notebook_plan import entry, page, snapshot


class FakeRemote:
    """Stateful fake at the network boundary; keeps real planning/apply logic."""

    def __init__(self, state=None, fail=None):
        self.state = state or snapshot()
        self.trees = {}
        self.fail = fail
        self.writes = []
        self.next_id = 0

    def snapshot(self, _):
        return copy.deepcopy(
            {**self.state, "pages": [p for p in self.state["pages"] if not p.get("archived")]}
        )

    def query(self, _, key=None):
        return [
            copy.deepcopy(p)
            for p in self.state["pages"]
            if not p.get("archived") and (key is None or rich_value(p, "Key") == key)
        ]

    def page(self, id):
        return copy.deepcopy(next(p for p in self.state["pages"] if p["id"] == id))

    def blocks(self, id):
        tree = copy.deepcopy(self.trees.get(id, []))
        for block in tree:
            if self.trees.get(block["id"]):
                block[block["type"]]["children"] = self.blocks(block["id"])
        return tree

    def create(self, source, properties):
        self.writes.append(("create", source))
        self.next_id += 1
        p = {
            "id": f"new-{self.next_id}",
            "properties": copy.deepcopy(properties),
            "last_edited_time": "created",
        }
        self.state["pages"].append(p)
        if self.fail == "create":
            self.fail = None
            raise SyncError("create outcome unknown")
        return copy.deepcopy(p)

    def append(self, parent, children):
        self.writes.append(("append", parent))
        result = copy.deepcopy(children)
        for child in result:
            self.next_id += 1
            child["id"] = f"block-{self.next_id}"
            embedded = child[child["type"]].pop("children", [])
            if embedded:
                for row in embedded:
                    self.next_id += 1
                    row["id"] = f"block-{self.next_id}"
                self.trees[child["id"]] = embedded
        self.trees.setdefault(parent, []).extend(result)
        if self.fail == "append":
            self.fail = None
            raise SyncError("append outcome unknown")
        return {"results": result}

    def update_properties(self, id, properties):
        self.writes.append(("properties", id))
        p = next(p for p in self.state["pages"] if p["id"] == id)
        p["properties"].update(copy.deepcopy(properties))
        return self.page(id)

    def archive(self, id):
        self.writes.append(("archive", id))
        next(p for p in self.state["pages"] if p["id"] == id)["archived"] = True
        if self.fail == "archive":
            self.fail = None
            raise SyncError("archive outcome unknown")
        return self.page(id)


def test_apply_new_then_new_plan_is_unchanged_and_zero_writes(tmp_path):
    item = entry()
    remote = FakeRemote()
    plan = build_plan([item], remote.snapshot("db"))
    result = apply_plan(remote, [item], plan, tmp_path / "journal.json")
    assert result["completed"] == [item.key]
    assert len(remote.state["pages"]) == 1
    assert rich_value(remote.state["pages"][0], "Key") == item.key
    next_plan = build_plan([item], remote.snapshot("db"), read_blocks=remote.blocks)
    assert next_plan["counts"] == {"UNCHANGED": 1}
    writes = len(remote.writes)
    apply_plan(remote, [item], next_plan, tmp_path / "next.json")
    assert len(remote.writes) == writes


@pytest.mark.parametrize("failure", ["create", "append", "archive"])
def test_partial_failures_resume_without_duplicate_or_early_archive(tmp_path, failure):
    item = entry(body="changed")
    state = snapshot()
    state["pages"] = [page(entry(), "notebook-v1:previous")]
    remote = FakeRemote(state, fail=failure)
    remote.trees["old"] = projection(entry(), [entry()])[1]
    plan = build_plan([item], remote.snapshot("db"), include_updates=True)
    journal = tmp_path / "journal.json"
    with pytest.raises(SyncError):
        apply_plan(remote, [item], plan, journal)
    if failure != "archive":
        assert not remote.page("old").get("archived")
    result = apply_plan(remote, [item], plan, journal, resume=True)
    assert result["completed"] == [item.key]
    assert remote.page("old")["archived"]
    assert len([p for p in remote.state["pages"] if not p.get("archived")]) == 1
    assert [w[0] for w in remote.writes].count("create") == 1


def test_readback_mismatch_preserves_predecessor(tmp_path):
    item = entry(body="changed")
    state = snapshot()
    state["pages"] = [page(entry(), "old-hash")]
    remote = FakeRemote(state)
    original = remote.blocks

    def corrupt(id):
        tree = original(id)
        if tree:
            tree[0][tree[0]["type"]]["rich_text"][0]["text"]["content"] = "corrupted"
        return tree

    remote.blocks = corrupt
    with pytest.raises(SyncError):
        apply_plan(
            remote,
            [item],
            build_plan([item], remote.snapshot("db"), include_updates=True),
            tmp_path / "j.json",
        )
    assert not remote.page("old").get("archived")
    assert all(w[0] != "archive" for w in remote.writes)


@pytest.mark.parametrize("change", ["local", "remote", "schema", "manifest", "blocked"])
def test_stale_or_blocked_manifest_causes_zero_writes(tmp_path, change):
    items = [entry()]
    remote = FakeRemote()
    plan = build_plan(items, remote.snapshot("db"))
    if change == "local":
        items = [entry(body="edit")]
    elif change == "remote":
        remote.state["pages"].append(page(entry("human")))
    elif change == "schema":
        remote.state["schema"]["Key"]["id"] = "changed"
    elif change == "manifest":
        plan["selected"] = []
    else:
        remote.state["schema"].pop("Content Hash")
        plan = build_plan(items, remote.snapshot("db"))
    with pytest.raises(SyncError):
        apply_plan(remote, items, plan, tmp_path / "j.json")
    assert remote.writes == []


def test_journal_cannot_be_reused_for_a_different_manifest(tmp_path):
    item = entry()
    remote = FakeRemote()
    path = tmp_path / "j.json"
    apply_plan(remote, [item], build_plan([item], remote.snapshot("db")), path)
    with pytest.raises(SyncError):
        apply_plan(
            remote,
            [item, entry("second")],
            build_plan([item, entry("second")], remote.snapshot("db")),
            path,
            resume=True,
        )
    assert json.loads(path.read_text())["completed"] == [item.key]


def test_large_recursive_body_table_and_cyclic_wikilinks_read_back(tmp_path):
    body = "> [!note] note\n" + "".join(f"> - item {i}\n" for i in range(205))
    body += "\n| head | value |\n| --- | --- |\n" + "".join(
        f"| {i} | value |\n" for i in range(150)
    )
    first = entry("first", body + "\n[[second]]\n")
    second = entry("second", "[[first]]")
    remote = FakeRemote()
    plan = build_plan([first, second], remote.snapshot("db"))
    apply_plan(remote, [first, second], plan, tmp_path / "j.json")
    after = build_plan([first, second], remote.snapshot("db"), read_blocks=remote.blocks)
    assert after["counts"] == {"UNCHANGED": 2}
    active = {rich_value(p, "Key"): p["id"] for p in remote.state["pages"]}
    blocks = remote.blocks(active[first.key])
    assert len(blocks[0]["callout"]["children"]) == 205
    table = next(b for b in blocks if b["type"] == "table")
    assert len(table["table"]["children"]) == 151
    links = [
        r["text"].get("link", {}).get("url")
        for b in blocks
        if "rich_text" in b[b["type"]]
        for r in b[b["type"]]["rich_text"]
    ]
    assert "https://www.notion.so/" + active[second.key].replace("-", "") in links


def test_unknown_create_with_no_remote_receipt_does_not_retry(tmp_path):
    item = entry()
    remote = FakeRemote()

    def no_receipt(source, props):
        remote.writes.append(("create", source))
        raise SyncError("unknown")

    remote.create = no_receipt
    plan = build_plan([item], remote.snapshot("db"))
    journal = tmp_path / "j.json"
    with pytest.raises(SyncError):
        apply_plan(remote, [item], plan, journal)
    with pytest.raises(SyncError, match="자동 재생성 금지"):
        apply_plan(remote, [item], plan, journal, resume=True)
    assert len(remote.writes) == 1


def test_competing_remote_create_during_fill_prevents_promotion(tmp_path):
    item = entry()
    remote = FakeRemote()
    append = remote.append

    def race(parent, children):
        result = append(parent, children)
        if not any(p["id"] == "competitor" for p in remote.state["pages"]):
            remote.state["pages"].append(page(item, id="competitor"))
        return result

    remote.append = race
    with pytest.raises(SyncError):
        apply_plan(remote, [item], build_plan([item], remote.snapshot("db")), tmp_path / "j.json")
    assert all(w[0] != "properties" for w in remote.writes)


def test_update_of_link_target_requires_dependents_in_manifest(tmp_path):
    first, second = entry("first", "[[second]]"), entry("second", "old")
    remote = FakeRemote()
    apply_plan(
        remote,
        [first, second],
        build_plan([first, second], remote.snapshot("db")),
        tmp_path / "initial.json",
    )
    changed = entry("second", "new")
    plan = build_plan(
        [first, changed],
        remote.snapshot("db"),
        include_updates=True,
        only_keys=[changed.key],
        read_blocks=remote.blocks,
    )
    assert plan["blockers"]
    writes = len(remote.writes)
    with pytest.raises(SyncError):
        apply_plan(remote, [first, changed], plan, tmp_path / "update.json")
    assert len(remote.writes) == writes


def test_transitive_relink_manifest_preserves_live_links(tmp_path):
    a, b, c = entry("a", "[[b]]"), entry("b", "[[c]]"), entry("c", "old")
    remote = FakeRemote()
    apply_plan(
        remote, [a, b, c], build_plan([a, b, c], remote.snapshot("db")), tmp_path / "initial.json"
    )
    changed = entry("c", "new")
    plan = build_plan(
        [a, b, changed], remote.snapshot("db"), include_updates=True, read_blocks=remote.blocks
    )
    assert plan["counts"] == {"RELINK_CANDIDATE": 2, "UPDATE_CANDIDATE": 1}
    assert len(plan["selected"]) == 3
    apply_plan(remote, [a, b, changed], plan, tmp_path / "update.json")
    after = build_plan([a, b, changed], remote.snapshot("db"), read_blocks=remote.blocks)
    assert after["counts"] == {"UNCHANGED": 3}


def test_target_lock_blocks_same_database_with_different_journal(tmp_path):
    import tempfile
    from pathlib import Path

    from src.integrations.notebook_notion.apply import journal_lock
    from src.integrations.notebook_notion.remote import digest

    item = entry()
    remote = FakeRemote()
    lock = Path(tempfile.gettempdir()) / ("jarvis-notebook-notion-" + digest("db") + ".json")
    with journal_lock(lock), pytest.raises(SyncError):
        apply_plan(
            remote, [item], build_plan([item], remote.snapshot("db")), tmp_path / "other.json"
        )
    assert remote.writes == []


def test_new_link_target_requires_existing_dependents_relinked(tmp_path):
    first, second = entry("first", "[[second]]"), entry("second", "body")
    remote = FakeRemote()
    initial = build_plan([first, second], remote.snapshot("db"), only_keys=[first.key])
    apply_plan(remote, [first, second], initial, tmp_path / "initial.json")
    only_target = build_plan(
        [first, second], remote.snapshot("db"), only_keys=[second.key], read_blocks=remote.blocks
    )
    assert only_target["blockers"]
    complete = build_plan(
        [first, second], remote.snapshot("db"), include_updates=True, read_blocks=remote.blocks
    )
    assert complete["counts"] == {"RELINK_CANDIDATE": 1, "CREATE_CANDIDATE": 1}
    apply_plan(remote, [first, second], complete, tmp_path / "complete.json")
    assert build_plan([first, second], remote.snapshot("db"), read_blocks=remote.blocks)[
        "counts"
    ] == {"UNCHANGED": 2}


def test_resume_before_promotion_preserves_candidate_human_edit(tmp_path):
    item = entry()
    remote = FakeRemote()
    plan = build_plan([item], remote.snapshot("db"))
    journal = tmp_path / "j.json"
    update = remote.update_properties
    remote.update_properties = lambda *args: (_ for _ in ()).throw(SyncError("unknown promotion"))
    with pytest.raises(SyncError):
        apply_plan(remote, [item], plan, journal)
    candidate = remote.state["pages"][0]
    candidate["properties"]["이름"]["title"][0]["text"]["content"] = "human edit"
    remote.update_properties = update
    with pytest.raises(SyncError):
        apply_plan(remote, [item], plan, journal, resume=True)
    assert candidate["properties"]["이름"]["title"][0]["text"]["content"] == "human edit"
