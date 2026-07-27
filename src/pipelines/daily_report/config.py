"""Daily report 파이프라인 설정."""

from src.llm.stage_config import StageLLMConfig, resolve_stage_llm


def get_stage_llm(stage: str) -> StageLLMConfig:
    """config.yaml llm.daily 섹션에서 스테이지 설정을 얻는다."""
    return resolve_stage_llm("daily", stage)


__all__ = ["StageLLMConfig", "get_stage_llm"]

# Map stage 청크 설정
MAP_MAX_TOKENS_PER_CHUNK = 80_000

# LLM 호출 재시도/타임아웃
LLM_TIMEOUT_SECONDS = 180.0
LLM_MAX_RETRIES = 3

# 매크로 데이터 수집 재시도
MACRO_MAX_RETRIES = 3
