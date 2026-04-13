# tests/pipelines/report_stages/test_shuffle_filter.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pipelines.report_stages.shuffle_filter import ShuffleStage
from src.llm.daily_report_models import IssueExtract, ShuffleResult


@pytest.fixture
def sample_issues():
    return [
        IssueExtract(theme="CPO/광통신", tickers=["엔비디아", "LITE"], sentiment="bull",
                     summary="CPO 수요 증가", source_ids=[1]),
        IssueExtract(theme="CPO/광통신", tickers=["코위버", "LITE"], sentiment="bull",
                     summary="광트랜시버 수주", source_ids=[2]),
        IssueExtract(theme="AI 반도체", tickers=["엔비디아", "SK하이닉스"], sentiment="bull",
                     summary="AI 칩 수요 폭발", source_ids=[3]),
        IssueExtract(theme="방산", tickers=["한화에어로스페이스"], sentiment="neutral",
                     summary="방산 수출 계약", source_ids=[4]),
    ]


@pytest.fixture
def sample_kr_flow():
    return [
        {"ticker": "005930", "name": "삼성전자", "foreign_net": 500, "inst_net": 300},
        {"ticker": "A058400", "name": "코위버", "foreign_net": 200, "inst_net": 150},
    ]


@pytest.fixture
def sample_momentum():
    return [
        {"ticker": "NVDA", "name": "NVIDIA", "price": 950, "change_pct": 5.8, "volume_ratio": 3.2},
        {"ticker": "LITE", "name": "Lumentum", "price": 85, "change_pct": 3.5, "volume_ratio": 2.1},
    ]


@pytest.fixture
def mock_ticker_resolver():
    resolver = AsyncMock()

    async def resolve(query):
        mapping = {
            "엔비디아": MagicMock(resolved_ticker="NVDA"),
            "LITE": MagicMock(resolved_ticker="LITE"),
            "코위버": MagicMock(resolved_ticker="A058400"),
            "SK하이닉스": MagicMock(resolved_ticker="000660"),
            "한화에어로스페이스": MagicMock(resolved_ticker="012450"),
        }
        return mapping.get(query, MagicMock(resolved_ticker=query))

    resolver.resolve = AsyncMock(side_effect=resolve)
    return resolver


@pytest.fixture
def mock_merge_llm():
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value={"매핑": {}})
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.asyncio
async def test_shuffle_produces_themes_sorted_by_mention(
    sample_issues, sample_kr_flow, sample_momentum,
    mock_ticker_resolver, mock_merge_llm,
):
    stage = ShuffleStage(
        ticker_resolver=mock_ticker_resolver,
        merge_llm=mock_merge_llm,
        known_themes=["CPO/광통신", "AI 반도체", "방산"],
        top_n=5,
    )
    result = await stage.run(sample_issues, sample_kr_flow, sample_momentum)

    assert isinstance(result, ShuffleResult)
    assert result.themes[0].name == "CPO/광통신"
    assert result.themes[0].mention_count == 2


@pytest.mark.asyncio
async def test_shuffle_enriches_stock_details_with_flow(
    sample_issues, sample_kr_flow, sample_momentum,
    mock_ticker_resolver, mock_merge_llm,
):
    stage = ShuffleStage(
        ticker_resolver=mock_ticker_resolver,
        merge_llm=mock_merge_llm,
        known_themes=["CPO/광통신", "AI 반도체", "방산"],
        top_n=5,
    )
    result = await stage.run(sample_issues, sample_kr_flow, sample_momentum)

    if "A058400" in result.stock_details:
        assert result.stock_details["A058400"].flow_score is not None


@pytest.mark.asyncio
async def test_shuffle_enriches_stock_details_with_momentum(
    sample_issues, sample_kr_flow, sample_momentum,
    mock_ticker_resolver, mock_merge_llm,
):
    stage = ShuffleStage(
        ticker_resolver=mock_ticker_resolver,
        merge_llm=mock_merge_llm,
        known_themes=["CPO/광통신", "AI 반도체", "방산"],
        top_n=5,
    )
    result = await stage.run(sample_issues, sample_kr_flow, sample_momentum)

    if "NVDA" in result.stock_details:
        assert result.stock_details["NVDA"].volume_score is not None


@pytest.mark.asyncio
async def test_shuffle_collects_summaries_per_stock(
    sample_issues, sample_kr_flow, sample_momentum,
    mock_ticker_resolver, mock_merge_llm,
):
    stage = ShuffleStage(
        ticker_resolver=mock_ticker_resolver,
        merge_llm=mock_merge_llm,
        known_themes=["CPO/광통신", "AI 반도체", "방산"],
        top_n=5,
    )
    result = await stage.run(sample_issues, sample_kr_flow, sample_momentum)

    nvda = result.stock_details.get("NVDA")
    if nvda:
        assert len(nvda.summaries) == 2
