"""jarvis report upload 경로의 파일명 파싱·중복 방지 테스트."""

from unittest.mock import MagicMock

import pytest

from src.integrations.notion import _archive_existing_report_pages, extract_report_date


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


def test_archive_existing_report_pages_archives_all_matches():
    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.data_sources.query.return_value = {"results": [{"id": "p1"}, {"id": "p2"}]}

    archived = _archive_existing_report_pages(notion, "db1", "Daily", "2026-07-20")

    assert archived == 2
    notion.pages.update.assert_any_call(page_id="p1", archived=True)
    notion.pages.update.assert_any_call(page_id="p2", archived=True)


def test_archive_existing_report_pages_no_data_source():
    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": []}

    assert _archive_existing_report_pages(notion, "db1", "Daily", "2026-07-20") == 0
    notion.pages.update.assert_not_called()
