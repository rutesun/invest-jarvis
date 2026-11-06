"""점수의 시점·이력·진단 공개 경계와 위험 날짜를 사용자 출력에서 검증한다."""

from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from src.pipelines.analysis_overview import render_analysis_overview
from src.tools.technical.chart_analysis.models import FeatureValue
from tests.pipelines.test_chart_analysis_render import result_for
from tests.pipelines.test_observation_render import _analysis


def quality_on(day, value, *, finality="FINAL", reasons=(), axes=None, features=None):
    result = result_for(quality=value, reasons=reasons)
    manifest = replace(result.analysis.manifest, as_of=day, finality=finality)
    return replace(
        result,
        analysis=replace(result.analysis, manifest=manifest, features=features or {}),
        quality=replace(
            result.quality,
            as_of=day,
            manifest=manifest,
            axes=axes or result.quality.axes,
        ),
    )


def case(current, history=()):
    base = _analysis()
    return SimpleNamespace(
        **(
            vars(base)
            | {
                "chart_analysis": current,
                "quality_history": history,
                "quality_history_unavailable": None,
                "chart_analysis_unavailable": None,
            }
        )
    )


def render(analysis):
    return render_analysis_overview(analysis.scorecard, analysis)


def test_current_quality_explains_four_axes_using_only_available_measurements():
    features = {
        key: FeatureValue(value, "READY")
        for key, value in {
            "Close": 99,
            "SMA_50": 100,
            "SMA_150": 110,
            "SMA_200": 120,
            "High_20_New": 130,
            "Low_20_New": 90,
            "RSI": 42,
            "Close_Lag20": 110,
            "Up_Volume_20": 300,
            "Down_Volume_20": 700,
        }.items()
    }
    output = render(case(quality_on(date(2026, 9, 2), 67.12, features=features)))
    assert "차트 상태 점수(Quality)" in output and "0~100" in output
    assert "67.12 / 100" in output and "확정" in output
    assert "50일선 아래" in output and "20일 고가 130.00 / 저가 90.00" in output
    assert "20일 수익률 -10.00%" in output
    quality_section = output.split("### 차트 상태 점수(Quality)")[1].split("### 주요 가격대")[0]
    assert "RSI" not in quality_section  # Quality momentum uses price returns, not RSI.
    assert "상승일 거래량 30.0% / 하락일 70.0%" in output
    assert "거래량 방향(Participation)" in output
    assert "parameter_id" not in output and "calculated_quality" not in output


@pytest.mark.parametrize("reason", ["POLICY_HISTORY_SHORT", "INCOMPLETE_PREFIX", "INPUT_MISSING"])
def test_unpublished_diagnostic_is_not_shown_as_a_provisional_quality(reason):
    output = render(case(quality_on(date(2026, 9, 2), None, reasons=(reason,))))
    assert "미산출" in output and "null" not in output
    assert "67.12" not in output and "preview" not in output


def test_only_current_provisional_complete_diagnostic_can_be_shown_as_intraday():
    result = quality_on(
        date(2026, 9, 2), None, finality="PROVISIONAL", reasons=("PROVISIONAL_PREVIEW",)
    )
    output = render(case(result))
    assert "장중 잠정 67.12 / 100" in output
    first_line = output.splitlines()[0]
    assert "현재가격" in first_line and "종가" not in first_line


def test_history_uses_each_days_quality_and_keeps_missing_and_current_separate():
    start = date(2026, 8, 28)
    days = tuple(start + timedelta(days=i) for i in range(6))
    values = [40, 45, 55, 58, 60, None]
    history = tuple(
        quality_on(
            day,
            value,
            finality="PROVISIONAL" if i == 5 else "FINAL",
            reasons=("PROVISIONAL_PREVIEW",) if i == 5 else (),
        )
        for i, (day, value) in enumerate(zip(days, values, strict=True))
        if i != 2
    )
    analysis = case(history[-1], history)
    analysis.exchange_sessions = days
    output = render(analysis)
    table = output.split("### 최근 5거래일")[1].split("**핵심 변화**")[0]
    assert "Quality(전일차)" in table and "기술점수(Δ)" in table
    assert "| 2026-08-29 |" in table and "45.00 (+5.00)" in table
    missing = next(line for line in table.splitlines() if "2026-08-30" in line)
    assert "미평가" in missing and "67.12" not in missing
    row_after_gap = next(line for line in table.splitlines() if "2026-08-31" in line)
    assert "58.00 (—)" in row_after_gap
    assert "장중 잠정 67.12" in table
    assert "확정 기간 Quality" in output and "+15.00점" in output
    assert "오늘 장중 Quality" in output and "+7.12점" in output


def test_four_axis_previous_session_changes_are_readable_and_do_not_claim_contribution():
    previous = quality_on(
        date(2026, 9, 1),
        60,
        axes={"trend": 50, "structure": 75, "momentum": 80, "participation": 90},
    )
    current = quality_on(date(2026, 9, 2), 67.12)
    output = render(case(current, (previous, current)))
    assert "추세 61.23" in output and "+11.23점" in output
    assert "구조 70.00" in output and "-5.00점" in output
    assert "기여" not in output
    assert "축 점수 변화" in output


def test_shadow_flag_missing_occurrence_is_not_inferred_from_evaluation_day():
    analysis = case(None)
    shadow = analysis.strategy_run.signal_bundles[0].entry_shadow
    analysis.strategy_run.signal_bundles[0].entry_shadow = shadow.model_copy(
        update={
            "risk_flags": [
                f.model_copy(update={"occurred_on": None, "confirmed_on": None})
                for f in shadow.risk_flags
            ]
        }
    )
    output = render(analysis)
    assert "발생일 미확인" in output
    assert "현재 평가일 2026-09-02" in output
    assert "진입 구조" in output and "신규 매도 명령" in output


def test_current_quality_stays_in_table_when_historical_calculation_fails():
    analysis = case(quality_on(date(2026, 9, 2), 67.12))
    analysis.quality_history_unavailable = "historical calculation unavailable"
    output = render(analysis)
    table = output.split("### 최근 5거래일")[1].split("**핵심 변화**")[0]
    current = next(row for row in table.splitlines() if "2026-09-02" in row)
    assert "67.12 (—)" in current
    assert "historical calculation unavailable" in output


def test_provisional_prefix_stays_unpublished_even_with_a_previous_published_score():
    previous = quality_on(date(2026, 9, 1), 60)
    current = quality_on(
        date(2026, 9, 2),
        None,
        finality="PROVISIONAL",
        reasons=("PROVISIONAL_PREVIEW", "INCOMPLETE_PREFIX"),
    )
    verified = render(case(current, (previous, current)))
    assert "장중 잠정 67.12 / 100" not in verified
    assert "입력 이력 누락 또는 확정 여부 확인 부족" in verified
    unverified = render(case(current, (current,)))
    assert "장중 잠정 67.12" not in unverified
    assert "미산출" in unverified


def test_policy_short_provisional_stays_unpublished_despite_previous_score():
    previous = quality_on(date(2026, 9, 1), 60)
    current = quality_on(
        date(2026, 9, 2),
        None,
        finality="PROVISIONAL",
        reasons=("PROVISIONAL_PREVIEW", "INCOMPLETE_PREFIX", "POLICY_HISTORY_SHORT"),
    )
    output = render(case(current, (previous, current)))
    assert "장중 잠정 67.12" not in output
    assert "252봉 부족" in output


def test_future_shadow_dates_are_excluded_from_current_risk_details():
    analysis = case(None)
    bundle = analysis.strategy_run.signal_bundles[0]
    flag = bundle.entry_shadow.risk_flags[0].model_copy(update={"occurred_on": date(2026, 9, 3)})
    bundle.entry_shadow = bundle.entry_shadow.model_copy(update={"risk_flags": [flag]})
    output = render(analysis)
    assert "발생일·확정일 불일치" in output
    assert "발생일 2026-09-03" not in output


@pytest.mark.asyncio
async def test_actual_service_provisional_result_keeps_incomplete_prefix_unpublished():
    from src.pipelines.quality_overview import render_quality_overview
    from tests.pipelines.test_integrated_quality_plans import quality_service
    from tests.tools.technical.chart_analysis.test_history import raw_history

    full = raw_history().frame
    service, technical, _, day = quality_service(full, full)
    bundle = await service.chart_loader.load()
    bundle.instrument.bars[-1].finality.value = "provisional"
    result = await service.evaluate("TEST", technical, as_of=day)
    assert result.chart_analysis.quality.diagnostics["calculated_quality"] is not None
    assert "INCOMPLETE_PREFIX" in result.chart_analysis.quality.reasons
    analysis = SimpleNamespace(
        scorecard=SimpleNamespace(as_of=day),
        exchange_sessions=result.exchange_sessions,
        chart_analysis=result.chart_analysis,
        quality_history=result.quality_history,
    )
    output = render_quality_overview(analysis)
    assert "Quality: 미산출" in output
    assert "입력 이력 누락 또는 확정 여부 확인 부족" in output
    assert "최근 확정 Quality:" in output
    assert "장중 잠정 " not in output.split("| 축 / 현재 점수 |")[0]


def test_quality_history_uses_its_measured_close_when_legacy_history_is_missing():
    previous = quality_on(date(2026, 9, 1), 60, features={"Close": FeatureValue(100, "READY")})
    current = quality_on(date(2026, 9, 2), 65, features={"Close": FeatureValue(99, "READY")})
    output = render(case(current, (previous, current)))
    table = output.split("### 최근 5거래일")[1].split("**핵심 변화**")[0]
    row = next(line for line in table.splitlines() if "2026-09-02" in line)
    assert "99.00 (-1.00%)" in row
    assert "65.00 (+5.00)" in row
    assert "미평가" in row  # Technical Score는 Quality 입력으로 추정하지 않는다.


def test_provisional_bundle_uses_current_price_even_if_quality_is_unavailable():
    from src.strategies.models import SignalFinality

    analysis = case(None)
    analysis.strategy_run.signal_bundles[0].entry_opportunity.finality = SignalFinality.PROVISIONAL
    header = render(analysis).splitlines()[0]
    assert "현재가격 99.00" in header and "종가" not in header


def test_early_failure_price_is_dated_event_measurement_not_current_price():
    analysis = case(None)
    bundle = analysis.strategy_run.signal_bundles[0]
    flag = bundle.entry_shadow.risk_flags[0]
    evidence = flag.evidence[0].model_copy(update={"observed_value": 88})
    flag = flag.model_copy(
        update={
            "code": "EARLY_FAILED_BREAKOUT_CANDIDATE",
            "occurred_on": date(2026, 9, 1),
            "confirmed_on": date(2026, 9, 1),
            "evidence": [evidence],
        }
    )
    bundle.entry_shadow = bundle.entry_shadow.model_copy(update={"risk_flags": [flag]})
    output = render(analysis)
    assert "발생 당시 가격(2026-09-01) 88.00" in output
    assert "현재가격 99.00" in output
    assert "평가가격 88.00" not in output
