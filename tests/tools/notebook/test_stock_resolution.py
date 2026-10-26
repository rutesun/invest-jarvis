from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest

from src.providers.stock_search import SearchResult, StockIdentity, StockSearchError
from src.tools.notebook.models import NotebookEntry
from src.tools.notebook.stocks import resolve_stock_entries


NOW = datetime(2026, 10, 22, tzinfo=UTC)


def entry(stocks=None, themes=None):
    return NotebookEntry(
        "research",
        "2026-10-22",
        "note",
        "original body",
        "source",
        stocks=stocks or [],
        themes=themes or [],
    )


def cached(results, checked_at=NOW):
    return {
        "version": 2,
        "provider": "naver-stock-search",
        "queries": {
            q: {"checked_at": checked_at.isoformat(), "result": asdict(r)}
            for q, r in results.items()
        },
    }


def test_search_results_not_hardcoded_names_unify_code_and_alias():
    stock = StockIdentity("123456", "새상장회사", "KOSDAQ", "KOR")
    calls = []

    def search(query):
        calls.append(query)
        return SearchResult("resolved", stock)

    original = entry(themes=["새상장회사", "123456", "123456.KQ"])
    [resolved], report, cache = resolve_stock_entries([original], {}, search=search, now=NOW)
    assert resolved.stocks == ["새상장회사"]
    assert resolved.themes == []
    assert resolved.body_markdown == original.body_markdown
    assert resolved.key == original.key
    assert original.stocks == []
    assert len(calls) == 3
    assert report["blockers"] == []
    assert cache["queries"]["123456"]["result"]["stock"]["market"] == "KOSDAQ"


def test_fresh_cache_reproduces_resolution_without_network():
    stock = StockIdentity("005930", "삼성전자", "KOSPI", "KOR")
    cache = cached({"삼성전자": SearchResult("resolved", stock)})
    [resolved], report, _ = resolve_stock_entries([entry(themes=["삼성전자"])], cache, now=NOW)
    assert resolved.stocks == ["삼성전자"]
    assert report["blockers"] == []


def test_theme_ticker_collision_is_reviewed_while_explicit_stock_is_resolved():
    stock = StockIdentity("HBM", "허드베이 미네랄스", "NYSE", "USA")
    cache = cached({"HBM": SearchResult("resolved", stock)})
    entries, report, _ = resolve_stock_entries(
        [entry(themes=["HBM"]), entry(stocks=["HBM"])], cache, now=NOW
    )
    assert entries[0].stocks == []
    assert entries[0].themes == ["HBM"]
    assert entries[1].stocks == ["HBM"]
    assert any(i["reason"] == "TAG_TICKER_COLLISION" for i in report["issues"])


def test_ambiguous_tag_is_preserved_and_explicit_stock_blocks_apply():
    cache = cached({"삼성": SearchResult("ambiguous")})
    entries, report, _ = resolve_stock_entries(
        [entry(stocks=["삼성"], themes=["삼성"])], cache, now=NOW
    )
    assert entries[0].stocks == []
    assert entries[0].themes == ["삼성"]
    assert "UNRESOLVED_EXPLICIT_STOCK" in report["blockers"]


def test_offline_expired_cache_is_not_used_as_confirmed_stock():
    stock = StockIdentity("005930", "삼성전자", "KOSPI", "KOR")
    cache = cached({"삼성전자": SearchResult("resolved", stock)}, NOW - timedelta(days=31))
    [resolved], report, _ = resolve_stock_entries([entry(themes=["삼성전자"])], cache, now=NOW)
    assert resolved.stocks == []
    assert resolved.themes == ["삼성전자"]
    assert "STOCK_SEARCH_INCOMPLETE" in report["blockers"]


def test_search_outage_is_not_cached_as_not_found():
    def broken(query):
        raise StockSearchError("search unavailable")

    with pytest.raises(StockSearchError):
        resolve_stock_entries([entry(themes=["삼성전자"])], {}, search=broken, now=NOW)


def test_api_not_found_tag_remains_theme_and_queries_are_deduplicated():
    calls = []

    def search(query):
        calls.append(query)
        return SearchResult("not_found")

    entries, report, _ = resolve_stock_entries(
        [entry(themes=["반도체"]), entry(themes=["반도체"])], {}, search=search, now=NOW
    )
    assert calls == ["반도체"]
    assert all(e.themes == ["반도체"] for e in entries)
    assert report["blockers"] == []


def test_label_collisions_between_distinct_securities_block_apply():
    cache = cached(
        {
            "a": SearchResult("resolved", StockIdentity("123456", "동일이름", "KOSPI", "KOR")),
            "b": SearchResult("resolved", StockIdentity("123457", "동일이름", "KOSDAQ", "KOR")),
        }
    )
    _, report, _ = resolve_stock_entries([entry(stocks=["a", "b"])], cache, now=NOW)
    assert "STOCK_LABEL_CONFLICT" in report["blockers"]


def test_search_progress_can_be_saved_before_a_later_outage():
    saved = []

    def search(query):
        if query == "b":
            raise StockSearchError("outage")
        return SearchResult("not_found")

    with pytest.raises(StockSearchError):
        resolve_stock_entries(
            [entry(themes=["a", "b"])], {}, search=search, now=NOW, on_cache_update=saved.append
        )
    assert len(saved) == 1
    assert set(saved[0]["queries"]) == {"a"}


def test_explicit_stock_is_not_duplicated_as_a_theme_collision():
    stock = StockIdentity("HBM", "허드베이 미네랄스", "NYSE", "USA")
    cache = cached({"HBM": SearchResult("resolved", stock)})
    [resolved], report, _ = resolve_stock_entries(
        [entry(stocks=["HBM"], themes=["HBM"])], cache, now=NOW
    )
    assert resolved.stocks == ["HBM"]
    assert resolved.themes == []
    assert report["issues"] == []


@pytest.mark.parametrize("tag", ["hbm", "ai", "Ai"])
def test_short_theme_collision_is_case_insensitive(tag):
    stock = StockIdentity(tag.upper(), "public security", "NYSE", "USA")
    [resolved], report, _ = resolve_stock_entries(
        [entry(themes=[tag])], cached({tag: SearchResult("resolved", stock)}), now=NOW
    )
    assert resolved.stocks == []
    assert resolved.themes == [tag]
    assert report["issues"][0]["reason"] == "TAG_TICKER_COLLISION"


def test_resume_can_replay_expired_frozen_evidence_without_search():
    stock = StockIdentity("005930", "삼성전자", "KOSPI", "KOR")
    evidence = cached({"삼성전자": SearchResult("resolved", stock)}, NOW - timedelta(days=90))
    [resolved], report, _ = resolve_stock_entries(
        [entry(themes=["삼성전자"])], evidence, now=NOW, allow_expired=True
    )
    assert resolved.stocks == ["삼성전자"]
    assert report["blockers"] == []


def test_partial_theme_match_to_etf_requires_review():
    stock = StockIdentity("091160", "KODEX 반도체", "KOSPI", "KOR", kind="etf")
    cache = cached({"반도체": SearchResult("resolved", stock, match_kind="partial")})
    [resolved], report, _ = resolve_stock_entries([entry(themes=["반도체"])], cache, now=NOW)
    assert resolved.stocks == []
    assert resolved.themes == ["반도체"]
    assert report["issues"][0]["reason"] == "PARTIAL_TAG_MATCH"


def test_partial_company_alias_uses_verified_equity_evidence():
    stock = StockIdentity("000660", "SK하이닉스", "KOSPI", "KOR", kind="equity")
    cache = cached({"하이닉스": SearchResult("resolved", stock, match_kind="partial")})
    [resolved], report, _ = resolve_stock_entries([entry(themes=["하이닉스"])], cache, now=NOW)
    assert resolved.stocks == ["SK하이닉스"]
    assert report["issues"] == []


@pytest.mark.parametrize("corrupt", ["queries", "record", "result", "status", "match_kind"])
def test_malformed_cache_fails_safely(corrupt):
    cache = cached(
        {"삼성전자": SearchResult("resolved", StockIdentity("005930", "삼성전자", "KOSPI", "KOR"))}
    )
    if corrupt == "queries":
        cache["queries"] = 42
    elif corrupt == "record":
        cache["queries"]["삼성전자"] = []
    elif corrupt == "result":
        cache["queries"]["삼성전자"]["result"] = []
    elif corrupt == "status":
        cache["queries"]["삼성전자"]["result"]["status"] = []
    else:
        del cache["queries"]["삼성전자"]["result"]["match_kind"]
    with pytest.raises(StockSearchError):
        resolve_stock_entries([entry(themes=["삼성전자"])], cache, now=NOW)
