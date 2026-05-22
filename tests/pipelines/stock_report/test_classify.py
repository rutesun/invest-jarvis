from __future__ import annotations

from datetime import UTC, date, datetime

from src.pipelines.stock_report.classify import classify_messages
from src.pipelines.stock_report.models import (
    EvidenceItem,
    NormalizedMessage,
    SemanticExtractionDraft,
    SemanticExtractionLLMOutput,
    SemanticUnitDraft,
    SemanticUnitLLMOutput,
)
from src.pipelines.stock_report.taxonomy import load_taxonomy_registry


def _normalized_message(clean_text: str, *, raw_text: str | None = None) -> NormalizedMessage:
    return NormalizedMessage(
        telegram_message_id=1,
        source_date=date(2026, 5, 8),
        date_kst=date(2026, 5, 8),
        posted_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        channel_key="hana_us_stock",
        source_channel_key="hana_us_stock",
        source_channel_name="hana_us_stock",
        channel_message_id="1",
        raw_text=raw_text or clean_text,
        clean_text=clean_text,
        urls=[],
        has_media=False,
        content_hash="hash",
        processing_mode="full",
        grouped_message_ids=[],
    )


def test_classify_normalizes_llm_output_into_canonical_fields(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("NVIDIA·IREN, 최대 5GW AI 인프라 구축 전략적 파트너십 발표")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert row.clean_text
        assert provider == "openai"
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="파트너십",
                    category_key="AI infra",
                    main_theme="데이터센터 전력",
                    sub_themes=["AI 칩"],
                    ticker_tags=["NVDA", "IREN"],
                    canonical_summary="NVIDIA·IREN, 최대 5GW AI 인프라 파트너십 발표",
                    supporting_facts=[
                        "양사는 IREN 데이터센터 파이프라인 전반에 NVIDIA 인프라 배치를 추진",
                        "스페인 Ingenostrum 인수로 IREN 전력 포트폴리오가 확대될 예정",
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].structure_type == "single_topic_deep"
    assert result[0].unit_index == 0
    assert result[0].category_key == "AI인프라"
    assert result[0].main_theme == "AI 데이터센터 전력"
    assert result[0].sub_themes == ["AI 반도체"]
    assert result[0].event_type == "수주/계약"
    assert result[0].ticker_tags == ["NVDA", "IREN"]
    assert result[0].canonical_summary == "NVIDIA·IREN, 최대 5GW AI 인프라 파트너십 발표"
    assert len(result[0].supporting_facts) == 2


def test_classify_derives_supporting_facts_from_typed_evidence(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("Seagate 주가 8% 하락, 메모리 가격 전망은 견조")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert "evidence_items" in system_prompt
        assert "supporting_facts" not in system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="해석/전망",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["Seagate"],
                    canonical_summary="Seagate 하락에도 메모리 가격 전망은 견조",
                    evidence_items=[
                        EvidenceItem(kind="metric", text="Seagate 주가는 8% 하락"),
                        EvidenceItem(
                            kind="market_context",
                            text="메모리 가격은 2027년 말까지 높은 수준을 유지할 수 있다는 전망",
                        ),
                    ],
                    supporting_facts=["legacy fact should not win"],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].supporting_facts == [
        "Seagate 주가는 8% 하락",
        "메모리 가격은 2027년 말까지 높은 수준을 유지할 수 있다는 전망",
    ]
    assert [item.kind for item in result[0].evidence_items] == ["metric", "market_context"]
    assert "legacy_facts_diverged" in [warning.code for warning in result[0].qa_warnings]


def test_classify_converts_legacy_supporting_facts_to_fact_evidence(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("NVIDIA·IREN 파트너십")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="파트너십",
                    category_key="AI인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NVDA", "IREN"],
                    canonical_summary="NVIDIA·IREN AI 인프라 파트너십 발표",
                    supporting_facts=["최대 5GW 규모 AI 인프라 배치를 지원할 계획"],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].supporting_facts == ["최대 5GW 규모 AI 인프라 배치를 지원할 계획"]
    assert result[0].evidence_items == [
        EvidenceItem(kind="fact", text="최대 5GW 규모 AI 인프라 배치를 지원할 계획")
    ]


def test_classify_maps_invalid_evidence_kind_to_fact_and_warns(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("메모리 가격 전망")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="해석/전망",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["Seagate"],
                    canonical_summary="메모리 가격 전망이 견조하다는 평가",
                    evidence_items=[
                        {"kind": "forecast_context", "text": "메모리 가격 전망이 견조"}
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert result[0].evidence_items == [EvidenceItem(kind="fact", text="메모리 가격 전망이 견조")]
    assert "unknown_evidence_kind" in [warning.code for warning in result[0].qa_warnings]


def test_classify_numeric_qa_ignores_noise_tokens(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "S&P500 map\n오리온(271560.KS) 기업분석부 조상훈 ☎02-3772-2578\n"
        "삼성전자 005930, SK하이닉스 000660.KS\n"
        "2026-05-19 07:09 원문 확인: https://example.com/file.pdf?attachmentId=351531"
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="market_wrap",
            units=[
                SemanticUnitDraft(
                    message_type="opinion",
                    event_type="해석/전망",
                    category_key="소비재/유통",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["오리온"],
                    canonical_summary="오리온 리포트 고지와 제목이 포함된 메시지",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="오리온 리포트 고지와 제목이 포함")
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    warning_codes = [warning.code for warning in result[0].qa_warnings]
    assert "missing_metric_candidate" not in warning_codes
    assert "unsupported_numeric" not in warning_codes


def test_classify_numeric_qa_ignores_plain_six_digit_stock_code(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("오리온 271560 기업분석 리포트")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="해석/전망",
                    category_key="소비재/유통",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["오리온", "271560"],
                    canonical_summary="오리온 기업분석 리포트",
                    evidence_items=[EvidenceItem(kind="fact", text="오리온 기업분석 리포트")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "missing_metric_candidate" not in [warning.code for warning in result[0].qa_warnings]


def test_classify_numeric_qa_accepts_equivalent_units(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("주가는 8퍼센트 하락했고 투자 규모는 $2B로 제시")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="해석/전망",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="주가 하락과 투자 규모가 함께 언급",
                    evidence_items=[
                        EvidenceItem(kind="metric", text="주가는 8% 하락"),
                        EvidenceItem(kind="metric", text="투자 규모는 20억달러"),
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "unsupported_numeric" not in [warning.code for warning in result[0].qa_warnings]


def test_classify_flags_unsupported_numeric_in_non_metric_evidence(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("메타가 루이지애나에 초대형 AI 데이터센터를 건설 중")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="투자",
                    category_key="AI인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["Meta"],
                    canonical_summary="메타 AI 데이터센터 건설 추진",
                    evidence_items=[
                        EvidenceItem(
                            kind="fact",
                            text="메타가 2000억달러 규모 AI 데이터센터를 건설",
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "unsupported_numeric" in [warning.code for warning in result[0].qa_warnings]


def test_classify_flags_long_evidence(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("긴 근거 테스트")
    long_text = "이 문장은 원문 근거라기보다 과도하게 긴 요약처럼 보이는 설명입니다. " * 5

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="opinion",
                    event_type="해석/전망",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="긴 근거 경고 테스트",
                    evidence_items=[EvidenceItem(kind="thesis", text=long_text)],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "long_evidence" in [warning.code for warning in result[0].qa_warnings]


def test_llm_output_schema_does_not_include_legacy_supporting_facts():
    unit = SemanticUnitLLMOutput(
        message_type="signal",
        category_key="AI인프라",
        canonical_summary="AI 인프라 투자 확대",
        evidence_items=[EvidenceItem(kind="fact", text="AI 인프라 투자 확대")],
        supporting_facts=["legacy field ignored"],
    )
    draft = SemanticExtractionLLMOutput(structure_type="single_topic_deep", units=[unit])

    assert not hasattr(draft.units[0], "supporting_facts")
    assert (
        "supporting_facts"
        not in draft.model_json_schema()["$defs"]["SemanticUnitLLMOutput"]["properties"]
    )


def test_classify_admin_warning_only_when_normalized_non_admin(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("채널 공지: 라이브 일정 안내")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="notice",
            units=[
                SemanticUnitDraft(
                    message_type="admin",
                    event_type="공지",
                    category_key=None,
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="채널 공지와 라이브 일정 안내",
                    evidence_items=[EvidenceItem(kind="fact", text="채널 공지와 라이브 일정 안내")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert result[0].message_type == "admin"
    assert "admin_contradiction" not in [warning.code for warning in result[0].qa_warnings]


def test_classify_llm_failure_fallback_keeps_typed_fields_empty_and_warning_visible(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("NVIDIA AI 인프라 투자 확대")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].evidence_items == []
    assert result[0].supporting_facts == []
    assert "llm_extraction_failed" in [warning.code for warning in result[0].qa_warnings]


def test_classify_splits_multi_item_digest_into_multiple_report_units(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("신한 자동차 뉴스 digest")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="multi_item_digest",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="상장",
                    category_key="자동차",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["현대차"],
                    canonical_summary="현대차, 보스턴다이내믹스 상장 검토",
                    supporting_facts=[],
                ),
                SemanticUnitDraft(
                    message_type="data",
                    event_type="판매량",
                    category_key="자동차",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["기아"],
                    canonical_summary="기아 인도 EV 판매 900% 넘게 증가",
                    supporting_facts=[],
                ),
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="anthropic")

    assert len(result) == 2
    assert [item.structure_type for item in result] == ["multi_item_digest", "multi_item_digest"]
    assert [item.unit_index for item in result] == [0, 1]
    assert [item.event_type for item in result] == ["상장", "판매량"]
    assert [item.canonical_summary for item in result] == [
        "현대차, 보스턴다이내믹스 상장 검토",
        "기아 인도 EV 판매 900% 넘게 증가",
    ]


def test_classify_uses_theme_category_when_llm_category_is_missing(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("임상 결과 발표")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="approval",
                    category_key=None,
                    main_theme="임상",
                    sub_themes=["FDA"],
                    ticker_tags=["알테오젠"],
                    canonical_summary="알테오젠, 임상 데이터 발표로 신약개발 기대 부각",
                    supporting_facts=[],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].category_key == "바이오/헬스케어"
    assert result[0].event_type == "인증/승인"
    assert result[0].main_theme == "신약개발"
    assert result[0].sub_themes == []


def test_classify_filters_blank_units_from_llm_output(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("운영 공지")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="notice",
            units=[
                SemanticUnitDraft(
                    message_type="admin",
                    event_type="공지",
                    category_key=None,
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="   ",
                    supporting_facts=[],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert result == []


def test_classify_normalizes_convertible_bond_event_type(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("IREN, 20억달러 전환선순위채권 발행 추진")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="capped call",
                    category_key=None,
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["IREN"],
                    canonical_summary="IREN, 20억달러 전환사채 발행으로 투자재원 확보 추진",
                    supporting_facts=[],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].event_type == "자본조달"


def test_classify_warns_when_metric_candidate_is_missing_without_synthesizing_fact(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("1분기 매출 1.63억, 영업이익 2200만, YoY 85% 증가")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="실적",
                    category_key="AI인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["PLTR"],
                    canonical_summary="실적 급증으로 가이던스 상향",
                    supporting_facts=["수요가 빠르게 확대됨"],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    joined = " ".join(result[0].supporting_facts)
    assert "핵심 수치:" not in joined
    assert "missing_metric_candidate" in [warning.code for warning in result[0].qa_warnings]


def test_classify_does_not_append_message_level_numeric_fact_to_market_wrap(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "S&P500 map\n\n반도체 중심 AI 하드웨어 하락\n\n소프트웨어는 순환매 상승"
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="market_wrap",
            units=[
                SemanticUnitDraft(
                    message_type="opinion",
                    event_type="해석/전망",
                    category_key="AI인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="AI 하드웨어 약세와 소프트웨어 순환매",
                    supporting_facts=["AI 하드웨어 관련주가 하락"],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    joined = " ".join(result[0].supporting_facts)
    assert "핵심 수치:" not in joined
    assert "작성자 코멘트:" not in joined


def test_classify_preserves_deep_supporting_facts_up_to_safety_limit(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("NEE가 Dominion을 인수해 데이터센터 전력 수요를 확보")
    facts = [f"근거 {idx}" for idx in range(1, 26)]

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert "thesis" in system_prompt
        assert "market_context" in system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="M&A",
                    category_key="AI인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NEE", "D"],
                    canonical_summary="넥스트에라가 도미니언 인수로 데이터센터 전력 수요를 확보",
                    supporting_facts=facts,
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert len(result[0].supporting_facts) == 20
    assert result[0].supporting_facts[0] == "근거 1"
    assert result[0].supporting_facts[-1] == "근거 20"


def test_classify_does_not_synthesize_numeric_lead_comment(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "Cognizant, Astreya 인수로 AI 데이터센터 서비스 확장",
        raw_text=(
            "어제 20억 달러 규모 자사주매입 목표 상향 설정했네요\n\n"
            "[Cognizant, Astreya 인수로 AI 데이터센터 서비스 확장]\n"
            "- Cognizant는 Astreya를 6억달러에 인수"
        ),
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert "작성자 코멘트" in system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="M&A",
                    category_key="AI인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["Cognizant", "Astreya"],
                    canonical_summary="Cognizant가 Astreya 인수로 AI 데이터센터 서비스를 확장",
                    supporting_facts=[
                        "Cognizant는 Astreya를 6억달러에 인수",
                        "Astreya는 하이퍼스케일러 고객 기반을 보유",
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert not any(fact.startswith("작성자 코멘트:") for fact in result[0].supporting_facts)
    assert result[0].supporting_facts == [
        "Cognizant는 Astreya를 6억달러에 인수",
        "Astreya는 하이퍼스케일러 고객 기반을 보유",
    ]


def test_classify_does_not_promote_report_title_or_byline_as_lead_comment(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "오리온, 해외 매출 회복과 원가 완화로 실적 개선 기대",
        raw_text=(
            "『오리온(271560.KS) – 전쟁 중에도 초코파이는 먹는다 』\n"
            "기업분석부 조상훈 ☎02-3772-2578\n\n"
            "▶ 매출 성장률 회복과 원가 부담 완화\n"
            "- 지난 2년간 외형 성장 부진하며 주가도 약세\n"
            "- 목표주가 160,000원 유지\n"
            "위 내용은 조사분석자료 공표 승인이 이뤄진 내용입니다."
        ),
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert "하단 고지 때문에 `admin`으로 분류하지 않는다" in system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="admin",
                    event_type="해석/전망",
                    category_key="소비재/유통",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["오리온", "271560.KS"],
                    canonical_summary="오리온, 해외 매출 회복과 원가 완화로 실적 개선 기대",
                    supporting_facts=[
                        "4월 국가별 전년대비 매출증감률은 중국 +22.9%, 러시아 +21.6%",
                        "목표주가 160,000원을 유지",
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].message_type == "opinion"
    assert not any(fact.startswith("작성자 코멘트:") for fact in result[0].supporting_facts)
    assert "admin_contradiction" in [warning.code for warning in result[0].qa_warnings]


def test_classify_assigns_provisional_overlay_for_unclassified(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("PCTC 운임 강세와 유류할증료 상승, BAF 회수 시차가 관건")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="해석/전망",
                    category_key="misc",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["현대글로비스"],
                    canonical_summary="PCTC 수요는 견조하나 유가 상승분 전가 시차가 존재",
                    supporting_facts=["BAF 반영은 통상 5~6개월 지연"],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].category_key == "unclassified"
    assert result[0].provisional_category == "운송/물류"
    assert result[0].provisional_theme == "연료비/BAF"
    assert result[0].is_provisional is True


def test_classify_does_not_override_canonical_category_with_overlay(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("AI 데이터센터 투자 확대")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="투자",
                    category_key="AI 인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NVDA"],
                    canonical_summary="하이퍼스케일러의 AI 데이터센터 전력 투자 확대",
                    supporting_facts=["AI 전력 수요 지속 증가"],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].category_key == "AI인프라"
    assert result[0].provisional_category is None
    assert result[0].provisional_theme == "AI 데이터센터 전력"
    assert result[0].is_provisional is False


def test_classify_overlay_ignores_short_english_alias_noise(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("AI 랠리 언급이 있었지만 구체 섹터 근거는 없는 일반 코멘트")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        assert system_prompt
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="opinion",
                    event_type="해석/전망",
                    category_key="misc",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="장중 변동성 확대에 대한 일반 코멘트",
                    supporting_facts=["AI 랠리 과열 경계 문구 포함"],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert len(result) == 1
    assert result[0].category_key == "unclassified"
    assert result[0].provisional_category is None
    assert result[0].is_provisional is False
