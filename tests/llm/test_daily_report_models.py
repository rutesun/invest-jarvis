# tests/llm/test_daily_report_models.py
import pytest
from src.llm.daily_report_models import (
    IngestResult,
    IssueExtract,
    StockDetail,
    Theme,
    ShuffleResult,
    StockCatalyst,
    DailyReport,
)


def test_ingest_result_creation():
    result = IngestResult(
        telegram_messages=[{"id": 1, "channel": "ch1", "text": "test", "timestamp": "2026-04-13T09:00:00"}],
        macro_snapshot={"vix": 18.2, "fear_greed": 62},
        market_news=[{"title": "SPY rises", "summary": "S&P 500 up 1%", "source": "yfinance", "url": "http://example.com"}],
        kr_flow=[{"ticker": "005930", "name": "삼성전자", "foreign_net": 500, "inst_net": 300}],
        momentum=[{"ticker": "NVDA", "price": 950.0, "change_pct": 5.8, "volume_ratio": 3.2}],
    )
    assert len(result.telegram_messages) == 1
    assert result.macro_snapshot["vix"] == 18.2


def test_issue_extract_creation():
    issue = IssueExtract(
        theme="CPO/광통신",
        tickers=["엔비디아", "LITE", "코위버"],
        sentiment="bull",
        summary="TSMC 실적 호조로 CPO 수요 확대 기대",
        source_ids=[101, 102],
    )
    assert issue.theme == "CPO/광통신"
    assert issue.sentiment == "bull"
    assert len(issue.tickers) == 3


def test_issue_extract_rejects_invalid_sentiment():
    with pytest.raises(Exception):
        IssueExtract(
            theme="test",
            tickers=[],
            sentiment="invalid",
            summary="test",
            source_ids=[],
        )


def test_stock_detail_optional_scores():
    stock = StockDetail(
        ticker="NVDA",
        market="US",
        mention_count=5,
        flow_score=None,
        volume_score=3.2,
        source="both",
        summaries=["NVDA 관련 요약"],
    )
    assert stock.flow_score is None
    assert stock.volume_score == 3.2


def test_theme_with_ticker_list():
    theme = Theme(
        name="CPO/광통신",
        narrative="TSMC 실적 발표로 CPO 수요 증가 기대",
        sentiment="bull",
        mention_count=15,
        stocks=["NVDA", "LITE", "코위버"],
    )
    assert theme.stocks == ["NVDA", "LITE", "코위버"]


def test_shuffle_result_stock_details_dict():
    detail = StockDetail(
        ticker="NVDA", market="US", mention_count=5,
        flow_score=None, volume_score=3.2, source="telegram",
        summaries=["summary1"],
    )
    theme = Theme(
        name="AI", narrative="AI boom", sentiment="bull",
        mention_count=10, stocks=["NVDA"],
    )
    result = ShuffleResult(themes=[theme], stock_details={"NVDA": detail})
    assert result.stock_details["NVDA"].ticker == "NVDA"


def test_stock_catalyst_multiple_themes():
    catalyst = StockCatalyst(
        ticker="NVDA",
        themes=["AI 반도체", "CPO/광통신"],
        news=["NVDA announces new chip"],
        catalyst_summary="차세대 칩 발표로 AI 인프라 수요 견인",
    )
    assert len(catalyst.themes) == 2


def test_daily_report_creation():
    report = DailyReport(
        date="2026-04-13",
        market_pulse="VIX 18.2 | F&G 62 | 리스크온 환경 지속",
        narrative_and_themes="오늘 시장의 핵심은 AI 인프라...",
        featured_analysis="[CPO/광통신]\n- 코위버: 외인 순매수 +30억",
    )
    assert report.date == "2026-04-13"


def test_models_json_roundtrip():
    """모든 모델은 캐시 저장을 위해 JSON 직렬화/역직렬화가 가능해야 한다."""
    theme = Theme(
        name="AI", narrative="AI boom", sentiment="bull",
        mention_count=10, stocks=["NVDA"],
    )
    detail = StockDetail(
        ticker="NVDA", market="US", mention_count=5,
        flow_score=None, volume_score=3.2, source="telegram",
        summaries=["summary1"],
    )
    result = ShuffleResult(themes=[theme], stock_details={"NVDA": detail})
    json_str = result.model_dump_json()
    restored = ShuffleResult.model_validate_json(json_str)
    assert restored.themes[0].name == "AI"
    assert restored.stock_details["NVDA"].volume_score == 3.2
