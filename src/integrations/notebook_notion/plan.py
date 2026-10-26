"""Pure planning and stable logical-link projections; no remote writes."""

import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from urllib.parse import quote

from src.integrations.notebook_notion.remote import (
    SyncError,
    canonical_blocks,
    canonical_properties,
    digest,
    option_identity,
    rich_value,
)


VERSION = "notebook-v2"
BASE_SCHEMA = {
    "이름": "title",
    "Type": "select",
    "Date": "date",
    "종목": "multi_select",
    "테마": "multi_select",
    "액션": "select",
    "출처": "url",
    "Key": "rich_text",
}
EXTRA_SCHEMA = {"Source Path": "rich_text", "Content Hash": "rich_text", "PDF 원문": "url"}
STAGING_PREFIX = "__staging__/"


def manifest_digest(manifest):
    return digest({k: v for k, v in manifest.items() if k not in ("manifest_id", "created_at")})


def schema_fingerprint(schema):
    return digest(schema)


def remote_fingerprint(pages):
    return digest(
        sorted(
            [
                {
                    "id": p["id"],
                    "edited": p.get("last_edited_time"),
                    "properties": canonical_properties(p["properties"]),
                }
                for p in pages
            ],
            key=lambda p: p["id"],
        )
    )


def local_fingerprint(entries):
    return digest(
        sorted(
            [
                {"key": e.key, "body": e.body_markdown, "properties": e.properties()}
                for e in entries
            ],
            key=lambda e: e["key"],
        )
    )


def stock_groups(entries):
    """Preview the local projection by stock, including unselected/legacy entries."""
    groups = defaultdict(set)
    for entry in entries:
        for option in entry.properties().get("종목", {}).get("multi_select", []):
            groups[option["name"]].add(entry.key)
    return {name: sorted(keys) for name, keys in sorted(groups.items())}


def resolve_key(target, current, entries):
    target = target.split("|", 1)[0]
    if "#" in target:
        path, title = target.split("#", 1)
        path = path.removeprefix("notebook/").removesuffix(".md")
        candidates = [
            e
            for e in entries
            if e.title == title
            and (
                not path
                or e.source_path.split("#")[0].removeprefix("notebook/").removesuffix(".md") == path
                or (
                    "/" not in path
                    and e.type == current.type
                    and e.source_path.split("#")[0].endswith("/" + path + ".md")
                )
            )
        ]
    else:
        candidates = [e for e in entries if e.title == target]
    return candidates[0].key if len(candidates) == 1 else None


def projection(entry, entries, page_ids=None):
    from src.tools.notebook.markdown import render_markdown

    def resolver(target):
        key = resolve_key(target, entry, entries)
        if not key:
            return None
        if page_ids is not None:
            page_id = page_ids.get(key)
            return "https://www.notion.so/" + page_id.replace("-", "") if page_id else None
        return "https://notebook.invalid/" + quote(key, safe="")

    properties = entry.properties()
    logical_blocks = render_markdown(
        entry.body_markdown,
        lambda t: (
            ("https://notebook.invalid/" + quote(key, safe=""))
            if (key := resolve_key(t, entry, entries))
            else None
        ),
    )
    hash_value = (
        VERSION
        + ":"
        + digest(
            {
                "properties": canonical_properties(properties),
                # Text segmentation is independent from read-back normalization.
                "blocks": canonical_blocks(logical_blocks, coalesce_text=False),
            }
        )
    )
    properties["Content Hash"] = {"rich_text": [{"text": {"content": hash_value}}]}
    blocks = logical_blocks if page_ids is None else render_markdown(entry.body_markdown, resolver)
    return properties, blocks


def schema_check(schema, entries):
    blockers, proposal = [], {}
    for name, kind in {**BASE_SCHEMA, **EXTRA_SCHEMA}.items():
        if name not in schema:
            if name in BASE_SCHEMA:
                blockers.append("SCHEMA_DRIFT:" + name)
            else:
                proposal[name] = {kind: {}}
        elif schema[name].get("type") != kind:
            blockers.append("SCHEMA_DRIFT:" + name)
    for name, kind, required in [
        ("Type", "select", {"trades", "thoughts", "research"}),
        ("액션", "select", {e.action for e in entries if e.action}),
        *[
            (
                name,
                "multi_select",
                {
                    o["name"]
                    for e in entries
                    for o in e.properties().get(name, {}).get("multi_select", [])
                },
            )
            for name in ("종목", "테마")
        ],
    ]:
        prop = schema.get(name, {})
        if prop.get("type") != kind:
            continue
        options = prop[kind].get("options", [])
        existing = {option_identity(o["name"]) for o in options}
        missing = {name for name in required if option_identity(name) not in existing}
        if missing:
            proposal[name] = {
                kind: {"options": [*options, *[{"name": option} for option in sorted(missing)]]}
            }
    if proposal:
        blockers.append("SCHEMA_CHANGE_REQUIRED")
    return blockers, {"properties": proposal}


def build_plan(entries, snapshot, *, only_keys=None, include_updates=False, read_blocks=None):
    blockers, proposal = schema_check(snapshot["schema"], entries)
    local = {e.key: e for e in entries}
    if len(local) != len(entries):
        blockers.append("DUPLICATE_LOCAL_KEY")
    remote = defaultdict(list)
    unmanaged = 0
    for page in snapshot["pages"]:
        key = rich_value(page, "Key")
        if key.startswith(STAGING_PREFIX):
            blockers.append("RECOVERY_REQUIRED:" + page["id"])
        elif key:
            remote[key].append(page)
        else:
            unmanaged += 1
    duplicate_keys = {key for key, pages in remote.items() if len(pages) != 1}
    blockers.extend("DUPLICATE_REMOTE_KEY:" + key for key in sorted(duplicate_keys))
    page_ids = {key: pages[0]["id"] for key, pages in remote.items() if len(pages) == 1}
    rows, warnings = [], []
    for entry in sorted(entries, key=lambda e: e.key):
        properties, _ = projection(entry, entries)
        hash_value = properties["Content Hash"]["rich_text"][0]["text"]["content"]
        pages = remote.get(entry.key, [])
        status = "CREATE_CANDIDATE"
        if entry.key in duplicate_keys:
            status = "CONFLICT"
        elif pages:
            old_hash = rich_value(pages[0], "Content Hash")
            status = (
                "LEGACY_UNVERIFIED"
                if not old_hash
                else ("UNCHANGED" if old_hash == hash_value else "UPDATE_CANDIDATE")
            )
            if status == "UNCHANGED" and read_blocks:
                expected_props, expected_blocks = projection(entry, entries, page_ids)
                actual_props = {k: pages[0]["properties"].get(k, {}) for k in expected_props}
                if canonical_properties(actual_props) != canonical_properties(
                    expected_props
                ) or canonical_blocks(read_blocks(pages[0]["id"])) != canonical_blocks(
                    expected_blocks
                ):
                    status = "CONFLICT"
                    blockers.append("REMOTE_EDIT:" + pages[0]["id"])
        for target in re.findall(r"\[\[([^\]]+)\]\]", entry.body_markdown):
            if not resolve_key(target, entry, entries):
                warnings.append(
                    {"key": entry.key, "warning": "UNRESOLVED_WIKILINK", "target": target}
                )
        rows.append(
            {
                "key": entry.key,
                "source_path": entry.source_path,
                "hash": hash_value,
                "status": status,
                "page_id": pages[0]["id"] if len(pages) == 1 else None,
            }
        )
    for key in sorted(set(remote) - set(local)):
        rows.append(
            {
                "key": key,
                "status": "CONFLICT" if key in duplicate_keys else "ORPHAN_CANDIDATE",
                "page_id": remote[key][0]["id"],
            }
        )
    # Replacing a target changes its page ID. Explicitly plan transitive link
    # dependents so a successful sync cannot leave links to archived pages.
    row_index = {r["key"]: r for r in rows}
    dependencies = {
        e.key: {
            key
            for target in re.findall(r"\[\[([^\]]+)\]\]", e.body_markdown)
            if (key := resolve_key(target, e, entries))
        }
        for e in entries
    }
    replaced = {r["key"] for r in rows if r["status"] in ("CREATE_CANDIDATE", "UPDATE_CANDIDATE")}
    while True:
        dependents = {
            key
            for key, targets in dependencies.items()
            if targets & replaced and row_index[key]["status"] == "UNCHANGED"
        }
        if not dependents:
            break
        for key in dependents:
            row_index[key]["status"] = "RELINK_CANDIDATE"
        replaced |= dependents
    eligible = {
        r["key"]: r
        for r in rows
        if r["status"] == "CREATE_CANDIDATE"
        or (include_updates and r["status"] in ("UPDATE_CANDIDATE", "RELINK_CANDIDATE"))
    }
    if only_keys and any(key not in eligible for key in only_keys):
        raise SyncError("선택 Key가 없거나 일반 apply 대상이 아닙니다.")
    selected = [eligible[k] for k in sorted(only_keys if only_keys is not None else eligible)]
    selected_replacements = {r["key"] for r in selected}
    for key, targets in dependencies.items():
        if (
            targets & selected_replacements
            and row_index[key]["status"] in ("UNCHANGED", "RELINK_CANDIDATE", "UPDATE_CANDIDATE")
            and key not in {r["key"] for r in selected}
        ):
            blockers.append("LINK_DEPENDENTS_MISSING:" + key)
    plan = {
        "version": VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "database_id": snapshot["database_id"],
        "data_source_id": snapshot["data_source_id"],
        "schema_fingerprint": schema_fingerprint(snapshot["schema"]),
        "local_fingerprint": local_fingerprint(entries),
        "remote_fingerprint": remote_fingerprint(snapshot["pages"]),
        "baseline_pages": [
            {"id": p["id"], "key": rich_value(p, "Key"), "fingerprint": remote_fingerprint([p])}
            for p in snapshot["pages"]
        ],
        "counts": dict(Counter(r["status"] for r in rows)),
        "unmanaged": unmanaged,
        "entries": rows,
        "stock_groups": stock_groups(entries),
        "selected": selected,
        "warnings": warnings,
        "blockers": sorted(set(blockers)),
        "schema_proposal": proposal,
    }
    plan["manifest_id"] = manifest_digest(plan)
    return plan
