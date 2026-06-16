from datetime import datetime

from src.cli.analyze_render import (
    _format_disclosure_title,
    _format_factor_section,
    format_deep_dive_output,
)
from src.pipelines.analyze_decision import (
    AnalyzeDecisionSummary,
    AnalyzeScenario,
    FactorAssessment,
)
from src.tools.technical.models import ChartPatternResult, IndicatorSnapshot, TechnicalResult


def test_format_deep_dive_output_shows_summary_and_factor_reasons():
    """플랜 A 레이아웃: Summary/Event 섹션 + 팩터 분류 포함."""
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
        "chart_patterns": {
            "double_bottom": ChartPatternResult(
                pattern_name="Double Bottom",
                detected=True,
                confidence=0.82,
                completed_date="2026-05-01",
                days_ago=10,
                current_price=91500.0,
                breakout_level=92000.0,
                support_level=89000.0,
                description="이중 바닥 완성 후 넥라인 재확인",
                key_levels={"target": 98000.0},
            ),
        },
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
                "- **지지 존**: 88000.00~89500.00",
                "- **저항 존**: 96000.00~97500.00",
                "",
            ],
            "llm_context": "구조 레벨",
        },
    }

    output = format_deep_dive_output(result)

    assert "## 📊 Summary" in output
    assert "## 구조 레벨" in output
    assert "## Event" in output
    assert "## 원시 데이터" in output
    assert "판단 요약" not in output  # 삭제됨
    assert output.index("## 📊 Summary") < output.index("## 원시 데이터")
    assert "- **가격**: 신고가 돌파" in output
    assert "- **이벤트**: 반복 기대 기사" in output
    assert "Double Bottom" in output
    assert "10일 전 완성" in output
    assert "지지 존" in output
    assert "저항 존" in output
    assert "88000.00~89500.00" in output
    assert "RSI 과열로 추격 부담" in output
    assert "신규 정보가 부족해 actionability가 낮음" in output


def test_format_deep_dive_output_shows_structure_section():
    """presented_structure 없이 structure_levels만 있으면 ## 구조 레벨 섹션을 출력한다."""
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
        "factor_assessments": [],
        "scenarios": [],
        "structure_levels": {"summary_label": "support_zone"},
        "execution_levels": [],
    }

    output = format_deep_dive_output(result)

    assert "## 구조 레벨" in output


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


def test_format_disclosure_title_normalizes_sec_primary_document_name():
    title = _format_disclosure_title("10-Q", "alab-20260331.htm")
    assert title == "SEC 10-Q 공시"


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


def test_format_deep_dive_output_renders_playbook_section_with_gate_pass():
    """criteria_verdict가 있으면 플레이북 평가 섹션이 렌더돼야 한다 (게이트 통과)."""
    from src.tools.criteria.models import (
        CanslimResult,
        CriteriaCheck,
        CriteriaVerdict,
        ElementVerdict,
        MarketRegimeResult,
        PositionPlan,
        RelativeStrengthResult,
    )

    snapshot = IndicatorSnapshot(price=178.50, change_pct=2.5)
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

    verdict = CriteriaVerdict(
        ticker="AAPL",
        holding=False,
        market_regime=MarketRegimeResult(
            regime="상승", allow_new_buy=True, index_symbol="SPY", detail="SPY > SMA150"
        ),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=5.0,
            outperform_6m=10.0,
            rp_slope_4w=0.5,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=CanslimResult(
            c=ElementVerdict(met=True, detail="EPS +25%"),
            a=ElementVerdict(met=True, detail="연간 EPS 성장"),
            n=ElementVerdict(met=True, detail="52주 신고가"),
            s=ElementVerdict(met=None, detail="데이터 없음"),
            l=ElementVerdict(met=True, detail="RS 상위"),
            i=ElementVerdict(met=None, detail="업종 데이터 없음"),
            m=ElementVerdict(met=True, detail="시장 상승"),
        ),
        checks=[
            CriteriaCheck(name="시장환경(A)", required=True, met=True, reason="SPY 상승추세"),
            CriteriaCheck(name="Stage2(B)", required=True, met=True, reason="Stage2 확인"),
            CriteriaCheck(name="업종강도(C)", required=False, met=None, reason="데이터 없음"),
            CriteriaCheck(name="수급(E)", required=False, met=None, reason="해당없음"),
        ],
        quality_grade="B",
        veto_reason=None,
        position_plan=PositionPlan(
            entry=178.50,
            stop=170.0,
            stop_basis="-8%",
            per_share_risk=8.5,
            shares=100,
            position_value=17850.0,
            weight_pct=2.0,
            r_targets={"+2R": 195.5, "+3R": 204.0},
            capital_mode="absolute",
            error=None,
        ),
        exit_verdict=None,
        headline="AAPL: 매수 적격 (grade=B) — 100주 @ 178.50, stop=170.00",
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
                "rationale": "좋음",
            },
        )(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="technical",
            core_variables=["가격 모멘텀"],
            action="매수",
            timing="조정_대기",
            action_sentence="눌림 후 접근",
        ),
        "factor_assessments": [],
        "scenarios": [],
        "criteria_verdict": verdict,
    }

    output = format_deep_dive_output(result)

    assert "📋 포지션 플랜 / 청산 판단" in output
    assert "C✅" in verdict.canslim.summary  # canslim summary 검증
    assert "100주" in output  # position plan
    assert "178.50" in output  # entry price
    assert "170.0" in output  # stop price


def test_format_deep_dive_output_renders_playbook_section_with_gate_fail():
    """gate FAIL이면 부적격 + veto_reason이 출력돼야 한다."""
    from src.tools.criteria.models import (
        CriteriaCheck,
        CriteriaVerdict,
        MarketRegimeResult,
        RelativeStrengthResult,
    )

    snapshot = IndicatorSnapshot(price=50.0, change_pct=-1.5)
    technical = TechnicalResult(
        ticker="XYZ",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=20,
        strategies=[],
        overall_assessment="관망",
        confidence_score=30.0,
        key_insights=[],
        warnings=[],
    )

    verdict = CriteriaVerdict(
        ticker="XYZ",
        holding=False,
        market_regime=MarketRegimeResult(regime="하락", allow_new_buy=False, index_symbol="SPY"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=-2.0,
            outperform_6m=-5.0,
            rp_slope_4w=-0.3,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=None,
        checks=[
            CriteriaCheck(name="시장환경(A)", required=True, met=False, reason="SPY 하락추세"),
        ],
        quality_grade=None,
        veto_reason="시장 환경 불량: 하락 국면",
        position_plan=None,
        exit_verdict=None,
        headline="XYZ: 매수 거부 — 시장 환경 불량: 하락 국면",
    )

    result = {
        "ticker": "XYZ",
        "technical": technical,
        "technical_summary": type(
            "TechSummary",
            (),
            {
                "summary": "약세",
                "key_insights": [],
                "recommendation": "관망",
                "confidence": 0.3,
                "rationale": "약세",
            },
        )(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="technical",
            core_variables=["추세 약화"],
            action="관망",
            timing="보류",
            action_sentence="관망",
        ),
        "factor_assessments": [],
        "scenarios": [],
        "criteria_verdict": verdict,
    }

    output = format_deep_dive_output(result)

    # 포지션 플랜 없어도 섹션 헤더는 렌더됨 (비어있음)
    assert "📋 포지션 플랜 / 청산 판단" in output
    # 판단요약은 플랜 A에서 제거됨
    assert "판단 요약" not in output


def test_format_deep_dive_output_no_playbook_section_when_verdict_is_none():
    """criteria_verdict=None이면 플레이북 섹션이 없어야 한다."""
    snapshot = IndicatorSnapshot(price=100.0, change_pct=0.5)
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
                "rationale": "좋음",
            },
        )(),
        "decision_summary": AnalyzeDecisionSummary(
            leader="technical",
            core_variables=["가격 모멘텀"],
            action="매수",
            timing="조정_대기",
            action_sentence="눌림 후 접근",
        ),
        "factor_assessments": [],
        "scenarios": [],
        "criteria_verdict": None,
    }

    output = format_deep_dive_output(result)
    assert "📋 포지션 플랜 / 청산 판단" not in output
