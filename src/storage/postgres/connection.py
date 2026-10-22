from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def resolve_db_dsn(env_keys: tuple[str, ...], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for key in env_keys:
        if value := os.getenv(key):
            return value
    raise ValueError(f"DB DSN이 없습니다: {', '.join(env_keys)}")


def _load_psycopg() -> Any:
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency/runtime guard
        raise RuntimeError("psycopg가 설치되지 않았습니다. `uv sync` 후 다시 실행하세요.") from exc
    return psycopg


@contextmanager
def connect_db(dsn: str) -> Iterator[Any]:
    conn = _load_psycopg().connect(dsn)
    try:
        yield conn
    finally:
        conn.close()
