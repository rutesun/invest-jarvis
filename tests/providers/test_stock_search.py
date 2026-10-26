"""네이버 공개 검색 raw 응답부터 종목 identity까지 고정한다."""

import json
from pathlib import Path

import httpx
import pytest

from src.providers.stock_search import StockSearch, StockSearchError


FIXTURES = Path(__file__).parents[1] / "fixtures" / "notebook_notion"
REQUIRED = ("code", "name", "typeCode")


@pytest.fixture
def raw_response():
    def load(slug):
        data = json.loads((FIXTURES / f"stock-search-{slug}.json").read_text())
        # Boundary contract: captured public responses must preserve provider assumptions.
        assert isinstance(data["query"], str)
        assert isinstance(data["items"], list)
        for item in data["items"]:
            for field in REQUIRED:
                assert isinstance(item[field], str) and item[field]
            assert "nationCode" in item
            assert item["nationCode"] is None or (
                isinstance(item["nationCode"], str) and item["nationCode"]
            )
        return data

    return load


def search(payload, query):
    def handler(request):
        if request.url.host == "m.stock.naver.com":
            code = request.url.path.split("/")[-2]
            basic = json.loads((FIXTURES / f"stock-search-basic-{code}.json").read_text())
            return httpx.Response(200, json=basic)
        return httpx.Response(200, json=payload)

    with StockSearch(transport=httpx.MockTransport(handler)) as client:
        return client.search(query)


@pytest.mark.parametrize(
    ("slug", "query", "identity", "label"),
    [
        ("samsung", "삼성전자", "KOR:KOSPI:005930", "삼성전자"),
        ("samsung-code", "005930", "KOR:KOSPI:005930", "삼성전자"),
        ("samsung-code", "005930.KS", "KOR:KOSPI:005930", "삼성전자"),
        ("hynix", "하이닉스", "KOR:KOSPI:000660", "SK하이닉스"),
        ("nvidia", "nvda", "USA:NASDAQ:NVDA", "NVDA"),
        ("kosdaq", "247540.KQ", "KOR:KOSDAQ:247540", "에코프로비엠"),
        ("etf", "KODEX_반도체", "KOR:KOSPI:091160", "KODEX 반도체"),
        ("tsmc", "TSMC", "USA:NYSE:TSM", "TSM"),
    ],
)
def test_golden_resolves_verified_identity(raw_response, slug, query, identity, label):
    result = search(raw_response(slug), query)
    assert result.status == "resolved"
    assert result.stock.identity == identity
    assert result.stock.label == label


@pytest.mark.parametrize(("slug", "query"), [("samsung-broad", "삼성"), ("kosdaq", "247540.KS")])
def test_does_not_guess_ambiguous_or_wrong_market(raw_response, slug, query):
    result = search(raw_response(slug), query)
    assert result.status == "ambiguous"
    assert result.stock is None
    assert result.candidates


def test_valid_empty_response_is_not_found(raw_response):
    assert search(raw_response("missing"), "nothing").status == "not_found"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": []},
        {"query": "x", "items": {}},
        {"query": "x", "items": [{}]},
        {
            "query": "x",
            "items": [{"code": 123, "name": "x", "typeCode": "KOSPI", "nationCode": "KOR"}],
        },
    ],
)
def test_malformed_responses_raise_safe_error(payload):
    with pytest.raises(StockSearchError, match="응답"):
        search(payload, "secret-free")


def test_unknown_market_is_review_candidate_not_not_found(raw_response):
    payload = raw_response("samsung-code")
    payload["items"][0]["typeCode"] = "NEW_MARKET"
    result = search(payload, "005930")
    assert result.status == "ambiguous"
    assert result.stock is None


def test_http_error_is_not_no_results():
    with (
        StockSearch(
            transport=httpx.MockTransport(lambda _: httpx.Response(503, text="private body"))
        ) as client,
        pytest.raises(StockSearchError) as error,
    ):
        client.search("private query")
    assert "private" not in str(error.value)


def test_transport_error_is_not_no_results():
    def fail(request):
        raise httpx.ConnectError("private details", request=request)

    with (
        StockSearch(transport=httpx.MockTransport(fail)) as client,
        pytest.raises(StockSearchError) as error,
    ):
        client.search("private query")
    assert "private" not in str(error.value)


def test_request_uses_normalized_query_and_stock_target(raw_response):
    def handler(request):
        assert request.url.params["q"] == "KODEX 반도체"
        assert request.url.params["target"] == "stock"
        return httpx.Response(200, json=raw_response("etf"))

    with StockSearch(transport=httpx.MockTransport(handler)) as client:
        assert client.search("KODEX_반도체").stock.code == "091160"


def test_alphabetic_substring_does_not_match_arbitrary_name():
    payload = {
        "query": "AI",
        "items": [{"code": "ABNB", "name": "Airbnb", "typeCode": "NASDAQ", "nationCode": "USA"}],
    }
    assert search(payload, "AI").status == "ambiguous"


def test_numeric_query_does_not_use_name_tokens():
    payload = {
        "query": "123456",
        "items": [
            {"code": "999999", "name": "ETF 123456", "typeCode": "KOSPI", "nationCode": "KOR"}
        ],
    }
    assert search(payload, "123456").status == "ambiguous"


def test_same_ticker_on_two_markets_requires_review():
    payload = {
        "query": "ABC",
        "items": [
            {"code": "ABC", "name": "ABC One", "typeCode": "NASDAQ", "nationCode": "USA"},
            {"code": "ABC", "name": "ABC Two", "typeCode": "NYSE", "nationCode": "USA"},
        ],
    }
    assert search(payload, "ABC").status == "ambiguous"


def test_unknown_nation_is_not_not_found(raw_response):
    payload = raw_response("samsung-code")
    payload["items"][0]["nationCode"] = "UNKNOWN"
    assert search(payload, "005930").status == "ambiguous"


def test_golden_nullable_country_preserves_exact_known_match(raw_response):
    result = search(raw_response("null-country"), "파마리서치")
    assert result.status == "resolved"
    assert result.stock.identity == "KOR:KOSDAQ:214450"
    assert [candidate.identity for candidate in result.candidates] == [
        "KOR:KOSDAQ:214450",
        "UNKNOWN:KONEX:217950",
    ]


def test_nullable_country_alone_requires_review(raw_response):
    payload = raw_response("null-country")
    payload["items"] = payload["items"][1:]
    result = search(payload, "파마리서치바이오")
    assert result.status == "ambiguous"
    assert result.stock is None
    assert result.candidates[0].identity == "UNKNOWN:KONEX:217950"


@pytest.mark.parametrize("nation", ["", " ", 123, [], {}])
def test_invalid_country_type_remains_schema_error(raw_response, nation):
    payload = raw_response("samsung-code")
    payload["items"][0]["nationCode"] = nation
    with pytest.raises(StockSearchError, match="응답"):
        search(payload, "005930")


def test_missing_country_remains_schema_error(raw_response):
    payload = raw_response("samsung-code")
    del payload["items"][0]["nationCode"]
    with pytest.raises(StockSearchError, match="응답"):
        search(payload, "005930")


def test_html_response_is_safe_schema_error():
    with (
        StockSearch(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, text="<html>private</html>")
            )
        ) as client,
        pytest.raises(StockSearchError, match="JSON") as error,
    ):
        client.search("private query")
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    ("slug", "query", "match_kind"),
    [
        ("samsung", "삼성전자", "exact"),
        ("tsmc", "TSMC", "name_token"),
        ("hynix", "하이닉스", "partial"),
    ],
)
def test_match_evidence_is_explicit(raw_response, slug, query, match_kind):
    assert search(raw_response(slug), query).match_kind == match_kind


@pytest.mark.parametrize(
    ("code", "query", "kind"),
    [
        ("000660", "하이닉스", "equity"),
        ("487240", "AI전력핵심설비", "etf"),
    ],
)
def test_partial_match_uses_basic_product_evidence(code, query, kind):
    basic = json.loads((FIXTURES / f"stock-search-basic-{code}.json").read_text())
    # Boundary contract on captured basic API response.
    assert basic["itemCode"] == code
    assert isinstance(basic["stockEndType"], str)
    assert basic["stockExchangeType"]["name"] == "KOSPI"
    assert basic["stockExchangeType"]["nationCode"] == "KOR"
    payload = {
        "query": query,
        "items": [
            {"code": code, "name": basic["stockName"], "typeCode": "KOSPI", "nationCode": "KOR"}
        ],
    }
    result = search(payload, query)
    assert result.stock.kind == kind
    assert result.match_kind == "partial"


def test_malformed_basic_identity_raises(raw_response):
    def handler(request):
        if request.url.host == "m.stock.naver.com":
            return httpx.Response(200, json={"stockEndType": "stock", "itemCode": "wrong"})
        return httpx.Response(200, json=raw_response("hynix"))

    with (
        StockSearch(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(StockSearchError, match="종류"),
    ):
        client.search("하이닉스")
