"""Readable Notion blocks; the complete Markdown source stays in the local notebook."""

import json
import re
from collections.abc import Callable

from src.tools.notebook.models import split_text


Resolver = Callable[[str], str | None]
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_LIST = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.*)$")
_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_DIVIDER = re.compile(r"^ {0,3}(?:\*\s*){3,}$|^ {0,3}(?:-\s*){3,}$|^ {0,3}(?:_\s*){3,}$")
_CALLOUT = re.compile(r"^\[!(\w+)\][+-]?\s*(.*)$")
_ICONS = {"note": "📝", "warning": "⚠️", "info": "ℹ️"}
_LANGUAGES = {
    "bash",
    "c",
    "c++",
    "c#",
    "css",
    "go",
    "html",
    "java",
    "javascript",
    "json",
    "kotlin",
    "latex",
    "lua",
    "markdown",
    "php",
    "plain text",
    "python",
    "r",
    "ruby",
    "rust",
    "shell",
    "sql",
    "swift",
    "toml",
    "typescript",
    "xml",
    "yaml",
}
_LANGUAGE_ALIASES = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "sh": "shell",
    "md": "markdown",
    "yml": "yaml",
}
_MAX_BLOCK_BYTES = 340000


def _text(text: str, annotations: dict | None = None, url: str | None = None) -> list[dict]:
    parts = []
    for chunk in split_text(text):
        value: dict = {"content": chunk}
        if url:
            value["link"] = {"url": url}
        item: dict = {"type": "text", "text": value}
        if annotations:
            item["annotations"] = dict(annotations)
        parts.append(item)
    return parts


def _markdown_link(text: str, start: int) -> tuple[str, str, int] | None:
    label_end = text.find("](", start + 1)
    if label_end < 0:
        return None
    index, depth = label_end + 2, 1
    url_start = index
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                url = text[url_start:index]
                if (
                    url.startswith(("https://", "http://", "mailto:"))
                    and not re.search(r"\s", url)
                    and len(url) <= 2000
                ):
                    return text[start + 1 : label_end], url, index + 1
                return None
        index += 1
    return None


def _inline(text: str, resolver: Resolver | None, annotations: dict | None = None) -> list[dict]:
    parts: list[dict] = []
    plain: list[str] = []
    index = 0

    def flush() -> None:
        parts.extend(_text("".join(plain), annotations))
        plain.clear()

    while index < len(text):
        if text.startswith("[[", index):
            end = text.find("]]", index + 2)
            if end >= 0:
                literal = text[index : end + 2]
                target, separator, label = text[index + 2 : end].partition("|")
                url = resolver(target) if resolver else None
                flush()
                parts.extend(
                    _text(label if separator else target, annotations, url)
                    if url
                    else _text(literal, annotations)
                )
                index = end + 2
                continue
        if text[index] == "[":
            link = _markdown_link(text, index)
            if link:
                label, url, end = link
                flush()
                label_parts = _inline(label, resolver, annotations)
                for part in label_parts:
                    part["text"]["link"] = {"url": url}
                parts.extend(label_parts)
                index = end
                continue
        matched = False
        for delimiter, style in (
            ("`", "code"),
            ("**", "bold"),
            ("__", "bold"),
            ("~~", "strikethrough"),
            ("*", "italic"),
            ("_", "italic"),
        ):
            if not text.startswith(delimiter, index):
                continue
            end = text.find(delimiter, index + len(delimiter))
            if end > index + len(delimiter):
                flush()
                styled = {**(annotations or {}), style: True}
                inner = text[index + len(delimiter) : end]
                parts.extend(
                    _text(inner, styled) if style == "code" else _inline(inner, resolver, styled)
                )
                index, matched = end + len(delimiter), True
                break
        if not matched:
            plain.append(text[index])
            index += 1
    flush()
    return parts


def _block(kind: str, data: dict) -> dict:
    return {"object": "block", "type": kind, kind: data}


def _rich_blocks(kind: str, rich: list[dict], **fields) -> list[dict]:
    # ASCII escaping is the upper bound for either JSON serializer. Leave room
    # for the outer request so a single block never exceeds Notion's 500KB limit.
    overhead = len(json.dumps(fields)) + 128
    groups: list[list[dict]] = []
    group: list[dict] = []
    size = overhead
    for part in rich:
        part_size = len(json.dumps(part)) + 2
        if group and (len(group) == 100 or size + part_size >= _MAX_BLOCK_BYTES):
            groups.append(group)
            group, size = [], overhead
        group.append(part)
        size += part_size
    groups.append(group)
    return [_block(kind, {"rich_text": group, **fields}) for group in groups]


def _cells(line: str) -> list[str]:
    """Honor escaped pipes and code-span pipes when splitting a table row."""
    value = line.strip().strip("|")
    cells: list[str] = []
    start = 0
    code = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "`":
            code = not code
        elif char == "|" and not code:
            cells.append(value[start:index].strip())
            start = index + 1
    cells.append(value[start:].strip())
    return cells


def _table_at(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and "|" in lines[index]
        and all(re.fullmatch(r":?-{3,}:?", cell) for cell in _cells(lines[index + 1]))
    )


def _special(lines: list[str], index: int) -> bool:
    line = lines[index].rstrip("\r\n")
    return bool(
        _FENCE.match(line)
        or _HEADING.match(line)
        or _DIVIDER.match(line)
        or _LIST.match(line)
        or re.match(r"^ {0,3}>", line)
        or _table_at(lines, index)
    )


def _render_lines(lines: list[str], resolver: Resolver | None) -> list[dict]:
    blocks: list[dict] = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip("\r\n")
        if not line.strip():
            index += 1
            continue
        fence = _FENCE.match(line)
        heading = _HEADING.match(line)
        item = _LIST.match(line)
        if fence:
            marker, language = fence[1], fence[2].strip().split(" ")[0].lower()
            language = _LANGUAGE_ALIASES.get(language, language)
            if language not in _LANGUAGES:
                language = "plain text"
            index += 1
            code: list[str] = []
            while index < len(lines):
                closing = _FENCE.match(lines[index].rstrip("\r\n"))
                if (
                    closing
                    and closing[1][0] == marker[0]
                    and len(closing[1]) >= len(marker)
                    and not closing[2].strip()
                ):
                    index += 1
                    break
                code.append(lines[index])
                index += 1
            blocks.extend(_rich_blocks("code", _text("".join(code)), language=language))
        elif heading:
            blocks.extend(
                _rich_blocks(f"heading_{min(len(heading[1]), 3)}", _inline(heading[2], resolver))
            )
            index += 1
        elif _DIVIDER.match(line):
            blocks.append(_block("divider", {}))
            index += 1
        elif re.match(r"^ {0,3}>", line):
            quote: list[str] = []
            while index < len(lines) and re.match(r"^ {0,3}>", lines[index]):
                quote.append(re.sub(r"^ {0,3}> ?", "", lines[index], count=1))
                index += 1
            first = quote[0].rstrip("\r\n")
            callout = _CALLOUT.match(first)
            kind = "quote" if callout is None or callout[1].lower() == "quote" else "callout"
            title = callout[2] if callout else first
            fields = (
                {"icon": {"type": "emoji", "emoji": _ICONS.get(callout[1].lower(), "📝")}}
                if kind == "callout"
                else {}
            )
            rendered = _rich_blocks(kind, _inline(title, resolver), **fields)
            children = _render_lines(quote[1:], resolver)
            if children:
                rendered[-1][kind]["children"] = children
            blocks.extend(rendered)
        elif _table_at(lines, index):
            rows = [_cells(lines[index])]
            width = len(rows[0])
            start = index
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_cells(lines[index]))
                index += 1
            rendered_rows = [[_inline(cell, resolver) for cell in row] for row in rows]
            if any(
                len(row) != width
                or any(len(cell) > 100 for cell in row)
                or len(json.dumps({"cells": row})) >= _MAX_BLOCK_BYTES
                for row in rendered_rows
            ):
                # An invalid/oversized table remains literal, without truncation.
                blocks.extend(_rich_blocks("paragraph", _text("".join(lines[start:index]))))
            else:
                blocks.append(
                    _block(
                        "table",
                        {
                            "table_width": width,
                            "has_column_header": True,
                            "has_row_header": False,
                            "children": [
                                _block("table_row", {"cells": row}) for row in rendered_rows
                            ],
                        },
                    )
                )
        elif item:
            kind = "bulleted_list_item" if item[2] in {"-", "+", "*"} else "numbered_list_item"
            rendered = _rich_blocks(kind, _inline(item[3], resolver))
            indentation = len(item[1].expandtabs(4))
            index += 1
            child_lines: list[str] = []
            while index < len(lines):
                following = lines[index]
                if not following.strip():
                    if (
                        index + 1 >= len(lines)
                        or len(lines[index + 1]) - len(lines[index + 1].lstrip()) <= indentation
                    ):
                        break
                elif len(following) - len(following.lstrip()) <= indentation:
                    break
                child_lines.append(following)
                index += 1
            if any(child.strip() for child in child_lines):
                dedent = min(
                    len(child) - len(child.lstrip()) for child in child_lines if child.strip()
                )
                children = _render_lines(
                    [child[dedent:] if child.strip() else child for child in child_lines], resolver
                )
                if children:
                    rendered[-1][kind]["children"] = children
            blocks.extend(rendered)
        else:
            paragraph = [line]
            index += 1
            while index < len(lines) and lines[index].strip() and not _special(lines, index):
                paragraph.append(lines[index].rstrip("\r\n"))
                index += 1
            blocks.extend(_rich_blocks("paragraph", _inline("\n".join(paragraph), resolver)))
    return blocks


def render_markdown(text: str, resolver: Resolver | None = None) -> list[dict]:
    """Render the reading copy without duplicating the source as an appendix."""
    return _render_lines(text.splitlines(keepends=True), resolver)
