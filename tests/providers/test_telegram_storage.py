# tests/providers/test_telegram_storage.py
import csv
import json
import pytest
from pathlib import Path
from src.providers.telegram_storage import TelegramStorage


@pytest.fixture
def storage(tmp_path):
    return TelegramStorage(output_dir=tmp_path)


def _make_message(msg_id: int, channel: str = "test_chan", text: str = "hello") -> dict:
    return {
        "message_id": msg_id,
        "timestamp": "2026-04-13T09:00:00+00:00",
        "channel_name": channel,
        "author": "user1",
        "content": text,
        "media_info": json.dumps(None),
        "forward_from": "",
    }


def test_save_creates_csv(storage, tmp_path):
    messages = [_make_message(1), _make_message(2)]
    storage.save("test_chan", "2026-04-13", messages)

    csv_path = tmp_path / "2026-04" / "2026-04-13-test_chan.csv"
    assert csv_path.exists()

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["message_id"] == "1"
    assert rows[1]["message_id"] == "2"


def test_save_appends_without_duplicates(storage, tmp_path):
    storage.save("ch", "2026-04-13", [_make_message(1), _make_message(2)])
    storage.save("ch", "2026-04-13", [_make_message(2), _make_message(3)])

    csv_path = tmp_path / "2026-04" / "2026-04-13-ch.csv"
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    ids = [int(r["message_id"]) for r in rows]
    assert sorted(ids) == [1, 2, 3]


def test_csv_columns(storage, tmp_path):
    storage.save("ch", "2026-04-13", [_make_message(1)])
    csv_path = tmp_path / "2026-04" / "2026-04-13-ch.csv"
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    expected_cols = {"message_id", "timestamp", "channel_name", "author", "content", "media_info", "forward_from"}
    assert set(row.keys()) == expected_cols


def test_get_existing_ids_empty_file(storage, tmp_path):
    ids = storage.get_existing_ids("ch", "2026-04-13")
    assert ids == set()


def test_get_existing_ids_from_csv(storage, tmp_path):
    storage.save("ch", "2026-04-13", [_make_message(10), _make_message(20)])
    ids = storage.get_existing_ids("ch", "2026-04-13")
    assert ids == {10, 20}


def test_csv_path_format(storage, tmp_path):
    path = storage.csv_path("my_channel", "2026-01-05")
    assert path == tmp_path / "2026-01" / "2026-01-05-my_channel.csv"


def test_save_empty_messages(storage, tmp_path):
    storage.save("ch", "2026-04-13", [])
    csv_path = tmp_path / "2026-04" / "2026-04-13-ch.csv"
    assert not csv_path.exists()
