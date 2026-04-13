# src/providers/telegram_client.py
from __future__ import annotations

import os
import logging

from telethon import TelegramClient

logger = logging.getLogger(__name__)


class TelegramClientWrapper:
    """Telethon 클라이언트를 래핑하여 세션 관리를 담당한다.

    환경 변수:
        TELEGRAM_API_ID: Telegram API ID
        TELEGRAM_API_HASH: Telegram API Hash
        TELETHON_SESSION_NAME: 세션 파일명 (기본값: 'anon')
    """

    def __init__(self) -> None:
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            raise ValueError(
                "TELEGRAM_API_ID와 TELEGRAM_API_HASH 환경 변수가 필요합니다. "
                ".env 파일을 확인하세요."
            )
        session_name = os.getenv("TELETHON_SESSION_NAME", "anon")
        self._client = TelegramClient(session_name, int(api_id), api_hash)

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def start(self) -> None:
        """클라이언트를 시작한다. 첫 실행 시 인증이 필요할 수 있다."""
        await self._client.start()
        logger.info("Telegram 클라이언트 연결됨")

    async def stop(self) -> None:
        """클라이언트 연결을 종료한다."""
        await self._client.disconnect()
        logger.info("Telegram 클라이언트 연결 해제됨")
