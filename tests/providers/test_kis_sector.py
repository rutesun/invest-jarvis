"""Tests for KIS sector index (get_sector_index_history) — Plan 5 TDD."""

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.providers.kis import KISProvider


@pytest.fixture
def cached_token():
    return "test_cached_token"


@pytest.fixture
def sector_index_response():
    """Mock response for inquire-daily-indexchartprice (tr FHKUP03500100)."""
    return {
        "output1": {
            "bstp_nmix_prpr": "2800.00",
            "bstp_kor_isnm": "코스피",
        },
        "output2": [
            {
                "stck_bsop_date": "20260610",
                "bstp_nmix_oprc": "2780.00",
                "bstp_nmix_hgpr": "2810.00",
                "bstp_nmix_lwpr": "2770.00",
                "bstp_nmix_prpr": "2800.00",
                "acml_vol": "500000",
            },
            {
                "stck_bsop_date": "20260609",
                "bstp_nmix_oprc": "2760.00",
                "bstp_nmix_hgpr": "2790.00",
                "bstp_nmix_lwpr": "2750.00",
                "bstp_nmix_prpr": "2780.00",
                "acml_vol": "480000",
            },
        ],
    }


@pytest.mark.asyncio
async def test_get_sector_index_history_calls_correct_tr_id(cached_token, sector_index_response):
    """get_sector_index_history가 tr_id=FHKUP03500100으로 호출한다."""
    with (
        patch.object(KISProvider, "_read_cached_token", return_value=cached_token),
        patch("src.providers.kis.httpx.AsyncClient") as mock_client,
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = sector_index_response
        mock_resp.raise_for_status = MagicMock()

        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        provider = KISProvider(app_key="key", app_secret="secret")
        await provider.get_sector_index_history("0001", period="1mo")

        # tr_id 헤더 확인
        call_kwargs = mock_instance.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("tr_id") == "FHKUP03500100"


@pytest.mark.asyncio
async def test_get_sector_index_history_returns_ohlcv_dataframe(
    cached_token, sector_index_response
):
    """get_sector_index_history가 OHLCV DataFrame을 반환한다."""
    with (
        patch.object(KISProvider, "_read_cached_token", return_value=cached_token),
        patch("src.providers.kis.httpx.AsyncClient") as mock_client,
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = sector_index_response
        mock_resp.raise_for_status = MagicMock()

        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        provider = KISProvider(app_key="key", app_secret="secret")
        df = await provider.get_sector_index_history("0001", period="1mo")

        assert isinstance(df, pd.DataFrame)
        assert {"Open", "High", "Low", "Close", "Volume"}.issubset(df.columns)
        assert len(df) == 2
        assert df.index.name == "Date"


@pytest.mark.asyncio
async def test_get_sector_index_history_uses_mrkt_div_u(cached_token, sector_index_response):
    """FID_COND_MRKT_DIV_CODE='U'(업종지수)로 호출한다."""
    with (
        patch.object(KISProvider, "_read_cached_token", return_value=cached_token),
        patch("src.providers.kis.httpx.AsyncClient") as mock_client,
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = sector_index_response
        mock_resp.raise_for_status = MagicMock()

        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        provider = KISProvider(app_key="key", app_secret="secret")
        await provider.get_sector_index_history("0001", period="1mo")

        call_kwargs = mock_instance.get.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert params.get("FID_COND_MRKT_DIV_CODE") == "U"
        assert params.get("FID_INPUT_ISCD") == "0001"


@pytest.mark.asyncio
async def test_get_sector_index_history_empty_output(cached_token):
    """output2가 빈 경우 빈 DataFrame을 반환한다."""
    empty_response = {"output1": {}, "output2": []}

    with (
        patch.object(KISProvider, "_read_cached_token", return_value=cached_token),
        patch("src.providers.kis.httpx.AsyncClient") as mock_client,
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = empty_response
        mock_resp.raise_for_status = MagicMock()

        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        provider = KISProvider(app_key="key", app_secret="secret")
        df = await provider.get_sector_index_history("0001")

        assert isinstance(df, pd.DataFrame)
        assert df.empty
