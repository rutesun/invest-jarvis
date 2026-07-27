"""jarvis report upload 경로의 파일명 파싱·중복 방지 테스트."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.integrations.notion import (
    _find_existing_report_page_ids,
    extract_report_date,
    upload_report_from_file,
)


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("daily_2026-07-20", "2026-07-20"),
        ("daily_v2_2026-06-19", "2026-06-19"),
        ("screen-2026-07-24", "2026-07-24"),
        ("daily_2026-07-15.AB-gpt56", None),  # 실험용 변형은 업로드 대상 아님
        ("daily_v2_2026-06-19-draft", None),
        ("weekly_2026-07-20", None),
    ],
)
def test_extract_report_date(stem, expected):
    assert extract_report_date(stem) == expected


def test_find_existing_report_page_ids_returns_all_matches():
    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.data_sources.query.return_value = {"results": [{"id": "p1"}, {"id": "p2"}]}

    assert _find_existing_report_page_ids(notion, "db1", "Daily", "2026-07-20") == ["p1", "p2"]


def test_find_existing_report_page_ids_no_data_source():
    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": []}

    assert _find_existing_report_page_ids(notion, "db1", "Daily", "2026-07-20") == []


def _upload_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db1")


def test_upload_archives_existing_pages_only_after_successful_create(tmp_path, monkeypatch):
    """기존 페이지 아카이브는 새 페이지 업로드 성공 후에만 실행된다."""
    _upload_env(monkeypatch)
    md = tmp_path / "daily_2026-07-20.md"
    md.write_text("# Report\n\n본문", encoding="utf-8")

    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.data_sources.query.return_value = {"results": [{"id": "old1"}]}
    notion.pages.create.return_value = {"id": "new1", "url": "https://notion.so/new1"}

    with patch("src.integrations.notion.Client", return_value=notion):
        url = upload_report_from_file(Path(md), "2026-07-20")

    assert url == "https://notion.so/new1"
    notion.pages.update.assert_called_once_with(page_id="old1", archived=True)


def test_upload_preserves_existing_pages_when_create_fails(tmp_path, monkeypatch):
    """페이지 생성 실패 시 기존 페이지를 아카이브하지 않는다 (리포트 유실 방지)."""
    _upload_env(monkeypatch)
    md = tmp_path / "daily_2026-07-20.md"
    md.write_text("# Report\n\n본문", encoding="utf-8")

    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.data_sources.query.return_value = {"results": [{"id": "old1"}]}
    notion.pages.create.side_effect = RuntimeError("429 rate limited")

    with (
        patch("src.integrations.notion.Client", return_value=notion),
        pytest.raises(Exception, match="Notion page creation failed"),
    ):
        upload_report_from_file(Path(md), "2026-07-20")

    notion.pages.update.assert_not_called()
