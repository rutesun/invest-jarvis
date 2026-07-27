from __future__ import annotations

import os
from dataclasses import dataclass

from src.llm.stage_config import StageLLMConfig, resolve_stage_llm


def get_semantic_extraction_llm_config() -> StageLLMConfig:
    """daily_v2 extraction 스테이지 LLM 설정 (config.yaml llm.daily_v2.extraction)."""
    return resolve_stage_llm("daily_v2", "extraction")


def get_report_synthesis_llm_config() -> StageLLMConfig:
    """daily_v2 synthesis 스테이지 LLM 설정 (config.yaml llm.daily_v2.synthesis)."""
    return resolve_stage_llm("daily_v2", "synthesis")


SEMANTIC_EXTRACTION_MAX_CONCURRENCY = 8
SEMANTIC_EXTRACTION_TIMEOUT_SECONDS = 180.0
SEMANTIC_EXTRACTION_MAX_RETRIES = 3

GOOGLE_GROUNDING_DEFAULT_MODEL = "gemini-3.5-flash"


@dataclass(frozen=True)
class GoogleGroundingConfig:
    api_key: str | None = None
    model: str = GOOGLE_GROUNDING_DEFAULT_MODEL


def get_google_grounding_config() -> GoogleGroundingConfig:
    return GoogleGroundingConfig(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model=os.getenv("STOCK_REPORT_GOOGLE_MODEL") or GOOGLE_GROUNDING_DEFAULT_MODEL,
    )
