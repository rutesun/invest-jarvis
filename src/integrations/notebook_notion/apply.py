"""Manifest admission, durable recovery, and verified create-before-archive."""

import copy
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from src.integrations.notebook_notion.plan import (
    STAGING_PREFIX,
    VERSION,
    build_plan,
    local_fingerprint,
    manifest_digest,
    projection,
    remote_fingerprint,
    schema_fingerprint,
)
from src.integrations.notebook_notion.remote import (
    SyncError,
    canonical_blocks,
    canonical_properties,
    digest,
    rich_value,
)


def write_private_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def journal_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SyncError("동일 journal의 다른 실행이 진행 중입니다.") from None
        yield
    finally:
        os.close(fd)


def _shallow(block):
    block = copy.deepcopy(block)
    block.pop("id", None)
    block.pop("has_children", None)
    block[block["type"]].pop("children", None)
    return block


def _batches(blocks):
    batch, size = [], 0
    for block in blocks:
        block_size = len(json.dumps(block, ensure_ascii=False).encode())
        if block_size > 450_000:
            raise SyncError("단일 block이 Notion payload 제한을 넘습니다.")
        if len(batch) == 100 or size + block_size > 450_000:
            yield batch
            batch, size = [], 0
        batch.append(block)
        size += block_size
    if batch:
        yield batch


def _fill_tree(remote, parent, expected):
    """Resume only from a verified prefix; never repeat an unknown append."""
    current = remote.blocks(parent)
    if len(current) > len(expected) or canonical_blocks(
        [_shallow(b) for b in current]
    ) != canonical_blocks([_shallow(b) for b in expected[: len(current)]]):
        raise SyncError("candidate block prefix 불일치: 수동 검토가 필요합니다.")
    new = []
    for block in expected[len(current) :]:
        payload = _shallow(block)
        if block["type"] == "table":
            # Notion requires at least one row when creating a table.
            rows = block["table"].get("children", [])
            if not rows:
                raise SyncError("빈 table은 생성할 수 없습니다.")
            payload["table"]["children"] = [_shallow(rows[0])]
        new.append(payload)
    for batch in _batches(new):
        remote.append(parent, batch)
    current = remote.blocks(parent)
    if len(current) != len(expected):
        raise SyncError("candidate block 수 검증 실패")
    for actual, wanted in zip(current, expected, strict=True):
        children = wanted[wanted["type"]].get("children", [])
        if children:
            _fill_tree(remote, actual["id"], children)


def _verify_properties(remote, page_id, properties):
    page = remote.page(page_id)
    actual = {key: page["properties"].get(key, {}) for key in properties}
    if page.get("archived") or canonical_properties(actual) != canonical_properties(properties):
        raise SyncError("read-back 검증 실패: 기존 page를 보존합니다.")


def _verify(remote, page_id, properties, blocks):
    _verify_properties(remote, page_id, properties)
    if canonical_blocks(remote.blocks(page_id)) != canonical_blocks(blocks):
        raise SyncError("read-back 본문 검증 실패: 기존 page를 보존합니다.")


def _admit(entries, manifest):
    if manifest.get("version") != VERSION or manifest.get("manifest_id") != manifest_digest(
        manifest
    ):
        raise SyncError("manifest version 또는 checksum 불일치")
    if manifest["blockers"]:
        raise SyncError("manifest blocker가 있습니다. schema 검토·재조회가 필요합니다.")
    if manifest["local_fingerprint"] != local_fingerprint(entries):
        raise SyncError("로컬 원본이 manifest 이후 변경되었습니다.")
    rows = {r["key"]: r for r in manifest["entries"]}
    keys = [r["key"] for r in manifest["selected"]]
    if len(keys) != len(set(keys)):
        raise SyncError("manifest 선택 Key 중복")
    for row in manifest["selected"]:
        if row != rows.get(row["key"]) or row["status"] not in (
            "CREATE_CANDIDATE",
            "UPDATE_CANDIDATE",
            "RELINK_CANDIDATE",
        ):
            raise SyncError("legacy/orphan/conflict는 일반 apply 대상이 아닙니다.")


def _check_baseline(remote, snapshot, manifest, journal):
    if (
        snapshot["data_source_id"] != manifest["data_source_id"]
        or schema_fingerprint(snapshot["schema"]) != manifest["schema_fingerprint"]
    ):
        raise SyncError("schema 또는 data source가 manifest 이후 변경되었습니다.")
    candidate_ids = {record.get("page_id") for record in journal["items"].values()}
    current = {p["id"]: p for p in snapshot["pages"] if p["id"] not in candidate_ids}
    allowed_archived = {
        r["old_id"]
        for r in journal["items"].values()
        if r.get("old_id") and r["state"] in ("ARCHIVE_PENDING", "DONE")
    }
    baseline = {p["id"]: p for p in manifest["baseline_pages"]}
    if set(current) - set(baseline):
        raise SyncError("manifest 이후 remote page가 추가되었습니다.")
    for page_id, old in baseline.items():
        if page_id not in current:
            if page_id not in allowed_archived or not remote.page(page_id).get("archived"):
                raise SyncError("manifest 이후 remote page가 사라졌습니다.")
        elif remote_fingerprint([current[page_id]]) != old["fingerprint"]:
            raise SyncError("manifest 이후 remote page가 변경되었습니다.")


def apply_plan(remote, entries, manifest, journal_path: Path, *, resume=False):
    """Only call after external apply approval. This session tests it with fakes."""
    _admit(entries, manifest)
    journal_path = Path(journal_path)
    target_lock = Path(tempfile.gettempdir()) / (
        "jarvis-notebook-notion-" + digest(manifest["database_id"]) + ".json"
    )
    with journal_lock(target_lock), journal_lock(journal_path):
        if journal_path.exists():
            if not resume:
                raise SyncError("journal이 이미 있습니다. --resume으로 복구하세요.")
            journal = json.loads(journal_path.read_text())
            if journal["manifest_id"] != manifest["manifest_id"]:
                raise SyncError("다른 manifest의 journal입니다.")
        else:
            if resume:
                raise SyncError("복구할 journal이 없습니다.")
            journal = {"manifest_id": manifest["manifest_id"], "items": {}, "completed": []}
        source = manifest["data_source_id"]
        # Resolve an unknown create result from its deterministic staging Key.
        for record in journal["items"].values():
            if record["state"] == "CREATE_PENDING":
                candidates = remote.query(source, key=record["staging_key"])
                if len(candidates) != 1:
                    raise SyncError(
                        "create 결과 불확실: staging Key 조회가 유일하지 않습니다. 자동 재생성 금지."
                    )
                record.update(page_id=candidates[0]["id"], state="CREATED")
                write_private_json(journal_path, journal)
        state = remote.snapshot(manifest["database_id"])
        if (
            state["data_source_id"] != source
            or schema_fingerprint(state["schema"]) != manifest["schema_fingerprint"]
        ):
            raise SyncError("schema 또는 data source가 manifest 이후 변경되었습니다.")
        if not journal["items"]:
            if remote_fingerprint(state["pages"]) != manifest["remote_fingerprint"]:
                raise SyncError("remote가 manifest 이후 변경되었습니다.")
            fresh = build_plan(
                entries,
                state,
                only_keys=[r["key"] for r in manifest["selected"]],
                include_updates=True,
                read_blocks=remote.blocks,
            )
            if fresh["blockers"] or fresh["selected"] != manifest["selected"]:
                raise SyncError("적용 대상 재검증 실패")
        _check_baseline(remote, state, manifest, journal)
        index = {e.key: e for e in entries}
        rows = {r["key"]: r for r in manifest["selected"]}

        def save():
            write_private_json(journal_path, journal)

        # Pass 1: allocate all page IDs before rendering cross-entry links.
        for key, row in rows.items():
            if key in journal["items"]:
                continue
            staging_key = STAGING_PREFIX + manifest["manifest_id"][:16] + "/" + key
            if len(staging_key.encode("utf-16-le")) // 2 > 2000:
                raise SyncError("staging Key가 Notion 길이 제한을 넘습니다.")
            properties, _ = projection(index[key], entries)
            properties["Key"] = {"rich_text": [{"text": {"content": staging_key}}]}
            record = {
                "state": "CREATE_PENDING",
                "staging_key": staging_key,
                "old_id": row["page_id"],
            }
            journal["items"][key] = record
            save()
            created = remote.create(source, properties)
            record.update(page_id=created["id"], state="CREATED")
            save()
        page_ids = {p["key"]: p["id"] for p in manifest["baseline_pages"] if p["key"]}
        page_ids.update({key: record["page_id"] for key, record in journal["items"].items()})
        # Pass 2: fill and verify ALL candidates before swapping any predecessor.
        for key, record in journal["items"].items():
            properties, blocks = projection(index[key], entries, page_ids)
            properties["Key"] = {"rich_text": [{"text": {"content": record["staging_key"]}}]}
            if record["state"] in ("CREATED", "FILLING"):
                _verify_properties(remote, record["page_id"], properties)
                record["state"] = "FILLING"
                save()
                _fill_tree(remote, record["page_id"], blocks)
                _verify(remote, record["page_id"], properties, blocks)
                record["state"] = "VERIFIED"
                save()
        for key, record in journal["items"].items():
            properties, blocks = projection(index[key], entries, page_ids)
            staged_props = copy.deepcopy(properties)
            staged_props["Key"] = {"rich_text": [{"text": {"content": record["staging_key"]}}]}
            _check_baseline(remote, remote.snapshot(manifest["database_id"]), manifest, journal)
            if record["state"] == "VERIFIED":
                _verify(remote, record["page_id"], staged_props, blocks)
                record["state"] = "PROMOTE_PENDING"
                save()
            if record["state"] == "PROMOTE_PENDING":
                actual_key = rich_value(remote.page(record["page_id"]), "Key")
                if actual_key == record["staging_key"]:
                    _verify(remote, record["page_id"], staged_props, blocks)
                    remote.update_properties(record["page_id"], properties)
                elif actual_key != key:
                    raise SyncError("candidate Key가 변경되었습니다.")
                _verify(remote, record["page_id"], properties, blocks)
                record["state"] = "ARCHIVE_PENDING"
                save()
            if record["state"] == "ARCHIVE_PENDING":
                _verify(remote, record["page_id"], properties, blocks)
                old_id = record["old_id"]
                if old_id:
                    old = remote.page(old_id)
                    if not old.get("archived"):
                        original = next(p for p in manifest["baseline_pages"] if p["id"] == old_id)
                        if remote_fingerprint([old]) != original["fingerprint"]:
                            raise SyncError("교체 직전 기존 page가 변경되어 archive를 차단합니다.")
                        remote.archive(old_id)
                    if not remote.page(old_id).get("archived"):
                        raise SyncError("archive read-back 실패")
                record["state"] = "DONE"
                if key not in journal["completed"]:
                    journal["completed"].append(key)
                save()
            if record["state"] == "DONE":
                _verify(remote, record["page_id"], properties, blocks)
        save()
        return journal
