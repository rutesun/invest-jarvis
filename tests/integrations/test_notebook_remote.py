import httpx
import pytest

from src.integrations.notebook_notion.remote import Remote, SyncError, canonical_blocks


def test_remote_query_paginates_without_mutations():
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/query"):
            import json

            body = json.loads(request.content)
            if "start_cursor" not in body:
                return httpx.Response(
                    200, json={"results": [{"id": "one"}], "has_more": True, "next_cursor": "next"}
                )
            assert body["start_cursor"] == "next"
            return httpx.Response(
                200, json={"results": [{"id": "two"}], "has_more": False, "next_cursor": None}
            )
        raise AssertionError("unexpected endpoint")

    with Remote("fake", transport=httpx.MockTransport(handle)) as remote:
        assert [p["id"] for p in remote.query("source")] == ["one", "two"]
        with pytest.raises(SyncError, match="읽기 전용"):
            remote.create("source", {})
    assert all(method == "POST" and path.endswith("/query") for method, path in calls)


def test_recursive_blocks_pagination_and_canonical_readback():
    def handle(request):
        if request.url.path == "/v1/blocks/page/children":
            if request.url.params.get("start_cursor"):
                return httpx.Response(
                    200,
                    json={
                        "results": [{"id": "b", "type": "divider", "divider": {}}],
                        "has_more": False,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "a",
                            "type": "callout",
                            "has_children": True,
                            "callout": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "plain_text": "note",
                                        "href": None,
                                        "text": {"content": "note", "link": None},
                                        "annotations": {"bold": False, "color": "default"},
                                    }
                                ],
                                "icon": {"type": "emoji", "emoji": "💡"},
                                "color": "default",
                            },
                        }
                    ],
                    "has_more": True,
                    "next_cursor": "cursor",
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "child",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": "child"}}]
                        },
                    }
                ],
                "has_more": False,
            },
        )

    expected = [
        {
            "type": "callout",
            "callout": {
                "rich_text": [{"text": {"content": "note"}}],
                "icon": {"type": "emoji", "emoji": "💡"},
                "children": [
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"text": {"content": "child"}}]},
                    }
                ],
            },
        },
        {"type": "divider", "divider": {}},
    ]
    with Remote("fake", transport=httpx.MockTransport(handle)) as remote:
        assert canonical_blocks(remote.blocks("page")) == canonical_blocks(expected)


def test_broken_pagination_and_error_messages_fail_closed():
    with (
        Remote(
            "fake",
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, json={"results": [], "has_more": True, "next_cursor": None}
                )
            ),
        ) as remote,
        pytest.raises(SyncError, match="pagination"),
    ):
        remote.query("source")
    with Remote(
        "secret",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={"message": "secret private text"})
        ),
    ) as remote:
        with pytest.raises(SyncError) as error:
            remote.query("source")
        assert "secret" not in str(error.value)


def test_readback_keeps_links_annotations_and_order():
    plain = [
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "text": {"content": "a", "link": {"url": "https://example.com"}},
                        "annotations": {"bold": True},
                    }
                ]
            },
        }
    ]
    edited = [
        {
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": "a"}, "annotations": {"bold": True}}]},
        }
    ]
    assert canonical_blocks(plain) != canonical_blocks(edited)


def test_notion_coalesced_adjacent_rich_text_preserves_content_and_style():
    def paragraph(parts):
        return [{"type": "paragraph", "paragraph": {"rich_text": parts}}]

    split = paragraph(
        [
            {"text": {"content": "text "}},
            {"text": {"content": "[[unresolved]]"}},
            {"text": {"content": " link", "link": {"url": "https://example.com"}}},
        ]
    )
    merged = paragraph(
        [
            {"text": {"content": "text [[unresolved]]"}},
            {"text": {"content": " link", "link": {"url": "https://example.com"}}},
        ]
    )
    assert canonical_blocks(split) == canonical_blocks(merged)
    merged[0]["paragraph"]["rich_text"][0]["text"]["content"] = "changed"
    assert canonical_blocks(split) != canonical_blocks(merged)


def test_notion_empty_paragraph_icon_is_a_default_but_real_icon_is_preserved():
    expected = [{"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "text"}}]}}]
    actual = [
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": "text"}}],
                "icon": None,
            },
        }
    ]
    assert canonical_blocks(actual) == canonical_blocks(expected)
    actual[0]["paragraph"]["icon"] = {"type": "emoji", "emoji": "*"}
    assert canonical_blocks(actual) != canonical_blocks(expected)


def test_notions_default_heading_and_code_caption_read_back():
    expected = [
        {"type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "title"}}]}},
        {
            "type": "code",
            "code": {
                "rich_text": [{"text": {"content": "raw"}}],
                "language": "markdown",
                "caption": [{"type": "text", "text": {"content": "Raw Markdown"}}],
            },
        },
    ]
    actual = [
        {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": "title", "link": None},
                        "annotations": {"bold": False, "color": "default"},
                        "plain_text": "title",
                        "href": None,
                    }
                ],
                "is_toggleable": False,
                "color": "default",
            },
        },
        {
            "type": "code",
            "code": {
                "rich_text": [{"text": {"content": "raw", "link": None}}],
                "language": "markdown",
                "caption": [
                    {
                        "type": "text",
                        "text": {"content": "Raw Markdown", "link": None},
                        "annotations": {"bold": False, "color": "default"},
                        "plain_text": "Raw Markdown",
                        "href": None,
                    }
                ],
            },
        },
    ]
    assert canonical_blocks(actual) == canonical_blocks(expected)
