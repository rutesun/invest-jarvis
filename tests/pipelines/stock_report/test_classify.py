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
        EvidenceItem(kind="metric", text="최대 5GW 규모 AI 인프라 배치를 지원할 계획")
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


def test_classify_numeric_qa_accepts_sign_and_currency_equivalence(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("가이던스는 +13.4% 상향, EPS는 $1.87로 제시")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="실적",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NVDA"],
                    canonical_summary="가이던스와 EPS가 제시됨",
                    evidence_items=[
                        EvidenceItem(kind="metric", text="가이던스는 13.4% 상향"),
                        EvidenceItem(kind="metric", text="EPS는 1.87달러"),
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


def test_classify_numeric_qa_accepts_negative_percent_decline_expression(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("출하량은 -14% 조정")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="data",
                    event_type="통계/지표",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="출하량 하향 조정",
                    evidence_items=[EvidenceItem(kind="metric", text="출하량 14% 하락")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "unsupported_numeric" not in [warning.code for warning in result[0].qa_warnings]


def test_classify_numeric_qa_flags_opposite_explicit_percent_sign(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("가이던스는 +13.4% 상향")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="실적",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NVDA"],
                    canonical_summary="가이던스 변동",
                    evidence_items=[EvidenceItem(kind="metric", text="가이던스는 -13.4% 하향")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "unsupported_numeric" in [warning.code for warning in result[0].qa_warnings]


def test_classify_numeric_qa_accepts_two_digit_year_form(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("투자 회수 시점은 '27년으로 제시")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="opinion",
                    event_type="해석/전망",
                    category_key="AI인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="투자 회수 시점을 제시",
                    evidence_items=[EvidenceItem(kind="metric", text="투자 회수 시점은 2027년")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "unsupported_numeric" not in [warning.code for warning in result[0].qa_warnings]


def test_classify_numeric_qa_ignores_date_range_and_schedule_dates(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("공모 일정: 2026-05-21 ~ 2027-12-26, 청약일 5월 21일")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="공지",
                    category_key=None,
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="공모 일정 안내",
                    evidence_items=[EvidenceItem(kind="fact", text="청약일은 2026년 5월 21일")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    warning_codes = [warning.code for warning in result[0].qa_warnings]
    assert "unsupported_numeric" not in warning_codes
    assert "missing_metric_candidate" not in warning_codes


def test_classify_missing_metric_candidate_uses_unit_local_text_for_schedule(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "DB손보, 미국 보험사 포테그라 인수 30일 마무리",
        raw_text="- 엔비디아 가이던스 +13.4% 상향\n- DB손보, 미국 보험사 포테그라 인수 30일 마무리",
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="multi_item_digest",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="M&A",
                    category_key=None,
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["DB손보"],
                    canonical_summary="DB손보, 미국 보험사 포테그라 인수 30일 마무리",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="인수 절차는 30일 내 마무리 예정")
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


def test_classify_schedule_fact_numeric_stays_fact(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("BAF 반영은 통상 12개월 지연")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="opinion",
                    event_type="해석/전망",
                    category_key="운송/물류",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["현대글로비스"],
                    canonical_summary="BAF 반영 시차가 존재",
                    evidence_items=[EvidenceItem(kind="fact", text="BAF 반영은 통상 12개월 지연")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert result[0].evidence_items == [
        EvidenceItem(kind="fact", text="BAF 반영은 통상 12개월 지연")
    ]
    assert "missing_metric_candidate" not in [warning.code for warning in result[0].qa_warnings]


def test_classify_missing_metric_candidate_real_metric_in_local_text_warns(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("미 법무부, 6710억 원 과징금 검토")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="정책",
                    category_key=None,
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["GOOGL"],
                    canonical_summary="미 법무부, 6710억 원 과징금 검토",
                    evidence_items=[EvidenceItem(kind="fact", text="반독점 조사 강도를 높일 계획")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "missing_metric_candidate" in [warning.code for warning in result[0].qa_warnings]


def test_classify_ordinal_schedule_number_does_not_warn_missing_metric_candidate(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("스페이스X 12차 비행 성공")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="출시/제품",
                    category_key="AI인프라",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["TSLA"],
                    canonical_summary="스페이스X 12차 비행 성공",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="12차 시험 비행이 성공적으로 완료")
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


def test_classify_missing_metric_uses_unit_local_numbers_not_whole_digest(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "Daily Digest\n"
        "1) 공정위가 밀가루 담합에 6710억 원 과징금을 부과\n"
        "2) Xreal 차세대 스마트 안경은 2026년 말 출시 예정"
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="multi_item_digest",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="출시/제품",
                    category_key="디스플레이/광학",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["Xreal"],
                    canonical_summary="Xreal 차세대 스마트 안경은 2026년 말 출시 예정",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="차세대 제품은 2026년 말 출시 예정")
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "missing_metric_candidate" not in [warning.code for warning in result[0].qa_warnings]
    assert result[0].evidence_items == [
        EvidenceItem(kind="fact", text="차세대 제품은 2026년 말 출시 예정")
    ]


def test_classify_missing_metric_warns_for_real_metric_in_unit_summary(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("공정위가 밀가루 담합에 6710억 원 과징금을 부과")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="정책",
                    category_key="소비재/유통",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="공정위가 밀가루 담합에 6710억 원 과징금을 부과",
                    evidence_items=[EvidenceItem(kind="fact", text="공정위가 밀가루 담합을 적발")],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "missing_metric_candidate" in [warning.code for warning in result[0].qa_warnings]


def test_classify_temporal_numeric_facts_are_not_promoted_to_metric(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "DB손보 포테그라 인수 30일 마무리. 스페이스X 12차 비행 성공. "
        "ECB는 2026년 3분기까지 가이드라인 이행 지시."
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="multi_item_digest",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="M&A",
                    category_key="금융",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["DB손보"],
                    canonical_summary="DB손보 포테그라 인수 30일 마무리",
                    evidence_items=[EvidenceItem(kind="fact", text="포테그라 인수는 30일 마무리")],
                ),
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="수주/계약",
                    category_key="우주/항공",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["스페이스X"],
                    canonical_summary="스페이스X 12차 비행 성공",
                    evidence_items=[EvidenceItem(kind="fact", text="12차 비행에서 재진입 성공")],
                ),
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="정책",
                    category_key="금융",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["ECB"],
                    canonical_summary="ECB는 2026년 3분기까지 AI 감사 가이드라인 이행 지시",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="2026년 3분기까지 이행하도록 지시")
                    ],
                ),
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    for unit in result:
        assert "missing_metric_candidate" not in [warning.code for warning in unit.qa_warnings]
        assert [item.kind for item in unit.evidence_items] == ["fact"]


def test_classify_promotes_single_digit_leverage_fact_to_metric(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("삼성전자·SK하이닉스 2배 레버리지 ETF 출시")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="single_topic_deep",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="출시/제품",
                    category_key="금융상품",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="삼성전자·SK하이닉스 2배 레버리지 ETF 출시",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="삼성전자·SK하이닉스 2배 레버리지 ETF 출시")
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert result[0].evidence_items == [
        EvidenceItem(kind="metric", text="삼성전자·SK하이닉스 2배 레버리지 ETF 출시")
    ]
    assert "missing_metric_candidate" not in [warning.code for warning in result[0].qa_warnings]


def test_classify_promotes_meaningful_numeric_fact_to_metric(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("1분기 매출 1.63억, 영업이익 2200만, YoY 85% 증가")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
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
                    canonical_summary="실적 급증",
                    evidence_items=[
                        EvidenceItem(
                            kind="fact", text="1분기 매출 1.63억, 영업이익 2200만, YoY 85% 증가"
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

    assert result[0].evidence_items == [
        EvidenceItem(kind="metric", text="1분기 매출 1.63억, 영업이익 2200만, YoY 85% 증가")
    ]
    assert "missing_metric_candidate" not in [warning.code for warning in result[0].qa_warnings]


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


def test_classify_warns_under_split_candidate_for_digest_like_message(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "Daily Market Digest\n"
        "1) KOSPI/KOSDAQ 장중 흐름\n"
        "2) WTI 반등과 금리 변화\n"
        "3) MU/SOX/NVDA 반도체 동향\n"
        "4) SpaceX 기업 이슈\n"
        "5) FOMC 발언 요약"
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="multi_item_digest",
            units=[
                SemanticUnitDraft(
                    message_type="opinion",
                    event_type="해석/전망",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NVDA", "MU"],
                    canonical_summary="반도체와 거시 이슈를 함께 다룬 데일리 다이제스트",
                    evidence_items=[
                        EvidenceItem(kind="market_context", text="KOSPI/KOSDAQ 장중 흐름"),
                        EvidenceItem(kind="market_context", text="WTI 반등과 금리 변화"),
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "under_split_candidate" in [warning.code for warning in result[0].qa_warnings]


def test_classify_does_not_double_count_identical_raw_and_clean_blocks_for_under_split(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    text = "Daily Market Digest\n1) KOSPI 장중 흐름\n2) WTI 반등"
    row = _normalized_message(text, raw_text=text)

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="multi_item_digest",
            units=[
                SemanticUnitDraft(
                    message_type="opinion",
                    event_type="해석/전망",
                    category_key="매크로/정책",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=[],
                    canonical_summary="두 가지 시장 흐름을 다룬 짧은 다이제스트",
                    evidence_items=[
                        EvidenceItem(kind="market_context", text="KOSPI 장중 흐름"),
                        EvidenceItem(kind="market_context", text="WTI 반등"),
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert "under_split_candidate" not in [warning.code for warning in result[0].qa_warnings]


def test_classify_warns_over_merged_unit_candidate(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message(
        "전세계 반도체 밸류체인 주요 종목 주가를 일괄 집계했다\n"
        "- NVDA 주가 등락률\n"
        "- MU 주가 등락률\n"
        "- ARM 주가 등락률\n"
        "- ASML 주가 등락률\n"
        "- TSLA 주가 등락률"
    )

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="multi_item_digest",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="해석/전망",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NVDA", "MU", "ARM", "ASML", "TSLA", "AAL"],
                    canonical_summary="반도체/항공/소매/AI를 한 unit으로 묶은 요약",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="NVDA 조정 이후 메모리 업황은 강세 유지"),
                        EvidenceItem(kind="fact", text="ARM 신규 고객 확대"),
                        EvidenceItem(kind="fact", text="ASML 수주 가시성 확인"),
                        EvidenceItem(kind="fact", text="AAL 수요 회복"),
                        EvidenceItem(kind="fact", text="TJX 리테일 지표 개선"),
                        EvidenceItem(kind="fact", text="TSLA 가격 정책 변화"),
                    ],
                )
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    warning = next(
        warning for warning in result[0].qa_warnings if warning.code == "over_merged_unit_candidate"
    )
    assert "structure=multi_item_digest" in warning.detail
    assert "source_blocks=5" in warning.detail
    assert "digest_like=true" in warning.detail
    assert "list_like=true" in warning.detail
    assert "tickers=5" in warning.detail
    assert "evidence=6" in warning.detail
    assert "sample_tickers=NVDA,MU,ARM,ASML,TSLA" in warning.detail
    assert "list_signals=" in warning.detail
    assert "주가" in warning.detail
    assert "밸류체인" in warning.detail


def test_classify_warns_duplicate_unit_candidate_when_units_overlap_heavily(monkeypatch):
    taxonomy = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    row = _normalized_message("Market wrap 중복 unit QA")

    async def _fake_extract_message_semantics(*, row, taxonomy, provider, system_prompt):
        return SemanticExtractionDraft(
            structure_type="market_wrap",
            units=[
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="해석/전망",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NVDA", "MU"],
                    canonical_summary="엔비디아 조정 이후 메모리 강세 지속",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="NVDA 조정 이후에도 메모리 강세 지속"),
                        EvidenceItem(kind="fact", text="MU 가이던스 상향 가능성"),
                    ],
                ),
                SemanticUnitDraft(
                    message_type="signal",
                    event_type="해석/전망",
                    category_key="반도체",
                    main_theme=None,
                    sub_themes=[],
                    ticker_tags=["NVDA", "MU", "SOX"],
                    canonical_summary="NVDA 조정 뒤 메모리 업황 강세와 MU 가이던스 상향",
                    evidence_items=[
                        EvidenceItem(kind="fact", text="NVDA 조정 이후에도 메모리 강세 지속"),
                        EvidenceItem(kind="fact", text="MU 가이던스 상향 가능성"),
                    ],
                ),
            ],
        )

    monkeypatch.setattr(
        "src.pipelines.stock_report.classify._extract_message_semantics",
        _fake_extract_message_semantics,
    )

    result = classify_messages([row], taxonomy=taxonomy, provider="openai")

    assert any(
        "duplicate_unit_candidate" in [warning.code for warning in unit.qa_warnings]
        for unit in result
    )


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
