from types import SimpleNamespace
from typing import get_args, get_type_hints

import pytest
from pydantic import ValidationError

from src.llm.models import FundamentalSummaryOutput, NewsAnalysisOutput, TechnicalSummaryOutput
from src.pipelines.analyze_decision import (
    AnalyzeDecisionSummary,
    AnalyzeScenario,
    FactorAssessment,
    build_analyze_decision_bundle,
    build_decision_summary,
    build_default_scenarios,
    build_event_assessment,
    build_flow_assessment,
    build_technical_assessment,
    build_valuation_assessment,
    classify_leader_label,
)
from src.tools.flow import InvestorFlow, InvestorFlowEntry


def test_factor_assessment_keeps_role_reason():
    assessment = FactorAssessment(
        factor_type="event",
        role="참고",
        freshness_score=4,
        magnitude_score=2,
        actionability_score=1,
        total_score=7,
        summary="반복 보도 중심",
        role_reason="신규 정보가 부족해 actionability가 낮음",
        evidence=["증권사 해설 기사 3건"],
    )

    assert assessment.factor_type == "event"
    assert assessment.role == "참고"
    assert assessment.role_reason == "신규 정보가 부족해 actionability가 낮음"


def test_factor_assessment_rejects_out_of_range_total_score():
    with pytest.raises(ValidationError) as exc_info:
        FactorAssessment(
            factor_type="event",
            role="참고",
            freshness_score=4,
            magnitude_score=2,
            actionability_score=1,
            total_score=16,
            summary="반복 보도 중심",
            role_reason="신규 정보가 부족해 actionability가 낮음",
            evidence=["증권사 해설 기사 3건"],
        )

    assert "less than or equal to 15" in str(exc_info.value)


def test_decision_summary_accepts_defer_reason():
    summary = AnalyzeDecisionSummary(
        leader="판단 보류",
        core_variables=["수급 데이터 부재", "event 신호 약함"],
        action="관망",
        timing="보류",
        action_sentence="지금은 강한 단정보다 관망이 낫다",
        defer_reason="계산 가능한 팩터가 1개뿐임",
    )

    assert summary.leader == "판단 보류"
    assert summary.defer_reason == "계산 가능한 팩터가 1개뿐임"


def test_scenario_requires_invalidation_conditions():
    scenario = AnalyzeScenario(
        name="기본 시나리오",
        trigger_price_levels=["20일선 유지"],
        confirming_factors=["외인 순매수 지속"],
        invalidation_conditions=["20일선 종가 이탈", "거래량 둔화"],
        expected_path="눌림 후 재상승",
        recommended_action="조정 구간 분할 접근",
    )

    assert scenario.invalidation_conditions == ["20일선 종가 이탈", "거래량 둔화"]


def test_scenario_raises_validation_error_without_invalidation_conditions():
    with pytest.raises(ValidationError) as exc_info:
        AnalyzeScenario(
            name="기본 시나리오",
            trigger_price_levels=["20일선 유지"],
            confirming_factors=["외인 순매수 지속"],
            expected_path="눌림 후 재상승",
            recommended_action="조정 구간 분할 접근",
        )

    assert "invalidation_conditions" in str(exc_info.value)


def test_classify_leader_label_returns_mixed_when_margin_is_small():
    factor_scores = [
        {"factor_type": "technical", "total_score": 11},
        {"factor_type": "flow", "total_score": 10},
    ]

    assert classify_leader_label(factor_scores) == "혼합"


def test_classify_leader_label_returns_defer_when_only_one_factor_exists():
    factor_scores = [
        {"factor_type": "technical", "total_score": 10},
    ]

    assert classify_leader_label(factor_scores) == "판단 보류"


def test_classify_leader_label_returns_winner_when_gap_is_clear():
    factor_scores = [
        {"factor_type": "technical", "total_score": 12},
        {"factor_type": "flow", "total_score": 9},
    ]

    assert classify_leader_label(factor_scores) == "technical"


def test_classify_leader_label_returns_defer_when_leader_score_is_below_threshold():
    factor_scores = [
        {"factor_type": "technical", "total_score": 6},
        {"factor_type": "flow", "total_score": 5},
    ]

    assert classify_leader_label(factor_scores) == "판단 보류"


def test_classify_leader_label_returns_winner_at_gap_boundary():
    factor_scores = [
        {"factor_type": "technical", "total_score": 9},
        {"factor_type": "flow", "total_score": 7},
    ]

    assert classify_leader_label(factor_scores) == "technical"


def test_classify_leader_label_returns_winner_at_score_boundary():
    factor_scores = [
        {"factor_type": "technical", "total_score": 7},
        {"factor_type": "flow", "total_score": 5},
    ]

    assert classify_leader_label(factor_scores) == "technical"


def test_classify_leader_label_declares_explicit_factor_score_shape():
    factor_scores_type = get_type_hints(classify_leader_label)["factor_scores"]
    factor_score_entry_type = get_args(factor_scores_type)[0]

    assert factor_score_entry_type.__required_keys__ == {"factor_type", "total_score"}


def test_technical_assessment_downgrades_stale_pattern_to_reference():
    assessment = build_technical_assessment(
        total_score=140,
        rsi=78.0,
        chart_patterns=[
            {
                "pattern_name": "Double Bottom",
                "detected": True,
                "days_ago": 145,
            }
        ],
    )

    assert assessment.role == "보조"
    assert assessment.headline == "신고가 돌파"
    assert "145일 전" in assessment.role_reason


def test_technical_assessment_keeps_non_stale_signal_when_fresh_pattern_exists():
    assessment = build_technical_assessment(
        total_score=140,
        rsi=78.0,
        chart_patterns=[
            {
                "pattern_name": "Double Bottom",
                "detected": True,
                "days_ago": 145,
            },
            {
                "pattern_name": "Breakout",
                "detected": True,
                "days_ago": 8,
            },
        ],
    )

    assert assessment.role == "주도"
    assert "145일 전" not in assessment.role_reason


def test_technical_assessment_marks_negative_score_as_bearish():
    assessment = build_technical_assessment(
        total_score=-45,
        rsi=31.0,
        chart_patterns=[],
    )

    assert assessment.role == "보조"
    assert assessment.bias == "bearish"
    assert assessment.headline == "추세 약화"
    assert "약세" in assessment.summary


def test_event_assessment_uses_news_and_disclosure_metadata_only():
    assessment = build_event_assessment(
        news_titles=["제룡전기, 480억원 공급계약 체결"],
        disclosure_items=[{"form_type": "공시", "description": "공급계약 체결"}],
    )

    assert assessment.factor_type == "event"
    assert "공급계약" in assessment.summary
    assert assessment.total_score >= 10


def test_event_assessment_ignores_empty_disclosure_entries():
    assessment = build_event_assessment(
        news_titles=["제룡전기, 480억원 공급계약 체결"],
        disclosure_items=[{}],
    )

    assert assessment.factor_type == "event"
    assert assessment.role == "보조"
    assert assessment.total_score == 7
    assert assessment.actionability_score == 2


def test_event_assessment_keeps_directionless_disclosure_as_reference():
    assessment = build_event_assessment(
        news_titles=[],
        disclosure_items=[{"form_type": "DART", "description": "조회공시 답변"}],
    )

    assert assessment.role == "참고"
    assert assessment.total_score == 0
    assert assessment.headline == "신규 재료 제한적"
    assert assessment.bias == "neutral"


def test_flow_assessment_scores_supportive_flow_data():
    flow = InvestorFlow(
        code="033100",
        entries=[
            InvestorFlowEntry(
                date=f"2024-01-{day:02d}",
                foreign_net=1_000,
                institution_net=500,
            )
            for day in range(1, 11)
        ],
    )

    assessment = build_flow_assessment(flow)

    assert assessment.factor_type == "flow"
    assert assessment.role == "주도"
    assert assessment.total_score == 10
    assert assessment.headline == "외인·기관 동행"


def test_valuation_assessment_uses_high_confidence_undervalued_signal():
    assessment = build_valuation_assessment(
        FundamentalSummaryOutput(
            summary="밸류에이션 매력이 존재함",
            strengths=["저평가"],
            weaknesses=[],
            valuation_assessment="저평가",
            confidence=0.82,
        )
    )

    assert assessment.factor_type == "valuation"
    assert assessment.role == "보조"
    assert assessment.headline == "밸류 매력"
    assert assessment.bias == "bullish"


def test_valuation_assessment_sets_short_headline_for_bearish_valuation():
    assessment = build_valuation_assessment(
        FundamentalSummaryOutput(
            summary="전반적으로 강력한 재무 성과를 보여주지만 현재 밸류는 부담스럽다.",
            strengths=["높은 ROE"],
            weaknesses=["매출 성장 둔화"],
            valuation_assessment="고평가",
            confidence=0.85,
        )
    )

    assert assessment.headline == "고평가 부담"
    assert "전반적으로 강력한 재무 성과" in assessment.summary


def test_build_decision_summary_prefers_headline_for_core_variables():
    summary = build_decision_summary(
        leader_label="valuation",
        assessments=[
            FactorAssessment(
                factor_type="valuation",
                role="보조",
                freshness_score=3,
                magnitude_score=3,
                actionability_score=2,
                total_score=7,
                headline="고평가 부담",
                summary="전반적으로 강력한 재무 성과를 보여주지만 현재 밸류는 부담스럽다.",
                role_reason="고평가 해석이라 공격적 추격을 경계해야 함",
                evidence=["valuation=고평가"],
                bias="bearish",
            ),
            FactorAssessment(
                factor_type="flow",
                role="보조",
                freshness_score=4,
                magnitude_score=2,
                actionability_score=4,
                total_score=7,
                headline="기관 매수 우위",
                summary="외인/기관 수급이 현재 흐름을 뒷받침함",
                role_reason="한 축의 수급은 우호적이지만 일치도는 제한적임",
                evidence=["기관 5일: 매수"],
                bias="bullish",
            ),
        ],
    )

    assert summary.core_variables == ["고평가 부담", "기관 매수 우위"]


def test_build_decision_summary_gives_price_weight_in_mixed_core_variables():
    summary = build_decision_summary(
        leader_label="혼합",
        assessments=[
            FactorAssessment(
                factor_type="flow",
                role="보조",
                freshness_score=4,
                magnitude_score=2,
                actionability_score=4,
                total_score=7,
                headline="기관 매수 우위",
                summary="외인/기관 수급이 현재 흐름을 뒷받침함",
                role_reason="한 축의 수급은 우호적이지만 일치도는 제한적임",
                evidence=["기관 5일: 매수"],
                bias="bullish",
            ),
            FactorAssessment(
                factor_type="technical",
                role="참고",
                freshness_score=2,
                magnitude_score=4,
                actionability_score=2,
                total_score=6,
                headline="단기 과열",
                summary="기술 신호는 살아 있으나 오래된 패턴은 참고용",
                role_reason="145일 전 Double Bottom 패턴이라 현재 액션은 최근 추세를 더 우선해야 함",
                evidence=["technical total_score=140"],
                bias="bullish",
            ),
        ],
    )

    assert summary.core_variables == ["단기 과열", "기관 매수 우위"]


def test_build_decision_summary_uses_defer_reason_when_signal_is_weak():
    summary = build_decision_summary(
        leader_label="판단 보류",
        assessments=[],
    )

    assert summary.leader == "판단 보류"
    assert "계산 가능한 팩터" in summary.defer_reason
    assert summary.action == "관망"
    assert summary.timing == "보류"


def test_build_decision_summary_prioritizes_leader_assessment_summary():
    summary = build_decision_summary(
        leader_label="event",
        assessments=[
            FactorAssessment(
                factor_type="technical",
                role="주도",
                freshness_score=4,
                magnitude_score=4,
                actionability_score=3,
                total_score=11,
                summary="기술 흐름이 먼저 보이는 상태",
                role_reason="추세가 강함",
                evidence=["technical total_score=140"],
            ),
            FactorAssessment(
                factor_type="event",
                role="주도",
                freshness_score=5,
                magnitude_score=4,
                actionability_score=4,
                total_score=10,
                summary="공급계약 공시가 액션을 설명함",
                role_reason="뉴스와 공시가 일치함",
                evidence=["공급계약 체결"],
            ),
        ],
    )

    assert summary.leader == "event"
    assert summary.core_variables[0] == "공급계약 공시가 액션을 설명함"


def test_build_decision_summary_returns_sell_for_bearish_event_leader():
    summary = build_decision_summary(
        leader_label="event",
        assessments=[
            FactorAssessment(
                factor_type="event",
                role="주도",
                freshness_score=5,
                magnitude_score=4,
                actionability_score=4,
                total_score=10,
                summary="규제 리스크가 부각됨",
                role_reason="부정 뉴스가 집중됨",
                evidence=["부정 뉴스"],
                bias="bearish",
            )
        ],
    )

    assert summary.action == "매도"
    assert summary.timing == "지금"


def test_build_default_scenarios_switches_template_for_bearish_action():
    summary = AnalyzeDecisionSummary(
        leader="technical",
        core_variables=["지지선 이탈", "거래량 동반 약세"],
        action="매도",
        timing="조정_대기",
        action_sentence="기술 약세가 주도라 반등 시 비중 축소가 우선",
    )

    scenarios = build_default_scenarios(
        summary,
        SimpleNamespace(
            support_levels=[SimpleNamespace(description="20일선 이탈")],
            resistance_levels=[SimpleNamespace(description="20일선 회복 실패")],
        ),
        [
            FactorAssessment(
                factor_type="technical",
                role="주도",
                freshness_score=4,
                magnitude_score=4,
                actionability_score=3,
                total_score=11,
                summary="지지선 이탈",
                role_reason="추세 훼손이 명확함",
                evidence=["technical total_score=-95"],
                bias="bearish",
            )
        ],
    )

    assert len(scenarios) == 2
    assert "눌림 후 재확인" not in scenarios[0].expected_path
    assert "비중 축소" in scenarios[0].recommended_action


def test_build_default_scenarios_expands_trigger_levels_with_ma50_ma150_and_invalidation():
    summary = AnalyzeDecisionSummary(
        leader="혼합",
        core_variables=["단기 과열", "기관 매수 우위"],
        action="관망",
        timing="조정_대기",
        action_sentence="핵심 레벨 확인 후 접근",
    )

    scenarios = build_default_scenarios(
        summary,
        SimpleNamespace(
            support_levels=[
                SimpleNamespace(type="swing_low", description="스윙 저점", price=205000),
                SimpleNamespace(type="sma_150", description="150일 이평선", price=182000),
            ],
            resistance_levels=[
                SimpleNamespace(type="pivot_r1", description="피봇 저항1", price=223000),
                SimpleNamespace(type="sma_50", description="50일 이평선", price=198000),
            ],
        ),
        [
            FactorAssessment(
                factor_type="flow",
                role="보조",
                freshness_score=4,
                magnitude_score=2,
                actionability_score=4,
                total_score=7,
                summary="외인/기관 수급이 현재 흐름을 뒷받침함",
                role_reason="한 축의 수급은 우호적이지만 일치도는 제한적임",
                evidence=["기관 5일: 매수"],
                bias="bullish",
            )
        ],
    )

    assert any("최근 지지" in level for level in scenarios[0].trigger_price_levels)
    assert any("최근 저항" in level for level in scenarios[0].trigger_price_levels)
    assert any("50일선" in level for level in scenarios[0].trigger_price_levels)
    assert any("150일선" in level for level in scenarios[0].trigger_price_levels)
    assert any("무효화 레벨" in condition for condition in scenarios[0].invalidation_conditions)


def test_build_default_scenarios_uses_snapshot_ma_levels_when_price_levels_missing_ma():
    summary = AnalyzeDecisionSummary(
        leader="혼합",
        core_variables=["단기 과열", "기관 매수 우위"],
        action="관망",
        timing="조정_대기",
        action_sentence="핵심 레벨 확인 후 접근",
    )
    scenarios = build_default_scenarios(
        summary,
        SimpleNamespace(
            support_levels=[
                SimpleNamespace(type="pivot_s1", description="피봇 지지1", price=205000)
            ],
            resistance_levels=[
                SimpleNamespace(type="pivot_r1", description="피봇 저항1", price=223000)
            ],
        ),
        [],
        snapshot=SimpleNamespace(sma_50=151996.0, sma_150=126301.33),
    )

    assert any(
        "50일선: 50일 이평선 (151,996)" in level for level in scenarios[0].trigger_price_levels
    )
    assert any(
        "150일선: 150일 이평선 (126,301)" in level for level in scenarios[0].trigger_price_levels
    )


def test_build_analyze_decision_bundle_keeps_strong_non_contract_news_event():
    technical_data = SimpleNamespace(
        total_score=75,
        indicators=None,
        snapshot=SimpleNamespace(rsi=55.0),
    )
    technical_summary = TechnicalSummaryOutput(
        summary="기술 흐름 양호",
        key_insights=["20일선 위 유지"],
        recommendation="매수",
        confidence=0.75,
        rationale="추세 유지",
    )
    news_analysis = NewsAnalysisOutput(
        sentiment="긍정",
        confidence=0.86,
        key_themes=["FDA 승인"],
        summary="승인 이슈가 재평가를 유도함",
        impact_assessment="단기 모멘텀 강화 가능",
    )
    bundle = build_analyze_decision_bundle(
        technical_data=technical_data,
        technical_summary=technical_summary,
        news_articles=[SimpleNamespace(title="FDA 승인 획득")],
        news_analysis=news_analysis,
        fundamental_summary=None,
        disclosure_items=None,
        flow_data=None,
        chart_patterns={},
        price_levels=SimpleNamespace(support_levels=[], resistance_levels=[]),
    )

    event_assessment = next(
        assessment for assessment in bundle.factor_assessments if assessment.factor_type == "event"
    )

    assert event_assessment.total_score == 7
    assert event_assessment.summary == "승인 이슈가 재평가를 유도함"
    assert len(bundle.scenarios) == 2


def test_build_analyze_decision_bundle_scores_disclosure_only_event():
    technical_data = SimpleNamespace(
        total_score=75,
        indicators=None,
        snapshot=SimpleNamespace(rsi=55.0),
    )
    technical_summary = TechnicalSummaryOutput(
        summary="기술 흐름 양호",
        key_insights=["20일선 위 유지"],
        recommendation="매수",
        confidence=0.75,
        rationale="추세 유지",
    )

    bundle = build_analyze_decision_bundle(
        technical_data=technical_data,
        technical_summary=technical_summary,
        news_articles=[],
        news_analysis=None,
        fundamental_summary=None,
        disclosure_items=[SimpleNamespace(form_type="DART", description="단일판매·공급계약체결")],
        flow_data=None,
        chart_patterns={},
        price_levels=SimpleNamespace(support_levels=[], resistance_levels=[]),
    )

    event_assessment = next(
        assessment for assessment in bundle.factor_assessments if assessment.factor_type == "event"
    )

    assert event_assessment.total_score >= 7
    assert event_assessment.role in {"보조", "주도"}
    assert "공급계약" in event_assessment.summary
