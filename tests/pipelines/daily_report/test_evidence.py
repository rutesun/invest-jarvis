"""Tests for source evidence classification."""

from src.pipelines.daily_report.evidence import classify_fragment, classify_source_type
from src.pipelines.daily_report.models import ArticleFragment, SourceType


def test_classify_source_type_broker_summary():
    source_type = classify_source_type(
        channel_id="shinhanresearch",
        title="아침 시황 브리프",
        body="전일 마감 요약",
    )
    assert source_type is SourceType.BROKER_SUMMARY


def test_classify_source_type_primary_news():
    source_type = classify_source_type(
        channel_id="marketwatch",
        title="Reuters: 반도체 공급망 이슈",
        body="속보 업데이트",
        url="https://news.example.com/semiconductor",
    )
    assert source_type is SourceType.PRIMARY_NEWS


def test_classify_source_type_market_signal():
    source_type = classify_source_type(
        channel_id="futures_flow",
        title="장중 수급 변화",
        body="선물 매수 우위",
    )
    assert source_type is SourceType.MARKET_SIGNAL


def test_classify_fragment_updates_source_type():
    fragment = ArticleFragment(
        fragment_id="test-1#f0",
        raw_message_id="test-1",
        channel_id="dailybrief",
        title="일반 메모",
        body="특별한 출처 없음",
        fragment_index=0,
    )

    classified = classify_fragment(fragment)
    assert classified.source_type is SourceType.UNKNOWN
