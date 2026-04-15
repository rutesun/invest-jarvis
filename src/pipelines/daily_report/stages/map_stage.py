"""Map stage: 텔레그램 메시지에서 테마를 가진 이슈 추출."""
import asyncio
import json
import os
from typing import List
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from src.llm.provider import LLMProvider

# LangSmith 추적을 위한 환경변수 로드
load_dotenv()
from src.pipelines.daily_report.models import TelegramMessage, MappedIssue
from src.pipelines.daily_report.prompts import MAP_PROMPT
from src.pipelines.daily_report.examples.map_examples import get_map_examples


def map_stage(
    messages: List[TelegramMessage],
    date: str = None,
    max_tokens_per_chunk: int = 80000,
) -> List[MappedIssue]:
    """
    청크 단위로 텔레그램 메시지에서 이슈 추출.

    Args:
        messages: 텔레그램 메시지 리스트
        date: 날짜 문자열 (LangSmith 그룹핑용, 선택)
        max_tokens_per_chunk: 청크당 최대 토큰 수 (대략)

    Returns:
        테마를 가진 MappedIssue 리스트
    """
    if not messages:
        return []

    # 날짜 추출 (없으면 첫 메시지에서)
    if not date and messages:
        date = messages[0].timestamp.strftime("%Y-%m-%d")

    chunks = _chunk_messages(messages, max_tokens_per_chunk)

    # 청크를 병렬로 처리
    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(_analyze_chunks_parallel(chunks, date))

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
    date: str,
) -> List[List[MappedIssue]]:
    """asyncio로 청크를 병렬 분석."""
    llm = LLMProvider.create(provider="openai", model="gpt-4o", temperature=0.2)

    tasks = [
        _analyze_chunk(chunk, llm, chunk_index, date)
        for chunk_index, chunk in enumerate(chunks)
    ]
    return await asyncio.gather(*tasks)


async def _analyze_chunk(
    chunk: List[TelegramMessage],
    llm,
    chunk_index: int,
    date: str,
) -> List[MappedIssue]:
    """LLM으로 단일 청크 분석."""
    # 프롬프트용 메시지 포맷팅
    messages_text = "\n".join([
        f"[{msg.message_id}] {msg.text}"
        for msg in chunk
    ])

    # 목표 이슈 개수 계산 (메시지의 15-20%)
    message_count = len(chunk)
    target_count = max(int(message_count * 0.18), 5)  # 최소 5개

    # 프롬프트 분리: 예시는 SystemMessage로 (캐싱 가능)
    examples = get_map_examples()
    system_prompt = f"""당신은 한국 금융 시장 전문 애널리스트입니다.

**작업**: 메시지를 이슈로 압축

**클러스터링 방법** (Few-shot):
{examples}

**지침**:
1. **먼저 그룹핑**: 모든 메시지를 읽고 유사한 것들끼리 묶기
   - 같은 기업: "블룸 에너지", "오라클-블룸", "Bloom Energy" → 하나
   - 같은 산업: "삼성 HBM", "SK하이닉스 HBM", "마이크론 가격" → 하나
   - 같은 트렌드: "AI 데이터센터 전력", "전력 인프라 투자" → 하나

2. **테마**: 2-3개, 구체적으로
   - "반도체" (X) → "AI 메모리 업사이클" (O)

3. **Sentiment**: 정확히 이 3개 중 하나만 사용
   - "bull" - 명확한 호재 (실적 개선, 계약 체결, 긍정 전망)
   - "bear" - 명확한 악재 (실적 부진, 리스크, 부정 전망)
   - "neutral" - 그 외 모든 경우 (정보, 불확실, 혼재)

4. **Source_ids**: 묶인 모든 메시지 ID 나열"""

    user_prompt = f"""**입력 ({message_count}개 메시지)**:
{messages_text}

**출력 (정확히 {target_count}개 이슈)**:
```json
[
  {{
    "title": "한글 제목",
    "summary": "통합 요약 (2-3문장)",
    "themes": ["테마1", "테마2"],
    "keywords": ["종목", "기술용어"],
    "sentiment": "bull",
    "source_ids": ["id1", "id2", "id3", ...]
  }}
]
```"""

    # LangSmith 그룹핑을 위한 메타데이터 설정
    run_name = f"Map Stage - {date} - Chunk {chunk_index+1}"
    config = {
        "run_name": run_name,
        "tags": ["daily_report", "map_stage", f"date:{date}"],
        "metadata": {
            "stage": "map",
            "date": date,
            "chunk_index": chunk_index,
            "message_count": message_count,
            "target_count": target_count,
        },
    }

    # LLM 호출 (예시를 SystemMessage로 분리하여 캐싱 가능)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    response = await llm.ainvoke(messages, config=config)

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
    issues = map_stage(ingest_result.messages, date)
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
