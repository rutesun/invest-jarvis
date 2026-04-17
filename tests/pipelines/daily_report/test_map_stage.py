"""Map stage 테스트."""

import pytest

from src.pipelines.daily_report.stages.map_stage import (
    _chunk_messages,
    map_stage,
)


def test_chunk_messages_respects_max_tokens(sample_messages):
    """_chunk_messages가 토큰 제한을 지키는지 테스트."""
    # 작은 청크 강제
    chunks = _chunk_messages(sample_messages, max_tokens=100)

    # 여러 청크가 생성되어야 함
    assert len(chunks) > 1

    # 각 청크는 제한 내여야 함 (대략 체크)
    for chunk in chunks:
        total_chars = sum(len(msg.text) for msg in chunk)
        assert total_chars * 2 <= 150  # 약간의 여유 허용


def test_map_stage_with_sample_messages(sample_messages):
    """샘플 메시지로 Map stage 테스트."""
    issues = map_stage(sample_messages)

    # 최소 1개 이슈 추출되어야 함
    assert len(issues) >= 1

    # 구조 검증
    for issue in issues:
        assert issue.title  # 제목 존재
        assert 1 <= len(issue.themes) <= 3  # 1-3개 테마
        assert issue.sentiment in ["bull", "bear", "neutral"]
        assert len(issue.source_ids) > 0  # 소스 참조 존재


@pytest.mark.integration
def test_map_stage_with_real_data():
    """실제 2026-04-14 데이터로 통합 테스트."""
    from src.pipelines.daily_report.stages.ingest_stage import ingest

    ingest_result = ingest("2026-04-14")
    issues = map_stage(ingest_result.messages)

    # 실제 데이터는 이슈를 생성해야 함
    assert len(issues) > 0

    # 압축률 체크
    message_count = len(ingest_result.messages)
    compression_rate = len(issues) / message_count
    print(f"\n압축률: {message_count}개 → {len(issues)}개 ({compression_rate:.1%})")
    assert compression_rate < 0.7  # 최소 30% 압축

    # 클러스터링 품질 체크
    avg_sources = sum(len(issue.source_ids) for issue in issues) / len(issues)
    print(f"평균 소스/이슈: {avg_sources:.1f}")
    assert avg_sources >= 1.5  # 평균 1.5개 이상의 소스

    # 테마 다양성 체크
    unique_themes = len({theme for issue in issues for theme in issue.themes})
    total_themes = sum(len(issue.themes) for issue in issues)
    print(f"테마: {total_themes}개 총, {unique_themes}개 고유")
    assert unique_themes >= 20  # 최소 20개 이상의 고유 테마
