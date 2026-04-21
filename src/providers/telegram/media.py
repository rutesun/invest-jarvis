# src/providers/telegram/media.py
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx


logger = logging.getLogger(__name__)

# 메시지 본문에서 URL 추출용 정규식
# 모든 HTTP(S) URL을 찾고, _fetch_url_pdf()에서 실제 PDF 여부 확인
# 단축 URL(vo.la, bit.ly 등)도 지원
URL_PATTERN = re.compile(
    r"https?://[^\s\)\]]+",
    re.IGNORECASE,
)


class TelegramMediaDownloader:
    """텔레그램 메시지의 사진/PDF를 로컬에 다운로드한다.

    파일명 규칙 (channel_id 사용):
    - 사진: {base_dir}/images/YYYY-MM-DD/{channel_id}_{msg_id}.jpg
    - PDF:  {base_dir}/files/YYYY-MM-DD/{channel_id}_{msg_id}_{filename}.pdf
    - URL PDF: {base_dir}/files/YYYY-MM-DD/{channel_id}_url_{msg_id}_{filename}.pdf

    channel_id는 config.yaml의 영문 ID (예: "shinhanresearch")
    """

    def __init__(self, client: Any, base_dir: Path) -> None:
        self._client = client
        self._base_dir = base_dir

    async def download(self, msg: Any, channel_id: str, date_str: str) -> dict:
        """메시지의 미디어를 다운로드하고 media_info dict를 반환한다.

        사진/PDF만 다운로드하고, 그 외 미디어는 type만 기록한다.

        Args:
            msg: Telethon Message 객체
            channel_id: 채널 ID (영문, 예: "shinhanresearch")
            date_str: 날짜 문자열 (YYYY-MM-DD)
        """
        media = msg.media

        # 사진
        if getattr(media, "photo", None):
            return await self._download_photo(msg, channel_id, date_str)

        # 문서 (PDF만 다운로드)
        if getattr(media, "document", None):
            doc = media.document
            mime = getattr(doc, "mime_type", "")
            if mime == "application/pdf":
                return await self._download_pdf(msg, channel_id, date_str)
            return {"type": type(media).__name__, "mime_type": mime}

        return {"type": type(media).__name__}

    async def _download_photo(self, msg: Any, channel_id: str, date_str: str) -> dict:
        dir_path = self._base_dir / "images" / date_str
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{channel_id}_{msg.id}.jpg"
        try:
            await self._client.download_media(msg, str(file_path))
            return {"type": "photo", "local_path": str(file_path)}
        except Exception as e:
            logger.warning("사진 다운로드 실패 (msg=%d): %s", msg.id, e)
            return {"type": "photo"}

    async def _download_pdf(self, msg: Any, channel_id: str, date_str: str) -> dict:
        dir_path = self._base_dir / "files" / date_str
        dir_path.mkdir(parents=True, exist_ok=True)

        # 원본 파일명 추출
        filename = f"{msg.id}.pdf"
        doc = msg.media.document
        for attr in getattr(doc, "attributes", []):
            if hasattr(attr, "file_name") and attr.file_name:
                filename = f"{msg.id}_{attr.file_name}"
                break

        file_path = dir_path / f"{channel_id}_{filename}"
        try:
            await self._client.download_media(msg, str(file_path))
            return {
                "type": "document",
                "mime_type": "application/pdf",
                "local_path": str(file_path),
            }
        except Exception as e:
            logger.warning("PDF 다운로드 실패 (msg=%d): %s", msg.id, e)
            return {"type": "document", "mime_type": "application/pdf"}

    async def download_url_pdfs(
        self,
        content: str,
        channel_id: str,
        date_str: str,
        msg_id: int,
    ) -> list[str]:
        """메시지 본문에서 PDF URL을 찾아 다운로드한다.

        Args:
            content: 메시지 본문
            channel_id: 채널 ID (영문, 예: "shinhanresearch")
            date_str: 날짜 문자열 (YYYY-MM-DD)
            msg_id: 메시지 ID

        Returns:
            다운로드된 파일 경로 리스트
        """
        urls = URL_PATTERN.findall(content)
        if not urls:
            return []

        # 중복 제거 (마크다운 링크에서 URL이 두 번 나타날 수 있음)
        urls = list(dict.fromkeys(urls))

        dir_path = self._base_dir / "files" / date_str
        downloaded: list[str] = []

        for url in urls:
            # URL에서 파일명 추출
            url_filename = url.split("/")[-1].split("?")[0]
            if not url_filename.lower().endswith(".pdf"):
                url_filename = f"{msg_id}.pdf"
            file_path = dir_path / f"{channel_id}_url_{msg_id}_{url_filename}"

            if await self._fetch_url_pdf(url, file_path):
                downloaded.append(str(file_path))

        return downloaded

    async def _fetch_url_pdf(self, url: str, path: Path) -> bool:
        """URL에서 PDF를 다운로드한다. 성공 시 True."""
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                # HEAD로 Content-Type 확인 (실패 시 GET으로 fallback)
                content_type = ""
                final_url = url

                try:
                    head = await client.head(url)
                    content_type = head.headers.get("content-type", "").lower()
                    final_url = str(head.url).lower()
                except httpx.TooManyRedirects:
                    # HEAD 지원 안 하는 사이트 (예: DART)는 GET으로 확인
                    logger.debug("HEAD failed (redirects), trying GET: %s", url)
                    resp = await client.get(url)
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "").lower()
                    final_url = str(resp.url).lower()

                    # Content-Type 또는 URL 확장자로 PDF 확인
                    is_pdf = "application/pdf" in content_type or final_url.endswith(".pdf")

                    if not is_pdf:
                        logger.debug(
                            "Not a PDF: %s (type=%s, url=%s)", url, content_type, final_url
                        )
                        return False

                    # 이미 GET으로 받았으므로 바로 저장
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(resp.content)
                    logger.info("URL PDF 다운로드 완료: %s", path)
                    return True

                # Content-Type 또는 URL 확장자로 PDF 확인
                is_pdf = "application/pdf" in content_type or final_url.endswith(".pdf")

                if not is_pdf:
                    logger.debug("Not a PDF: %s (type=%s, url=%s)", url, content_type, final_url)
                    return False

                # 스트림 다운로드
                resp = await client.get(url)
                resp.raise_for_status()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(resp.content)
                logger.info("URL PDF 다운로드 완료: %s", path)
                return True
        except Exception as e:
            logger.warning("URL PDF 다운로드 실패 (%s): %s", url, e)
            return False
