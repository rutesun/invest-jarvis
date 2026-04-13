# tests/providers/test_telegram_collector.py
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from src.providers.telegram_collector import TelegramCollector
from src.providers.telegram_config import ChannelConfig


def _make_tg_message(msg_id: int, text: str, date: datetime, sender_id: int = 123):
    """Telethon Message 객체를 모사하는 mock."""
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.date = date
    msg.sender_id = sender_id
    msg.media = None
    msg.forward = None
    return msg


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_entity = AsyncMock()
    return client


@pytest.fixture
def channel_config():
    return ChannelConfig(id="test_channel")


@pytest.fixture
def channel_config_with_filter():
    return ChannelConfig(id="test_channel", include=["중요|Breaking"])


@pytest.mark.asyncio
async def test_fetch_messages_for_date(mock_client, channel_config):
    target_date = datetime(2026, 4, 13, tzinfo=timezone.utc)
    messages = [
        _make_tg_message(1, "첫 번째 메시지", datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc)),
        _make_tg_message(2, "두 번째 메시지", datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)),
    ]

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter(messages))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    assert len(result) == 2
    assert result[0]["message_id"] == 1
    assert result[0]["content"] == "첫 번째 메시지"
    assert result[0]["channel_name"] == "test_channel"


@pytest.mark.asyncio
async def test_fetch_applies_include_filter(mock_client, channel_config_with_filter):
    messages = [
        _make_tg_message(1, "중요한 소식입니다", datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc)),
        _make_tg_message(2, "일반 잡담", datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)),
        _make_tg_message(3, "Breaking: 속보", datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc)),
    ]

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter(messages))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config_with_filter, "2026-04-13")

    assert len(result) == 2
    texts = [r["content"] for r in result]
    assert "일반 잡담" not in texts


@pytest.mark.asyncio
async def test_fetch_skips_none_text_and_no_media(mock_client, channel_config):
    """text=None이고 media도 None이면 스킵."""
    messages = [
        _make_tg_message(1, None, datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc)),
        _make_tg_message(2, "유효한 메시지", datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)),
    ]

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter(messages))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    assert len(result) == 1
    assert result[0]["content"] == "유효한 메시지"


@pytest.mark.asyncio
async def test_fetch_keeps_media_only_message(mock_client, channel_config):
    """text=None이지만 media가 있으면 수집한다."""
    msg_with_media = _make_tg_message(1, None, datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc))
    msg_with_media.media = MagicMock()  # media 존재

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter([msg_with_media]))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    assert len(result) == 1
    assert result[0]["content"] == ""


@pytest.mark.asyncio
async def test_fetch_includes_forward_info(mock_client, channel_config):
    msg = _make_tg_message(1, "포워드 메시지", datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc))
    fwd = MagicMock()
    fwd.chat_id = 99999
    msg.forward = fwd

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter([msg]))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    assert result[0]["forward_from"] == "99999"


@pytest.mark.asyncio
async def test_fetch_since_returns_grouped_by_date(mock_client, channel_config):
    """fetch_since는 날짜별로 그룹핑된 dict를 반환한다."""
    messages = [
        _make_tg_message(10, "msg1", datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)),
        _make_tg_message(11, "msg2", datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc)),
        _make_tg_message(12, "msg3", datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc)),
    ]

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter(messages))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_since(channel_config, min_id=5)

    assert isinstance(result, dict)
    assert "2026-04-12" in result
    assert "2026-04-13" in result
    assert len(result["2026-04-12"]) == 1
    assert len(result["2026-04-13"]) == 2


@pytest.mark.asyncio
async def test_message_dict_format(mock_client, channel_config):
    msg = _make_tg_message(42, "테스트", datetime(2026, 4, 13, 9, 30, tzinfo=timezone.utc))

    entity = MagicMock()
    entity.title = "test_channel"
    mock_client.get_entity.return_value = entity
    mock_client.iter_messages = MagicMock(return_value=_async_iter([msg]))

    collector = TelegramCollector(client=mock_client)
    result = await collector.fetch_channel(channel_config, "2026-04-13")

    row = result[0]
    assert set(row.keys()) == {
        "message_id", "timestamp", "channel_name", "author", "content", "media_info", "forward_from",
    }
    assert row["message_id"] == 42
    assert row["author"] == "123"
    assert row["timestamp"] == "2026-04-13T09:30:00+00:00"


async def _async_iter(items):
    """동기 리스트를 async iterator로 변환하는 헬퍼."""
    for item in items:
        yield item
