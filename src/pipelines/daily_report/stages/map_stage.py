"""Map stage: 텔레그램 메시지에서 테마를 가진 이슈 추출."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import cast

from dotenv import load_dotenv


# LangSmith 추적을 위한 환경변수 로드
load_dotenv()
from langsmith import traceable

from src.pipelines.daily_report.config import MAP_LLM, MAP_MAX_TOKENS_PER_CHUNK
from src.pipelines.daily_report.evidence import classify_fragment
from src.pipelines.daily_report.examples.map_examples import get_map_examples
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.daily_report.models import (
    ArticleFragment,
    MappedIssue,
    MappedIssueList,
    TelegramMessage,
)
from src.pipelines.daily_report.prompts import MAP_SYSTEM_PROMPT, MAP_USER_PROMPT
from src.pipelines.daily_report.source_parsing import split_telegram_message


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

    fragments = _build_fragments(messages)
    chunks = _chunk_messages(fragments, max_tokens_per_chunk)
    chunk_sizes = [len(c) for c in chunks]

    logger.info(
        "Map stage started: %d messages -> %d fragments -> %d chunks (sizes: %s)",
        len(messages),
        len(fragments),
        len(chunks),
        chunk_sizes,
    )

    # 청크를 병렬로 처리
    results = asyncio.run(_analyze_chunks_parallel(chunks, date))

    # 결과 flatten
    all_issues: list[MappedIssue] = []
    for chunk_issues in results:
        all_issues.extend(chunk_issues)

    elapsed = time.time() - start_time

    # 클러스터링 품질 검증 (경고만, 실패는 아님)
    if all_issues:
        avg_sources = sum(len(issue.source_fragment_ids) for issue in all_issues) / len(all_issues)
        if avg_sources < 1.7:
            logger.warning(
                "Map stage clustering quality below target: avg_fragments=%.2f (target: ≥1.7). "
                "Consider strengthening clustering instructions.",
                avg_sources,
            )

    logger.info(
        "Map stage completed: %d fragments → %d events in %.1fs (%.1f frag/s)",
        len(fragments),
        len(all_issues),
        elapsed,
        len(fragments) / elapsed if elapsed > 0 else 0,
    )

    return all_issues


def _chunk_messages(
    messages: list[TelegramMessage] | list[ArticleFragment],
    max_tokens: int,
) -> list[list[TelegramMessage] | list[ArticleFragment]]:
    """
    토큰 추정치 기반으로 메시지를 청크로 분할.

    대략적인 추정: 한글 1자 ≈ 2 토큰, 영어 1단어 ≈ 1.3 토큰
    """
    chunks: list[list[TelegramMessage] | list[ArticleFragment]] = []
    current_chunk: list[TelegramMessage] | list[ArticleFragment] = []
    current_tokens = 0

    for msg in messages:
        # 대략적인 토큰 추정
        message_text = msg.text if isinstance(msg, TelegramMessage) else f"{msg.title}\n{msg.body}"
        msg_tokens = len(message_text) * 2  # 보수적 추정

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
    chunks: list[list[TelegramMessage] | list[ArticleFragment]],
    date: str,
) -> list[list[MappedIssue]]:
    """asyncio로 청크를 병렬 분석."""
    llm = MAP_LLM.create_llm()

    tasks = [
        _analyze_chunk(chunk, llm, chunk_index, date) for chunk_index, chunk in enumerate(chunks)
    ]
    return await asyncio.gather(*tasks)


async def _analyze_chunk(
    chunk: list[TelegramMessage] | list[ArticleFragment],
    llm,
    chunk_index: int,
    date: str,
) -> list[MappedIssue]:
    """LLM으로 단일 청크 분석."""
    import time

    start_time = time.time()

    logger.info("[Chunk %d] Processing %d messages...", chunk_index, len(chunk))

    # 프롬프트용 메시지 포맷팅
    normalized_chunk = _ensure_fragments(chunk)
    messages_text = "\n".join(
        [
            (
                f"[{fragment.fragment_id}] "
                f"(channel={fragment.channel_id}, source_type={fragment.source_type})\n"
                f"title: {fragment.title}\n"
                f"body: {fragment.body}"
            )
            for fragment in normalized_chunk
        ]
    )

    message_count = len(normalized_chunk)

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

    messages = MAP_LLM.build_messages(system_prompt, user_prompt)

    try:
        llm_start = time.time()
        response = await invoke_llm_with_retry(llm, MappedIssueList, messages, config)
        llm_duration = time.time() - llm_start

        issues = [_normalize_issue(issue, normalized_chunk) for issue in response.issues]
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
        logger.error("[Chunk %d] Failed after %.1fs: %s", chunk_index, elapsed, e)
        logger.warning(
            "[Chunk %d] Switching to fallback fragment mapper because LLM call failed.",
            chunk_index,
        )
        return _fallback_issues_from_fragments(normalized_chunk)


def _build_fragments(messages: list[TelegramMessage]) -> list[ArticleFragment]:
    fragments: list[ArticleFragment] = []
    for message in messages:
        split_fragments = split_telegram_message(message)
        fragments.extend([classify_fragment(fragment) for fragment in split_fragments])
    return fragments


def _ensure_fragments(
    chunk: list[TelegramMessage] | list[ArticleFragment],
) -> list[ArticleFragment]:
    if not chunk:
        return []

    if isinstance(chunk[0], ArticleFragment):
        return cast(list[ArticleFragment], chunk)

    telegram_messages = cast(list[TelegramMessage], chunk)
    return _build_fragments(telegram_messages)


def _normalize_issue(issue: MappedIssue, chunk: list[ArticleFragment]) -> MappedIssue:
    fragment_ids = {fragment.fragment_id for fragment in chunk}

    source_fragment_ids = [
        fragment_id for fragment_id in issue.source_fragment_ids if fragment_id in fragment_ids
    ]

    if not source_fragment_ids:
        source_fragment_ids = sorted(fragment_ids)

    source_ids = sorted(
        {fragment_id.split("#", 1)[0] for fragment_id in source_fragment_ids if "#" in fragment_id}
    )

    update_data = {
        "source_fragment_ids": source_fragment_ids,
        "source_ids": source_ids,
    }

    if not issue.entities:
        update_data["entities"] = list(dict.fromkeys(issue.keywords))[:8]

    if not issue.summary_fact:
        update_data["summary_fact"] = issue.summary

    if issue.stance is None:
        update_data["stance"] = issue.sentiment

    if not issue.summary_interpretation:
        update_data["summary_interpretation"] = ""

    return issue.model_copy(update=update_data)


def _fallback_issues_from_fragments(chunk: list[ArticleFragment]) -> list[MappedIssue]:
    """LLM 장애 시 fragment 기반 최소 이벤트를 생성한다."""
    fallback_issues: list[MappedIssue] = []

    for fragment in chunk:
        text = " ".join((fragment.title, fragment.body)).strip()
        tokens = [token for token in re.split(r"\s+", text) if token]

        # 키워드가 비어도 모델 검증을 통과하도록 최대 8개까지 채운다.
        keywords = list(dict.fromkeys(tokens[:8]))
        if not keywords:
            keywords = [fragment.channel_id]

        summary_fact = fragment.body.strip() if fragment.body else fragment.title

        fallback_issues.append(
            MappedIssue(
                category="기타",
                title=fragment.title or fragment.raw_message_id,
                summary=summary_fact,
                themes=[fragment.channel_id],
                keywords=keywords,
                impact="LLM 호출 실패로 fragment 기반 임시 분류",
                sentiment="neutral",
                source_ids=[fragment.raw_message_id],
                entities=keywords[:5],
                event_type="fallback_fragment",
                stance="neutral",
                source_fragment_ids=[fragment.fragment_id],
                confidence=0.2,
                summary_fact=summary_fact,
                summary_interpretation="",
                source_type=fragment.source_type,
            )
        )

    return fallback_issues


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
    avg_sources = (
        sum(len(issue.source_fragment_ids) for issue in issues) / len(issues) if issues else 0
    )

    print(f"✓ 테마: {total_themes}개 총, {unique_themes}개 고유")
    print(f"✓ 이슈당 평균 fragment 수: {avg_sources:.1f}")

    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/map_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump([issue.model_dump() for issue in issues], f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")
