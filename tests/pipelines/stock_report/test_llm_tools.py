"""Task 1 — invoke_llm_with_tools + ToolCallTrace TDD tests."""

from __future__ import annotations

import asyncio
import threading
from datetime import date
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from src.pipelines.stock_report.retrieval import DocumentSearchHit


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def _make_hit(chunk_id: int, content: str = "test content") -> DocumentSearchHit:
    return DocumentSearchHit(
        chunk_id=chunk_id,
        document_id=chunk_id * 10,
        doc_title=f"Report {chunk_id}",
        source_path=f"/path/to/doc{chunk_id}.pdf",
        broker_key="samsung",
        published_date=date(2026, 6, 1),
        section_path="section/1",
        is_table=False,
        content_clean=content,
        category_key="tech",
        main_theme="AI",
        ticker_tags=["005930"],
        similarity=0.9,
    )


class FakeOutputModel(BaseModel):
    result: str = "ok"


def _make_tool_call(id: str, query: str, category: str | None = None, ticker: str | None = None, top_k: int = 3) -> dict:
    args: dict[str, Any] = {"query": query, "top_k": top_k}
    if category:
        args["category"] = category
    if ticker:
        args["ticker"] = ticker
    return {"id": id, "name": "search_documents", "args": args}


def _ai_message_with_tool_call(tool_call_id: str, query: str, **kwargs) -> AIMessage:
    tool_call = _make_tool_call(tool_call_id, query, **kwargs)
    msg = AIMessage(content="", tool_calls=[tool_call])
    return msg


def _ai_message_no_tool_call(content: str = "done") -> AIMessage:
    return AIMessage(content=content)


def _make_fake_llm(responses: list[AIMessage]):
    """Fake LLM that returns responses in order on each .invoke() call."""
    call_count = 0
    invoke_history: list[list[BaseMessage]] = []

    class FakeBoundLLM:
        def invoke(self, messages: list[BaseMessage], config: dict | None = None) -> AIMessage:
            nonlocal call_count
            invoke_history.append(list(messages))
            response = responses[call_count % len(responses)]
            call_count += 1
            return response

        async def ainvoke(self, messages: list[BaseMessage], config: dict | None = None) -> AIMessage:
            return self.invoke(messages, config)

    class FakeStructuredLLM:
        def __init__(self):
            self.last_messages: list[BaseMessage] = []

        def invoke(self, messages: list[BaseMessage], config: dict | None = None) -> BaseModel:
            self.last_messages = list(messages)
            return FakeOutputModel(result="structured_ok")

        async def ainvoke(self, messages: list[BaseMessage], config: dict | None = None) -> BaseModel:
            return self.invoke(messages, config)

    structured_llm = FakeStructuredLLM()
    bound_llm = FakeBoundLLM()

    class FakeLLM:
        def bind_tools(self, tools, **kwargs):
            return bound_llm

        def with_structured_output(self, model):
            return structured_llm

    return FakeLLM(), structured_llm, invoke_history


# ---------------------------------------------------------------------------
# Import guard — verifies module doesn't exist yet
# ---------------------------------------------------------------------------


def test_module_import():
    """llm_tools 모듈이 정상적으로 임포트되어야 한다."""
    from src.pipelines.stock_report.llm_tools import (  # noqa: F401
        ToolCallRecord,
        ToolCallTrace,
        invoke_llm_with_tools,
    )


# ---------------------------------------------------------------------------
# Test: ToolCallTrace dataclass
# ---------------------------------------------------------------------------


def test_tool_call_trace_all_document_chunk_ids_dedup():
    """ToolCallTrace.all_document_chunk_ids는 중복 제거된 chunk_id 집합을 반환한다."""
    from src.pipelines.stock_report.llm_tools import ToolCallRecord, ToolCallTrace

    hit1 = _make_hit(101)
    hit2 = _make_hit(102)
    hit3 = _make_hit(101)  # duplicate

    record1 = ToolCallRecord(query="q1", category="tech", ticker=None, top_k=3, hits=[hit1, hit2])
    record2 = ToolCallRecord(query="q2", category=None, ticker="005930", top_k=3, hits=[hit2, hit3])

    trace = ToolCallTrace(records=[record1, record2])
    # collected_hits가 모든 hits를 포함해야 함
    assert len(trace.collected_hits) == 4  # hit1, hit2, hit2, hit3

    ids = trace.all_document_chunk_ids
    assert ids == [101, 102]  # dedup, 첫 등장 순 유지


# ---------------------------------------------------------------------------
# Test: 1라운드 tool_call → 결과 반환
# ---------------------------------------------------------------------------


def test_invoke_llm_with_tools_single_round():
    """LLM이 1라운드 tool_call을 하고 다음 라운드에 결과를 반환하는 기본 경로."""
    from src.pipelines.stock_report.llm_tools import invoke_llm_with_tools

    hits = [_make_hit(201), _make_hit(202)]
    search_fn_calls: list[dict] = []

    def fake_search_fn(query: str, *, category=None, ticker=None, top_k=3) -> list[DocumentSearchHit]:
        search_fn_calls.append({"query": query, "category": category, "ticker": ticker, "top_k": top_k})
        return hits

    llm, structured_llm, invoke_history = _make_fake_llm([
        _ai_message_with_tool_call("tc1", "AI semiconductor trend", category="tech", top_k=3),
        _ai_message_no_tool_call(),
    ])

    messages = [HumanMessage(content="Summarize the market")]
    output, trace = asyncio.run(
        invoke_llm_with_tools(
            llm=llm,
            output_model=FakeOutputModel,
            messages=messages,
            search_fn=fake_search_fn,
            config={},
        )
    )

    # 반환 타입
    assert isinstance(output, FakeOutputModel)
    assert output.result == "structured_ok"

    # search_fn이 올바른 인자로 호출됨
    assert len(search_fn_calls) == 1
    assert search_fn_calls[0]["query"] == "AI semiconductor trend"
    assert search_fn_calls[0]["category"] == "tech"
    assert search_fn_calls[0]["top_k"] == 3

    # trace 기록
    assert len(trace.records) == 1
    assert trace.records[0].query == "AI semiconductor trend"
    assert trace.records[0].category == "tech"
    assert len(trace.records[0].hits) == 2

    # collected_hits 집계
    assert len(trace.collected_hits) == 2
    assert trace.all_document_chunk_ids == [201, 202]


# ---------------------------------------------------------------------------
# Test: 즉답 (tool_call 없음) → search_fn 미호출
# ---------------------------------------------------------------------------


def test_invoke_llm_with_tools_no_tool_call():
    """LLM이 첫 응답에서 tool_call 없이 바로 답하면 search_fn이 호출되지 않는다."""
    from src.pipelines.stock_report.llm_tools import invoke_llm_with_tools

    search_fn_called = []

    def fake_search_fn(query: str, **kwargs) -> list[DocumentSearchHit]:
        search_fn_called.append(query)
        return []

    llm, _, _ = _make_fake_llm([_ai_message_no_tool_call("direct answer")])

    output, trace = asyncio.run(
        invoke_llm_with_tools(
            llm=llm,
            output_model=FakeOutputModel,
            messages=[HumanMessage(content="Quick summary")],
            search_fn=fake_search_fn,
            config={},
        )
    )

    assert isinstance(output, FakeOutputModel)
    assert search_fn_called == []
    assert trace.records == []
    assert trace.collected_hits == []


# ---------------------------------------------------------------------------
# Test: B4 — max_tool_rounds 도달 시 미응답 tool_call 정리 + 최종 output 정상
# ---------------------------------------------------------------------------


def test_invoke_llm_with_tools_max_rounds_cleanup():
    """max_tool_rounds 도달 → 미응답 tool_call이 정리되고 최종 output이 정상 반환된다 (OpenAI 400 방지)."""
    from src.pipelines.stock_report.llm_tools import invoke_llm_with_tools

    hits = [_make_hit(301)]

    def fake_search_fn(query: str, **kwargs) -> list[DocumentSearchHit]:
        return hits

    # 두 라운드 모두 tool_call을 반환 → max_tool_rounds=2 도달
    llm, structured_llm, invoke_history = _make_fake_llm([
        _ai_message_with_tool_call("tc1", "query 1"),
        _ai_message_with_tool_call("tc2", "query 2"),
    ])

    output, trace = asyncio.run(
        invoke_llm_with_tools(
            llm=llm,
            output_model=FakeOutputModel,
            messages=[HumanMessage(content="Analyze")],
            search_fn=fake_search_fn,
            config={},
            max_tool_rounds=2,
        )
    )

    # 예외 없이 정상 반환
    assert isinstance(output, FakeOutputModel)

    # trace에 2라운드 기록
    assert len(trace.records) == 2


# ---------------------------------------------------------------------------
# Test: B4 — 최종 with_structured_output 호출에 누적 이력(ToolMessage 포함) 전달
# ---------------------------------------------------------------------------


def test_invoke_llm_with_tools_history_passed_to_final():
    """최종 with_structured_output 호출 시 누적 이력(HumanMessage + AIMessage + ToolMessage)이 전달된다."""
    from src.pipelines.stock_report.llm_tools import invoke_llm_with_tools

    def fake_search_fn(query: str, **kwargs) -> list[DocumentSearchHit]:
        return [_make_hit(401)]

    llm, structured_llm, _ = _make_fake_llm([
        _ai_message_with_tool_call("tc1", "search query"),
        _ai_message_no_tool_call(),
    ])

    asyncio.run(
        invoke_llm_with_tools(
            llm=llm,
            output_model=FakeOutputModel,
            messages=[HumanMessage(content="Analyze market")],
            search_fn=fake_search_fn,
            config={},
        )
    )

    # 최종 호출에 ToolMessage가 포함되어 있어야 함
    last_msgs = structured_llm.last_messages
    assert any(isinstance(m, ToolMessage) for m in last_msgs)
    # 원본 HumanMessage도 포함
    assert any(isinstance(m, HumanMessage) for m in last_msgs)


# ---------------------------------------------------------------------------
# Test: B1 — sync search_fn이 asyncio.to_thread 경유 호출
# ---------------------------------------------------------------------------


def test_invoke_llm_with_tools_search_fn_called_from_thread():
    """sync search_fn이 to_thread 경유로 호출된다 (이벤트 루프 블로킹 방지)."""
    from src.pipelines.stock_report.llm_tools import invoke_llm_with_tools

    call_threads: list[threading.Thread] = []

    def fake_search_fn(query: str, **kwargs) -> list[DocumentSearchHit]:
        call_threads.append(threading.current_thread())
        return [_make_hit(501)]

    llm, _, _ = _make_fake_llm([
        _ai_message_with_tool_call("tc1", "thread test query"),
        _ai_message_no_tool_call(),
    ])

    asyncio.run(
        invoke_llm_with_tools(
            llm=llm,
            output_model=FakeOutputModel,
            messages=[HumanMessage(content="test")],
            search_fn=fake_search_fn,
            config={},
        )
    )

    # to_thread는 워커 스레드에서 실행 → 메인 스레드가 아니어야 함
    assert len(call_threads) == 1
    assert call_threads[0] is not threading.main_thread()


# ---------------------------------------------------------------------------
# Test: graceful — tool 실행 예외 흡수
# ---------------------------------------------------------------------------


def test_invoke_llm_with_tools_search_exception_absorbed():
    """search_fn이 예외를 던져도 흡수되고 output이 정상 반환된다."""
    from src.pipelines.stock_report.llm_tools import invoke_llm_with_tools

    def failing_search_fn(query: str, **kwargs) -> list[DocumentSearchHit]:
        raise RuntimeError("DB connection failed")

    llm, _, _ = _make_fake_llm([
        _ai_message_with_tool_call("tc1", "failing query"),
        _ai_message_no_tool_call(),
    ])

    output, trace = asyncio.run(
        invoke_llm_with_tools(
            llm=llm,
            output_model=FakeOutputModel,
            messages=[HumanMessage(content="test")],
            search_fn=failing_search_fn,
            config={},
        )
    )

    assert isinstance(output, FakeOutputModel)
    # 예외 흡수 → hits 없음
    assert trace.collected_hits == []
