# tests/providers/test_telegram_client.py
import pytest
from unittest.mock import patch
from src.providers.telegram_client import TelegramClientWrapper


def test_missing_api_id_raises_error():
    """TELEGRAM_API_ID 없을 때 명확한 에러 메시지"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="TELEGRAM_API_ID"):
            TelegramClientWrapper()


def test_missing_api_hash_raises_error():
    """TELEGRAM_API_HASH 없을 때 명확한 에러 메시지"""
    with patch.dict("os.environ", {"TELEGRAM_API_ID": "12345"}, clear=True):
        with pytest.raises(ValueError, match="TELEGRAM_API_HASH"):
            TelegramClientWrapper()


def test_valid_env_creates_client():
    """환경변수가 올바르면 클라이언트 생성 성공"""
    with patch.dict("os.environ", {
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "abc123",
        "TELETHON_SESSION_NAME": "test",
    }):
        with patch("src.providers.telegram_client.TelegramClient") as mock_client:
            wrapper = TelegramClientWrapper()
            assert wrapper.client is not None
            mock_client.assert_called_once_with("test", 12345, "abc123")
