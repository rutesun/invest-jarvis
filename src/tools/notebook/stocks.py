"""Resolve source metadata with recorded search evidence, never a company whitelist."""

import re
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

from src.providers.stock_search import StockSearchError


PROVIDER = "naver-stock-search"
CACHE_VERSION = 2
CACHE_DAYS = 30


def _fresh(record, now, allow_expired=False):
    try:
        checked = datetime.fromisoformat(record["checked_at"])
        return timedelta(0) <= now - checked and (
            allow_expired or now - checked < timedelta(days=CACHE_DAYS)
        )
    except (KeyError, TypeError, ValueError):
        return False


def _result(record):
    if not isinstance(record, dict):
        raise StockSearchError("종목 검색 cache 항목 형식이 잘못되었습니다.")
    result = record.get("result", {})
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("status"), str)
        or result["status"] not in {"resolved", "not_found", "ambiguous"}
    ):
        raise StockSearchError("종목 검색 cache 형식이 변경되었습니다. 새 미리보기가 필요합니다.")
    if not isinstance(result.get("match_kind"), str) or result["match_kind"] not in {
        "exact",
        "name_token",
        "partial",
    }:
        raise StockSearchError("종목 검색 cache의 매칭 근거가 잘못되었습니다.")
    if result["status"] == "resolved":
        stock = result.get("stock")
        if not isinstance(stock, dict) or any(
            not isinstance(stock.get(k), str) or not stock[k]
            for k in ("code", "name", "market", "nation", "kind")
        ):
            raise StockSearchError("종목 검색 cache의 종목 정보가 잘못되었습니다.")
    return result


def resolve_stock_entries(
    entries, cache, *, search=None, now=None, on_cache_update=None, allow_expired=False
):
    """Search unique metadata queries, or reproduce fresh evidence without network.

    A short uppercase tag can mean a theme (HBM) even when it is also a real
    ticker. Keep it as a theme for review; an explicit stock field is unambiguous.
    The returned cache is saved by the CLI outside the read-only source directory.
    """
    now = now or datetime.now(UTC)
    if not isinstance(cache, dict):
        raise StockSearchError("종목 검색 cache 형식이 잘못되었습니다.")
    if cache and (cache.get("version") != CACHE_VERSION or cache.get("provider") != PROVIDER):
        raise StockSearchError("종목 검색 cache 버전이 다릅니다. 새 경로를 사용하세요.")
    if not isinstance(cache.get("queries", {}), dict):
        raise StockSearchError("종목 검색 cache 목록 형식이 잘못되었습니다.")
    stored = dict(cache.get("queries", {}))
    queries = sorted({q for e in entries for q in [*e.stocks, *e.themes]})
    used = {}
    for query in queries:
        record = stored.get(query, {})
        if query in stored:
            _result(record)
        if not _fresh(record, now, allow_expired):
            if search is None:
                used[query] = None
                continue
            record = {"checked_at": now.isoformat(), "result": asdict(search(query))}
            stored[query] = record
            if on_cache_update is not None:
                on_cache_update(
                    {"version": CACHE_VERSION, "provider": PROVIDER, "queries": dict(stored)}
                )
        _result(record)
        used[query] = record
    resolved, issues, blockers = [], [], set()
    labels = {}
    for entry in entries:
        stocks, themes = [], []
        for query, explicit in [
            *((q, True) for q in entry.stocks),
            *((q, False) for q in entry.themes),
        ]:
            record = used[query]
            result = _result(record) if record else {"status": "missing"}
            reason = result["status"].upper()
            if result["status"] == "resolved":
                stock = result["stock"]
                if (
                    not explicit
                    and query not in entry.stocks
                    and re.fullmatch(r"[A-Za-z]{1,3}", query)
                ):
                    reason = "TAG_TICKER_COLLISION"
                elif (
                    not explicit
                    and query not in entry.stocks
                    and result.get("match_kind") == "partial"
                    and stock.get("kind") != "equity"
                ):
                    reason = "PARTIAL_TAG_MATCH"
                else:
                    label = stock["name"] if stock["nation"] == "KOR" else stock["code"]
                    identity = (stock["nation"], stock["market"], stock["code"])
                    if label in labels and labels[label] != identity:
                        blockers.add("STOCK_LABEL_CONFLICT")
                    labels[label] = identity
                    stocks.append(label)
                    continue
            if not explicit:
                themes.append(query)
            if reason != "NOT_FOUND" or explicit:
                issues.append(
                    {"key": entry.key, "query": query, "reason": reason, "explicit": explicit}
                )
            if explicit:
                blockers.add("UNRESOLVED_EXPLICIT_STOCK")
            if result["status"] == "missing":
                blockers.add("STOCK_SEARCH_INCOMPLETE")
        resolved.append(
            replace(entry, stocks=list(dict.fromkeys(stocks)), themes=list(dict.fromkeys(themes)))
        )
    evidence = {
        "version": CACHE_VERSION,
        "provider": PROVIDER,
        "queries": {q: v for q, v in used.items() if v},
    }
    report = {**evidence, "issues": issues, "blockers": sorted(blockers)}
    updated = {"version": CACHE_VERSION, "provider": PROVIDER, "queries": stored}
    return resolved, report, updated
