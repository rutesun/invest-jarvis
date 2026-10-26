"""Notebook identity and writable Notion properties."""

from dataclasses import dataclass, field
from urllib.parse import urlparse


def split_text(text: str, limit: int = 2000) -> list[str]:
    """Split without dropping characters, counting Notion's UTF-16 units."""
    chunks: list[str] = []
    start = units = 0
    for index, char in enumerate(text):
        width = 2 if ord(char) > 0xFFFF else 1
        if units + width > limit:
            chunks.append(text[start:index])
            start, units = index, 0
        units += width
    if start < len(text):
        chunks.append(text[start:])
    return chunks


def text_property(text: str, kind: str = "rich_text") -> dict:
    parts = [{"type": "text", "text": {"content": chunk}} for chunk in split_text(text)]
    if len(parts) > 100:
        raise ValueError("Notion property exceeds 100 rich_text items")
    return {kind: parts}


@dataclass
class NotebookEntry:
    type: str
    date: str
    title: str
    body_markdown: str
    source_path: str
    stocks: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    action: str | None = None
    source_url: str | None = None
    pdf_url: str | None = None

    @property
    def key(self) -> str:
        return f"{self.type}/{self.date}#{self.title}"

    def properties(self) -> dict:
        """Content Hash belongs to the projection planner, not the source."""
        for names in (self.stocks, self.themes):
            if len(names) > 100:
                raise ValueError("Notion multi_select exceeds 100 items")
        for name in [
            self.type,
            *self.stocks,
            *self.themes,
            *([self.action] if self.action else []),
        ]:
            if not name or "," in name or len(name.encode("utf-16-le")) // 2 > 100:
                raise ValueError(
                    "Notion select name is empty, contains comma, or exceeds 100 units"
                )
        for url in (self.source_url, self.pdf_url):
            if url is None:
                continue
            try:
                parsed = urlparse(url)
                valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            except ValueError:
                valid = False
            if (
                not valid
                or any(char.isspace() for char in url)
                or len(url.encode("utf-16-le")) // 2 > 2000
            ):
                raise ValueError("Notion URL is invalid or exceeds 2000 units")
        return {
            "이름": text_property(self.title, "title"),
            "Type": {"select": {"name": self.type}},
            "Date": {"date": {"start": self.date}},
            "종목": {"multi_select": [{"name": name} for name in self.stocks]},
            "테마": {"multi_select": [{"name": name} for name in self.themes]},
            "액션": {"select": {"name": self.action} if self.action else None},
            "출처": {"url": self.source_url},
            "Key": text_property(self.key),
            "Source Path": text_property(self.source_path),
            "PDF 원문": {"url": self.pdf_url},
        }
