"""Ingest stage 테스트."""

from unittest.mock import patch

import pytest

from src.pipelines.daily_report.stages.ingest_stage import _fetch_macro, ingest


def test_ingest_no_csv_raises_error():
    """CSV 파일이 없을 때 ingest가 에러를 발생시키는지 테스트."""
    with pytest.raises(FileNotFoundError, match="텔레그램 메시지를 찾을 수 없습니다"):
        ingest("2099-01-01", data_dir="nonexistent")


@patch("yfinance.Ticker")
def test_fetch_macro_handles_api_failures(mock_ticker):
    """_fetch_macro가 API 실패 시 기본값을 반환하는지 테스트."""
    # 모든 API 실패 시뮬레이션
    mock_ticker.return_value.history.side_effect = Exception("yfinance 다운")

    macro = _fetch_macro("2026-04-14")

    # 크래시하지 않고 기본값 반환해야 함
    assert macro.vix == 0.0
    assert 0 <= macro.fear_greed <= 100  # VIX 0이면 70 (Greed)
    assert macro.us_markets["S&P500"] == 0.0
    assert macro.kr_markets["KOSPI"] == 0.0
    assert macro.krw_usd == 1320.0


def test_ingest_with_real_data():
    """실제 2026-04-14 데이터로 통합 테스트."""
    # 실제 CSV 파일 사용
    result = ingest("2026-04-14")

    assert result.date == "2026-04-14"
    assert len(result.messages) > 0
    assert result.macro.vix >= 0
    assert 0 <= result.macro.fear_greed <= 100
