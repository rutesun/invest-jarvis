from src.integrations.notion import _markdown_to_blocks


def test_markdown_to_blocks_treats_hashtag_line_as_paragraph():
    blocks = _markdown_to_blocks("# Report\n\n#KB금융 #신한지주\n\nnext")

    assert [block["type"] for block in blocks] == [
        "heading_2",
        "paragraph",
        "paragraph",
    ]
