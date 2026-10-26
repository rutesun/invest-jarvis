"""Parse only monthly H2-date/H3-entry documents, without modifying source files."""

import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from src.tools.notebook.models import NotebookEntry


_TYPES = ("trades", "thoughts", "research")
_ACTIONS = {"매수", "매도", "관망", "손절"}
_MONTH = re.compile(r"^\d{4}-\d{2}\.md$")
_HEADING = re.compile(r"^ {0,3}(#{2,3})\s+(.+?)\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_FIELD = re.compile(r"^\s*-?\s*\*\*([^*]+)\*\*\s*:\s*(.*)$")
_HASHTAG = re.compile(r"#([^\s#]+)")


def _unfenced_lines(text: str):
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        match = _FENCE.match(line.rstrip("\r\n"))
        if fence:
            if (
                match
                and match[1][0] == fence[0]
                and len(match[1]) >= len(fence)
                and not match[2].strip()
            ):
                fence = None
            yield line, False
        elif match:
            fence = match[1]
            yield line, False
        else:
            yield line, True


def _url(text: str) -> str | None:
    match = re.search(r"https?://[^\s<>]+", text)
    if not match:
        return None
    url = match[0]
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1]
    return url


def _trade_candidate(title: str) -> str:
    """Keep the full name before the action, preferring an explicit trailing code."""
    name = re.split(r"\s+(?:매수|매도|관망|손절)(?=\s|$|\()", title, maxsplit=1)[0].strip()
    code = re.search(r"\(([A-Za-z][A-Za-z0-9.^=-]*|\d{6}(?:\.[A-Za-z]+)?)\)\s*$", name)
    return code[1] if code else name


def _entry(kind: str, day: str, title: str, body: str, source_path: str) -> NotebookEntry:
    tags: list[str] = []
    explicit_stocks: list[str] = []
    source_url = pdf_url = None
    for line, visible in _unfenced_lines(body):
        match = _FIELD.match(line) if visible else None
        if not match:
            continue
        label, value = match[1].strip(), match[2]
        if label in {"태그", "액션"}:
            tags.extend(_HASHTAG.findall(value))
        elif label == "종목":
            explicit_stocks.extend(_HASHTAG.findall(value))
        elif label == "출처" and source_url is None:
            source_url = _url(value)
        elif label.replace(" ", "") in {"원문PDF", "PDF원문"} and pdf_url is None:
            candidate = _url(value)
            if candidate and urlparse(candidate).hostname == "drive.google.com":
                pdf_url = candidate
    # Search-backed classification runs after parsing. Preserve each raw candidate.
    stocks = list(explicit_stocks)
    if kind == "trades":
        stocks.insert(0, _trade_candidate(title))
    themes: list[str] = []
    action = None
    for tag in tags:
        if tag in _ACTIONS:
            action = action or tag
        else:
            themes.append(tag)
    return NotebookEntry(
        type=kind,
        date=day,
        title=title,
        body_markdown=body,
        source_path=source_path,
        stocks=list(dict.fromkeys(stocks)),
        themes=list(dict.fromkeys(themes)),
        action=action,
        source_url=source_url,
        pdf_url=pdf_url,
    )


def _parse_file(path: Path, kind: str) -> list[NotebookEntry]:
    # bytes.decode preserves CRLF and trailing whitespace in the entry body.
    text = path.read_bytes().decode("utf-8-sig")
    entries: list[NotebookEntry] = []
    day: str | None = None
    title: str | None = None
    body_start = offset = 0
    frontmatter = text.startswith("---\n") or text.startswith("---\r\n")

    def flush(end: int) -> None:
        if title is not None and day is not None:
            entries.append(
                _entry(
                    kind, day, title, text[body_start:end], f"notebook/{kind}/{path.name}#{title}"
                )
            )

    for number, (line, visible) in enumerate(_unfenced_lines(text), start=1):
        plain = line.rstrip("\r\n")
        if frontmatter:
            if number > 1 and plain.strip() == "---":
                frontmatter = False
            offset += len(line)
            continue
        heading = _HEADING.match(plain) if visible else None
        if heading:
            flush(offset)
            title = None
            if heading[1] == "##":
                value = heading[2]
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                        raise ValueError
                    day = date.fromisoformat(value).isoformat()
                except ValueError:
                    raise ValueError(f"Invalid date header: {path.name}:{number}") from None
            else:
                if day is None:
                    raise ValueError(f"Entry is missing date: {path.name}:{number}")
                title = heading[2]
                body_start = offset + len(line)
        offset += len(line)
    if frontmatter:
        raise ValueError(f"Unclosed frontmatter: {path.name}")
    flush(len(text))
    return entries


def parse_notebook_dir(notebook_dir: Path) -> list[NotebookEntry]:
    """Return deterministic entries; malformed dates/duplicate identities stop the plan."""
    if not notebook_dir.is_dir():
        raise ValueError("Notebook directory does not exist")
    entries: list[NotebookEntry] = []
    keys: set[str] = set()
    for kind in _TYPES:
        for path in sorted((notebook_dir / kind).glob("*.md")):
            if not _MONTH.fullmatch(path.name):
                continue
            try:
                date.fromisoformat(f"{path.stem}-01")
            except ValueError:
                raise ValueError(f"Invalid monthly date: {path.name}") from None
            for entry in _parse_file(path, kind):
                if entry.key in keys:
                    raise ValueError(f"Duplicate notebook Key in {path.name}")
                keys.add(entry.key)
                entries.append(entry)
    return entries
