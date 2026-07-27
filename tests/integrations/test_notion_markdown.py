from src.integrations.notion import _markdown_to_blocks


def test_markdown_to_blocks_treats_hashtag_line_as_paragraph():
    blocks = _markdown_to_blocks("# Report\n\n#KB금융 #신한지주\n\nnext")

    assert [block["type"] for block in blocks] == [
        "heading_2",
        "paragraph",
        "paragraph",
    ]


def test_markdown_to_blocks_consumes_non_table_pipe_line():
    """표 형식이 아닌 '|' 시작 줄도 소비된다 (수정 전에는 무한 루프)."""
    blocks = _markdown_to_blocks("text\n| lone pipe at eof")

    assert [block["type"] for block in blocks] == ["paragraph", "paragraph"]


def test_markdown_to_blocks_consumes_pipe_line_followed_by_text():
    blocks = _markdown_to_blocks("| header only\nplain text")

    assert [block["type"] for block in blocks] == ["paragraph", "paragraph"]
