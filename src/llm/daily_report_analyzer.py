# src/llm/daily_report_analyzer.py
from __future__ import annotations

import logging
from typing import Any, List
from pydantic import BaseModel

from langchain_core.language_models import BaseChatModel

from src.llm.daily_report_models import IssueExtract, StockCatalyst, DailyReport
from src.llm.prompts.daily_report import DailyReportPrompts

logger = logging.getLogger(__name__)


class IssueListResult(BaseModel):
    """Wrapper for list of issues to work with structured output."""
    issues: List[IssueExtract]


async def map_chunk(
    llm: BaseChatModel,
    known_themes: str,
    messages_text: str,
    run_name: str = "map_chunk",
    metadata: dict | None = None,
) -> list[IssueExtract]:
    """단일 메시지 청크에서 이슈를 추출한다."""
    structured_llm = llm.with_structured_output(IssueListResult)
    prompt = DailyReportPrompts.map_issues(known_themes, messages_text)
    result = await structured_llm.ainvoke(
        prompt,
        config={"run_name": run_name, "metadata": metadata or {}},
    )
    return result.issues if result else []


async def merge_themes_llm(
    llm: BaseChatModel,
    known_themes: str,
    new_themes: str,
) -> dict[str, str]:
    """유사 테마를 LLM으로 병합한다."""
    prompt = DailyReportPrompts.merge_themes(known_themes, new_themes)
    structured_llm = llm.with_structured_output(dict)
    result = await structured_llm.ainvoke(
        prompt,
        config={"run_name": "merge_themes"},
    )
    return result.get("매핑", {})


async def synthesize_report(
    llm: BaseChatModel,
    macro: str,
    news: str,
    themes: str,
    catalysts: str,
    metadata: dict | None = None,
) -> DailyReport:
    """전체 데이터를 통합하여 최종 리포트를 생성한다."""
    structured_llm = llm.with_structured_output(DailyReport)
    prompt = DailyReportPrompts.synthesize(macro, news, themes, catalysts)
    result = await structured_llm.ainvoke(
        prompt,
        config={"run_name": "synthesize_final", "metadata": metadata or {}},
    )
    return result
