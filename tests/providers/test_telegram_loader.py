# tests/providers/test_telegram_loader.py
import csv
import pytest
from pathlib import Path
from src.providers.telegram_loader import TelegramLoader


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path


def _write_csv(data_dir: Path, date_str: str, channel: str, rows: list[dict]):
    month = date_str[:7]
    csv_dir = data_dir / month
    csv_dir.mkdir(parents=True, exist_ok=True)
    path = csv_dir / f"{date_str}-{channel}.csv"
    fieldnames = ["message_id", "timestamp", "channel_name", "author", "content", "media_info", "forward_from"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_load_returns_messages_for_date(data_dir):
    _write_csv(data_dir, "2026-04-13", "chan1", [
        {"message_id": "1", "timestamp": "2026-04-13T09:00:00", "channel_name": "chan1",
         "author": "user1", "content": "테스트 메시지", "media_info": "", "forward_from": ""},
    ])
    loader = TelegramLoader(data_dir)
    messages = loader.load("2026-04-13")
    assert len(messages) == 1
    assert messages[0]["id"] == 1
    assert messages[0]["channel"] == "chan1"
    assert messages[0]["text"] == "테스트 메시지"
    assert messages[0]["timestamp"] == "2026-04-13T09:00:00"


def test_load_merges_multiple_channels(data_dir):
    _write_csv(data_dir, "2026-04-13", "chan1", [
        {"message_id": "1", "timestamp": "2026-04-13T09:00:00", "channel_name": "chan1",
         "author": "a", "content": "msg1", "media_info": "", "forward_from": ""},
    ])
    _write_csv(data_dir, "2026-04-13", "chan2", [
        {"message_id": "2", "timestamp": "2026-04-13T09:30:00", "channel_name": "chan2",
         "author": "b", "content": "msg2", "media_info": "", "forward_from": ""},
    ])
    loader = TelegramLoader(data_dir)
    messages = loader.load("2026-04-13")
    assert len(messages) == 2
    channels = {m["channel"] for m in messages}
    assert channels == {"chan1", "chan2"}


def test_load_no_files_returns_empty(data_dir):
    loader = TelegramLoader(data_dir)
    messages = loader.load("2026-04-13")
    assert messages == []


def test_load_default_date_is_yesterday(data_dir):
    """date 미지정 시 전날 데이터를 로드한다."""
    from datetime import datetime, timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    _write_csv(data_dir, yesterday, "ch", [
        {"message_id": "1", "timestamp": f"{yesterday}T10:00:00", "channel_name": "ch",
         "author": "a", "content": "yesterday", "media_info": "", "forward_from": ""},
    ])
    loader = TelegramLoader(data_dir)
    messages = loader.load()
    assert len(messages) == 1
    assert messages[0]["text"] == "yesterday"


def test_load_sorted_by_timestamp(data_dir):
    _write_csv(data_dir, "2026-04-13", "ch", [
        {"message_id": "2", "timestamp": "2026-04-13T10:00:00", "channel_name": "ch",
         "author": "a", "content": "later", "media_info": "", "forward_from": ""},
        {"message_id": "1", "timestamp": "2026-04-13T09:00:00", "channel_name": "ch",
         "author": "a", "content": "earlier", "media_info": "", "forward_from": ""},
    ])
    loader = TelegramLoader(data_dir)
    messages = loader.load("2026-04-13")
    assert messages[0]["text"] == "earlier"
    assert messages[1]["text"] == "later"
