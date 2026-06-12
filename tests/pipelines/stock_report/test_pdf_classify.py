from __future__ import annotations

from src.pipelines.stock_report import pdf_classify
from src.pipelines.stock_report.pdf_classify import (
    PdfClassificationLLMOutput,
    _fallback_overlay,
    _normalize_category,
    _normalize_theme,
    classify_document,
)
from src.pipelines.stock_report.pdf_parser import ParsedDocument
from src.pipelines.stock_report.taxonomy import (
    CategoryNode,
    TaxonomyRegistry,
    ThemeNode,
    build_match_dictionary,
)


def _taxonomy() -> TaxonomyRegistry:
    return TaxonomyRegistry(
        categories=[
            CategoryNode(
                key="반도체",
                aliases=["semiconductor", "메모리"],
                themes=[ThemeNode(key="HBM", aliases=["고대역폭메모리"])],
            ),
            CategoryNode(
                key="이차전지",
                aliases=["배터리"],
                themes=[ThemeNode(key="양극재", aliases=["cathode"])],
            ),
            CategoryNode(key="매크로/정책", aliases=["매크로"], themes=[]),
        ]
    )


def _parsed(markdown: str) -> ParsedDocument:
    return ParsedDocument(
        source_path="data/files/2026-06-09/x.pdf",
        markdown=markdown,
        page_count=2,
        text_char_count=len(markdown),
        image_ref_count=0,
        parse_mode="local",
        json_blocks=None,
        warnings=[],
    )


# --- 정규화 -------------------------------------------------------------------


def test_normalize_category_maps_key_and_alias_case_insensitive() -> None:
    category_map, _ = build_match_dictionary(_taxonomy())
    assert _normalize_category("반도체", category_map) == "반도체"
    assert _normalize_category("메모리", category_map) == "반도체"  # alias
    assert _normalize_category("SEMICONDUCTOR", category_map) == "반도체"  # 대소문자 무시
    assert _normalize_category("없는카테고리", category_map) is None
    assert _normalize_category(None, category_map) is None


def test_normalize_theme_requires_category_consistency() -> None:
    _, theme_map = build_match_dictionary(_taxonomy())
    # HBM은 반도체 소속 → 반도체 category와 일치하면 통과
    assert _normalize_theme("HBM", theme_map, "반도체") == "HBM"
    # 양극재는 이차전지 소속 → 반도체 category와 불일치 → 버린다
    assert _normalize_theme("양극재", theme_map, "반도체") is None
    assert _normalize_theme("없는테마", theme_map, "반도체") is None
    assert _normalize_theme(None, theme_map, "반도체") is None


# --- fallback overlay ---------------------------------------------------------


def test_fallback_overlay_picks_most_mentioned_category_and_theme() -> None:
    body = "이 리포트는 HBM 메모리 반도체 업황을 다룬다. 메모리 가격 반등이 핵심이다."
    category, theme = _fallback_overlay("반도체 업데이트", body, _taxonomy())
    assert category == "반도체"
    assert theme == "HBM"


def test_fallback_overlay_returns_none_when_no_alias_hit() -> None:
    category, theme = _fallback_overlay("제목", "관련 키워드가 전혀 없는 본문이다.", _taxonomy())
    assert category is None
    assert theme is None


# --- classify_document (LLM mock) --------------------------------------------


def test_classify_document_uses_llm_result_normalized(monkeypatch) -> None:
    async def fake_async(title, body, taxonomy, provider):
        return PdfClassificationLLMOutput(category_key="이차전지", main_theme="양극재")

    monkeypatch.setattr(pdf_classify, "_classify_async", fake_async)

    category, theme = classify_document(
        _parsed("배터리 양극재 리포트 본문이다."),
        title="배터리",
        taxonomy=_taxonomy(),
        provider="openai",
    )
    assert category == "이차전지"
    assert theme == "양극재"


def test_classify_document_falls_back_on_llm_failure(monkeypatch) -> None:
    async def boom(title, body, taxonomy, provider):
        raise RuntimeError("llm down")

    monkeypatch.setattr(pdf_classify, "_classify_async", boom)

    # 본문에 반도체/HBM 키워드 → LLM 실패해도 fallback overlay가 잡아야 한다.
    category, theme = classify_document(
        _parsed("HBM 메모리 반도체 업황 리포트"),
        title="반도체",
        taxonomy=_taxonomy(),
        provider="openai",
    )
    assert category == "반도체"
    assert theme == "HBM"


def test_classify_document_out_of_taxonomy_value_falls_back(monkeypatch) -> None:
    async def weird(title, body, taxonomy, provider):
        return PdfClassificationLLMOutput(category_key="존재하지않는카테고리", main_theme=None)

    monkeypatch.setattr(pdf_classify, "_classify_async", weird)

    # LLM이 taxonomy 밖 값 → 정규화 None → fallback overlay(배터리/양극재)로 보강.
    category, theme = classify_document(
        _parsed("배터리 양극재 cathode 리포트"),
        title="배터리",
        taxonomy=_taxonomy(),
        provider="openai",
    )
    assert category == "이차전지"
    assert theme == "양극재"


def test_classify_document_empty_body_returns_none() -> None:
    category, theme = classify_document(
        _parsed("   \n\n  "),
        title="제목",
        taxonomy=_taxonomy(),
        provider="openai",
    )
    assert category is None
    assert theme is None
