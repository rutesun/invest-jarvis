#!/usr/bin/env python3
"""Fetch and clean public Lilys AI digest note content."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request


NOTE_API = (
    "https://wp8tovrz8a.execute-api.ap-northeast-2.amazonaws.com/release"
    "/v3/note/{session_id}/{note_id}?provider=&whisper=false"
)


def parse_lilys_url(url: str) -> tuple[str, str]:
    match = re.search(r"lilys\.ai/digest/(\d+)/(\d+)", url)
    if not match:
        raise ValueError(
            "Lilys digest URL must look like https://lilys.ai/digest/{session_id}/{note_id}"
        )
    return match.group(1), match.group(2)


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def clean_content(content: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</(p|li|ul|ol|h[1-6]|lilys-heading|lilys-section)>", "\n", text, flags=re.IGNORECASE
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a public Lilys AI digest note.")
    parser.add_argument("url", help="Lilys digest URL")
    parser.add_argument(
        "--max-chars", type=int, default=0, help="Truncate cleaned content to N characters"
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    args = parser.parse_args()

    try:
        session_id, note_id = parse_lilys_url(args.url)
        api_url = NOTE_API.format(session_id=session_id, note_id=note_id)
        payload = fetch_json(api_url)
        note = payload.get("note") or {}
        content = clean_content(note.get("content") or "")
        if args.max_chars and len(content) > args.max_chars:
            content = content[: args.max_chars].rstrip()

        result = {
            "title": note.get("title") or "",
            "session_id": session_id,
            "note_id": note_id,
            "status": note.get("status") or payload.get("status") or "",
            "content": content,
        }

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Title: {result['title']}")
            print(f"Session: {session_id}")
            print(f"Note: {note_id}")
            print()
            print(content)
        return 0
    except (ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
