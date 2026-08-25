from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.providers.kis import KISProvider


@pytest.fixture
def mock_token_response():
    return {
        "access_token": "test_token",
        "token_type": "Bearer",
        "expires_in": 86400,
    }


@pytest.fixture
def mock_investor_ranking_response():
    """실제 FHPTJ04400000 응답 형태: rt_cd + 종목별 외국인·기관 순매수 동시 포함."""
    return {
        "rt_cd": "0",
        "msg1": "정상처리 되었습니다.",
        "output": [
            {
                "hts_kor_isnm": "삼성전자",
                "mksc_shrn_iscd": "005930",
                "frgn_ntby_qty": "500000",
                "frgn_ntby_tr_pbmn": "35000000000",
                "orgn_ntby_qty": "10000",
                "orgn_ntby_tr_pbmn": "1000000000",
            },
            {
                "hts_kor_isnm": "현대건설",
                "mksc_shrn_iscd": "000720",
                "frgn_ntby_qty": "100000",
                "frgn_ntby_tr_pbmn": "10000000000",
                "orgn_ntby_qty": "800000",
                "orgn_ntby_tr_pbmn": "50000000000",
            },
            {
                "hts_kor_isnm": "기관만산종목",
                "mksc_shrn_iscd": "111111",
                "frgn_ntby_qty": "-50000",
                "frgn_ntby_tr_pbmn": "-5000000000",
                "orgn_ntby_qty": "20000",
                "orgn_ntby_tr_pbmn": "2000000000",
            },
        ],
    }


@pytest.fixture(autouse=True)
def _skip_token_cache():
    """Bypass file-based token cache for all tests."""
    with patch.object(KISProvider, "_read_cached_token", return_value=None):
        yield


@pytest.mark.asyncio
async def test_get_investor_ranking(mock_token_response, mock_investor_ranking_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_ranking_resp = MagicMock()
        mock_ranking_resp.json.return_value = mock_investor_ranking_response
        mock_ranking_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_ranking_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_investor_ranking(investor_type="foreign", top_n=10)

        # 외국인 순매수(>0)만, 금액순: 삼성전자(35B) > 현대건설(10B). 순매도 종목 제외
        assert [r["ticker"] for r in result] == ["005930", "000720"]
        assert result[0]["name"] == "삼성전자"
        assert result[0]["net_buy_amount"] == 35_000_000_000


def _mock_investor_call(mock_client, token_response, ranking_response):
    """토큰 + 랭킹 응답을 mock httpx에 연결하는 헬퍼."""
    from unittest.mock import MagicMock

    token_resp = MagicMock()
    token_resp.json.return_value = token_response
    token_resp.raise_for_status = MagicMock()
    ranking_resp = MagicMock()
    ranking_resp.json.return_value = ranking_response
    ranking_resp.raise_for_status = MagicMock()
    instance = AsyncMock()
    instance.post.return_value = token_resp
    instance.get.return_value = ranking_resp
    mock_client.return_value.__aenter__.return_value = instance


@pytest.mark.asyncio
async def test_get_investor_ranking_institution_sorted(
    mock_token_response, mock_investor_ranking_response
):
    """기관 순매수는 기관 금액순으로 정렬 — 현대건설(50B) > 삼성전자(1B) > 기관만산종목(2B)."""
    with patch("httpx.AsyncClient") as mock_client:
        _mock_investor_call(mock_client, mock_token_response, mock_investor_ranking_response)
        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_investor_ranking(investor_type="institution", top_n=10)

        assert [r["ticker"] for r in result] == ["000720", "111111", "005930"]
        assert result[0]["net_buy_amount"] == 50_000_000_000


@pytest.mark.asyncio
async def test_get_investor_ranking_rt_cd_guard(mock_token_response):
    """rt_cd != '0'이면 조용히 0건이 아니라 경고 후 빈 리스트 (파라미터 계약 회귀 방지)."""
    error_response = {"rt_cd": "2", "msg1": "ERROR INPUT FIELD NOT FOUND", "output": []}
    with patch("httpx.AsyncClient") as mock_client:
        _mock_investor_call(mock_client, mock_token_response, error_response)
        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_investor_ranking(investor_type="foreign", top_n=10)
        assert result == []


@pytest.mark.asyncio
async def test_get_us_ranking_updown(mock_token_response):
    mock_us_response = {
        "output2": [
            {
                "symb": "NVDA",
                "name": "NVIDIA Corp",
                "rate": "5.20",
                "last": "950.00",
                "tvol": "50000000",
            },
        ]
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_ranking_resp = MagicMock()
        mock_ranking_resp.json.return_value = mock_us_response
        mock_ranking_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_ranking_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_us_ranking_updown(exchange="NAS", direction="up", top_n=10)

        assert len(result) == 1
        assert result[0]["ticker"] == "NVDA"


@pytest.mark.asyncio
async def test_get_us_ranking_volume(mock_token_response):
    mock_us_response = {
        "output2": [
            {
                "symb": "AAPL",
                "name": "Apple Inc",
                "last": "180.00",
                "tvol": "75000000",
            },
        ]
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_ranking_resp = MagicMock()
        mock_ranking_resp.json.return_value = mock_us_response
        mock_ranking_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_ranking_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_us_ranking_volume(exchange="NAS", top_n=10)

        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["name"] == "Apple Inc"
        assert result[0]["volume"] == 75000000


@pytest.mark.asyncio
async def test_get_investor_trend(mock_token_response):
    mock_trend_response = {
        "output": [
            {
                "stck_bsop_date": "20260409",
                "frgn_ntby_qty": "100",
                "orgn_ntby_qty": "200",
            },
        ]
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = mock_token_response
        mock_token_resp.raise_for_status = MagicMock()

        mock_trend_resp = MagicMock()
        mock_trend_resp.json.return_value = mock_trend_response
        mock_trend_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_token_resp
        mock_client_instance.get.return_value = mock_trend_resp
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        provider = KISProvider(app_key="test", app_secret="test")
        result = await provider.get_investor_trend(ticker="005930", days=10)

        assert len(result) == 1
        assert result[0]["date"] == "20260409"
        assert result[0]["foreign_net"] == 100
        assert result[0]["institution_net"] == 200
        assert result[0]["total_net"] == 300
