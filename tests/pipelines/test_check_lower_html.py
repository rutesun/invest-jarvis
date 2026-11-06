"""하단 표시가 날짜·전략별 원래 의미와 Quality 공개 경계를 보존한다."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date
from html.parser import HTMLParser

import pytest

from src.pipelines.quick_check import QuickCheckPipeline
from src.position.models import DirectiveKind, PositionDirective, PositionPlan, QuantityStatus
from tests.pipelines.test_check_html import render, result_for
from tests.pipelines.test_observation_story import alab, recovered_today
from tests.pipelines.test_readable_quality import case, quality_on


class Element:
    def __init__(self, tag="root", attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    @property
    def text(self):
        return "".join(c if isinstance(c, str) else c.text for c in self.children)

    @property
    def folded(self):
        return (
            self.tag == "details"
            and "open" not in self.attrs
            or bool(self.parent and self.parent.folded)
        )


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.current = Element()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs, self.current)
        self.current.children.append(node)
        self.elements.append(node)
        if tag not in {"meta", "input", "img", "br", "hr"}:
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)

    def by_class(self, name):
        return [e for e in self.elements if name in e.attrs.get("class", "").split()]


def lower(analysis):
    document = Document(render([result_for(analysis)]))
    assert document.by_class("check-lower"), "승인된 하단 레이아웃이 표시되어야 합니다"
    return document


def test_folded_history_preserves_date_grouped_events_and_both_owners():
    analysis = alab()
    second = analysis.strategy_run.signal_bundles[0].model_copy(deep=True)
    second.strategy_id = "OTHER_STRATEGY"
    analysis.strategy_run.signal_bundles.append(second)
    document = lower(analysis)
    observation = document.by_class("lower-observation")[0]
    assert observation.folded
    assert "청산 조건 충족 후 미회복" not in observation.text
    assert "청산 조건 충족 후 미회복" in document.by_class("current")[0].text
    days = document.by_class("observation-day")
    assert [d.attrs["data-day"] for d in days] == sorted({d.attrs["data-day"] for d in days})
    exit_day = next(d for d in days if d.attrs["data-day"] == "2026-10-30")
    assert "SWING_W150" in exit_day.text and "OTHER_STRATEGY" in exit_day.text
    events = [e for e in document.elements if e.tag == "li" and e.parent.parent.parent is exit_day]
    assert sum("2회 연속 종가 이탈" in e.text for e in events) == 2
    current = lower(recovered_today()).by_class("current")[0]
    assert "150일선: 당일 회복 확인" in current.text
    assert "현재 청산 조건 지속 여부 미평가" not in current.text


def test_three_strategy_cards_keep_actual_independent_quantities_and_unavailable_separate():
    analysis = alab()
    analysis.position_plans.update(
        {
            "TECHNICAL_LEGACY": PositionPlan(
                PositionDirective(DirectiveKind.KEEP_CURRENT),
                42,
                42,
                0,
                0,
                QuantityStatus.AVAILABLE,
            ),
            "PLAYBOOK_V1": PositionPlan(
                PositionDirective(DirectiveKind.FLAT), 42, 0, 0, 42, QuantityStatus.AVAILABLE
            ),
            "SWING_W150": PositionPlan(
                PositionDirective(DirectiveKind.FREEZE),
                42,
                None,
                None,
                None,
                QuantityStatus.UNAVAILABLE,
            ),
        }
    )
    cards = lower(analysis).by_class("strategy-card")
    assert len(cards) == 3
    by_id = {c.attrs["data-strategy"]: c.text for c in cards}
    assert "42 → 42" in by_id["TECHNICAL_LEGACY"] and "매도 0" in by_id["TECHNICAL_LEGACY"]
    assert "42 → 0" in by_id["PLAYBOOK_V1"] and "매도 42" in by_id["PLAYBOOK_V1"]
    assert "수량 미산정" in by_id["SWING_W150"] and "매도 0" not in by_id["SWING_W150"]
    assert all("신규 진입" in c.text for c in cards)


def test_scope_and_quality_unavailability_remain_visible_without_opening_details():
    document = lower(alab())
    assert any("관찰 일부 미평가" in e.text and not e.folded for e in document.by_class("scope"))
    assert any(
        "계산 입력 이용 불가" in e.text and not e.folded
        for e in document.by_class("quality-warning")
    )


def actual_quality_case():
    days = (
        date(2026, 10, 30),
        date(2026, 11, 2),
        date(2026, 11, 3),
        date(2026, 11, 4),
        date(2026, 11, 5),
    )
    history = tuple(
        quality_on(
            d,
            v,
            finality="PROVISIONAL" if v is None else "FINAL",
            reasons=("PROVISIONAL_PREVIEW", "INCOMPLETE_PREFIX") if v is None else (),
        )
        for d, v in zip(days, (36.84, 39.06, 39.87, 39.31, None), strict=True)
    )
    analysis = case(history[-1], history)
    analysis.scorecard = analysis.scorecard.model_copy(update={"as_of": days[-1]})
    analysis.strategy_run.as_of = days[-1]
    analysis.strategy_run.scorecard = analysis.scorecard
    analysis.exchange_sessions = days
    return analysis


def test_stored_score_sequence_keeps_null_gap_latest_final_and_current_axes_dates():
    document = lower(actual_quality_case())
    latest = document.by_class("quality-latest")[0]
    assert "39.31" in latest.text and "2026-11-04" in latest.text and "-0.56" in latest.text
    graph = document.by_class("quality-chart")[0]
    points = [e for e in document.by_class("quality-point") if e.parent is graph]
    assert len(points) == 4
    assert all(v in graph.text for v in ("36.84", "39.06", "39.87", "39.31", "11/05"))
    assert "67.12" not in graph.text
    assert "2026-11-05" in document.by_class("quality-axes")[0].text
    assert "미산출" in document.by_class("quality-warning")[0].text


@pytest.mark.parametrize("blocked", [False, True])
def test_current_provisional_diagnostic_is_published_only_when_existing_policy_allows(blocked):
    day = date(2026, 9, 2)
    reasons = ("PROVISIONAL_PREVIEW", "INCOMPLETE_PREFIX") if blocked else ("PROVISIONAL_PREVIEW",)
    current = quality_on(day, None, finality="PROVISIONAL", reasons=reasons)
    document = lower(case(current))
    graph = document.by_class("quality-chart")[0]
    assert ("67.12" in graph.text) is not blocked
    assert len(document.by_class("quality-point")) == (0 if blocked else 1)
    if not blocked:
        assert "provisional" in document.by_class("quality-point")[0].attrs["class"]


def test_parameter_change_prevents_a_line_and_delta_between_incomparable_scores():
    before = quality_on(date(2026, 9, 1), 60)
    current = quality_on(date(2026, 9, 2), 65)
    current = replace(current, quality=replace(current.quality, parameter_id="different"))
    document = lower(case(current, (before, current)))
    assert not [e for e in document.elements if e.tag == "polyline"]
    assert "전 거래일 대비 미평가" in document.by_class("quality-latest")[0].text
    assert all("전일차 미평가" in axis.text for axis in document.by_class("quality-axis"))


def test_axis_absolute_values_are_neutral_and_signed_changes_have_direction():
    before = quality_on(
        date(2026, 9, 1),
        60,
        axes={"trend": 50, "structure": 75, "momentum": 80, "participation": 90},
    )
    document = lower(case(quality_on(date(2026, 9, 2), 67.12), (before,)))
    assert all(
        "up" not in e.attrs.get("class", "") and "down" not in e.attrs.get("class", "")
        for e in document.by_class("axis-value")
    )
    assert any("+11.23" in e.text for e in document.by_class("lower-up"))
    assert any("-5.00" in e.text for e in document.by_class("lower-down"))


@pytest.mark.parametrize(
    ("axes", "expected"),
    [
        (
            {"trend": 20, "structure": 20, "momentum": 60, "participation": 70},
            "추세·구조가 공동 최저",
        ),
        ({"trend": 20, "structure": None, "momentum": 60, "participation": 70}, "일부 축 미평가"),
        (
            {"trend": None, "structure": None, "momentum": None, "participation": None},
            "4축 모두 미평가",
        ),
    ],
)
def test_relative_axis_sentence_does_not_invent_a_unique_lowest_axis(axes, expected):
    document = lower(case(quality_on(date(2026, 9, 2), None, axes=axes)))
    sentence = document.by_class("quality-relative")[0].text
    assert expected in sentence
    assert "매매 권고" in sentence and "수익률 예측" in sentence


def test_mismatched_axis_evaluation_day_is_not_shown_as_current_or_ranked():
    current = quality_on(date(2026, 9, 1), 67.12)
    document = lower(case(current))
    assert "평가일 불일치" in document.by_class("quality-axes")[0].text
    assert not document.by_class("axis-value")
    assert "최저" not in document.by_class("quality-relative")[0].text


def test_html_does_not_change_default_text_or_serialized_inputs():
    analysis = alab()
    result = result_for(analysis)
    formatter = QuickCheckPipeline(None)
    text_before = formatter.format_output(result)
    before = deepcopy(asdict(analysis))
    render([result])
    assert formatter.format_output(result) == text_before
    assert asdict(analysis) == before


def test_strategy_unassessed_risk_warning_remains_visible_after_folding_evidence():
    document = lower(alab())
    assert any(
        "SWING_W150 보조 위험: 미평가" in node.text and not node.folded
        for node in document.by_class("lower-warnings")
    )


def test_no_returned_sessions_warning_remains_visible():
    analysis = replace(alab(), exchange_sessions=())
    document = lower(analysis)
    assert any(
        "반환 거래일 정보 없음" in node.text and not node.folded
        for node in document.by_class("current-warnings")
    )


def test_provisional_historical_event_warning_is_in_date_summary():
    from src.strategies.models import SignalFinality

    analysis = alab()
    analysis.strategy_run.signal_bundles[0].signal_history[0].finality = SignalFinality.PROVISIONAL
    document = lower(analysis)
    assert any(
        "잠정" in node.text
        for node in document.elements
        if node.tag == "summary" and node.parent.parent.attrs.get("data-day") == "2026-10-30"
    )


def test_fallback_keeps_scope_warnings_unfolded_without_synthesizing_cards():
    from src.pipelines.check_html import _markdown
    from src.pipelines.check_lower_html import render_lower_sections

    output = render_lower_sections(
        {}, [("평가 범위 / 상세", "### 평가 범위 / 상세\n\n- 원본 경고 <raw>")], _markdown
    )
    document = Document(output)
    assert not document.by_class("strategy-card")
    assert document.by_class("scope") and "원본 경고 <raw>" in document.by_class("scope")[0].text


def test_external_data_warning_stays_visible_when_turnaround_section_is_folded():
    result = result_for(
        warnings=["원본 데이터 누락 <raw>"], turnaround={"score": 1, "summary": "관찰 참고"}
    )
    document = Document(render([result]))
    assert any(
        "데이터 주의: 원본 데이터 누락 <raw>" in node.text and not node.folded
        for node in document.by_class("lower-warnings")
    )


def test_stale_analysis_run_uses_existing_section_fallback_without_current_inference():
    analysis = alab()
    analysis.strategy_run.as_of = date(2026, 10, 30)
    document = Document(render([result_for(analysis)]))
    assert not document.by_class("strategy-card") and not document.by_class("observation-current")
    assert "평가일 불일치" in render([result_for(analysis)])


def test_quality_graph_labels_are_direct_neutral_text_without_forced_horizontal_scroll():
    document = lower(actual_quality_case())
    labels = document.by_class("quality-value")
    assert [node.text for node in labels] == ["36.84", "39.06", "39.87", "39.31"]
    assert all(
        "lower-up" not in node.attrs.get("class", "")
        and "lower-down" not in node.attrs.get("class", "")
        for node in labels
    )
    assert not document.by_class("quality-chart-scroll")
    styles = "".join(e.text for e in document.elements if e.tag == "style")
    chart_style = styles.split(".check-lower .quality-chart {", 1)[1].split("}", 1)[0]
    assert "min-width" not in chart_style


def test_unavailable_plan_preserves_known_zero_fields_and_marks_only_missing_quantities():
    analysis = alab()
    analysis.position_plans["SWING_W150"] = PositionPlan(
        PositionDirective(DirectiveKind.FREEZE), 0, 0, 0, None, QuantityStatus.UNAVAILABLE
    )
    card = lower(analysis).by_class("strategy-card")[0]
    assert "0 → 0" in card.text and "매수 0" in card.text
    assert "매도 미산정" in card.text and "수량 미산정" in card.text


def test_missing_axis_measurements_are_summarized_outside_folded_evidence():
    document = lower(case(quality_on(date(2026, 9, 2), 100.0)))
    warning = document.by_class("quality-warning")[0]
    assert not warning.folded
    assert "실측 근거 미평가: 추세·구조·모멘텀·거래량 방향(Participation)" in warning.text
    original = [
        node
        for node in document.elements
        if node.tag == "li" and " 근거: 실측 근거 미평가" in node.text
    ]
    assert len(original) == 4 and all(node.folded for node in original)


def test_available_axis_measurements_stay_folded_while_only_missing_axes_are_summarized():
    from src.tools.technical.chart_analysis.models import FeatureValue

    current = quality_on(
        date(2026, 9, 2),
        100.0,
        features={"Close": FeatureValue(99, "READY"), "SMA_50": FeatureValue(100, "READY")},
    )
    document = lower(case(current))
    warning = document.by_class("quality-warning")[0]
    assert "실측 근거 미평가: 구조·모멘텀·거래량 방향(Participation)" in warning.text
    assert "추세" not in warning.text and "50일선 아래" not in warning.text
    normal = [
        node
        for node in document.elements
        if node.tag == "li" and "추세 근거: 50일선 아래" in node.text
    ]
    assert normal and all(node.folded for node in normal)


@pytest.mark.parametrize("values", [(100, 0, 100, 0, 100), (0, 100, 0, 100, 0)])
def test_zero_and_hundred_quality_labels_clear_the_svg_edges_points_and_dates(values):
    days = (
        date(2026, 8, 29),
        date(2026, 8, 30),
        date(2026, 8, 31),
        date(2026, 9, 1),
        date(2026, 9, 2),
    )
    history = tuple(quality_on(day, value) for day, value in zip(days, values, strict=True))
    analysis = case(history[-1], history)
    analysis.exchange_sessions = days
    document = lower(analysis)
    graph = document.by_class("quality-chart")[0]
    point_nodes = document.by_class("quality-point")
    label_nodes = document.by_class("quality-value")
    dates = [
        node
        for node in graph.children
        if not isinstance(node, str) and node.tag == "text" and "/" in node.text
    ]
    assert len(point_nodes) == len(label_nodes) == len(dates) == 5
    for point, label, day in zip(point_nodes, label_nodes, dates, strict=True):
        y, radius = float(point.attrs["cy"]), float(point.attrs["r"])
        baseline, date_baseline = float(label.attrs["y"]), float(day.attrs["y"])
        # 18px font 전체 높이와 4px 하강부 여유를 보수적으로 확보한다.
        assert baseline >= 18 and baseline + 4 < date_baseline - 18
        if baseline > y:
            assert baseline - 18 >= y + radius + 2
        else:
            assert baseline + 4 <= y - radius - 2


def signal_entry_analysis(*, unavailable=None):
    """기존 Signal 정책과 수량 planner의 실제 결과를 표시 입력으로 전달한다."""
    from src.strategies.models import EntryOpportunityStatus
    from src.tools.technical.scorecard_models import DataStatus
    from tests.pipelines.test_observation_story import analysis_for
    from tests.position.test_planner import TODAY, _signal, _signal_bundle, _signal_plan

    analysis = analysis_for(today=TODAY)
    bundle = _signal_bundle([_signal("TREND_BREAKOUT_ENTRY")])
    if unavailable == "opportunity_status":
        bundle.entry_opportunity.status = EntryOpportunityStatus.NOT_EVALUATED
    elif unavailable == "opportunity_day":
        bundle.entry_opportunity.evaluation_as_of = date(2026, 10, 7)
    elif unavailable == "bundle_day":
        bundle.as_of = date(2026, 10, 7)
    elif unavailable:
        bundle.data_status = DataStatus(unavailable)
    analysis.strategy_run.signal_bundles = [bundle]
    plan = _signal_plan(bundle)
    analysis.position_plans["SWING_W150"] = plan
    return analysis, plan


def test_policy_generated_normal_entry_card_keeps_response_entry_and_buy_plan_consistent():
    analysis, plan = signal_entry_analysis()
    assert plan.directive.kind is DirectiveKind.BUILD_ONLY_TO_RISK_TARGET
    assert (plan.current_quantity, plan.target_quantity, plan.buy_quantity, plan.sell_quantity) == (
        0,
        10,
        10,
        0,
    )
    before = QuickCheckPipeline(None).format_output(result_for(analysis))
    assert "| SWING_W150 | 진입 가능 | 당일 축소·청산 신호 기록 없음 |" in before
    document = lower(analysis)
    assert document.by_class("strategy-action")[0].text == "당일 축소·청산 신호 기록 없음"
    card = document.by_class("strategy-card")[0]
    assert "신규 진입: 진입 가능" in card.text
    assert "0 → 10" in card.text and "매수 10" in card.text and "매도 0" in card.text
    assert analysis.position_plans["SWING_W150"] == plan
    assert QuickCheckPipeline(None).format_output(result_for(analysis)) == before


@pytest.mark.parametrize(
    "unavailable",
    [
        "opportunity_status",
        "opportunity_day",
        "bundle_day",
        "not_evaluated",
        "insufficient_data",
        "error",
        "partial",
    ],
)
def test_signal_card_does_not_promote_unassessed_or_mismatched_input_to_evaluated_response(
    unavailable,
):
    analysis, plan = signal_entry_analysis(unavailable=unavailable)
    document = lower(analysis)
    assert document.by_class("strategy-action")[0].text == "판단 미평가"
    if unavailable.startswith("opportunity") or unavailable == "bundle_day":
        assert "신규 진입: 미평가" in document.by_class("strategy-card")[0].text
    assert analysis.position_plans["SWING_W150"] == plan


def test_quality_period_description_omits_display_implementation_language():
    document = lower(actual_quality_case())
    quality = document.by_class("lower-quality")[0]
    assert "최근 5개 반환 거래일 · 0~100" in quality.text
    assert "점수의 절대값은 중립 표시" not in quality.text
