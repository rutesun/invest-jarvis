"""Notion boundary: read-only by default, no automatic mutation retries."""

import copy
import hashlib
import json
import time

import httpx


class SyncError(ValueError):
    """Safe-to-display sync failure (never includes remote response bodies)."""


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def canonical_rich(items, *, coalesce=False):
    result = []
    for item in items:
        kind = item.get("type", "text")
        if kind != "text":
            # Mentions/equations are preserved so human edits cannot compare equal.
            result.append({"type": kind, kind: item.get(kind)})
            continue
        text = item["text"]
        result.append(
            {
                "text": {"content": text["content"], "link": text.get("link")},
                "annotations": {
                    k: v for k, v in item.get("annotations", {}).items() if v and v != "default"
                },
            }
        )
        if (
            coalesce
            and len(result) > 1
            and "text" in result[-2]
            and result[-2]["annotations"] == result[-1]["annotations"]
            and result[-2]["text"]["link"] == result[-1]["text"]["link"]
        ):
            result[-2]["text"]["content"] += result.pop()["text"]["content"]
    return result


def option_identity(name):
    """Notion matches option names without case or surrounding whitespace."""
    return name.strip().casefold()


def canonical_properties(properties):
    result = {}
    for name, prop in properties.items():
        kind = prop.get("type") or next((k for k in prop if k != "id"), None)
        value = prop.get(kind)
        if kind in ("rich_text", "title"):
            value = canonical_rich(value or [])
        elif kind == "select":
            value = option_identity(value["name"]) if value else None
        elif kind == "multi_select":
            value = sorted({option_identity(v["name"]) for v in value or []})
        elif kind == "date" and value:
            value = {k: value.get(k) for k in ("start", "end", "time_zone")}
        result[name] = {kind: value}
    return result


def canonical_blocks(blocks, *, coalesce_text=True):
    result = []
    for block in blocks:
        kind = block["type"]
        payload = copy.deepcopy(block[kind])
        if payload.get("color") == "default":
            payload.pop("color")
        if kind == "paragraph" and payload.get("icon") is None:
            payload.pop("icon", None)
        if kind.startswith("heading_") and payload.get("is_toggleable") is False:
            payload.pop("is_toggleable")
        if "rich_text" in payload:
            payload["rich_text"] = canonical_rich(payload["rich_text"], coalesce=coalesce_text)
        if "cells" in payload:
            payload["cells"] = [
                canonical_rich(cell, coalesce=coalesce_text) for cell in payload["cells"]
            ]
        if "children" in payload:
            payload["children"] = canonical_blocks(payload["children"], coalesce_text=coalesce_text)
        if kind == "code":
            payload.setdefault("caption", [])
            payload["caption"] = canonical_rich(payload["caption"], coalesce=coalesce_text)
        result.append({"type": kind, kind: payload})
    return result


def rich_value(page, name):
    return "".join(
        t.get("plain_text", t.get("text", {}).get("content", ""))
        for t in page.get("properties", {}).get(name, {}).get("rich_text", [])
    )


class Remote:
    def __init__(self, token: str, *, write_enabled=False, transport=None):
        self.write_enabled = write_enabled
        self.client = httpx.Client(
            base_url="https://api.notion.com/v1/",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2025-09-03",
            },
            timeout=30,
            transport=transport,
        )
        self.last_request = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def request(self, method, path, **kwargs):
        is_read = method == "GET" or (
            method == "POST" and path.startswith("data_sources/") and path.endswith("/query")
        )
        if not is_read and not self.write_enabled:
            raise SyncError("읽기 전용 client에서는 Notion 쓰기가 차단됩니다.")
        time.sleep(max(0, 0.35 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise SyncError(
                "Notion network 오류: 쓰기 결과는 불확실할 수 있습니다. journal로 복구하세요."
            ) from None
        if not response.is_success:
            raise SyncError(f"Notion HTTP {response.status_code}: 자동 재시도하지 않습니다.")
        try:
            return response.json()
        except ValueError:
            raise SyncError("Notion JSON 응답 오류") from None

    def _paginate(self, method, path, *, body=None):
        result, seen = [], set()
        cursor = None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self.request(
                method,
                path,
                **(
                    {"json": {**(body or {}), **params}} if method == "POST" else {"params": params}
                ),
            )
            result.extend(data["results"])
            if not data.get("has_more"):
                return result
            cursor = data.get("next_cursor")
            if not cursor or cursor in seen:
                raise SyncError("Notion pagination cursor 오류")
            seen.add(cursor)

    def query(self, source_id, *, key=None):
        body = {"filter": {"property": "Key", "rich_text": {"equals": key}}} if key else {}
        return self._paginate("POST", f"data_sources/{source_id}/query", body=body)

    def snapshot(self, database_id):
        db = self.request("GET", f"databases/{database_id}")
        sources = db.get("data_sources", [])
        if len(sources) != 1:
            raise SyncError("Database data source가 정확히 1개여야 합니다.")
        source_id = sources[0]["id"]
        source = self.request("GET", f"data_sources/{source_id}")
        pages = self.query(source_id)
        if len({p["id"] for p in pages}) != len(pages):
            raise SyncError("pagination에 중복 page ID가 있습니다.")
        return {
            "database_id": database_id.replace("-", ""),
            "data_source_id": source_id,
            "schema": source["properties"],
            "pages": pages,
        }

    def page(self, page_id):
        return self.request("GET", f"pages/{page_id}")

    def blocks(self, block_id):
        blocks = self._paginate("GET", f"blocks/{block_id}/children")
        for block in blocks:
            if block.get("has_children"):
                block[block["type"]]["children"] = self.blocks(block["id"])
        return blocks

    def create(self, source_id, properties):
        return self.request(
            "POST",
            "pages",
            json={
                "parent": {"type": "data_source_id", "data_source_id": source_id},
                "properties": properties,
            },
        )

    def append(self, block_id, children):
        if not 0 < len(children) <= 100:
            raise SyncError("append batch는 1~100개여야 합니다.")
        return self.request("PATCH", f"blocks/{block_id}/children", json={"children": children})

    def update_properties(self, page_id, properties):
        return self.request("PATCH", f"pages/{page_id}", json={"properties": properties})

    def archive(self, page_id):
        return self.request("PATCH", f"pages/{page_id}", json={"archived": True})
