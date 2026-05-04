"""Tests for source fragment splitting."""

from src.pipelines.daily_report.models import TelegramMessage
from src.pipelines.daily_report.source_parsing import (
    split_message_into_fragments,
    split_telegram_message,
)


def test_split_message_into_fragments_with_bundle_markers():
    text = "▶️ 1번 기사\n내용 A\nhttps://example.com/a\n▶️ 2번 기사\n내용 B\nhttps://example.com/b"

    fragments = split_message_into_fragments(
        raw_message_id="shinhanresearch-100",
        channel_id="shinhanresearch",
        text=text,
    )

    assert len(fragments) == 2
    assert fragments[0].fragment_index == 0
    assert fragments[1].fragment_index == 1
    assert fragments[0].title == "1번 기사"
    assert fragments[1].title == "2번 기사"
    assert fragments[0].url == "https://example.com/a"
    assert fragments[1].url == "https://example.com/b"


def test_split_message_into_fragments_fallback_single_fragment():
    fragments = split_message_into_fragments(
        raw_message_id="growthresearch-200",
        channel_id="growthresearch",
        text="단일 메시지\n추가 본문",
    )

    assert len(fragments) == 1
    assert fragments[0].fragment_id == "growthresearch-200#f0"
    assert fragments[0].title == "단일 메시지"
    assert fragments[0].body == "추가 본문"


def test_split_telegram_message_wrapper():
    message = TelegramMessage(
        channel_id="test",
        message_id="300",
        timestamp="2026-04-28T10:00:00+00:00",
        text="▶️ A\n본문",
    )

    fragments = split_telegram_message(message)

    assert len(fragments) == 1
    assert fragments[0].raw_message_id == "test-300"
