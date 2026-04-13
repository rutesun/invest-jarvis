# tests/providers/test_telegram_media.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock


from src.providers.telegram.media import TelegramMediaDownloader


@pytest.fixture
def downloader(tmp_path):
    client = AsyncMock()
    return TelegramMediaDownloader(client=client, base_dir=tmp_path)


def _make_photo_message(msg_id: int):
    msg = MagicMock()
    msg.id = msg_id
    msg.media = MagicMock()
    msg.media.photo = MagicMock()
    msg.media.document = None
    type(msg.media).__name__ = "MessageMediaPhoto"
    return msg


def _make_pdf_message(msg_id: int, filename: str = "report.pdf"):
    msg = MagicMock()
    msg.id = msg_id
    msg.media = MagicMock()
    msg.media.photo = None
    doc = MagicMock()
    doc.mime_type = "application/pdf"
    attr = MagicMock()
    attr.file_name = filename
    doc.attributes = [attr]
    msg.media.document = doc
    type(msg.media).__name__ = "MessageMediaDocument"
    return msg


def _make_video_message(msg_id: int):
    msg = MagicMock()
    msg.id = msg_id
    msg.media = MagicMock()
    msg.media.photo = None
    doc = MagicMock()
    doc.mime_type = "video/mp4"
    doc.attributes = []
    msg.media.document = doc
    type(msg.media).__name__ = "MessageMediaDocument"
    return msg


@pytest.mark.asyncio
async def test_download_photo(downloader, tmp_path):
    msg = _make_photo_message(42)
    # download_media가 파일을 생성하는 것을 시뮬레이션
    expected_path = tmp_path / "images" / "2026-04-13" / "test_chan_42.jpg"

    async def fake_download(message, file):
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        Path(file).write_bytes(b"fake_jpg")
        return str(file)

    downloader._client.download_media = fake_download

    result = await downloader.download(msg, "test_chan", "2026-04-13")

    assert result["type"] == "photo"
    assert result["local_path"] == str(expected_path)
    assert expected_path.exists()


@pytest.mark.asyncio
async def test_download_pdf(downloader, tmp_path):
    msg = _make_pdf_message(99, "analysis.pdf")
    expected_path = tmp_path / "files" / "2026-04-13" / "test_chan_99_analysis.pdf"

    async def fake_download(message, file):
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        Path(file).write_bytes(b"fake_pdf")
        return str(file)

    downloader._client.download_media = fake_download

    result = await downloader.download(msg, "test_chan", "2026-04-13")

    assert result["type"] == "document"
    assert result["mime_type"] == "application/pdf"
    assert result["local_path"] == str(expected_path)


@pytest.mark.asyncio
async def test_skip_video_no_download(downloader):
    msg = _make_video_message(10)

    result = await downloader.download(msg, "ch", "2026-04-13")

    assert result["type"] == "MessageMediaDocument"
    assert result["mime_type"] == "video/mp4"
    assert "local_path" not in result
    downloader._client.download_media.assert_not_called()


@pytest.mark.asyncio
async def test_download_failure_returns_type_only(downloader):
    msg = _make_photo_message(50)
    downloader._client.download_media = AsyncMock(side_effect=Exception("network error"))

    result = await downloader.download(msg, "ch", "2026-04-13")

    assert result["type"] == "photo"
    assert "local_path" not in result


@pytest.mark.asyncio
async def test_download_url_pdf(downloader, tmp_path):
    content = "좋은 리포트입니다 https://example.com/doc/report.pdf 참고하세요"

    async def fake_fetch(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"url_pdf_content")
        return True

    downloader._fetch_url_pdf = fake_fetch

    result = await downloader.download_url_pdfs(content, "ch", "2026-04-13", 77)

    assert len(result) == 1
    assert "report.pdf" in result[0]
    assert (tmp_path / "files" / "2026-04-13").exists()


@pytest.mark.asyncio
async def test_download_url_pdf_no_urls(downloader):
    result = await downloader.download_url_pdfs("URL 없는 메시지", "ch", "2026-04-13", 1)
    assert result == []


@pytest.mark.asyncio
async def test_download_url_pdf_non_pdf_url_skipped(downloader):
    content = "https://example.com/page.html 참조"

    async def fake_fetch(url, path):
        return False  # PDF가 아님

    downloader._fetch_url_pdf = fake_fetch

    result = await downloader.download_url_pdfs(content, "ch", "2026-04-13", 1)
    assert result == []
