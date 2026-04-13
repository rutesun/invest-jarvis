# tests/tools/test_telegram_loader.py
import pytest
from pathlib import Path
from src.tools.telegram_loader import TelegramMessageLoader


@pytest.fixture
def sample_csv(tmp_path):
    """테스트용 CSV 파일 생성"""
    data_dir = tmp_path / "data" / "2026-04"
    data_dir.mkdir(parents=True)

    csv_file = data_dir / "2026-04-13-test_channel.csv"
    csv_content = """message_id,timestamp,channel_name,author,content,media_info,forward_from
101,2026-04-13T09:00:00+00:00,test_channel,author1,엔비디아 실적 호조,,
102,2026-04-13T09:05:00+00:00,test_channel,author2,테슬라 신모델 출시,,
103,2026-04-13T09:10:00+00:00,test_channel,author3,,,
"""
    csv_file.write_text(csv_content, encoding="utf-8")
    return tmp_path / "data"


def test_load_messages_from_date(sample_csv):
    loader = TelegramMessageLoader(data_dir=sample_csv)
    messages = loader.load(date="2026-04-13")

    assert len(messages) == 2  # 빈 메시지 제외
    assert messages[0]["id"] == 101
    assert messages[0]["channel"] == "test_channel"
    assert "엔비디아" in messages[0]["text"]
    assert messages[1]["id"] == 102


def test_load_from_nonexistent_date(sample_csv):
    loader = TelegramMessageLoader(data_dir=sample_csv)
    messages = loader.load(date="2026-04-01")

    assert messages == []


def test_load_from_nonexistent_directory(tmp_path):
    loader = TelegramMessageLoader(data_dir=tmp_path / "nonexistent")
    messages = loader.load(date="2026-04-13")

    assert messages == []


def test_load_multiple_channels(tmp_path):
    data_dir = tmp_path / "data" / "2026-04"
    data_dir.mkdir(parents=True)

    # 채널 1
    csv1 = data_dir / "2026-04-13-channel1.csv"
    csv1.write_text(
        "message_id,timestamp,channel_name,author,content,media_info,forward_from\n"
        "101,2026-04-13T09:00:00+00:00,channel1,author1,메시지1,,\n",
        encoding="utf-8",
    )

    # 채널 2
    csv2 = data_dir / "2026-04-13-channel2.csv"
    csv2.write_text(
        "message_id,timestamp,channel_name,author,content,media_info,forward_from\n"
        "201,2026-04-13T09:00:00+00:00,channel2,author2,메시지2,,\n",
        encoding="utf-8",
    )

    loader = TelegramMessageLoader(data_dir=tmp_path / "data")
    messages = loader.load(date="2026-04-13")

    assert len(messages) == 2
    channels = {msg["channel"] for msg in messages}
    assert channels == {"channel1", "channel2"}


def test_skip_empty_messages(sample_csv):
    """빈 content는 제외되어야 함"""
    loader = TelegramMessageLoader(data_dir=sample_csv)
    messages = loader.load(date="2026-04-13")

    # message_id 103은 빈 content이므로 제외
    assert all(msg["text"] for msg in messages)
    assert len(messages) == 2
