"""Daily report 파이프라인용 LLM 호출 유틸리티."""

import asyncio
import logging

from pydantic import BaseModel

from src.pipelines.daily_report.config import LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS


logger = logging.getLogger(__name__)


async def invoke_llm_with_retry(
    llm,
    output_model: type[BaseModel],
    messages: list,
    config: dict,
    max_retries: int = LLM_MAX_RETRIES,
    timeout_seconds: float = LLM_TIMEOUT_SECONDS,
) -> BaseModel:
    """
    타임아웃 + exponential backoff 재시도가 적용된 LLM 호출.

    Args:
        llm: LangChain LLM 인스턴스
        output_model: 구조화된 출력 Pydantic 모델
        messages: LangChain 메시지 리스트
        config: LangSmith 설정
        max_retries: 최대 재시도 횟수
        timeout_seconds: 호출당 타임아웃 (초)

    Returns:
        파싱된 Pydantic 모델 인스턴스

    Raises:
        마지막 시도 실패 시 원본 예외를 그대로 raise
    """
    llm_with_output = llm.with_structured_output(output_model)
    last_exception = None

    for attempt in range(max_retries):
        try:
            response = await asyncio.wait_for(
                llm_with_output.ainvoke(messages, config=config),
                timeout=timeout_seconds,
            )
            return response
        except TimeoutError:
            last_exception = TimeoutError(f"LLM call timed out after {timeout_seconds}s")
            logger.warning(
                "LLM timeout (attempt %d/%d, %ds)",
                attempt + 1,
                max_retries,
                timeout_seconds,
            )
        except Exception as e:
            last_exception = e
            logger.warning(
                "LLM call failed (attempt %d/%d): %s",
                attempt + 1,
                max_retries,
                e,
            )

        if attempt < max_retries - 1:
            wait_time = 2**attempt
            await asyncio.sleep(wait_time)

    raise last_exception
