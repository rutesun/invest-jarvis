"""Map stage 테스트."""
import pytest
from src.pipelines.daily_report.stages.map_stage import (
    map_stage,
    _chunk_messages,
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

    # 클러스터링 품질 체크 (프롬프트 튜닝 필요 - 현재는 기본 검증만)
    avg_sources = sum(len(issue.source_ids) for issue in issues) / len(issues)
    print(f"\n평균 소스/이슈: {avg_sources:.1f}")
    assert avg_sources >= 1  # 최소한 각 이슈는 1개 이상의 소스

    # 테마 다양성 체크
    unique_themes = len(set(theme for issue in issues for theme in issue.themes))
    print(f"고유 테마 수: {unique_themes}")
    assert unique_themes >= 5  # 최소 5개 이상의 고유 테마
