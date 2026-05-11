from __future__ import annotations

from datetime import UTC, date, datetime

from src.pipelines.stock_report.models import RawTelegramMessage
from src.pipelines.stock_report.normalize import normalize_messages


def _raw_message(
    *,
    message_id: int,
    posted_at: datetime,
    channel_key: str = "hana_us_stock",
    raw_text: str = "NVDA +2.5%",
    media_info: str | None = None,
) -> RawTelegramMessage:
    return RawTelegramMessage(
        id=message_id,
        source_date=date(2026, 5, 8),
        date_kst=date(2026, 5, 8),
        posted_at=posted_at,
        channel_key=channel_key,
        channel_name=channel_key,
        channel_message_id=str(message_id),
        author=None,
        raw_text=raw_text,
        media_info=media_info,
        forward_from_channel_key=None,
        forward_from_channel_name=None,
    )


def test_normalize_extracts_urls_and_cleans_markdown():
    row = _raw_message(
        message_id=1,
        posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        raw_text="**뉴스** [링크](https://example.com) 참고 https://x.com/a",
    )
    result = normalize_messages([row], short_comment_channels={"hana_us_stock"})
    assert len(result) == 1
    assert result[0].clean_text == "뉴스 링크 참고"
    assert result[0].urls == ["https://example.com", "https://x.com/a"]
    assert result[0].processing_mode == "full"


def test_normalize_marks_grouped_only_for_short_messages_in_window():
    rows = [
        _raw_message(
            message_id=1,
            posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            raw_text="반도체 강세",
        ),
        _raw_message(
            message_id=2,
            posted_at=datetime(2026, 5, 8, 9, 20, tzinfo=UTC),
            raw_text="HBM 수급 타이트",
        ),
    ]

    result = normalize_messages(
        rows,
        short_comment_channels={"hana_us_stock"},
        short_comment_max_chars=100,
        group_window_minutes=30,
    )

    assert all(row.processing_mode == "grouped_only" for row in result)
    assert result[0].grouped_message_ids == [1, 2]
    assert result[1].grouped_message_ids == [1, 2]


def test_normalize_marks_skip_for_empty_text_without_media():
    row = _raw_message(
        message_id=1,
        posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        raw_text="   ",
        media_info=None,
    )

    result = normalize_messages([row], short_comment_channels={"hana_us_stock"})
    assert result[0].processing_mode == "skip"
