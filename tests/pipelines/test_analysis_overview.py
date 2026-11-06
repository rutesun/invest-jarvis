"""사용자 요약은 현재 관측·가격 경계·5일 변화만 읽고 전략 판단은 보존한다."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.pipelines.analysis_overview import render_analysis_overview
from src.pipelines.strategy_render import render_strategy_sections
from src.strategies.models import ObservationCode, ObservationStatus, SignalFinality
from src.tools.technical.models import ScoreHistoryPoint
from tests.pipelines.test_observation_render import _analysis, _evidence, _observation


def support(*, day=date(2026, 9, 1), status_day=date(2026, 9, 2), **kwargs):
    return _observation(
        ObservationCode.SUPPORT_BREAK,
        day=day,
        status_as_of=status_day,
        anchor_type="SMA150",
        anchor_id="SMA150",
        anchor_origin_price=Decimal("50"),
        evidence=[
            _evidence("SUPPORT_BREAK", 101, 103),
            _evidence("SUPPORT_BREAK_CURRENT", 99, 104),
        ],
        **kwargs,
    )


def test_overview_order_current_price_and_legacy_separation():
    analysis = _analysis([support()])
    before = analysis.strategy_run.model_dump(mode="json")
    output = render_analysis_overview(analysis.scorecard, analysis)
    headings = ["### 현재 상태", "### 주요 가격대", "### 최근 5거래일", "### 전략별 대응"]
    assert [output.index(h) for h in headings] == sorted(output.index(h) for h in headings)
    assert "2026-09-02" in output and "99.00" in output
    assert "시간외 시세 미포함" in output
    assert "150일선 이탈" in output and "2026-09-01부터" in output
    assert "$104.00" in output and "-4.81%" in output
    assert "$50.00" not in output  # 동적 앵커 최초값을 현재 가격으로 오인하지 않는다.
    assert "Technical Score" in output and "Quality" in output
    assert "Observation history" not in output and "parameter_fingerprint" not in output
    assert analysis.strategy_run.model_dump(mode="json") == before


@pytest.mark.parametrize("day", [date(2026, 9, 1), date(2026, 9, 3)])
def test_stale_or_future_observation_does_not_become_current(day):
    analysis = _analysis([support(status_day=day)])
    output = render_analysis_overview(analysis.scorecard, analysis)
    assert "$104.00" not in output
    assert "평가일 불일치" in output


def test_resolved_event_is_a_dated_change_not_an_active_risk():
    event = _observation(
        ObservationCode.LOWER_HIGH,
        status=ObservationStatus.RESOLVED,
        confirmed_on=date(2026, 9, 2),
        ended_on=date(2026, 9, 2),
    )
    analysis = _analysis([event])
    output = render_analysis_overview(analysis.scorecard, analysis)
    current = output.split("### 현재 상태")[1].split("### 주요 가격대")[0]
    assert "낮은 고점" not in current
    assert "낮은 고점" in output.split("### 최근 5거래일")[1]
    assert "확인" in output


def test_terminal_source_is_grouped_as_past_structure_not_live_entry_level():
    old = _observation(
        ObservationCode.BREAKOUT_LEVEL_BREACH,
        day=date(2026, 7, 1),
        status_as_of=date(2026, 9, 2),
        source_terminal=True,
        source_signal_id="old-signal",
        anchor_type="PRIOR_BREAKOUT_LEVEL",
        evidence=[_evidence("BREAKOUT_LEVEL_BREACH_CURRENT", 99, 140)],
    )
    analysis = _analysis([support(), old])
    output = render_analysis_overview(analysis.scorecard, analysis)
    levels = output.split("### 주요 가격대")[1].split("### 최근 5거래일")[0]
    assert "$140.00" not in levels
    assert "과거 구조" in output and "$140.00" in output
    assert "진입 기회 종료" in output


def test_five_sessions_include_missing_days_without_inventing_strategy_history():
    analysis = _analysis([support()])
    sessions = tuple(date(2026, 8, 26) + timedelta(days=i) for i in range(8))
    scores = tuple(
        ScoreHistoryPoint(
            date=str(day),
            close=100 - i,
            component_raw_total=20 - i,
            adjusted_score=20 - i,
            verdict_action="hold",
            one_line_reason="기존 기술 판단",
            change_drivers=["모멘텀 약화"] if i else [],
        )
        for i, day in enumerate(sessions)
        if i != 5
    )
    analysis = replace(analysis, exchange_sessions=sessions, score_history=scores)
    output = render_analysis_overview(analysis.scorecard, analysis)
    table = output.split("### 최근 5거래일")[1].split("### 전략별 대응")[0]
    assert "2026-08-28" not in table
    for day in sessions[-5:]:
        assert str(day) in table
    missing = next(line for line in table.splitlines() if "2026-08-31" in line)
    assert "미평가" in missing
    assert "모멘텀 약화" in table and "핵심 변화" in table
    assert "진입 가능 →" not in table


def test_provisional_observation_and_opportunity_are_not_called_confirmed():
    analysis = _analysis([support(finality=SignalFinality.PROVISIONAL)])
    analysis.strategy_run.signal_bundles[0].entry_opportunity.finality = SignalFinality.PROVISIONAL
    output = render_analysis_overview(analysis.scorecard, analysis)
    assert "잠정" in output
    assert "150일선 이탈" in output


@pytest.mark.parametrize("reference", [0, float("nan"), float("inf")])
def test_invalid_price_is_not_published_as_a_level(reference):
    item = support()
    item.evidence[-1].reference_value = reference
    analysis = _analysis([item])
    output = render_analysis_overview(analysis.scorecard, analysis)
    assert "$nan" not in output and "$inf" not in output and "$0.00" not in output


def test_missing_or_disabled_evaluation_does_not_claim_no_risk():
    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    bundle.observations_enabled = False
    output = render_analysis_overview(analysis.scorecard, analysis)
    assert "미평가" in output and "비활성" in output
    assert "위험 없음" not in output


def test_detail_preserves_original_full_output_exactly():
    analysis = _analysis([support()])
    assert render_analysis_overview(analysis.scorecard, analysis, detail=True) == (
        render_strategy_sections(analysis.scorecard, analysis, detail=True)
    )


def test_missing_analysis_retains_warning_and_no_guessed_price():
    analysis = _analysis()
    output = render_analysis_overview(analysis.scorecard, None, warning="market unavailable")
    assert "market unavailable" in output and "미평가" in output
    assert "$99" not in output


def test_check_default_uses_overview_without_duplicate_legacy_body():
    from src.pipelines.quick_check import QuickCheckPipeline

    analysis = _analysis([support()])
    result = {
        "success": True,
        "ticker": "ALAB",
        "price": 99,
        "change_pct": -1,
        "total_score": -40,
        "scorecard": analysis.scorecard,
        "strategy_analysis": analysis,
    }
    pipeline = QuickCheckPipeline(None)
    output = pipeline.format_output(result)
    assert (
        render_analysis_overview(analysis.scorecard, analysis, expanded_observations=True) in output
    )
    assert "**총점**" not in output
    detail = pipeline.format_output(result, detailed_strategy=True)
    assert "**총점**: -40" in detail
    assert "최근 Observation history" in detail


def test_summary_table_keeps_explanations_out_of_narrow_cells():
    analysis = _analysis([support()])
    output = render_analysis_overview(analysis.scorecard, analysis)
    table = output.split("### 최근 5거래일")[1].split("**핵심 변화**")[0]
    assert "기술점수" in table
    assert "기술점수(Δ)" in table
    assert "확정)" not in table


def test_swing_current_exit_signal_is_visible_in_strategy_response():
    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    signal = bundle.signal_history[0].model_copy(
        update={"occurred_on": bundle.as_of, "code": "SMA150_EXIT"}
    )
    bundle.current_signals = [signal]
    bundle.signal_history.append(signal)
    output = render_analysis_overview(analysis.scorecard, analysis)
    response = output.split("### 전략별 대응")[1]
    assert "SWING_W150" in response and "150일선 청산 조건 충족" in response


def test_provisional_close_is_labelled_at_analysis_header():
    analysis = _analysis()
    analysis.strategy_run.signal_bundles[0].entry_opportunity.finality = SignalFinality.PROVISIONAL
    first_line = render_analysis_overview(analysis.scorecard, analysis).splitlines()[0]
    assert "잠정" in first_line


def test_new_support_breach_uses_actual_detector_first_day_measurement():
    import pandas as pd

    from src.strategies.observations.detectors import evaluate_observations
    from src.strategies.observations.parameters import PRODUCT_OBSERVATION_PARAMETERS
    from tests.strategies.test_observations import features

    frame = features([{"Close": 99, "SMA_150": 104, "ATR": 2}])
    frame.frame.index = pd.DatetimeIndex(["2026-09-02"])
    observations = evaluate_observations(
        "AAPL", frame, [], [], source_contexts=[], params=PRODUCT_OBSERVATION_PARAMETERS
    )
    assert observations and observations[0].evidence[0].code == "SUPPORT_BREAK"
    analysis = _analysis(observations)
    output = render_analysis_overview(analysis.scorecard, analysis)
    assert "$104.00" in output and "-4.81%" in output


def test_pullback_watch_uses_refreshed_support_evidence_from_producer():
    import pandas as pd

    from src.strategies.swing_w150.parameters import SwingW150Parameters
    from src.strategies.swing_w150.signals import _pullback_evidence

    evidence = _pullback_evidence(
        pd.Series({"Close": 99, "SMA_150": 98}), None, ("SMA_150",), SwingW150Parameters()
    )
    watch = _observation(
        ObservationCode.PULLBACK_WATCH,
        day=date(2026, 9, 1),
        status_as_of=date(2026, 9, 2),
        evidence=evidence,
    )
    analysis = _analysis([watch])
    output = render_analysis_overview(analysis.scorecard, analysis)
    assert "$98.00" in output and "지지 관찰" in output


def test_analyze_keeps_news_fundamentals_and_integrated_explanation_by_default():
    from types import SimpleNamespace

    from src.cli.main import format_deep_dive_output
    from src.tools.technical.models import IndicatorSnapshot, TechnicalResult

    analysis = _analysis([support()])
    technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime(2026, 9, 2),
        snapshot=IndicatorSnapshot(price=99, change_pct=-1),
        components={},
        scorecard=analysis.scorecard,
    )
    result = {
        "ticker": "AAPL",
        "technical": technical,
        "scorecard": analysis.scorecard,
        "strategy_analysis": analysis,
        "technical_summary": SimpleNamespace(
            summary="LEGACY_TECH_SENTINEL",
            recommendation="hold",
            confidence=0.5,
            rationale="reason",
            key_insights=[],
        ),
        "news_analysis": SimpleNamespace(
            sentiment="neutral",
            confidence=0.5,
            summary="NEWS_SENTINEL",
            impact_assessment="impact",
            key_themes=[],
        ),
        "integrated_explanation": SimpleNamespace(
            decision_explanation="EXPLANATION_SENTINEL",
            rationale=[],
            risks=["RISK_SENTINEL"],
            monitoring_points=[],
        ),
        "fundamental": SimpleNamespace(sector=None, industry=None, quarterly_data=None),
        "fundamental_summary": SimpleNamespace(
            summary="FUNDAMENTAL_SENTINEL",
            valuation_assessment="fair",
            confidence=0.5,
            strengths=[],
            weaknesses=[],
        ),
    }
    for name in (
        "market_cap",
        "pe_ratio",
        "forward_pe",
        "peg_ratio",
        "pb_ratio",
        "ps_ratio",
        "ev_ebitda",
        "roe",
        "roa",
        "gross_margin",
        "operating_margin",
        "profit_margin",
        "revenue_growth",
        "earnings_growth",
        "debt_to_equity",
        "current_ratio",
        "quick_ratio",
        "free_cash_flow",
        "operating_cash_flow",
        "fcf_yield",
        "dividend_yield",
        "payout_ratio",
    ):
        setattr(result["fundamental"], name, None)
    output = format_deep_dive_output(result)
    for text in ("NEWS_SENTINEL", "FUNDAMENTAL_SENTINEL", "EXPLANATION_SENTINEL", "RISK_SENTINEL"):
        assert text in output
    assert "LEGACY_TECH_SENTINEL" not in output
    assert "LEGACY_TECH_SENTINEL" in format_deep_dive_output(result, detailed_strategy=True)


def test_shadow_risk_remains_visible_without_a_today_signal():
    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    assert not bundle.current_signals
    output = render_analysis_overview(analysis.scorecard, analysis)
    for flag in bundle.entry_shadow.risk_flags:
        assert flag.message in output
    assert "전략 판단·수량 계획을 변경하지 않습니다" in output


def test_expired_opportunity_keeps_end_date_separate_from_current_evidence():
    from src.strategies.models import EntryOpportunityStatus

    analysis = _analysis()
    opportunity = analysis.strategy_run.signal_bundles[0].entry_opportunity
    opportunity.status = EntryOpportunityStatus.EXPIRED
    opportunity.terminal_on = date(2026, 9, 1)
    output = render_analysis_overview(analysis.scorecard, analysis)
    assert "종료일 2026-09-01" in output
    assert "현재 평가 참고" in output
    assert "종료 당시 가격 근거" not in output


@pytest.mark.parametrize("ticker", ["005930", "005930.KS", "196170", "196170.KQ"])
def test_korean_price_levels_use_won_for_bare_and_suffixed_tickers(ticker):
    old = _observation(
        ObservationCode.BREAKOUT_LEVEL_BREACH,
        day=date(2026, 7, 1),
        status_as_of=date(2026, 9, 2),
        source_terminal=True,
        source_signal_id="old-signal",
        anchor_type="PRIOR_BREAKOUT_LEVEL",
        evidence=[_evidence("BREAKOUT_LEVEL_BREACH_CURRENT", 99, 140)],
    )
    analysis = _analysis([support(), old])
    card = analysis.scorecard.model_copy(update={"ticker": ticker})
    output = render_analysis_overview(card, replace(analysis, scorecard=card))
    assert "₩104.00" in output and "₩140.00" in output
    assert "$104.00" not in output and "$140.00" not in output
