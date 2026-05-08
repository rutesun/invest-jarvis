from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SEOUL_TZ = ZoneInfo("Asia/Seoul")


@dataclass(slots=True)
class TelegramIngestStats:
    csv_files: int
    parsed_rows: int
    upserted_rows: int


def discover_csv_files(date: str, data_dir: str = "data") -> list[Path]:
    year_month = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m")
    csv_dir = Path(data_dir) / year_month
    if not csv_dir.exists():
        return []
    return sorted(csv_dir.glob(f"{date}-*.csv"))


def parse_channel_key(date: str, csv_path: Path) -> str:
    prefix = f"{date}-"
    stem = csv_path.stem
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    return stem


def parse_timestamp(raw_timestamp: str) -> datetime:
    value = raw_timestamp.strip()
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed


def _normalize_nullable_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized.lower() == "null":
        return None
    return normalized


def _extract_forward_metadata(forward_from_raw: str | None) -> tuple[str | None, str | None]:
    if not forward_from_raw:
        return None, None

    if forward_from_raw.startswith("@"):
        return forward_from_raw[1:], forward_from_raw

    match = re.search(r"t\.me/([A-Za-z0-9_]+)", forward_from_raw)
    if match:
        channel_key = match.group(1)
        return channel_key, forward_from_raw

    if forward_from_raw.startswith("{") and forward_from_raw.endswith("}"):
        try:
            payload = json.loads(forward_from_raw)
        except json.JSONDecodeError:
            return None, forward_from_raw
        channel_key = (
            payload.get("channel_key")
            or payload.get("channel_id")
            or payload.get("username")
            or payload.get("author")
        )
        channel_name = payload.get("channel_name") or payload.get("title") or payload.get("name")
        if channel_key is not None:
            channel_key = str(channel_key)
        if channel_name is not None:
            channel_name = str(channel_name)
        return channel_key, channel_name or forward_from_raw

    return None, forward_from_raw


def _build_row_payload(
    *,
    source_date: str,
    channel_key: str,
    row: dict[str, str],
) -> tuple[Any, ...]:
    posted_at = parse_timestamp(row["timestamp"])
    date_kst = posted_at.astimezone(SEOUL_TZ).date()

    forward_from_raw = _normalize_nullable_text(row.get("forward_from"))
    forward_key, forward_name = _extract_forward_metadata(forward_from_raw)

    raw_text = row.get("content", "")
    media_info = _normalize_nullable_text(row.get("media_info"))

    return (
        source_date,
        date_kst,
        posted_at,
        channel_key,
        row.get("channel_name") or channel_key,
        str(row["message_id"]),
        _normalize_nullable_text(row.get("author")),
        raw_text,
        media_info,
        forward_from_raw,
        forward_key,
        forward_name,
        json.dumps(row, ensure_ascii=False),
    )


def upsert_telegram_messages(conn: Any, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0

    query = """
    INSERT INTO telegram_messages (
        source_date,
        date_kst,
        posted_at,
        channel_key,
        channel_name,
        channel_message_id,
        author,
        raw_text,
        media_info,
        forward_from_raw,
        forward_from_channel_key,
        forward_from_channel_name,
        raw_row
    )
    VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
    )
    ON CONFLICT (channel_key, channel_message_id) DO UPDATE
    SET
        source_date = EXCLUDED.source_date,
        date_kst = EXCLUDED.date_kst,
        posted_at = EXCLUDED.posted_at,
        channel_name = EXCLUDED.channel_name,
        author = EXCLUDED.author,
        raw_text = EXCLUDED.raw_text,
        media_info = EXCLUDED.media_info,
        forward_from_raw = EXCLUDED.forward_from_raw,
        forward_from_channel_key = EXCLUDED.forward_from_channel_key,
        forward_from_channel_name = EXCLUDED.forward_from_channel_name,
        raw_row = EXCLUDED.raw_row,
        updated_at = NOW();
    """

    with conn.cursor() as cur:
        cur.executemany(query, rows)
    conn.commit()
    return len(rows)


def ingest_telegram_raw_csvs(conn: Any, date: str, data_dir: str = "data") -> TelegramIngestStats:
    csv_files = discover_csv_files(date=date, data_dir=data_dir)
    payload_rows: list[tuple[Any, ...]] = []

    for csv_path in csv_files:
        channel_key = parse_channel_key(date=date, csv_path=csv_path)
        with csv_path.open(encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if not row.get("message_id") or not row.get("timestamp"):
                    continue
                payload_rows.append(
                    _build_row_payload(source_date=date, channel_key=channel_key, row=row)
                )

    upserted_rows = upsert_telegram_messages(conn, payload_rows)
    return TelegramIngestStats(
        csv_files=len(csv_files),
        parsed_rows=len(payload_rows),
        upserted_rows=upserted_rows,
    )
