import json

import pytest

from src.tools.notebook.markdown import render_markdown


def payload(block):
    return block[block["type"]]


def walk(blocks):
    for block in blocks:
        yield block
        yield from walk(payload(block).get("children", []))


def content(rich_text):
    return "".join(part["text"]["content"] for part in rich_text)


def original(blocks):
    return "".join(
        content(payload(block)["rich_text"])
        for block in blocks
        if block["type"] == "code" and content(payload(block).get("caption", [])) == "Raw Markdown"
    )


def test_readable_body_has_no_automatic_raw_appendix_but_keeps_authored_code():
    blocks = render_markdown("설명\n\n```markdown\n# 작성한 예시\n```\n")
    assert [block["type"] for block in blocks] == ["paragraph", "code"]
    assert content(payload(blocks[1])["rich_text"]) == "# 작성한 예시\n"
    assert original(blocks) == ""


def test_inline_links_annotations_and_unresolved_wikilinks_are_preserved():
    text = "**강조** *기울임* `code` [기사](https://example.com/a_(b)) [[research/2026-10#연구|연구 링크]] [[없는 항목]]"
    blocks = render_markdown(
        text,
        lambda target: "https://notion.so/example" if target == "research/2026-10#연구" else None,
    )
    rich = payload(blocks[0])["rich_text"]
    assert content(rich) == "강조 기울임 code 기사 연구 링크 [[없는 항목]]"
    assert next(part for part in rich if part["text"]["content"] == "강조")["annotations"]["bold"]
    assert next(part for part in rich if part["text"]["content"] == "기울임")["annotations"][
        "italic"
    ]
    assert next(part for part in rich if part["text"]["content"] == "code")["annotations"]["code"]
    assert (
        next(part for part in rich if part["text"]["content"] == "기사")["text"]["link"]["url"]
        == "https://example.com/a_(b)"
    )
    assert (
        next(part for part in rich if part["text"]["content"] == "연구 링크")["text"]["link"]["url"]
        == "https://notion.so/example"
    )
    assert original(blocks) == ""


def test_wikilink_resolver_accepts_logical_urls_for_hashing():
    blocks = render_markdown("[[연구]]", lambda target: "notebook://research/2026-10-14#연구")
    assert (
        payload(blocks[0])["rich_text"][0]["text"]["link"]["url"]
        == "notebook://research/2026-10-14#연구"
    )


def test_callouts_keep_nested_bullets_and_links_as_children():
    text = "> [!note] 내 분석\n> - 상위 [근거](https://example.com)\n>   - 하위\n\n> [!quote] 원문\n> 인용\n\n> [!warning] 리스크\n> 주의\n\n> [!info] 확인\n> 후속"
    blocks = render_markdown(text)
    assert blocks[0]["type"] == "callout"
    assert content(payload(blocks[0])["rich_text"]) == "내 분석"
    child = payload(blocks[0])["children"][0]
    assert child["type"] == "bulleted_list_item"
    assert payload(child)["children"][0]["type"] == "bulleted_list_item"
    assert any(part["text"].get("link") for part in payload(child)["rich_text"])
    assert [block["type"] for block in blocks[:4]] == ["callout", "quote", "callout", "callout"]
    assert (
        len({payload(block)["icon"]["emoji"] for block in [blocks[0], blocks[2], blocks[3]]}) == 3
    )
    assert original(blocks) == ""


def test_nested_lists_table_fence_and_headings_render_as_blocks():
    text = "# 제목\n\n1. 상위\n   - 하위\n\n| 열 A | 열 B |\n| --- | --- |\n| **값** | [링크](https://example.com) |\n\n```python\nprint('hi')\n```\n\n---\n"
    blocks = render_markdown(text)
    assert [block["type"] for block in blocks[:5]] == [
        "heading_1",
        "numbered_list_item",
        "table",
        "code",
        "divider",
    ]
    assert payload(blocks[1])["children"][0]["type"] == "bulleted_list_item"
    table = payload(blocks[2])
    assert table["table_width"] == 2
    assert table["has_column_header"] is True
    assert len(table["children"]) == 2
    assert table["children"][1]["table_row"]["cells"][0][0]["annotations"]["bold"]
    assert payload(blocks[3])["language"] == "python"
    assert content(payload(blocks[3])["rich_text"]) == "print('hi')\n"
    assert original(blocks) == ""


def test_long_unicode_and_many_formatted_spans_respect_notion_limits_losslessly():
    text = "한글😀" * 60000 + "\n\n" + " ".join(f"**항목{i}**" for i in range(140))
    blocks = render_markdown(text)
    for block in walk(blocks):
        data = payload(block)
        for rich in [data.get("rich_text", []), *data.get("cells", [])]:
            assert len(rich) <= 100
            assert all(
                len(part["text"]["content"].encode("utf-16-le")) // 2 <= 2000 for part in rich
            )
    assert original(blocks) == ""
    paragraphs = [block for block in blocks if block["type"] == "paragraph"]
    assert "".join(
        content(payload(block)["rich_text"]) for block in paragraphs
    ) == "한글😀" * 60000 + " ".join(f"항목{i}" for i in range(140))


def test_more_than_100_blocks_and_children_are_retained_for_batched_append():
    text = "> [!note] 분석\n" + "\n".join(f"> - 항목{i}" for i in range(110))
    blocks = render_markdown(text)
    assert len(payload(blocks[0])["children"]) == 110
    assert original(blocks) == ""
    text = "\n\n".join(f"문단{i}" for i in range(110))
    assert len([block for block in render_markdown(text) if block["type"] == "paragraph"]) == 110


def test_unsupported_syntax_remains_readable_without_raw_appendix():
    text = "  <custom>원문</custom>\r\n\r\n$$ a+b $$\r\n[^note]: 주석\r\n"
    blocks = render_markdown(text)
    rendered = "\n".join(content(payload(b).get("rich_text", [])) for b in blocks)
    assert "<custom>원문</custom>" in rendered
    assert "$$ a+b $$" in rendered
    assert "[^note]: 주석" in rendered
    assert original(blocks) == ""


def test_empty_markdown_has_no_placeholder_block():
    assert render_markdown("") == []


@pytest.mark.parametrize(
    "text",
    ["stock_code_value", "https://example.com/a_b_c", "stock__code__value"],
)
def test_intraword_underscores_preserve_identifiers_and_bare_urls(text):
    blocks = render_markdown(text)
    assert content(payload(blocks[0])["rich_text"]) == text


@pytest.mark.parametrize("text, expected", [("#### C#", "C#"), ("# C# ##", "C#")])
def test_heading_preserves_literal_hash_and_removes_only_spaced_closing_marks(text, expected):
    blocks = render_markdown(text)
    assert content(payload(blocks[0])["rich_text"]) == expected


def test_underscore_emphasis_still_formats_delimited_words():
    blocks = render_markdown("_기울임_ __강조__")
    rich = payload(blocks[0])["rich_text"]
    assert content(rich) == "기울임 강조"
    assert rich[0]["annotations"]["italic"]
    assert rich[-1]["annotations"]["bold"]


def test_multiple_blank_lines_after_list_do_not_create_empty_children():
    text = "- 항목\n\n\n다음 문단\n"
    blocks = render_markdown(text)
    assert [block["type"] for block in blocks[:2]] == ["bulleted_list_item", "paragraph"]
    assert "children" not in payload(blocks[0])
    assert original(blocks) == ""


def test_long_text_blocks_stay_below_notion_request_bytes_without_truncation():
    text = "한" * 210000
    blocks = render_markdown(text)
    assert all(len(json.dumps(block, ensure_ascii=False).encode()) < 350000 for block in blocks)
    assert "".join(content(payload(b)["rich_text"]) for b in blocks) == text.rstrip("\n")
    assert original(blocks) == ""


def test_oversized_table_row_falls_back_to_literal_without_data_loss():
    text = "| 열 |\n| --- |\n| " + "한" * 170000 + " |\n"
    blocks = render_markdown(text)
    assert blocks[0]["type"] == "paragraph"
    assert all(len(json.dumps(block, ensure_ascii=False).encode()) < 350000 for block in blocks)
    assert "".join(content(payload(b)["rich_text"]) for b in blocks) == text
    assert original(blocks) == ""
