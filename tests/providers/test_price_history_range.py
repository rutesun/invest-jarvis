"""범위 계약은 명시적 synthetic transport만 사용한다. 실 raw golden이 아니다."""

from datetime import date

import pandas as pd
import pytest

from src.providers.kis import ADJUSTED, KISProvider
from src.providers.kis_wrapper import KISProviderWrapper
from src.providers.price_history_range import (
    HistoryFinality,
    InputHistoryError,
    RangeHistoryUnavailableError,
)
from src.providers.yfinance_provider import YFinanceProvider
from tests.harness.price_history_range_contract import assert_kis_range_response_contract


@pytest.fixture
def kis_pages():
    def row(day, close="11"):
        return {
            "stck_bsop_date": day,
            "stck_oprc": "10",
            "stck_hgpr": "12",
            "stck_lwpr": "9",
            "stck_clpr": close,
            "acml_vol": "100",
        }

    pages = [{"output2": [row("20240105"), row("20240104")]}, {"output2": [row("20240103")]}]
    for page in pages:
        assert_kis_range_response_contract(page)
    return pages


@pytest.mark.asyncio
async def test_live_range_requires_captured_evidence():
    for provider in (YFinanceProvider(), KISProvider("test", "test")):
        assert provider.range_evidence_status == "STUB_ONLY"
        assert not provider.live_range_enabled
        with pytest.raises(RangeHistoryUnavailableError, match="raw range"):
            await provider.get_price_history_range(
                "TEST", start=date(2024, 1, 3), end=date(2024, 1, 5)
            )


@pytest.mark.asyncio
async def test_yfinance_inclusive_range_and_unknown_finality():
    def fetch(ticker, **kwargs):
        assert ticker == "AAPL"
        assert kwargs == {
            "start": date(2024, 1, 3),
            "end": date(2024, 1, 6),
            "interval": "1d",
            "auto_adjust": True,
        }
        return pd.DataFrame(
            {
                "Open": [10.0, 10.0],
                "High": [12.0, 12.0],
                "Low": [9.0, 9.0],
                "Close": [11.0, 11.0],
                "Volume": [0.0, 100.0],
            },
            index=pd.to_datetime(["2024-01-03", "2024-01-05"]),
        )

    raw = await YFinanceProvider(range_history_fetcher=fetch).get_price_history_range(
        "AAPL", start=date(2024, 1, 3), end=date(2024, 1, 5)
    )
    assert raw.frame.index.tolist() == [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05")]
    assert raw.frame["Volume"].tolist() == [0, 100]
    assert raw.provider == "yfinance"
    assert raw.adjustment_policy == "YFINANCE_AUTO_ADJUST_TRUE_1D"
    assert set(raw.finality.values()) == {HistoryFinality.UNKNOWN}
    assert raw.revision_if_known is None


@pytest.mark.asyncio
async def test_kis_pages_reach_requested_first_session_and_preserve_adjusted(kis_pages):
    requests = []

    async def fetch(params):
        requests.append(params)
        return kis_pages[len(requests) - 1]

    raw = await KISProvider("test", "test", range_page_fetcher=fetch).get_price_history_range(
        "005930", start=date(2024, 1, 3), end=date(2024, 1, 5)
    )
    assert [p["FID_INPUT_DATE_2"] for p in requests] == ["20240105", "20240103"]
    assert all(
        p["FID_INPUT_DATE_1"] == "20240103"
        and p["FID_ORG_ADJ_PRC"] == ADJUSTED
        and p["FID_PERIOD_DIV_CODE"] == "D"
        for p in requests
    )
    assert raw.coverage.reached_start
    assert raw.frame.index.tolist() == list(
        pd.to_datetime(["2024-01-03", "2024-01-04", "2024-01-05"])
    )
    assert raw.frame["Close"].tolist() == [11, 11, 11]
    assert raw.adjustment_policy == "KIS_FID_ORG_ADJ_PRC_0"


@pytest.mark.asyncio
async def test_kis_truncation_is_exposed(kis_pages, caplog):
    pages = iter([kis_pages[0], {"output2": []}])

    async def fetch(params):
        return next(pages)

    raw = await KISProvider("test", "test", range_page_fetcher=fetch).get_price_history_range(
        "005930", start=date(2024, 1, 3), end=date(2024, 1, 5)
    )
    assert not raw.coverage.reached_start
    assert "INCOMPLETE_PREFIX" in raw.coverage.reasons
    assert "truncated" in caplog.text


@pytest.mark.asyncio
async def test_kis_conflicting_overlap_is_error(kis_pages):
    second = {
        "output2": [dict(kis_pages[0]["output2"][1], stck_clpr="10"), kis_pages[1]["output2"][0]]
    }
    pages = iter([kis_pages[0], second])

    async def fetch(params):
        return next(pages)

    with pytest.raises(InputHistoryError, match="conflicting duplicate"):
        await KISProvider("test", "test", range_page_fetcher=fetch).get_price_history_range(
            "005930", start=date(2024, 1, 3), end=date(2024, 1, 5)
        )


@pytest.mark.asyncio
async def test_wrapper_normalizes_ticker_for_range(kis_pages):
    async def fetch(params):
        assert params["FID_INPUT_ISCD"] == "005930"
        return {"output2": kis_pages[0]["output2"] + kis_pages[1]["output2"]}

    wrapped = KISProviderWrapper(KISProvider("test", "test", range_page_fetcher=fetch))
    raw = await wrapped.get_price_history_range(
        "005930.KS", start=date(2024, 1, 3), end=date(2024, 1, 5)
    )
    assert len(raw.frame) == 3
    assert not wrapped.live_range_enabled


@pytest.mark.asyncio
async def test_kis_single_day_range(kis_pages):
    async def fetch(params):
        assert params["FID_INPUT_DATE_1"] == params["FID_INPUT_DATE_2"] == "20240105"
        return {"output2": kis_pages[0]["output2"][:1]}

    raw = await KISProvider("test", "test", range_page_fetcher=fetch).get_price_history_range(
        "005930", start=date(2024, 1, 5), end=date(2024, 1, 5)
    )
    assert len(raw.frame) == 1
    assert raw.coverage.reached_start


@pytest.mark.asyncio
async def test_kis_missing_value_remains_nan_instead_of_zero(kis_pages):
    item = dict(kis_pages[0]["output2"][0])
    item.pop("stck_clpr")
    item["acml_vol"] = ""

    async def fetch(params):
        return {"output2": [item]}

    raw = await KISProvider("test", "test", range_page_fetcher=fetch).get_price_history_range(
        "005930", start=date(2024, 1, 5), end=date(2024, 1, 5)
    )
    assert pd.isna(raw.frame.iloc[0]["Close"])
    assert pd.isna(raw.frame.iloc[0]["Volume"])
    assert raw.coverage.missing_fields[date(2024, 1, 5)] == ("Close", "Volume")
    assert not raw.coverage.complete


@pytest.mark.asyncio
async def test_yfinance_range_cannot_claim_verified_finality():
    def fetch(ticker, **kwargs):
        return pd.DataFrame(
            {"Open": [10.0], "High": [12.0], "Low": [9.0], "Close": [11.0], "Volume": [0.0]},
            index=pd.to_datetime(["2024-01-05"]),
        )

    raw = await YFinanceProvider(range_history_fetcher=fetch).get_price_history_range(
        "AAPL", start=date(2024, 1, 5), end=date(2024, 1, 5)
    )
    assert raw.coverage.unknown_finality_sessions == (date(2024, 1, 5),)
    assert not raw.coverage.complete


@pytest.mark.asyncio
async def test_empty_yfinance_response_is_incomplete_without_inventing_sessions():
    from src.tools.technical.chart_analysis.input import ExchangeSessionCalendar, prepare_history

    def fetch(ticker, **kwargs):
        return pd.DataFrame()

    raw = await YFinanceProvider(range_history_fetcher=fetch).get_price_history_range(
        "AAPL", start=date(2024, 1, 3), end=date(2024, 1, 5)
    )
    assert not raw.coverage.reached_start
    assert not raw.coverage.complete
    assert "INCOMPLETE_PREFIX" in raw.coverage.reasons
    assert "EMPTY_RESPONSE" in raw.coverage.reasons
    assert raw.coverage.no_session_basis is None
    with pytest.raises(InputHistoryError, match="no returned daily bar"):
        prepare_history(
            raw,
            as_of=date(2024, 1, 5),
            calendar=ExchangeSessionCalendar("XNYS", "America/New_York"),
            listing_first_session=date(2024, 1, 3),
        )


@pytest.mark.asyncio
async def test_kis_no_sessions_has_calendar_evidence_instead_of_empty_response():
    async def fetch(params):
        raise AssertionError("verified weekend must not request provider data")

    raw = await KISProvider("test", "test", range_page_fetcher=fetch).get_price_history_range(
        "005930", start=date(2024, 1, 6), end=date(2024, 1, 7)
    )
    assert raw.frame.empty
    assert raw.coverage.reached_start
    assert raw.coverage.complete
    assert "XKRX" in raw.coverage.no_session_basis
    assert "Asia/Seoul" in raw.coverage.no_session_basis
    assert "exchange_calendars:" in raw.coverage.no_session_basis
    assert "EMPTY_RESPONSE" not in raw.coverage.reasons
