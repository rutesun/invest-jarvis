"""T17 — LLM tool-calling loop for PDF evidence retrieval.

invoke_llm_with_tools: bind_tools 루프 → asyncio.to_thread으로 sync search_fn 실행 →
누적 이력을 with_structured_output 최종 호출에 전달.
invoke_llm_with_retry(공용)는 건드리지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from pydantic import BaseModel


if TYPE_CHECKING:
    from src.pipelines.stock_report.retrieval import DocumentSearchHit


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

SEARCH_DOCUMENTS_TOOL = {
    "name": "search_documents",
    "description": (
        "증권사 PDF 리포트에서 관련 내용을 의미 검색한다. "
        "category는 taxonomy key 중 하나(예: tech, finance, energy)만 사용한다. "
        "category/ticker 를 지정하지 않으면 전체 문서에서 검색한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "검색 쿼리 (한국어 또는 영어)"},
            "category": {"type": "string", "description": "taxonomy category key (선택)"},
            "ticker": {"type": "string", "description": "종목 코드 (선택, 예: 005930)"},
            "top_k": {"type": "integer", "description": "반환할 최대 결과 수 (기본 3)", "default": 3},
        },
        "required": ["query"],
    },
}

# ---------------------------------------------------------------------------
# Trace dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    query: str
    category: str | None
    ticker: str | None
    top_k: int
    hits: list[DocumentSearchHit]


@dataclass
class ToolCallTrace:
    records: list[ToolCallRecord] = field(default_factory=list)

    @property
    def collected_hits(self) -> list[DocumentSearchHit]:
        result = []
        for rec in self.records:
            result.extend(rec.hits)
        return result

    @property
    def all_document_chunk_ids(self) -> list[int]:
        seen: set[int] = set()
        result: list[int] = []
        for hit in self.collected_hits:
            if hit.chunk_id not in seen:
                seen.add(hit.chunk_id)
                result.append(hit.chunk_id)
        return result


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


async def _execute_tool_call(
    tool_call: dict[str, Any],
    search_fn,
    trace: ToolCallTrace,
    default_top_k: int,
    excerpt_chars: int,
) -> ToolMessage:
    """단일 tool_call을 실행하고 ToolMessage를 반환한다. 예외는 흡수."""
    tool_call_id = tool_call["id"]
    args = tool_call.get("args") or {}
    query: str = args.get("query", "")
    category: str | None = args.get("category")
    ticker: str | None = args.get("ticker")
    top_k: int = int(args.get("top_k") or default_top_k)

    hits: list[DocumentSearchHit] = []
    content = ""

    if query and search_fn is not None:
        try:
            hits = await asyncio.to_thread(
                search_fn,
                query,
                category=category,
                ticker=ticker,
                top_k=top_k,
            )
        except Exception:
            logger.exception("search_fn 실행 실패 (query=%.40s) — 빈 결과로 계속", query)
            hits = []

        # Excerpt 생성 (LLM에 전달)
        excerpts = []
        for hit in hits:
            text = (hit.content_clean or "")[:excerpt_chars]
            title = hit.doc_title or hit.source_path or "unknown"
            excerpts.append(f"[doc:{hit.chunk_id}] {title}\n{text}")
        content = "\n\n".join(excerpts) if excerpts else "검색 결과 없음"

    trace.records.append(
        ToolCallRecord(query=query, category=category, ticker=ticker, top_k=top_k, hits=hits)
    )

    return ToolMessage(content=content, tool_call_id=tool_call_id)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def invoke_llm_with_tools(
    llm,
    output_model: type[BaseModel],
    messages: list[BaseMessage],
    *,
    search_fn=None,
    config: dict | None = None,
    max_tool_rounds: int = 2,
    default_top_k: int = 3,
    excerpt_chars: int = 400,
    max_retries: int = 3,
    timeout_seconds: float = 180.0,
) -> tuple[BaseModel, ToolCallTrace]:
    """LLM tool-calling 루프를 실행하고 (structured_output, ToolCallTrace)를 반환한다.

    search_fn=None이면 tool_call이 와도 빈 결과로 응답 → 기존 동작 유지.
    예외는 모두 graceful — 리포트는 항상 생성된다.
    """
    config = config or {}
    trace = ToolCallTrace()
    history: list[BaseMessage] = list(messages)

    bound_llm = llm.bind_tools([SEARCH_DOCUMENTS_TOOL])

    for round_idx in range(max_tool_rounds):
        response: AIMessage = bound_llm.invoke(history, config)
        history.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break

        # 도구 실행
        tool_messages = await asyncio.gather(
            *[
                _execute_tool_call(tc, search_fn, trace, default_top_k, excerpt_chars)
                for tc in tool_calls
            ]
        )
        history.extend(tool_messages)

        # max_tool_rounds 마지막 라운드였으면 미응답 tool_call 정리 후 루프 종료
        if round_idx == max_tool_rounds - 1:
            logger.warning("max_tool_rounds(%d) 도달 — 추가 tool_call 무시", max_tool_rounds)
            break

    # 누적 이력 전달해 최종 structured output 1회 호출
    structured_llm = llm.with_structured_output(output_model)
    output: BaseModel = structured_llm.invoke(history, config)

    return output, trace
