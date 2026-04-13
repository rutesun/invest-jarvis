# src/providers/telegram/collector.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import ChannelConfig

logger = logging.getLogger(__name__)


class TelegramCollector:
    """Telethon 클라이언트를 사용하여 채널 메시지를 수집한다.

    두 가지 모드:
    - fetch_channel: 특정 날짜의 메시지 일괄 수집
    - fetch_since: 특정 message_id 이후 메시지를 날짜별로 그룹핑하여 수집 (catch-up용)

    미디어 다운로더가 설정되면 사진/PDF를 자동 다운로드한다.
    """

    def __init__(self, client: Any, media_downloader: Any = None) -> None:
        self._client = client
        self._media_downloader = media_downloader

    async def fetch_channel(
        self,
        channel_config: ChannelConfig,
        date_str: str,
    ) -> list[dict]:
        """특정 날짜의 채널 메시지를 수집한다.

        Args:
            channel_config: 채널 설정 (ID + 필터)
            date_str: YYYY-MM-DD (UTC 기준)

        Returns:
            CSV 저장용 dict 리스트
        """
        entity = await self._client.get_entity(channel_config.id)
        channel_name = getattr(entity, "title", str(channel_config.id))

        target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        offset_date = target_date + timedelta(days=1)

        messages: list[dict] = []
        async for msg in self._client.iter_messages(
            entity,
            offset_date=offset_date,
            reverse=True,
        ):
            if msg.date < target_date:
                continue
            if msg.date >= offset_date:
                break

            if msg.text is None and msg.media is None:
                continue

            if msg.text and not channel_config.should_include(msg.text):
                continue

            messages.append(await self._to_dict(msg, channel_name, date_str))

        logger.info(
            "%s에서 %s일자 메시지 %d건 수집",
            channel_name, date_str, len(messages),
        )
        return messages

    async def fetch_since(
        self,
        channel_config: ChannelConfig,
        min_id: int,
    ) -> dict[str, list[dict]]:
        """특정 message_id 이후의 메시지를 날짜별로 그룹핑하여 수집한다 (catch-up용).

        Args:
            channel_config: 채널 설정
            min_id: 이 ID 이후의 메시지만 수집

        Returns:
            날짜별 메시지 dict: {"2026-04-12": [...], "2026-04-13": [...]}
        """
        entity = await self._client.get_entity(channel_config.id)
        channel_name = getattr(entity, "title", str(channel_config.id))

        by_date: dict[str, list[dict]] = {}
        async for msg in self._client.iter_messages(entity, min_id=min_id, reverse=True):
            if msg.text is None and msg.media is None:
                continue
            if msg.text and not channel_config.should_include(msg.text):
                continue

            date_str = msg.date.strftime("%Y-%m-%d")
            msg_dict = await self._to_dict(msg, channel_name, date_str)
            by_date.setdefault(date_str, []).append(msg_dict)

        logger.info(
            "%s에서 min_id=%d 이후 메시지 %d일치 수집",
            channel_name, min_id, len(by_date),
        )
        return by_date

    async def _to_dict(self, msg: Any, channel_name: str, date_str: str) -> dict:
        """Telethon Message를 CSV 저장용 dict로 변환한다."""
        forward_from = ""
        if msg.forward:
            forward_from = str(getattr(msg.forward, "chat_id", ""))

        # Author 정보 추출: 채널 제목 또는 사용자 이름
        author = ""
        if msg.sender:
            # 채널인 경우: title 사용
            if hasattr(msg.sender, 'title') and msg.sender.title:
                author = msg.sender.title
            # 사용자인 경우: username 또는 이름
            elif hasattr(msg.sender, 'username') and msg.sender.username:
                author = f"@{msg.sender.username}"
            elif hasattr(msg.sender, 'first_name'):
                parts = [msg.sender.first_name or "", msg.sender.last_name or ""]
                author = " ".join(p for p in parts if p).strip()

        # Fallback: sender_id
        if not author:
            author = str(msg.sender_id or "")

        media_info = json.dumps(None)
        if msg.media and self._media_downloader:
            media_info = json.dumps(
                await self._media_downloader.download(msg, channel_name, date_str)
            )
        elif msg.media:
            media_info = json.dumps({"type": type(msg.media).__name__})

        return {
            "message_id": msg.id,
            "timestamp": msg.date.isoformat(),
            "channel_name": channel_name,
            "author": author,
            "content": msg.text or "",
            "media_info": media_info,
            "forward_from": forward_from,
        }
