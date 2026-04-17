# tests/pipelines/test_telegram_pipeline.py
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pipelines.telegram_pipeline import TelegramPipeline


@pytest.fixture
def mock_config():
    config = MagicMock()
    ch1 = MagicMock()
    ch1.id = "chan1"
    config.channels = [ch1]
    config.output_dir = Path("data")
    return config


@pytest.fixture
def mock_wrapper():
    wrapper = AsyncMock()
    return wrapper


@pytest.fixture
def mock_collector():
    collector = AsyncMock()
    return collector


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    return storage


@pytest.fixture
def mock_state():
    state = MagicMock()
    state.get_last_message_id.return_value = 0
    return state


@pytest.mark.asyncio
async def test_fetch_collects_and_saves(
    mock_config, mock_wrapper, mock_collector, mock_storage, mock_state
):
    """fetch는 collector를 호출하고 storage에 저장한다."""
    mock_collector.fetch_channel.return_value = [{"message_id": 1, "content": "test"}]

    pipeline = TelegramPipeline(
        config=mock_config,
        wrapper=mock_wrapper,
        collector=mock_collector,
        storage=mock_storage,
        state=mock_state,
    )

    total = await pipeline.fetch("2026-04-13")

    assert total == 1
    mock_collector.fetch_channel.assert_called_once()
    mock_storage.save.assert_called_once_with(
        "chan1", "2026-04-13", [{"message_id": 1, "content": "test"}]
    )
    mock_state.update.assert_called_once_with("chan1", 1)


@pytest.mark.asyncio
async def test_catch_up_uses_fetch_since(
    mock_config, mock_wrapper, mock_collector, mock_storage, mock_state
):
    """catch_up은 fetch_since를 호출하고 날짜별로 저장한다."""
    mock_state.get_last_message_id.return_value = 100
    mock_collector.fetch_since.return_value = {
        "2026-04-12": [{"message_id": 101, "content": "old"}],
        "2026-04-13": [{"message_id": 102, "content": "new"}],
    }

    pipeline = TelegramPipeline(
        config=mock_config,
        wrapper=mock_wrapper,
        collector=mock_collector,
        storage=mock_storage,
        state=mock_state,
    )

    total = await pipeline.catch_up()

    assert total == 2
    mock_collector.fetch_since.assert_called_once_with(mock_config.channels[0], 100)
    assert mock_storage.save.call_count == 2
    assert mock_state.update.call_count == 2


@pytest.mark.asyncio
async def test_create_raises_on_empty_channels(tmp_path):
    """channels가 없으면 ValueError 발생."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("telegram:\n  channels: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="channels가 설정되지 않았습니다"):
        await TelegramPipeline.create(config_file)


@pytest.mark.asyncio
async def test_close_stops_wrapper(
    mock_config, mock_wrapper, mock_collector, mock_storage, mock_state
):
    """close는 wrapper.stop을 호출한다."""
    pipeline = TelegramPipeline(
        config=mock_config,
        wrapper=mock_wrapper,
        collector=mock_collector,
        storage=mock_storage,
        state=mock_state,
    )

    await pipeline.close()

    mock_wrapper.stop.assert_called_once()
