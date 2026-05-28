from __future__ import annotations

from datetime import date

from src.pipelines.stock_report.retrieval import CategoryBucket, SameDayBundle, SameDayChunk
from src.pipelines.stock_report.synthesize import (
    LocalEvidenceSynthesisOutput,
    SynthesisCategoryCardOutput,
    SynthesisCoreThemeOutput,
    SynthesisFocusTickerOutput,
    SynthesisPulseItemOutput,
    synthesize_same_day_bundle,
)


def _chunk(
    chunk_id: int,
    *,
    category_key: str = "반도체",
    main_theme: str | None = "HBM",
    ticker_tags: list[str] | None = None,
    canonical_summary: str | None = None,
) -> SameDayChunk:
    return SameDayChunk(
        id=chunk_id,
        source_type="telegram_unit_v2",
        source_pk=chunk_id,
        source_message_db_id=chunk_id,
        source_date=date(2026, 5, 26),
        channel_key="kwusa",
        channel_name="키움 미국주식",
        channel_message_id=str(50000 + chunk_id),
        message_type="signal",
        event_type="해석/전망",
        category_key=category_key,
        main_theme=main_theme,
        provisional_category=None,
        provisional_theme=None,
        is_provisional=False,
        sub_themes=[],
        ticker_tags=ticker_tags or [],
        theme_tags=[],
        canonical_summary=canonical_summary or f"summary-{chunk_id}",
        supporting_facts=[],
        evidence_items=[],
        qa_warnings=[],
        content_clean=f"content-{chunk_id}",
        priority_score=1.0,
    )


def test_synthesize_same_day_bundle_uses_llm_synthesis_output(monkeypatch) -> None:
    nvda_chunk = _chunk(1, ticker_tags=["NVDA"], canonical_summary="NVDA HBM 수요가 강하다")
    samsung_chunk = _chunk(
        2,
        ticker_tags=["삼성전자"],
        canonical_summary="삼성전자 HBM 증설 기대가 이어졌다",
    )
    auto_chunk = _chunk(
        3,
        category_key="자동차",
        main_theme="하이브리드",
        ticker_tags=["현대차"],
        canonical_summary="현대차 하이브리드 전략이 부각됐다",
    )
    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=[nvda_chunk, samsung_chunk, auto_chunk],
        category_buckets=[
            CategoryBucket(category_key="반도체", chunks=[nvda_chunk, samsung_chunk]),
            CategoryBucket(category_key="자동차", chunks=[auto_chunk]),
        ],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )

    async def _fake_llm(*, bundle, provider):  # type: ignore[no-untyped-def]
        assert provider == "openai"
        assert len(bundle.chunks) == 3
        return LocalEvidenceSynthesisOutput(
            pulse=[
                SynthesisPulseItemOutput(
                    title="반도체 주도",
                    body="HBM 관련 수요가 집중됐다",
                    evidence_chunk_ids=[1, 2],
                )
            ],
            category_summaries=[
                SynthesisCategoryCardOutput(
                    category_key="반도체",
                    title="HBM 체인 강세",
                    evidence_bullets=["NVDA 수요 확대", "삼성전자 증설 기대"],
                    impact="메모리 밸류체인 심리 개선",
                    related_stocks=[{"name": "엔비디아", "ticker": "NVDA", "catalyst": "HBM 수요"}],
                    evidence_chunk_ids=[1, 2],
                )
            ],
            core_themes=[
                SynthesisCoreThemeOutput(
                    key="HBM",
                    title="HBM",
                    thesis="공급 타이트닝이 지속된다",
                    evidence_bullets=["NVDA 수요 확대", "삼성전자 증설 기대"],
                    impact="메모리 밸류체인 심리 개선",
                    watch_points=["공급 확대 속도"],
                    related_categories=["반도체"],
                    evidence_chunk_ids=[1, 2],
                ),
            ],
            focus_tickers=[
                SynthesisFocusTickerOutput(
                    key="NVDA",
                    title="NVDA",
                    investment_case="데이터센터 투자 사이클 수혜",
                    catalysts=["AI 서버 투자"],
                    evidence_bullets=["데이터센터 수요 증가"],
                    risks_or_watch_points=["CAPEX 둔화"],
                    related_themes=["AI인프라"],
                    evidence_chunk_ids=[1],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._synthesize_same_day_bundle_with_llm",
        _fake_llm,
    )

    artifact = synthesize_same_day_bundle(bundle, provider="openai")

    assert artifact.report_date == date(2026, 5, 26)
    assert artifact.pulse
    assert artifact.pulse[0].title == "반도체 주도"
    assert artifact.category_summaries[0].title == "HBM 체인 강세"
    assert artifact.category_summaries[0].body != (
        "NVDA HBM 수요가 강하다 / 삼성전자 HBM 증설 기대가 이어졌다"
    )
    assert artifact.category_summaries[0].evidence_bullets == [
        "NVDA 수요 확대",
        "삼성전자 증설 기대",
    ]
    assert {ref.section_key for ref in artifact.evidence_refs} >= {
        "pulse",
        "category_summaries",
        "core_themes",
        "focus_tickers",
    }
    cited_ids = {
        chunk_id
        for item in (
            artifact.pulse
            + artifact.category_summaries
            + artifact.core_themes
            + artifact.focus_tickers
        )
        for chunk_id in item.evidence_chunk_ids
    }
    assert {ref.knowledge_chunk_id for ref in artifact.evidence_refs} == cited_ids
    assert {ref.knowledge_chunk_id for ref in artifact.evidence_refs} == {1, 2}
    ref = artifact.evidence_refs[0]
    assert "channel_name" in ref.knowledge_chunk_snapshot
    assert "channel_message_id" in ref.knowledge_chunk_snapshot
    assert "source_message_db_id" in ref.knowledge_chunk_snapshot


def test_synthesize_same_day_bundle_keeps_all_cards_sorted_by_priority(monkeypatch) -> None:
    chunks = [_chunk(chunk_id) for chunk_id in range(1, 4)]
    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=chunks,
        category_buckets=[CategoryBucket(category_key="반도체", chunks=chunks)],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )

    async def _fake_llm(*, bundle, provider):  # type: ignore[no-untyped-def]
        return LocalEvidenceSynthesisOutput(
            category_summaries=[
                SynthesisCategoryCardOutput(
                    category_key="low",
                    title="낮은 우선순위",
                    evidence_bullets=["낮은 근거"],
                    impact="낮은 영향",
                    evidence_chunk_ids=[1],
                    priority_score=0.1,
                ),
                SynthesisCategoryCardOutput(
                    category_key="high",
                    title="높은 우선순위",
                    evidence_bullets=["높은 근거"],
                    impact="높은 영향",
                    evidence_chunk_ids=[2],
                    priority_score=0.9,
                ),
                SynthesisCategoryCardOutput(
                    category_key="mid",
                    title="중간 우선순위",
                    evidence_bullets=["중간 근거"],
                    impact="중간 영향",
                    evidence_chunk_ids=[3],
                    priority_score=0.5,
                ),
            ],
            core_themes=[
                SynthesisCoreThemeOutput(
                    key="theme-low",
                    title="테마 낮음",
                    thesis="낮은 주장",
                    evidence_bullets=["낮은 근거"],
                    impact="낮은 영향",
                    watch_points=["낮은 변수"],
                    related_categories=["반도체"],
                    evidence_chunk_ids=[1],
                    priority_score=0.2,
                ),
                SynthesisCoreThemeOutput(
                    key="theme-high",
                    title="테마 높음",
                    thesis="높은 주장",
                    evidence_bullets=["높은 근거"],
                    impact="높은 영향",
                    watch_points=["높은 변수"],
                    related_categories=["AI인프라", "반도체"],
                    evidence_chunk_ids=[2],
                    priority_score=0.8,
                ),
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._synthesize_same_day_bundle_with_llm",
        _fake_llm,
    )

    artifact = synthesize_same_day_bundle(bundle, provider="openai")

    assert [item.title for item in artifact.category_summaries] == [
        "높은 우선순위",
        "중간 우선순위",
        "낮은 우선순위",
    ]
    assert [item.title for item in artifact.core_themes] == ["테마 높음", "테마 낮음"]
    assert {ref.knowledge_chunk_id for ref in artifact.evidence_refs} == {1, 2, 3}


def test_synthesize_same_day_bundle_maps_rich_core_theme_fields(monkeypatch) -> None:
    chunks = [_chunk(chunk_id) for chunk_id in range(1, 4)]
    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=chunks,
        category_buckets=[CategoryBucket(category_key="반도체", chunks=chunks)],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )

    async def _fake_llm(*, bundle, provider):  # type: ignore[no-untyped-def]
        return LocalEvidenceSynthesisOutput(
            core_themes=[
                SynthesisCoreThemeOutput(
                    key="ai-infra-chain",
                    title="AI 인프라 수혜 확산",
                    thesis="AI CAPEX가 HBM·전력·부품으로 확산된다.",
                    evidence_bullets=["HBM 수요 증가", "전력 부품 수요 증가"],
                    impact="수혜 범위가 반도체 대형주 밖으로 넓어진다.",
                    watch_points=["CAPEX 지속성", "메모리 가격"],
                    related_categories=["AI인프라", "반도체"],
                    related_stocks=[{"name": "SK하이닉스", "ticker": "000660", "catalyst": "HBM"}],
                    evidence_chunk_ids=[1, 2],
                    priority_score=0.9,
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._synthesize_same_day_bundle_with_llm",
        _fake_llm,
    )

    artifact = synthesize_same_day_bundle(bundle, provider="openai")
    theme = artifact.core_themes[0]

    assert theme.thesis == "AI CAPEX가 HBM·전력·부품으로 확산된다."
    assert theme.evidence_bullets == ["HBM 수요 증가", "전력 부품 수요 증가"]
    assert theme.impact == "수혜 범위가 반도체 대형주 밖으로 넓어진다."
    assert theme.watch_points == ["CAPEX 지속성", "메모리 가격"]
    assert theme.related_categories == ["AI인프라", "반도체"]
    assert theme.related_stocks == [{"name": "SK하이닉스", "ticker": "000660", "catalyst": "HBM"}]


def test_synthesize_same_day_bundle_maps_rich_focus_ticker_fields(monkeypatch) -> None:
    chunks = [_chunk(chunk_id) for chunk_id in range(1, 3)]
    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=chunks,
        category_buckets=[CategoryBucket(category_key="반도체", chunks=chunks)],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )

    async def _fake_llm(*, bundle, provider):  # type: ignore[no-untyped-def]
        return LocalEvidenceSynthesisOutput(
            focus_tickers=[
                SynthesisFocusTickerOutput(
                    key="SK하이닉스",
                    title="SK하이닉스: ETF 수급과 HBM 기술 모멘텀",
                    investment_case="HBM 수요와 ETF 수급이 동시에 붙는 대표 수혜주다.",
                    catalysts=["iHBM 냉각 솔루션 공개", "단일종목 레버리지 ETF 출시"],
                    evidence_bullets=["주가 5.72% 급등", "HBM 패키지용 냉각 솔루션 출시"],
                    risks_or_watch_points=["ETF 출시 후 차익실현", "HBM 공급 경쟁 심화"],
                    related_themes=["HBM", "반도체 레버리지 ETF"],
                    evidence_chunk_ids=[1, 2],
                    priority_score=0.95,
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._synthesize_same_day_bundle_with_llm",
        _fake_llm,
    )

    artifact = synthesize_same_day_bundle(bundle, provider="openai")
    ticker = artifact.focus_tickers[0]

    assert ticker.investment_case == "HBM 수요와 ETF 수급이 동시에 붙는 대표 수혜주다."
    assert ticker.catalysts == ["iHBM 냉각 솔루션 공개", "단일종목 레버리지 ETF 출시"]
    assert ticker.evidence_bullets == ["주가 5.72% 급등", "HBM 패키지용 냉각 솔루션 출시"]
    assert ticker.risks_or_watch_points == ["ETF 출시 후 차익실현", "HBM 공급 경쟁 심화"]
    assert ticker.related_themes == ["HBM", "반도체 레버리지 ETF"]


def test_synthesize_same_day_bundle_preserves_deep_focus_ticker_evidence(monkeypatch) -> None:
    chunks = [_chunk(chunk_id) for chunk_id in range(1, 4)]
    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=chunks,
        category_buckets=[CategoryBucket(category_key="반도체", chunks=chunks)],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )
    evidence_bullets = [f"근거 {idx}" for idx in range(1, 10)]

    async def _fake_llm(*, bundle, provider):  # type: ignore[no-untyped-def]
        return LocalEvidenceSynthesisOutput(
            focus_tickers=[
                SynthesisFocusTickerOutput(
                    key="삼성전자",
                    title="삼성전자: 메모리 업사이클과 주주환원",
                    investment_case="메모리 가격 상승과 주주환원이 동시에 붙는 대형주다.",
                    catalysts=[
                        "HBM 공급 부족",
                        "DRAM 가격 상승",
                        "주주환원 확대",
                        "다년 공급 계약",
                        "서버용 eSSD 수요",
                        "파운드리 회복",
                    ],
                    key_metrics=["DRAM +93%", "NAND +89%", "영업이익 86.8조원 전망"],
                    evidence_bullets=evidence_bullets,
                    risks_or_watch_points=[
                        "스마트폰 수요 둔화",
                        "HBM 검증 지연",
                        "메모리 가격 피크아웃",
                        "환율 변동",
                        "CAPEX 둔화",
                        "중국 경쟁 심화",
                    ],
                    related_themes=["HBM", "메모리 가격", "주주환원", "AI 서버"],
                    evidence_chunk_ids=[1, 2, 3],
                    priority_score=0.99,
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._synthesize_same_day_bundle_with_llm",
        _fake_llm,
    )

    artifact = synthesize_same_day_bundle(bundle, provider="openai")
    ticker = artifact.focus_tickers[0]

    assert ticker.key_metrics == ["DRAM +93%", "NAND +89%", "영업이익 86.8조원 전망"]
    assert ticker.evidence_bullets == evidence_bullets
    assert ticker.catalysts == [
        "HBM 공급 부족",
        "DRAM 가격 상승",
        "주주환원 확대",
        "다년 공급 계약",
        "서버용 eSSD 수요",
        "파운드리 회복",
    ]
    assert ticker.risks_or_watch_points == [
        "스마트폰 수요 둔화",
        "HBM 검증 지연",
        "메모리 가격 피크아웃",
        "환율 변동",
        "CAPEX 둔화",
        "중국 경쟁 심화",
    ]


def test_synthesize_same_day_bundle_falls_back_to_deterministic_on_llm_failure(monkeypatch) -> None:
    async def _raise(**_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("llm down")

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._synthesize_same_day_bundle_with_llm",
        _raise,
    )

    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=[
            _chunk(1, category_key="반도체", canonical_summary="요약 A"),
            _chunk(2, category_key="반도체", canonical_summary="요약 B"),
        ],
        category_buckets=[
            CategoryBucket(
                category_key="반도체",
                chunks=[
                    _chunk(1, category_key="반도체", canonical_summary="요약 A"),
                    _chunk(2, category_key="반도체", canonical_summary="요약 B"),
                ],
            )
        ],
        focus_ticker_buckets=[],
        low_confidence_chunks=[],
    )

    artifact = synthesize_same_day_bundle(bundle, provider="openai")

    assert artifact.category_summaries[0].body == "요약 A / 요약 B"


def test_synthesize_same_day_bundle_keeps_low_confidence_separate_when_llm_empty(
    monkeypatch,
) -> None:
    async def _empty(**_kwargs):  # type: ignore[no-untyped-def]
        return LocalEvidenceSynthesisOutput()

    monkeypatch.setattr(
        "src.pipelines.stock_report.synthesize._synthesize_same_day_bundle_with_llm",
        _empty,
    )

    low_confidence = _chunk(
        10,
        category_key="unclassified",
        main_theme=None,
        ticker_tags=[],
        canonical_summary="분류가 애매한 시황",
    )
    bundle = SameDayBundle(
        report_date=date(2026, 5, 26),
        chunks=[low_confidence],
        category_buckets=[],
        focus_ticker_buckets=[],
        low_confidence_chunks=[low_confidence],
    )

    artifact = synthesize_same_day_bundle(bundle, provider="openai")

    assert artifact.low_confidence_notes == ["분류가 애매한 시황"]
    assert artifact.category_summaries == []
