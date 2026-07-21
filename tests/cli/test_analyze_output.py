from datetime import datetime

from src.cli.main import (
    _format_disclosure_title,
    _format_factor_section,
    _format_top_summary,
    format_deep_dive_output,
)
from src.pipelines.analyze_decision import (
    AnalyzeDecisionSummary,
    AnalyzeScenario,
    FactorAssessment,
)
from src.tools.technical.models import (
    ChartPatternResult,
    IndicatorSnapshot,
    ScoreHistoryPoint,
    TechnicalResult,
    TechnicalVerdict,
)


def test_format_deep_dive_output_shows_top_summary_and_factor_reasons():
    snapshot = IndicatorSnapshot(price=91500.0, change_pct=29.97, rsi=89.1)
    technical = TechnicalResult(
        ticker="033100.KQ",
        timestamp=datetime.now(),
        snapshot=snapshot,
        indicators=snapshot,
        components={},
        total_score=140,
        component_raw_total=140,
        adjusted_score=62,
        technical_verdict=TechnicalVerdict(
            action="hold",
            entry_mode="extended_hold",
            confidence="medium",
            new_entry_allowed=False,
            reasons=["상승 추세 유지"],
            cautions=["단기 과열"],
            invalidation_level=88000.0,
            score_trend_summary="최근 5거래일 adjusted score 둔화",
        ),
        score_history=[
            ScoreHistoryPoint(
                date="2026-07-16",
                close=91500.0,
                component_raw_total=140,
                adjusted_score=62,
                verdict_action="hold",
                one_line_reason="단기 과열",
            )
        ],
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
            "cup_handle": ChartPatternResult(
                pattern_name="Cup & Handle",
                detected=False,
                confidence=0.0,
                current_price=91500.0,
                description="미완성",
                key_levels={},
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
    assert "## 패턴 분석" in output
    assert "## 원시 데이터" in output
    assert output.index("## 판단 요약") < output.index("## 원시 데이터")
    assert "- **주도 팩터**: 혼합" in output
    assert "- **가격**: 신고가 돌파" in output
    assert "- **이벤트**: 반복 기대 기사" in output
    assert "Double Bottom" in output
    assert "10일 전 완성" in output
    assert "지지 존" in output
    assert "저항 존" in output
    assert "전환 레벨" in output
    assert "88000.00~89500.00" in output
    assert "피봇 S1" in output
    assert "**Component Raw Total**: 140" in output
    assert "**Adjusted Score**: 62" in output
    assert "**기술 Verdict**: hold" in output
    assert "상승 추세 유지" in output
    assert "주의: 단기 과열" in output
    assert "최근 5거래일 adjusted score 둔화" in output
    assert "2026-07-16: close 91,500.00, raw 140, adjusted 62, hold — 단기 과열" in output
    assert "조정 대기" in output
    assert "RSI 과열로 추격 부담" in output
    assert "신규 정보가 부족해 actionability가 낮음" in output
    assert "technical" not in output
    assert "event" not in output
    assert "조정_대기" not in output
    assert "**SMA 100**: N/A · — 데이터 부족" in output
    assert "**SMA 200**: N/A · — 데이터 부족" in output


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


def test_format_disclosure_title_normalizes_sec_primary_document_name():
    title = _format_disclosure_title("10-Q", "alab-20260331.htm")
    assert title == "SEC 10-Q 공시"


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


def test_format_deep_dive_output_renders_playbook_section_with_gate_pass():
    """playbook_verdict가 있으면 플레이북 평가 섹션이 렌더돼야 한다 (게이트 통과)."""
    from src.tools.playbook.models import (
        CanslimResult,
        ElementVerdict,
        GateCheck,
        GateResult,
        MarketRegimeResult,
        PlaybookVerdict,
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

    verdict = PlaybookVerdict(
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
        gate=GateResult(
            passed=True,
            checklist=[
                GateCheck(name="시장환경(A)", required=True, met=True, reason="SPY 상승추세"),
                GateCheck(name="Stage2(B)", required=True, met=True, reason="Stage2 확인"),
                GateCheck(name="업종강도(C)", required=False, met=None, reason="데이터 없음"),
                GateCheck(name="수급(E)", required=False, met=None, reason="해당없음"),
            ],
            quality_grade="B",
            veto_reason=None,
        ),
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
        "playbook_verdict": verdict,
    }

    output = format_deep_dive_output(result)

    assert "📋 플레이북 평가" in output
    assert "매수 적격" in output
    assert "시장환경(A)" in output
    assert "C✅" in verdict.canslim.summary  # canslim summary 검증
    assert "100주" in output  # position plan
    assert "178.50" in output  # entry price
    assert "170.0" in output  # stop price
    # CAN SLIM 7요소 상세 지표(detail) 출력
    assert "EPS +25%" in output  # C detail
    assert "RS 상위" in output  # L detail
    assert "시장 상승" in output  # M detail


def test_format_deep_dive_output_renders_playbook_section_with_gate_fail():
    """gate FAIL이면 부적격 + veto_reason이 출력돼야 한다."""
    from src.tools.playbook.models import (
        GateCheck,
        GateResult,
        MarketRegimeResult,
        PlaybookVerdict,
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

    verdict = PlaybookVerdict(
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
        gate=GateResult(
            passed=False,
            checklist=[
                GateCheck(name="시장환경(A)", required=True, met=False, reason="SPY 하락추세"),
            ],
            quality_grade=None,
            veto_reason="시장 환경 불량: 하락 국면",
        ),
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
        "playbook_verdict": verdict,
    }

    output = format_deep_dive_output(result)

    assert "📋 플레이북 평가" in output
    assert "매수 부적격" in output
    assert "시장 환경 불량" in output


def test_format_deep_dive_output_no_playbook_section_when_verdict_is_none():
    """playbook_verdict=None이면 플레이북 섹션이 없어야 한다."""
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
        "playbook_verdict": None,
    }

    output = format_deep_dive_output(result)
    assert "📋 플레이북 평가" not in output
