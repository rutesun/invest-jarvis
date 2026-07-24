"""Map stage: 텔레그램 메시지에서 테마를 가진 이슈 추출."""

import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv


# LangSmith 추적을 위한 환경변수 로드
load_dotenv()
from langsmith import traceable

from src.pipelines.daily_report.config import MAP_MAX_TOKENS_PER_CHUNK, get_stage_llm
from src.pipelines.daily_report.examples.map_examples import get_map_examples
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.daily_report.models import MappedIssue, MappedIssueList, TelegramMessage
from src.pipelines.daily_report.prompts import MAP_SYSTEM_PROMPT, MAP_USER_PROMPT


logger = logging.getLogger(__name__)


@traceable(name="Map Stage")
def map_stage(
    messages: list[TelegramMessage],
    date: str = None,
    max_tokens_per_chunk: int = MAP_MAX_TOKENS_PER_CHUNK,
) -> list[MappedIssue]:
    """
    청크 단위로 텔레그램 메시지에서 이슈 추출.

    Args:
        messages: 텔레그램 메시지 리스트
        date: 날짜 문자열 (LangSmith 그룹핑용, 선택)
        max_tokens_per_chunk: 청크당 최대 토큰 수 (대략)

    Returns:
        테마를 가진 MappedIssue 리스트
    """
    import time

    if not messages:
        return []

    start_time = time.time()

    # 날짜 추출 (없으면 첫 메시지에서)
    if not date and messages:
        date = messages[0].timestamp.strftime("%Y-%m-%d")

    chunks = _chunk_messages(messages, max_tokens_per_chunk)
    chunk_sizes = [len(c) for c in chunks]

    logger.info(
        "Map stage started: %d messages split into %d chunks (sizes: %s)",
        len(messages),
        len(chunks),
        chunk_sizes,
    )

    # 청크를 병렬로 처리
    results = asyncio.run(_analyze_chunks_parallel(chunks, date))

    # 결과 flatten
    all_issues = []
    for chunk_issues in results:
        all_issues.extend(chunk_issues)

    elapsed = time.time() - start_time

    # 클러스터링 품질 검증 (경고만, 실패는 아님)
    if all_issues:
        avg_sources = sum(len(issue.source_ids) for issue in all_issues) / len(all_issues)
        if avg_sources < 1.7:
            logger.warning(
                "Map stage clustering quality below target: avg_sources=%.2f (target: ≥1.7). "
                "Consider strengthening clustering instructions.",
                avg_sources,
            )

    logger.info(
        "Map stage completed: %d messages → %d issues in %.1fs (%.1f msg/s)",
        len(messages),
        len(all_issues),
        elapsed,
        len(messages) / elapsed if elapsed > 0 else 0,
    )

    return all_issues


def _chunk_messages(
    messages: list[TelegramMessage],
    max_tokens: int,
) -> list[list[TelegramMessage]]:
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
    chunks: list[list[TelegramMessage]],
    date: str,
) -> list[list[MappedIssue]]:
    """asyncio로 청크를 병렬 분석."""
    llm = get_stage_llm("map").create_llm()

    tasks = [
        _analyze_chunk(chunk, llm, chunk_index, date) for chunk_index, chunk in enumerate(chunks)
    ]
    return await asyncio.gather(*tasks)


async def _analyze_chunk(
    chunk: list[TelegramMessage],
    llm,
    chunk_index: int,
    date: str,
) -> list[MappedIssue]:
    """LLM으로 단일 청크 분석."""
    import time

    start_time = time.time()

    logger.info("[Chunk %d] Processing %d messages...", chunk_index, len(chunk))

    # 프롬프트용 메시지 포맷팅
    messages_text = "\n".join([f"[{msg.channel_id}-{msg.message_id}] {msg.text}" for msg in chunk])

    message_count = len(chunk)

    # prompts.py에서 프롬프트 가져오기
    examples = get_map_examples()
    system_prompt = MAP_SYSTEM_PROMPT.format(examples=examples)
    user_prompt = MAP_USER_PROMPT.format(
        message_count=message_count,
        messages=messages_text,
    )

    # LangSmith 그룹핑을 위한 메타데이터 설정
    run_name = f"Map Stage - {date} - Chunk {chunk_index + 1}"
    config = {
        "run_name": run_name,
        "tags": ["daily_report", "map_stage", f"date:{date}"],
        "metadata": {
            "stage": "map",
            "date": date,
            "chunk_index": chunk_index,
            "message_count": message_count,
        },
    }

    messages = get_stage_llm("map").build_messages(system_prompt, user_prompt)

    try:
        llm_start = time.time()
        response = await invoke_llm_with_retry(llm, MappedIssueList, messages, config)
        llm_duration = time.time() - llm_start

        issues = response.issues
        elapsed = time.time() - start_time

        logger.info(
            "[Chunk %d] Completed: %d issues extracted (LLM: %.1fs, Total: %.1fs)",
            chunk_index,
            len(issues),
            llm_duration,
            elapsed,
        )
        return issues
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("[Chunk %d] Failed after %.1fs: %s", chunk_index, elapsed, e, exc_info=True)
        return []


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys

    from src.pipelines.daily_report.stages.ingest_stage import ingest

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-15"

    # 데이터 로드
    ingest_result = ingest(date)
    print(f"✓ {len(ingest_result.messages)}개 메시지 로드")

    # Map stage 실행
    issues = map_stage(ingest_result.messages, date)
    print(f"✓ {len(issues)}개 이슈 추출")

    # 요약 출력
    total_themes = sum(len(issue.themes) for issue in issues)
    unique_themes = len({theme for issue in issues for theme in issue.themes})
    avg_sources = sum(len(issue.source_ids) for issue in issues) / len(issues) if issues else 0

    print(f"✓ 테마: {total_themes}개 총, {unique_themes}개 고유")
    print(f"✓ 이슈당 평균 소스 수: {avg_sources:.1f}")

    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/map_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump([issue.model_dump() for issue in issues], f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")
