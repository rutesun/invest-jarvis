"""공개 종목 검색 응답으로 이름과 코드를 검증한다."""

import re
from dataclasses import dataclass, field, replace
from typing import Literal

import httpx


_ENDPOINT = "https://ac.stock.naver.com/ac"
_MARKETS = {"KOR": {"KOSPI", "KOSDAQ", "KONEX"}, "USA": {"NASDAQ", "NYSE", "AMEX"}}
_SUFFIX_MARKETS = {".KS": "KOSPI", ".KQ": "KOSDAQ"}


@dataclass(frozen=True)
class StockIdentity:
    code: str
    name: str
    market: str
    nation: str
    kind: str = "unknown"

    @property
    def identity(self) -> str:
        return f"{self.nation}:{self.market}:{self.code}"

    @property
    def label(self) -> str:
        return self.name if self.nation == "KOR" else self.code


@dataclass(frozen=True)
class SearchResult:
    status: Literal["resolved", "not_found", "ambiguous"]
    stock: StockIdentity | None = None
    candidates: list[StockIdentity] = field(default_factory=list)
    match_kind: Literal["exact", "name_token", "partial"] = "exact"


class StockSearchError(RuntimeError):
    """검색 장애와 형식 오류. 검색어와 응답 본문을 노출하지 않는다."""


def _normalized(value: str) -> str:
    return re.sub(r"[\s_]+", "", value).casefold()


def _validate_response(payload: object) -> list[StockIdentity]:
    if not isinstance(payload, dict) or not isinstance(payload.get("query"), str):
        raise StockSearchError("종목 검색 응답 형식이 변경되었습니다.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise StockSearchError("종목 검색 응답 형식이 변경되었습니다.")
    stocks = []
    for item in items:
        fields = ("code", "name", "typeCode")
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip() for key in fields
        ):
            raise StockSearchError("종목 검색 응답 항목 형식이 변경되었습니다.")
        # Some public candidates have an explicitly unknown country; never infer it from market.
        if "nationCode" not in item or (
            item["nationCode"] is not None
            and (not isinstance(item["nationCode"], str) or not item["nationCode"].strip())
        ):
            raise StockSearchError("종목 검색 응답 항목 형식이 변경되었습니다.")
        nation = item["nationCode"] if item["nationCode"] is not None else "UNKNOWN"
        stock = StockIdentity(item["code"], item["name"], item["typeCode"], nation)
        if stock not in stocks:
            stocks.append(stock)
    return stocks


def _supported(stock: StockIdentity) -> bool:
    return stock.market in _MARKETS.get(stock.nation, set())


def _match(query: str, candidates: list[StockIdentity], market: str | None) -> SearchResult:
    if not candidates:
        return SearchResult("not_found")
    supported = [s for s in candidates if _supported(s) and (market is None or s.market == market)]
    normalized = _normalized(query)
    exact = [s for s in supported if normalized in (_normalized(s.code), _normalized(s.name))]
    if len(exact) == 1:
        return SearchResult("resolved", exact[0], candidates)
    if exact:
        return SearchResult("ambiguous", candidates=candidates)
    if query.isdigit():
        return SearchResult("ambiguous", candidates=candidates)
    # English company aliases must be complete name tokens, never arbitrary substrings.
    if re.fullmatch(r"[a-zA-Z0-9.\-]+", query):
        tokens = [
            s
            for s in supported
            if re.search(
                rf"(?<![a-zA-Z0-9]){re.escape(query)}(?![a-zA-Z0-9])", s.name, re.IGNORECASE
            )
        ]
        if len(tokens) == 1:
            return SearchResult("resolved", tokens[0], candidates, match_kind="name_token")
        return SearchResult("ambiguous", candidates=candidates)
    partial = [s for s in supported if normalized in _normalized(s.name)]
    if len(partial) == 1:
        return SearchResult("resolved", partial[0], candidates, match_kind="partial")
    if partial:
        shortest = min(partial, key=lambda s: len(_normalized(s.name)))
        core = _normalized(shortest.name)
        if all(core in _normalized(s.name) for s in partial):
            return SearchResult("resolved", shortest, candidates, match_kind="partial")
    return SearchResult("ambiguous", candidates=candidates)


class StockSearch:
    """검색 전용 클라이언트. HTTP 장애를 미검색 결과로 바꾸지 않는다."""

    def __init__(self, *, transport: httpx.BaseTransport | None = None, timeout: float = 15):
        self._client = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)

    def __enter__(self) -> "StockSearch":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def search(self, query: str) -> SearchResult:
        query = re.sub(r"\s+", " ", query.replace("_", " ")).strip()
        if not query:
            raise StockSearchError("종목 검색어가 비어 있습니다.")
        market = None
        suffix = query[-3:].upper()
        if suffix in _SUFFIX_MARKETS:
            market = _SUFFIX_MARKETS[suffix]
            query = query[:-3]
        try:
            response = self._client.get(_ENDPOINT, params={"q": query, "target": "stock"})
            response.raise_for_status()
        except httpx.HTTPError:
            raise StockSearchError("종목 검색 API 요청에 실패했습니다.") from None
        try:
            payload = response.json()
        except ValueError:
            raise StockSearchError("종목 검색 응답이 JSON 형식이 아닙니다.") from None
        result = _match(query, _validate_response(payload), market)
        if result.stock and result.stock.nation == "KOR" and result.match_kind == "partial":
            stock = self._product_kind(result.stock)
            return replace(
                result,
                stock=stock,
                candidates=[
                    stock if candidate.identity == stock.identity else candidate
                    for candidate in result.candidates
                ],
            )
        return result

    def _product_kind(self, stock: StockIdentity) -> StockIdentity:
        try:
            response = self._client.get(f"https://m.stock.naver.com/api/stock/{stock.code}/basic")
            response.raise_for_status()
        except httpx.HTTPError:
            raise StockSearchError("종목 종류 확인 API 요청에 실패했습니다.") from None
        try:
            payload = response.json()
        except ValueError:
            raise StockSearchError("종목 종류 응답이 JSON 형식이 아닙니다.") from None
        if not isinstance(payload, dict):
            raise StockSearchError("종목 종류 응답 형식이 변경되었습니다.")
        exchange = payload.get("stockExchangeType")
        if (
            payload.get("itemCode") != stock.code
            or _normalized(str(payload.get("stockName", ""))) != _normalized(stock.name)
            or not isinstance(payload.get("stockEndType"), str)
            or not payload["stockEndType"]
            or not isinstance(exchange, dict)
            or exchange.get("name") != stock.market
            or exchange.get("nationCode") != stock.nation
        ):
            raise StockSearchError("종목 종류 응답의 identity 또는 형식이 변경되었습니다.")
        kind = {"stock": "equity", "etf": "etf", "etn": "etn"}.get(
            payload["stockEndType"], "unknown"
        )
        return replace(stock, kind=kind)
