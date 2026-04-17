# src/providers/telegram/collector.py
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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
            channel_config: 채널 설정 (ID + 필터 + timezone)
            date_str: YYYY-MM-DD (채널 timezone 기준)

        Returns:
            CSV 저장용 dict 리스트
        """
        entity = await self._client.get_entity(channel_config.id)
        channel_name = getattr(entity, "title", str(channel_config.id))

        # 채널 timezone으로 target_date 파싱
        tz = ZoneInfo(channel_config.timezone)
        target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
        offset_date = target_date + timedelta(days=1)

        # UTC로 변환하여 비교 (msg.date는 UTC)
        target_date_utc = target_date.astimezone(UTC)
        offset_date_utc = offset_date.astimezone(UTC)

        messages: list[dict] = []
        async for msg in self._client.iter_messages(entity, limit=5000):
            # offset_date 이후 메시지는 스킵 (최신 메시지부터 오므로)
            if msg.date >= offset_date_utc:
                continue
            # target_date 이전 메시지는 중단 (더 이상 볼 필요 없음)
            if msg.date < target_date_utc:
                break

            if msg.text is None and msg.media is None:
                continue

            if msg.text and not channel_config.should_include(msg.text):
                continue

            # 메시지의 날짜를 채널 timezone으로 변환하여 저장
            msg_local_date = msg.date.astimezone(tz).strftime("%Y-%m-%d")
            messages.append(await self._to_dict(msg, channel_name, msg_local_date, channel_config))

        logger.info(
            "%s에서 %s일자 메시지 %d건 수집 (timezone: %s)",
            channel_name,
            date_str,
            len(messages),
            channel_config.timezone,
        )
        return messages

    async def fetch_since(
        self,
        channel_config: ChannelConfig,
        min_id: int,
    ) -> dict[str, list[dict]]:
        """특정 message_id 이후의 메시지를 날짜별로 그룹핑하여 수집한다 (catch-up용).

        Args:
            channel_config: 채널 설정 (timezone 포함)
            min_id: 이 ID 이후의 메시지만 수집

        Returns:
            날짜별 메시지 dict: {"2026-04-12": [...], "2026-04-13": [...]} (채널 timezone 기준)
        """
        entity = await self._client.get_entity(channel_config.id)
        channel_name = getattr(entity, "title", str(channel_config.id))

        tz = ZoneInfo(channel_config.timezone)
        by_date: dict[str, list[dict]] = {}
        async for msg in self._client.iter_messages(entity, min_id=min_id, reverse=True):
            if msg.text is None and msg.media is None:
                continue
            if msg.text and not channel_config.should_include(msg.text):
                continue

            # 메시지 날짜를 채널 timezone으로 변환
            date_str = msg.date.astimezone(tz).strftime("%Y-%m-%d")
            msg_dict = await self._to_dict(msg, channel_name, date_str, channel_config)
            by_date.setdefault(date_str, []).append(msg_dict)

        logger.info(
            "%s에서 min_id=%d 이후 메시지 %d일치 수집 (timezone: %s)",
            channel_name,
            min_id,
            len(by_date),
            channel_config.timezone,
        )
        return by_date

    async def _to_dict(
        self,
        msg: Any,
        channel_name: str,
        date_str: str,
        channel_config: ChannelConfig | str,
    ) -> dict:
        """Telethon Message를 CSV 저장용 dict로 변환한다.

        Args:
            msg: Telethon Message 객체
            channel_name: 채널 제목 (예: "epic AI - 투자 어시스턴트")
            date_str: 날짜 문자열 (YYYY-MM-DD, 채널 timezone 기준)
            channel_config: 채널 설정 또는 채널 ID 문자열
        """
        forward_from = ""
        if msg.forward:
            forward_from = str(getattr(msg.forward, "chat_id", ""))

        # Author: 채널 ID 사용 (config.yaml과 매칭 가능)
        channel_id = (
            channel_config.id if isinstance(channel_config, ChannelConfig) else channel_config
        )
        author = channel_id

        media_info = json.dumps(None)
        if msg.media and self._media_downloader:
            media_info = json.dumps(
                await self._media_downloader.download(msg, channel_id, date_str)
            )
        elif msg.media:
            media_info = json.dumps({"type": type(msg.media).__name__})

        # 메시지 본문에서 PDF URL 다운로드
        url_pdfs = []
        if msg.text and self._media_downloader:
            url_pdfs = await self._media_downloader.download_url_pdfs(
                msg.text, channel_id, date_str, msg.id
            )

        # URL PDF 경로를 media_info에 추가
        if url_pdfs:
            if media_info == json.dumps(None):
                media_info = json.dumps({"type": "url_pdf", "local_paths": url_pdfs})
            else:
                info = json.loads(media_info)
                info["url_pdf_paths"] = url_pdfs
                media_info = json.dumps(info)

        return {
            "message_id": msg.id,
            "timestamp": msg.date.isoformat(),
            "channel_name": channel_name,
            "author": author,
            "content": msg.text or "",
            "media_info": media_info,
            "forward_from": forward_from,
        }
