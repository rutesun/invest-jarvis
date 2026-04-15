"""Map stage: 텔레그램 메시지에서 테마를 가진 이슈 추출."""
import asyncio
import json
from typing import List
from pathlib import Path
from langchain_core.messages import HumanMessage
from src.llm.provider import LLMProvider
from src.pipelines.daily_report.models import TelegramMessage, MappedIssue
from src.pipelines.daily_report.prompts import MAP_PROMPT
from src.pipelines.daily_report.examples.map_examples import get_map_examples


def map_stage(
    messages: List[TelegramMessage],
    max_tokens_per_chunk: int = 6000,
) -> List[MappedIssue]:
    """
    청크 단위로 텔레그램 메시지에서 이슈 추출.

    Args:
        messages: 텔레그램 메시지 리스트
        max_tokens_per_chunk: 청크당 최대 토큰 수 (대략)

    Returns:
        테마를 가진 MappedIssue 리스트
    """
    if not messages:
        return []

    chunks = _chunk_messages(messages, max_tokens_per_chunk)

    # 청크를 병렬로 처리
    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(_analyze_chunks_parallel(chunks))

    # 결과 flatten
    all_issues = []
    for chunk_issues in results:
        all_issues.extend(chunk_issues)

    return all_issues


def _chunk_messages(
    messages: List[TelegramMessage],
    max_tokens: int,
) -> List[List[TelegramMessage]]:
    """
    토큰 추정치 기반으로 메시지를 청크로 분할.

    대략적인 추정: 한글 1자 ≈ 2 토큰, 영어 1단어 ≈ 1.3 토큰
    """
    chunks = []
    current_chunk = []
    current_tokens = 0

    for msg in messages:
        # 대략적인 토큰 추정
        msg_tokens = len(msg.text) * 2  # 보수적 추정

        if current_tokens + msg_tokens > max_tokens and current_chunk:
            # 새 청크 시작
            chunks.append(current_chunk)
            current_chunk = [msg]
            current_tokens = msg_tokens
        else:
            current_chunk.append(msg)
            current_tokens += msg_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


async def _analyze_chunks_parallel(
    chunks: List[List[TelegramMessage]],
) -> List[List[MappedIssue]]:
    """asyncio로 청크를 병렬 분석."""
    llm = LLMProvider.create(provider="openai", model="gpt-4o", temperature=0.3)

    tasks = [_analyze_chunk(chunk, llm) for chunk in chunks]
    return await asyncio.gather(*tasks)


async def _analyze_chunk(
    chunk: List[TelegramMessage],
    llm,
) -> List[MappedIssue]:
    """LLM으로 단일 청크 분석."""
    # 프롬프트용 메시지 포맷팅
    messages_text = "\n".join([
        f"[{msg.message_id}] {msg.text}"
        for msg in chunk
    ])

    # 프롬프트 구성
    prompt = MAP_PROMPT.format(
        examples=get_map_examples(),
        messages=messages_text,
    )

    # LLM 호출
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    # JSON 응답 파싱
    try:
        # 응답에서 JSON 추출 (마크다운 코드 블록 처리)
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        issues_data = json.loads(content)
        return [MappedIssue(**issue) for issue in issues_data]
    except Exception as e:
        print(f"⚠️  LLM 응답 파싱 실패: {e}")
        print(f"응답: {response.content[:200]}...")
        return []


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys
    from src.pipelines.daily_report.stages.ingest_stage import ingest

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"

    # 데이터 로드
    ingest_result = ingest(date)
    print(f"✓ {len(ingest_result.messages)}개 메시지 로드")

    # Map stage 실행
    issues = map_stage(ingest_result.messages)
    print(f"✓ {len(issues)}개 이슈 추출")

    # 요약 출력
    total_themes = sum(len(issue.themes) for issue in issues)
    unique_themes = len(set(theme for issue in issues for theme in issue.themes))
    avg_sources = sum(len(issue.source_ids) for issue in issues) / len(issues) if issues else 0

    print(f"✓ 테마: {total_themes}개 총, {unique_themes}개 고유")
    print(f"✓ 이슈당 평균 소스 수: {avg_sources:.1f}")

    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/map_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump([issue.model_dump() for issue in issues], f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")
