"""Ingest stage 테스트."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.pipelines.daily_report.models import MacroSnapshot
from src.pipelines.daily_report.stages.ingest_stage import _fetch_macro, _fetch_with_retry, ingest


def test_ingest_no_csv_raises_error():
    """CSV 파일이 없을 때 ingest가 에러를 발생시키는지 테스트."""
    with pytest.raises(FileNotFoundError, match="텔레그램 메시지를 찾을 수 없습니다"):
        ingest("2099-01-01", data_dir="nonexistent")


def test_fetch_with_retry_succeeds_first_try():
    """첫 시도에 성공하면 바로 반환."""
    fn = MagicMock(return_value=42.0)
    assert _fetch_with_retry(fn, "test") == 42.0
    assert fn.call_count == 1


def test_fetch_with_retry_succeeds_after_failures():
    """2회 실패 후 3회째 성공."""
    fn = MagicMock(side_effect=[Exception("fail"), Exception("fail"), 42.0])
    assert _fetch_with_retry(fn, "test") == 42.0
    assert fn.call_count == 3


def test_fetch_with_retry_all_fail_returns_none():
    """3회 모두 실패하면 None 반환."""
    fn = MagicMock(side_effect=Exception("fail"))
    assert _fetch_with_retry(fn, "test") is None
    assert fn.call_count == 3


@patch("src.pipelines.daily_report.stages.ingest_stage.fear_and_greed")
def test_fetch_fear_greed_uses_cnn(mock_fg):
    """CNN Fear & Greed 값을 사용하는지 확인."""
    from src.pipelines.daily_report.stages.ingest_stage import _fetch_fear_greed

    mock_fg.get.return_value = MagicMock(value=65.3)
    result = _fetch_fear_greed()
    assert result == 65


@patch("src.pipelines.daily_report.stages.ingest_stage.fear_and_greed")
def test_fetch_fear_greed_failure_returns_none(mock_fg):
    """CNN API 실패 시 None 반환."""
    from src.pipelines.daily_report.stages.ingest_stage import _fetch_fear_greed

    mock_fg.get.side_effect = Exception("CNN down")
    result = _fetch_fear_greed()
    assert result is None


@patch("src.pipelines.daily_report.stages.ingest_stage.fear_and_greed")
@patch("yfinance.Ticker")
def test_fetch_macro_handles_api_failures(mock_ticker, mock_fg):
    """_fetch_macro가 API 실패 시 기본값을 반환하는지 테스트."""
    mock_ticker.return_value.history.side_effect = Exception("yfinance 다운")
    mock_fg.get.side_effect = Exception("CNN 다운")

    macro = _fetch_macro("2026-04-14")

    assert macro.vix is None
    assert macro.fear_greed is None
    assert macro.us_markets["S&P500"] is None
    assert macro.kr_markets["KOSPI"] is None
    assert macro.krw_usd is None
    assert "vix" in macro.missing_fields
    assert "fear_greed" in macro.missing_fields
    assert "krw_usd" in macro.missing_fields


@pytest.mark.integration
def test_ingest_with_real_data():
    """실제 2026-04-14 데이터로 통합 테스트."""
    result = ingest("2026-04-14")

    assert result.date == "2026-04-14"
    assert len(result.messages) > 0
    assert result.macro.date == "2026-04-14"
    assert isinstance(result.macro.missing_fields, list)


@patch("src.pipelines.daily_report.stages.ingest_stage._fetch_macro")
def test_ingest_sorts_messages_and_sets_source_ids(mock_macro, tmp_path: Path):
    mock_macro.return_value = MacroSnapshot(
        date="2026-04-29",
        us_markets={"S&P500": None},
        kr_markets={"KOSPI": None},
        vix=None,
        fear_greed=None,
        krw_usd=None,
        missing_fields=["vix", "krw_usd"],
    )
    csv_dir = tmp_path / "data" / "2026-04"
    csv_dir.mkdir(parents=True)
    csv_dir.joinpath("2026-04-29-test.csv").write_text(
        "message_id,timestamp,content\n2,2026-04-29T11:00:00+00:00,목표주가 상향\n1,2026-04-29T09:00:00+00:00,DRAM spot 약세\n",
        encoding="utf-8",
    )

    result = ingest("2026-04-29", data_dir=str(tmp_path / "data"))

    assert [m.source_id for m in result.messages] == ["test-1", "test-2"]
    assert result.messages[0].message_type.value == "market_signal"
    assert result.messages[1].message_type.value == "broker_summary"
    assert result.macro.vix is None
