"""Daily report 파이프라인용 LLM 호출 유틸리티."""

import asyncio
import logging

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ValidationError

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
    original_msg_count = len(messages)
    messages_to_send = list(messages)

    for attempt in range(max_retries):
        try:
            response = await asyncio.wait_for(
                llm_with_output.ainvoke(messages_to_send, config=config),
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

            # ValidationError면 피드백 메시지를 다음 시도에 추가
            if isinstance(e, ValidationError):
                # 필드별 스펙 정보
                field_specs = {
                    "investment_theme": """
📋 investment_theme 요구사항:
- 길이: 20-40자 (쉼표 포함)
- 구조: [전반부 10-15자, 후반부 10-15자]
- 방향성 명확히 (가속/둔화/전환 등)
- 가능하면 구체적 종목/섹터 언급

✅ 올바른 예시:
- "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜" (29자)
- "엔터프라이즈 AI 채택 본격화, SaaS 가격 파워 회복" (31자)
- "스트리밍 가이던스 실망, 광고 전환 시급" (22자)""",
                    "keywords": """
📋 keywords 요구사항:
- 개수: 5-10개 (정확히)
- 포함: 종목명 (한글/영문), 기술용어, 트렌드

✅ 올바른 예시:
- ["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩", "공급망", "데이터센터"] (7개)
- ["팔란티어", "세일스포스", "AI 에이전트", "SaaS", "엔터프라이즈"] (5개)""",
                }

                # Extract error details with field-specific specs
                feedback_parts = ["⚠️ 검증 실패:\n"]
                error_summary = []
                for error in e.errors():
                    field = ".".join(str(loc) for loc in error["loc"])
                    msg = error["msg"]
                    feedback_parts.append(f"❌ {field}: {msg}\n")
                    error_summary.append(f"{field}: {msg}")

                    # 해당 필드의 스펙 추가
                    if field in field_specs:
                        feedback_parts.append(field_specs[field])
                        feedback_parts.append("")  # 빈 줄

                feedback_parts.append("위 요구사항을 정확히 지켜서 다시 생성해주세요.")

                feedback_message = HumanMessage(content="\n".join(feedback_parts))
                # Only keep original messages + latest feedback (discard previous feedbacks)
                messages_to_send = messages[:original_msg_count] + [feedback_message]

                logger.warning(
                    "ValidationError (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    "; ".join(error_summary),
                )
            else:
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
