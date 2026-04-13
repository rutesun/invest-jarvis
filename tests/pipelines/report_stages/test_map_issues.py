# tests/pipelines/report_stages/test_map_issues.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.pipelines.report_stages.map_issues import MapStage
from src.llm.daily_report_models import IssueExtract


@pytest.fixture
def sample_messages():
    return [
        {"id": i, "channel": "ch1", "text": f"메시지 {i}", "timestamp": "2026-04-13T09:00:00"}
        for i in range(120)
    ]


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=[
        IssueExtract(
            theme="CPO/광통신",
            tickers=["엔비디아", "LITE"],
            sentiment="bull",
            summary="CPO 수요 증가",
            source_ids=[1, 2],
        ),
    ])
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.asyncio
async def test_map_stage_chunks_messages(sample_messages, mock_llm):
    stage = MapStage(llm=mock_llm, known_themes="CPO/광통신\nAI 반도체", chunk_size=50)
    issues = await stage.run(sample_messages)

    assert len(issues) >= 1
    assert all(isinstance(i, IssueExtract) for i in issues)
    assert mock_llm.with_structured_output.return_value.ainvoke.call_count == 3


@pytest.mark.asyncio
async def test_map_stage_empty_messages(mock_llm):
    stage = MapStage(llm=mock_llm, known_themes="", chunk_size=50)
    issues = await stage.run([])
    assert issues == []


@pytest.mark.asyncio
async def test_map_stage_handles_chunk_failure(sample_messages, mock_llm):
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("LLM timeout")
        return [
            IssueExtract(
                theme="AI", tickers=["NVDA"], sentiment="bull",
                summary="AI boom", source_ids=[1],
            ),
        ]

    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=side_effect)
    stage = MapStage(llm=mock_llm, known_themes="", chunk_size=50)
    issues = await stage.run(sample_messages)

    assert len(issues) == 2
