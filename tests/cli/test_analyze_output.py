from datetime import datetime

from src.cli.main import _format_factor_section, _format_top_summary, format_deep_dive_output
from src.pipelines.analyze_decision import (
    AnalyzeDecisionSummary,
    AnalyzeScenario,
    FactorAssessment,
)
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


def test_format_deep_dive_output_shows_top_summary_and_factor_reasons():
    snapshot = IndicatorSnapshot(price=91500.0, change_pct=29.97, rsi=89.1)
    technical = TechnicalResult(
        ticker="033100.KQ",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=140,
        strategies=[],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=[],
        warnings=[],
    )

    result = {
        "ticker": "033100.KQ",
        "technical": technical,
        "technical_summary": type(
            "TechSummary",
            (),
            {
                "summary": "강세",
                "key_insights": [],
                "recommendation": "매수",
                "confidence": 0.75,
                "rationale": "기술적 강세",
            },
        )(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="혼합",
            core_variables=["신고가 구간", "RSI 과열"],
            action="관망",
            timing="조정_대기",
            action_sentence="지금 추격보다 눌림 확인이 유리",
        ),
        "factor_assessments": [
            FactorAssessment(
                factor_type="technical",
                role="보조",
                freshness_score=4,
                magnitude_score=4,
                actionability_score=3,
                total_score=11,
                summary="신고가 돌파",
                role_reason="RSI 과열로 추격 부담",
                evidence=["RSI 89.1"],
            ),
            FactorAssessment(
                factor_type="event",
                role="참고",
                freshness_score=3,
                magnitude_score=2,
                actionability_score=1,
                total_score=6,
                summary="반복 기대 기사",
                role_reason="신규 정보가 부족해 actionability가 낮음",
                evidence=["반복 기사 2건"],
            ),
        ],
        "scenarios": [
            AnalyzeScenario(
                name="기본 시나리오",
                trigger_price_levels=["20일선 유지"],
                confirming_factors=["외인 순매수"],
                invalidation_conditions=["20일선 종가 이탈"],
                expected_path="눌림 후 재상승",
                recommended_action="조정 구간 접근",
            )
        ],
        "presented_structure": {
            "top_judgment": "현재 핵심 구조: support_zone",
            "headline": "핵심 지지 존 우위",
            "why": "최근 지지 반응 우세",
            "cli_blocks": [
                "## 구조 레벨",
                "- **요약**: 핵심 지지 존 우위",
                "- **근거**: 최근 지지 반응 우세",
                "- **박스 존**: 없음",
                "- **지지 존**: 88000.00~89500.00",
                "- **저항 존**: 96000.00~97500.00",
                "- **전환 레벨**: 없음",
                "- **무효화 기준**: 88000.00~89500.00 하향 이탈",
                "",
                "## 실행 레벨",
                "- **핵심 실행 레벨**: 피봇 S1 $90000.00 (-1.6%), 50일선 $88500.00 (-3.3%)",
                "",
            ],
            "llm_context": "구조 레벨",
        },
    }

    output = format_deep_dive_output(result)

    assert "주도 팩터" in output
    assert "핵심 변수" in output
    assert "액션" in output
    assert "## 판단 요약" in output
    assert "## 구조 레벨" in output
    assert "## 실행 레벨" in output
    assert "## 원시 데이터" in output
    assert output.index("## 판단 요약") < output.index("## 원시 데이터")
    assert "- **주도 팩터**: 혼합" in output
    assert "- **가격**: 신고가 돌파" in output
    assert "- **이벤트**: 반복 기대 기사" in output
    assert "지지 존" in output
    assert "저항 존" in output
    assert "전환 레벨" in output
    assert "88000.00~89500.00" in output
    assert "피봇 S1" in output
    assert "조정 대기" in output
    assert "RSI 과열로 추격 부담" in output
    assert "신규 정보가 부족해 actionability가 낮음" in output
    assert "technical" not in output
    assert "event" not in output
    assert "조정_대기" not in output


def test_format_deep_dive_output_warns_when_presented_structure_missing():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)
    technical = TechnicalResult(
        ticker="ALAB",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=120,
        strategies=[],
        overall_assessment="관망",
        confidence_score=60.0,
        key_insights=[],
        warnings=[],
    )
    result = {
        "ticker": "ALAB",
        "technical": technical,
        "technical_summary": type(
            "TechSummary",
            (),
            {
                "summary": "중립",
                "key_insights": [],
                "recommendation": "관망",
                "confidence": 0.6,
                "rationale": "구조 레벨 확인 필요",
            },
        )(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="혼합",
            core_variables=["구조 레벨 혼재"],
            action="관망",
            timing="보류",
            action_sentence="핵심 레벨 확인 전 대기",
        ),
        "factor_assessments": [],
        "scenarios": [],
        "structure_levels": {"summary_label": "support_zone"},
        "execution_levels": [],
    }

    output = format_deep_dive_output(result)

    assert "presenter payload 누락" in output


def test_format_deep_dive_output_shows_defer_reason():
    summary = AnalyzeDecisionSummary(
        leader="판단 보류",
        core_variables=["계산 가능한 팩터 부족"],
        action="관망",
        timing="보류",
        action_sentence="지금은 관망이 낫다",
        defer_reason="수급 데이터 부재 + event 신호 약함",
    )

    output = _format_top_summary(summary)

    assert "판단 보류" in output
    assert "수급 데이터 부재 + event 신호 약함" in output


def test_format_deep_dive_output_uses_headline_in_top_summary_only():
    summary = AnalyzeDecisionSummary(
        leader="혼합",
        core_variables=["고평가 부담", "기관 매수 우위"],
        action="관망",
        timing="조정_대기",
        action_sentence="지금 추격보다 핵심 레벨 확인 후 접근이 유리",
    )

    output = _format_top_summary(summary)

    assert "고평가 부담" in output
    assert "기관 매수 우위" in output


def test_format_deep_dive_output_marks_event_as_reference_with_reason():
    assessment = FactorAssessment(
        factor_type="event",
        role="참고",
        freshness_score=4,
        magnitude_score=2,
        actionability_score=1,
        total_score=7,
        summary="AI 전력 수요 기대 기사",
        role_reason="기대감 반복 보도 위주라 현재 액션 설명력이 약함",
        evidence=["관련 기사 2건"],
    )

    output = _format_factor_section([assessment])

    assert "참고" in output
    assert "기대감 반복 보도 위주라 현재 액션 설명력이 약함" in output


def test_format_deep_dive_output_hides_integrated_recommendation_labels():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0, rsi=55.0)
    technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=75,
        strategies=[],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=[],
        warnings=[],
    )

    result = {
        "ticker": "AAPL",
        "technical": technical,
        "technical_summary": type(
            "TechSummary",
            (),
            {
                "summary": "강세",
                "key_insights": [],
                "recommendation": "매수",
                "confidence": 0.75,
                "rationale": "기술적 강세",
            },
        )(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="technical",
            core_variables=["20일선 위 유지"],
            action="관망",
            timing="조정_대기",
            action_sentence="조정 확인 후 접근이 유리",
        ),
        "factor_assessments": [],
        "scenarios": [],
        "integrated_analysis": type(
            "Integrated",
            (),
            {
                "recommendation": "매수",
                "action_summary": "기존 LLM 요약",
                "rationale": ["기술적: 강세"],
                "risks": [],
            },
        )(),
    }

    output = format_deep_dive_output(result)

    assert "## 종합 인사이트 참고" in output
    assert "투자 추천" not in output


def test_format_deep_dive_output_shows_na_for_missing_fundamental_metrics():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0, rsi=55.0)
    technical = TechnicalResult(
        ticker="033100.KQ",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=75,
        strategies=[],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=[],
        warnings=[],
    )

    result = {
        "ticker": "033100.KQ",
        "technical": technical,
        "technical_summary": type(
            "TechSummary",
            (),
            {
                "summary": "강세",
                "key_insights": [],
                "recommendation": "매수",
                "confidence": 0.75,
                "rationale": "기술적 강세",
            },
        )(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="technical",
            core_variables=["기관 매수 우위"],
            action="관망",
            timing="조정_대기",
            action_sentence="조정 확인 후 접근이 유리",
        ),
        "factor_assessments": [],
        "scenarios": [],
        "fundamental": type(
            "Fundamental",
            (),
            {
                "sector": None,
                "industry": None,
                "market_cap": None,
                "pe_ratio": None,
                "forward_pe": None,
                "peg_ratio": None,
                "pb_ratio": None,
                "ps_ratio": None,
                "ev_ebitda": None,
                "roe": None,
                "roa": None,
                "gross_margin": None,
                "operating_margin": None,
                "profit_margin": None,
                "revenue_growth": None,
                "earnings_growth": None,
                "debt_to_equity": None,
                "current_ratio": None,
                "quick_ratio": None,
                "free_cash_flow": None,
                "operating_cash_flow": None,
                "fcf_yield": None,
                "dividend_yield": None,
                "payout_ratio": None,
                "quarterly_data": None,
            },
        )(),
        "fundamental_summary": type(
            "FundSummary",
            (),
            {
                "summary": "데이터가 제한적이다.",
                "valuation_assessment": "적정",
                "confidence": 0.5,
                "strengths": [],
                "weaknesses": [],
            },
        )(),
    }

    output = format_deep_dive_output(result)

    assert "Sector/Industry**: N/A / N/A" in output
    assert "**시가총액**: N/A" in output
    assert "**ROE**: N/A" in output
